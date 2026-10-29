"""Silver line items: ai_extract (v2.1, confidence scores) reads the amount on each supporting invoice page
and every quoted line on a proforma."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import CATALOG, CURRENCIES, SILVER, expense_categories, json_literal

CATEGORIES = list(expense_categories())
V21 = "map('version', '2.1', 'enableConfidenceScores', 'true')"

INVOICE_SCHEMA = {
    "amount": {"type": "number", "description": "Total amount due on this invoice"},
    "currency": {"type": "enum", "labels": CURRENCIES},
    "description": {"type": "string", "description": "What the invoice is for, as written"},
}
QUOTE_SCHEMA = {
    "line_items": {"type": "array", "items": {"type": "object", "properties": {
        "expense_category": {"type": "enum", "labels": CATEGORIES},
        "description": {"type": "string"},
        "amount": {"type": "number"},
    }}},
    "currency": {"type": "enum", "labels": CURRENCIES},
}


@dp.temporary_view()
def supporting_invoice_lines():
    pages = spark.readStream.table(f"{CATALOG}.{SILVER}.page_expense_map").filter(
        "page_role = 'supporting_invoice' AND expense_category IS NOT NULL")
    x = F.expr(f"ai_extract(page_text, {json_literal(INVOICE_SCHEMA)}, {V21})")
    return pages.withColumn("x", x).select(
        "file_item_id", "proforma_id", "page_number", "expense_category",
        F.expr("x:response:description:value::STRING").alias("description"),
        F.expr("x:response:amount:value::DECIMAL(18,2)").alias("amount"),
        F.expr("x:response:currency:value::STRING").alias("currency"),
        F.least(F.col("confidence"), F.expr("x:response:amount:confidence_score::DOUBLE")).alias("confidence"),
        F.lit("supporting_invoice").alias("line_source"),
    )


@dp.temporary_view()
def proforma_quote_lines():
    pages = spark.readStream.table(f"{CATALOG}.{SILVER}.document_pages").filter(
        "doc_type = 'pda_quote' AND page_error IS NULL")
    x = F.expr(f"ai_extract(page_text, {json_literal(QUOTE_SCHEMA)}, {V21})")
    return (
        pages.withColumn("x", x)
        .select("file_item_id", "proforma_id", "page_number",
                F.expr("x:response:currency:value::STRING").alias("currency"),
                F.explode(F.expr("variant_get(x, '$.response.line_items', 'ARRAY<VARIANT>')")).alias("li"))
        .select(
            "file_item_id", "proforma_id", "page_number",
            F.expr("li:expense_category:value::STRING").alias("expense_category"),
            F.expr("li:description:value::STRING").alias("description"),
            F.expr("li:amount:value::DECIMAL(18,2)").alias("amount"),
            "currency",
            F.expr("li:amount:confidence_score::DOUBLE").alias("confidence"),
            F.lit("proforma_quote").alias("line_source"),
        )
    )


dp.create_streaming_table(
    name=f"{CATALOG}.{SILVER}.doc_line_items",
    comment="Amounts read from documents: one row per supporting invoice page (final packs) or quoted line (proformas)",
    cluster_by=["proforma_id"],
)


@dp.append_flow(target=f"{CATALOG}.{SILVER}.doc_line_items", name="supporting_invoices")
def supporting_invoices():
    return spark.readStream.table("supporting_invoice_lines")


@dp.append_flow(target=f"{CATALOG}.{SILVER}.doc_line_items", name="proforma_quotes")
def proforma_quotes():
    return spark.readStream.table("proforma_quote_lines")
