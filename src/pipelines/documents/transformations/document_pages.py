"""Silver pages: the text of every page rebuilt from the parsed elements, page numbers kept for citations."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import CATALOG, SILVER


@dp.table(
    name=f"{CATALOG}.{SILVER}.document_pages",
    comment="One row per page (page_number starts at 1); a page that failed to parse keeps its error, the document still flows",
    cluster_by=["file_item_id"],
)
def document_pages():
    docs = spark.readStream.table(f"{CATALOG}.{SILVER}.documents")
    return (
        docs.select("file_item_id", "proforma_id", "entity", "doc_type", "elements", "parse_errors",
                    F.explode(F.sequence(F.lit(0), F.col("page_count") - 1)).alias("page_id"))
        .select(
            "file_item_id", "proforma_id", "entity", "doc_type",
            (F.col("page_id") + 1).alias("page_number"),
            F.expr("concat_ws('\\n', transform(filter(elements, e -> e.bbox[0].page_id = page_id), e -> e.content))")
             .alias("page_text"),
            F.expr("filter(parse_errors, x -> x.page_id = page_id)[0].error_message").alias("page_error"),
        )
    )
