"""Silver pages: one row per page of every document, page numbers kept for citations.
A page that failed to parse keeps its error; the rest of the document still flows."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import AI_TABLE_PROPERTIES, CATALOG, SILVER


@dp.table(
    name=f"{CATALOG}.{SILVER}.document_pages",
    comment="One row per page (page_number starts at 1), with the text and any parse error of that page",
    cluster_by=["file_item_id"],
    table_properties=AI_TABLE_PROPERTIES,
)
def document_pages():
    return (
        spark.readStream.table(f"{CATALOG}.{SILVER}.documents")
        .select("file_item_id", "proforma_id", "entity", "doc_type", "parse_errors", F.explode("pages").alias("p"))
        .select(
            "file_item_id", "proforma_id", "entity", "doc_type",
            F.col("p.page_number").alias("page_number"),
            F.col("p.extracted_text").alias("page_text"),
            F.expr("filter(parse_errors, x -> x.page_id = p.page_number - 1)[0].error_message").alias("page_error"),
        )
    )
