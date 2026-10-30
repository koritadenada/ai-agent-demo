"""Silver bank details: ai_extract (v2.1) reads beneficiary, account, SWIFT, total, date and any printed rate of
exchange from the summary page. The match against the platform is NOT done here: gold applies deterministic rules.
The field vocabulary (IBAN, Account no., BIC...) is in the bank_details prompt, so new template wording is a new
prompt version, not a code change."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import AI_TABLE_PROPERTIES, CATALOG, CURRENCIES, SILVER, json_literal, prompt, sql_str

PROMPT = prompt("bank_details")  # ai_extract instructions, from the prompt registry
SCHEMA = {
    "beneficiary_name": {"type": "string"},
    "account_number": {"type": "string", "description": "IBAN or domestic account number exactly as printed"},
    "swift": {"type": "string", "description": "SWIFT / BIC code"},
    "bank_name": {"type": "string"},
    "total_amount": {"type": "number", "description": "Grand total of the disbursement account"},
    "currency": {"type": "enum", "labels": CURRENCIES},
    "document_date": {"type": "string", "description": "Date of the document, ISO format YYYY-MM-DD"},
    "rate_of_exchange": {"type": "number",
                         "description": "Units of the other currency per one unit of the document currency, if printed"},
    "exchange_currency": {"type": "enum", "labels": CURRENCIES, "description": "The other currency of the printed rate"},
}


@dp.table(
    name=f"{CATALOG}.{SILVER}.doc_bank_details",
    comment="Bank details and totals printed on each final DA pack, with per-field confidence",
    cluster_by=["proforma_id"],
    table_properties=AI_TABLE_PROPERTIES,
)
def doc_bank_details():
    pages = spark.readStream.table(f"{CATALOG}.{SILVER}.page_expense_map").filter("page_role = 'summary'")
    options = f"map('version', '2.1', 'enableConfidenceScores', 'true', 'instructions', {sql_str(PROMPT.template)})"
    x = F.expr(f"ai_extract(page_text, {json_literal(SCHEMA)}, {options})")
    v = lambda f, t="STRING": F.expr(f"x:response:{f}:value::{t}")  # noqa: E731
    c = lambda f: F.expr(f"x:response:{f}:confidence_score::DOUBLE")  # noqa: E731
    return pages.withColumn("x", x).select(
        "file_item_id", "proforma_id", "page_number",
        v("beneficiary_name").alias("beneficiary_name"),
        v("account_number").alias("account_number"),
        v("swift").alias("swift"),
        v("bank_name").alias("bank_name"),
        v("total_amount", "DECIMAL(18,2)").alias("total_amount"),
        v("currency").alias("currency"),
        F.expr("try_to_date(x:response:document_date:value::STRING)").alias("document_date"),
        v("rate_of_exchange", "DECIMAL(18,6)").alias("rate_of_exchange"),
        v("exchange_currency").alias("exchange_currency"),
        F.least(c("account_number"), c("swift")).alias("bank_confidence"),
        c("total_amount").alias("total_confidence"),
        c("document_date").alias("date_confidence"),
        F.lit(PROMPT.version).alias("prompt_version"),
    )
