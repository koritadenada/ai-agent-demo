"""Silver documents: Auto Loader reads each new PDF once, ai_parse_document parses it, ai_classify types it.

There is no bronze copy of the PDFs: the documents bucket is the raw layer (files never change), so the bytes
are read from it and only the keys, the parse result and the type are stored."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import AI_TABLE_PROPERTIES, CATALOG, DOCUMENTS_PATH, SILVER, json_literal, prompt, sql_str

DOC_TYPES = {
    "pda_quote": "Proforma disbursement account: the agent's quote before the port call",
    "final_da_pack": "Final disbursement account with the final amounts, bank details and supplier invoices",
    "statement_of_facts": "Statement of facts: timeline of the vessel's arrival, operations and departure",
    "other": "Anything else",
}

# <entity>/<entity_id>/<file_item_id>.pdf, for example proforma/50217/1348002.pdf (the key in file_item.s3_key)
KEY_PATTERN = r"/([a-z_]+)/(\d+)/(\d+)\.pdf$"

ELEMENTS = "ARRAY<STRUCT<type: STRING, content: STRING, bbox: ARRAY<STRUCT<page_id: INT>>>>"
ERRORS = "ARRAY<STRUCT<error_message: STRING, page_id: INT>>"
TYPE_PROMPT = prompt("document_type")  # instructions for ai_classify, from the prompt registry
# The page text of every page, in the stable shape downstream consumers rely on: [{page_number, extracted_text}]
PAGES = ("IF(page_count > 0, transform(sequence(0, page_count - 1), p -> named_struct('page_number', p + 1, "
         "'extracted_text', concat_ws('\\n', transform(filter(elements, e -> e.bbox[0].page_id = p), e -> e.content)))), "
         "array())")


@dp.table(
    name=f"{CATALOG}.{SILVER}.documents",
    comment="One row per document: parsed structure (ai_parse_document), text per page, page count, parse errors, "
            "classified type",
    cluster_by=["proforma_id"],
    table_properties=AI_TABLE_PROPERTIES,
)
def documents():
    path = F.col("_metadata.file_path")
    key = lambda i: F.regexp_extract(path, KEY_PATTERN, i)  # noqa: E731
    parsed = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "binaryFile")
        .option("pathGlobFilter", "*.pdf")
        .load(DOCUMENTS_PATH)
        .select(
            path.alias("path"),
            key(1).alias("entity"),
            key(2).cast("bigint").alias("entity_id"),
            F.nullif(key(3), F.lit("")).cast("bigint").alias("file_item_id"),
            # documents of a DA hang off its proforma (PDA and FDA packs, statements of facts)
            F.when(key(1) == "proforma", key(2).cast("bigint")).alias("proforma_id"),
            F.col("length").alias("size_bytes"),
            F.col("modificationTime").alias("landed_at"),
            "content",
        )
        # Files outside the key layout are skipped before parsing, so they cost nothing
        .filter("file_item_id IS NOT NULL")
        # Figure descriptions are not needed for text extraction and add cost
        .withColumn("parsed", F.expr("ai_parse_document(content, map('version', '2.0', 'descriptionElementTypes', ''))"))
        .withColumn("elements", F.expr(f"variant_get(parsed, '$.document.elements', '{ELEMENTS}')"))
        .withColumn("page_count", F.expr("size(variant_get(parsed, '$.document.pages', 'ARRAY<VARIANT>'))"))
        .withColumn("parse_errors", F.expr(f"coalesce(variant_get(parsed, '$.error_status', '{ERRORS}'), array())"))
        .withColumn("first_page_text", F.expr(
            "concat_ws('\\n', transform(filter(elements, e -> e.bbox[0].page_id = 0), e -> e.content))"))
    )
    classify = (f"ai_classify(first_page_text, {json_literal(DOC_TYPES)}, "
                f"map('version', '2.0', 'instructions', {sql_str(TYPE_PROMPT.template)})):response[0]::STRING")
    return parsed.select(
        "file_item_id", "proforma_id", "entity", "entity_id", "path", "size_bytes", "landed_at",
        "parsed", "page_count", "parse_errors",
        F.expr(PAGES).alias("pages"),
        F.expr(classify).alias("doc_type"),
        F.lit(TYPE_PROMPT.version).alias("prompt_version"),
        F.current_timestamp().alias("processed_at"),
    )
