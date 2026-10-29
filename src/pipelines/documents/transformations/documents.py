"""Silver documents: ai_parse_document once per file, then ai_classify the document type from its first page."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import BRONZE, CATALOG, SILVER, json_literal

DOC_TYPES = {
    "pda_quote": "Proforma disbursement account: the agent's quote before the port call",
    "final_da_pack": "Final disbursement account with the final amounts, bank details and supplier invoices",
    "statement_of_facts": "Statement of facts: timeline of the vessel's arrival, operations and departure",
    "other": "Anything else",
}

ELEMENTS = "ARRAY<STRUCT<type: STRING, content: STRING, bbox: ARRAY<STRUCT<page_id: INT>>>>"
ERRORS = "ARRAY<STRUCT<error_message: STRING, page_id: INT>>"


@dp.table(
    name=f"{CATALOG}.{SILVER}.documents",
    comment="One row per document: parsed structure (ai_parse_document), page count, parse errors, classified type",
    cluster_by=["proforma_id"],
)
def documents():
    parsed = (
        spark.readStream.table(f"{CATALOG}.{BRONZE}.documents_raw")
        # Figure descriptions are not needed for text extraction and add cost
        .withColumn("parsed", F.expr("ai_parse_document(content, map('version', '2.0', 'descriptionElementTypes', ''))"))
        .withColumn("elements", F.expr(f"variant_get(parsed, '$.document.elements', '{ELEMENTS}')"))
        .withColumn("page_count", F.expr("size(variant_get(parsed, '$.document.pages', 'ARRAY<VARIANT>'))"))
        .withColumn("parse_errors", F.expr(f"coalesce(variant_get(parsed, '$.error_status', '{ERRORS}'), array())"))
        .withColumn("first_page_text", F.expr(
            "concat_ws('\\n', transform(filter(elements, e -> e.bbox[0].page_id = 0), e -> e.content))"))
    )
    return parsed.select(
        "file_item_id", "proforma_id", "entity", "entity_id", "path", "size_bytes", "landed_at",
        "parsed", "elements", "page_count", "parse_errors",
        F.expr(f"ai_classify(first_page_text, {json_literal(DOC_TYPES)}, map('version', '2.0'))"
               ":response[0]::STRING").alias("doc_type"),
        F.current_timestamp().alias("processed_at"),
    )
