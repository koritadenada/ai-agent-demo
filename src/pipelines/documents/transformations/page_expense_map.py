"""Silver page map: ai_query with a JSON schema maps every page of a final DA pack to the expense it evidences."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import AI_TABLE_PROPERTIES, CATALOG, LLM_ENDPOINT, SILVER, expense_categories, json_literal, sql_str

CATEGORIES = expense_categories()

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "page_map",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["page_role", "expense_category", "confidence", "explanation"],
            "properties": {
                "page_role": {"type": "string", "enum": ["summary", "supporting_invoice", "other"]},
                "expense_category": {"type": "string", "enum": [*CATEGORIES, "none"]},
                "confidence": {"type": "number"},
                "explanation": {"type": "string"},
            },
        },
    },
}

PROMPT = (
    "You review one page of a final disbursement account pack for a port call. "
    "Decide whether the page is the summary (all expense lines and bank details), a supporting invoice for ONE expense, "
    "or something else. For a supporting invoice, pick the expense category it evidences; agencies name expenses "
    "differently, so match on meaning. Otherwise use 'none'. Confidence is between 0 and 1.\n"
    "Expense categories:\n"
    + "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
    + "\n\nPage text:\n"
)

MAP_SCHEMA = "STRUCT<page_role: STRING, expense_category: STRING, confidence: DOUBLE, explanation: STRING>"


@dp.table(
    name=f"{CATALOG}.{SILVER}.page_expense_map",
    comment="Page to expense category for final DA packs, with confidence and the model's explanation",
    cluster_by=["file_item_id"],
    table_properties=AI_TABLE_PROPERTIES,
)
def page_expense_map():
    pages = (
        spark.readStream.table(f"{CATALOG}.{SILVER}.document_pages")
        .filter("doc_type = 'final_da_pack' AND page_error IS NULL AND length(page_text) > 0")
    )
    answer = F.expr(
        f"ai_query({sql_str(LLM_ENDPOINT)}, concat({sql_str(PROMPT)}, page_text), "
        f"responseFormat => {json_literal(RESPONSE_FORMAT)}, failOnError => false)"
    )
    return (
        pages.withColumn("answer", answer)
        .withColumn("m", F.from_json("answer.result", MAP_SCHEMA))
        .select(
            "file_item_id", "proforma_id", "page_number", "page_text",
            F.col("m.page_role").alias("page_role"),
            F.nullif(F.col("m.expense_category"), F.lit("none")).alias("expense_category"),
            F.col("m.confidence").alias("confidence"),
            F.col("m.explanation").alias("explanation"),
            F.col("answer.errorMessage").alias("llm_error"),
        )
    )
