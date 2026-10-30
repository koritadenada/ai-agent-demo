"""Silver line items: ai_extract (v2.1, confidence scores) reads the amount on each supporting invoice page.
Quoted amounts are not read from proforma PDFs: the platform already has them in proforma_expense."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import AI_TABLE_PROPERTIES, CATALOG, CURRENCIES, SILVER, json_literal

SCHEMA = {
    "amount": {"type": "number", "description": "Total amount due on this invoice"},
    "currency": {"type": "enum", "labels": CURRENCIES},
    "description": {"type": "string", "description": "What the invoice is for, as written"},
}


@dp.table(
    name=f"{CATALOG}.{SILVER}.doc_line_items",
    comment="One row per supporting invoice page of a final DA pack: expense, amount and currency as printed",
    cluster_by=["proforma_id"],
    table_properties=AI_TABLE_PROPERTIES,
)
def doc_line_items():
    pages = spark.readStream.table(f"{CATALOG}.{SILVER}.page_expense_map").filter(
        "page_role = 'supporting_invoice' AND expense_category IS NOT NULL")
    x = F.expr(f"ai_extract(page_text, {json_literal(SCHEMA)}, map('version', '2.1', 'enableConfidenceScores', 'true'))")
    return pages.withColumn("x", x).select(
        "file_item_id", "proforma_id", "page_number", "expense_category",
        F.expr("x:response:description:value::STRING").alias("description"),
        F.expr("x:response:amount:value::DECIMAL(18,2)").alias("amount"),
        F.expr("x:response:currency:value::STRING").alias("currency"),
        # the weaker of the two signals: was it the right page, and was the amount read clearly
        F.least(F.col("confidence"), F.expr("x:response:amount:confidence_score::DOUBLE")).alias("confidence"),
    )
