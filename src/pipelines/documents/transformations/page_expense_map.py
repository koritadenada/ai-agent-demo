"""Silver page map: every page of a final DA pack mapped to the expense line of that DA it evidences.

The model gets the DA's own final lines (from expense_evaluation, joined in per page) and returns the line id, a
confidence and an explanation, and for an invoice page the amount and currency printed on it: one call per page.
The id is then checked against the DA's lines, so a made-up id never reaches gold.
The prompt and the model come from the prompt registry (page_map), so both change without a deploy.
"""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import (AI_TABLE_PROPERTIES, CATALOG, CURRENCIES, SILVER, expense_categories, json_literal,
                                prompt, sql_str)

CATEGORIES = expense_categories()
PROMPT = prompt("page_map")
TEMPLATE = PROMPT.template.replace("{{categories}}", "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items()))

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "page_map",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["page_role", "expense_line_id", "expense_category", "amount", "currency", "confidence",
                         "explanation"],
            "properties": {
                "page_role": {"type": "string", "enum": ["summary", "supporting_invoice", "other"]},
                "expense_line_id": {"type": "integer"},
                "expense_category": {"type": "string", "enum": [*CATEGORIES, "none"]},
                "amount": {"type": "number", "description": "Invoice pages: total amount due as printed, else 0"},
                "currency": {"type": "string", "enum": [*CURRENCIES, "none"]},
                "confidence": {"type": "number"},
                "explanation": {"type": "string"},
            },
        },
    },
}
ANSWER = ("STRUCT<page_role: STRING, expense_line_id: BIGINT, expense_category: STRING, amount: DECIMAL(18,2), "
          "currency: STRING, confidence: DOUBLE, explanation: STRING>")


def da_expense_lines():
    """The final lines of every DA, one row per proforma (read on every micro-batch, so new lines are seen)."""
    s = f"{CATALOG}.{SILVER}"
    return (
        spark.read.table(f"{s}.expense_evaluation").alias("e")
        .where("NOT COALESCE(e.is_platform_fee, FALSE) AND COALESCE(e.is_active, TRUE) "
               "AND e.deleted_on IS NULL AND e.merged_into_id IS NULL")
        .join(spark.read.table(f"{s}.expense_category").alias("c"), F.col("c.id") == F.col("e.category_id"), "left")
        .groupBy("e.proforma_id")
        .agg(
            F.concat_ws("\n", F.collect_list(F.format_string(
                "%d: %s, %s, %s", "e.id", "e.name", F.coalesce("c.name", F.lit("?")), F.coalesce("e.section", F.lit("?"))
            ))).alias("expense_lines"),
            F.map_from_entries(F.collect_list(F.struct(
                "e.id", F.struct(F.col("e.name").alias("name"), F.col("c.name").alias("category"))
            ))).alias("line_info"),
        )
    )


@dp.table(
    name=f"{CATALOG}.{SILVER}.page_expense_map",
    comment="Per page of a final DA pack: summary, supporting invoice or other; the DA expense line it evidences, "
            "the amount and currency printed on an invoice page, with confidence and the model's explanation",
    cluster_by=["file_item_id"],
    table_properties=AI_TABLE_PROPERTIES,
)
def page_expense_map():
    pages = (
        spark.readStream.table(f"{CATALOG}.{SILVER}.document_pages")
        .filter("doc_type = 'final_da_pack' AND page_error IS NULL AND length(page_text) > 0")
        .join(da_expense_lines(), "proforma_id", "left")
    )
    text = (f"replace(replace({sql_str(TEMPLATE)}, '{{{{expense_lines}}}}', "
            "coalesce(expense_lines, '(no lines on the platform yet)')), '{{page_text}}', page_text)")
    answer = F.expr(f"ai_query({sql_str(PROMPT.model)}, {text}, "
                    f"responseFormat => {json_literal(RESPONSE_FORMAT)}, failOnError => false)")
    m = F.from_json("answer.result", ANSWER)
    line = F.element_at("line_info", F.col("m.expense_line_id"))
    invoice = F.col("m.page_role") == "supporting_invoice"
    return (
        pages.withColumn("answer", answer).withColumn("m", m)
        .select(
            "file_item_id", "proforma_id", "page_number", "page_text",
            F.col("m.page_role").alias("page_role"),
            # only an id that is one of this DA's lines survives
            F.when(line.isNotNull(), F.col("m.expense_line_id")).alias("expense_evaluation_id"),
            line["name"].alias("expense_name"),
            F.coalesce(line["category"], F.nullif(F.col("m.expense_category"), F.lit("none"))).alias("expense_category"),
            F.when(invoice, F.col("m.amount")).alias("amount"),
            F.when(invoice, F.nullif(F.col("m.currency"), F.lit("none"))).alias("currency"),
            F.col("m.confidence").alias("confidence"),
            F.col("m.explanation").alias("explanation"),
            F.col("answer.errorMessage").alias("llm_error"),
            F.lit(PROMPT.version).alias("prompt_version"),
        )
    )
