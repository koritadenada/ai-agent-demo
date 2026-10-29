"""Bronze: each new PDF read once by Auto Loader as a binary file; the S3 key carries the join keys."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import BRONZE, CATALOG, DOCUMENTS_PATH

# <entity>/<entity_id>/<file_item_id>.pdf, for example proforma/50217/1348002.pdf (the key in file_item.s3_key)
KEY_PATTERN = r"/([a-z_]+)/(\d+)/(\d+)\.pdf$"


@dp.table(
    name=f"{CATALOG}.{BRONZE}.documents_raw",
    comment="PDF documents as received, one row per file, with the owning entity and file_item_id parsed from the key",
)
@dp.expect_or_drop("key_matches_layout", "file_item_id IS NOT NULL")
def documents_raw():
    path = F.col("_metadata.file_path")
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "binaryFile")
        .option("pathGlobFilter", "*.pdf")
        .load(DOCUMENTS_PATH)
        .select(
            path.alias("path"),
            F.regexp_extract(path, KEY_PATTERN, 1).alias("entity"),
            F.regexp_extract(path, KEY_PATTERN, 2).cast("bigint").alias("entity_id"),
            F.nullif(F.regexp_extract(path, KEY_PATTERN, 3), F.lit("")).cast("bigint").alias("file_item_id"),
            # Documents of a DA hang off its proforma (PDA and FDA packs, statements of facts)
            F.when(F.regexp_extract(path, KEY_PATTERN, 1) == "proforma", F.regexp_extract(path, KEY_PATTERN, 2).cast("bigint"))
             .alias("proforma_id"),
            "content",
            F.col("length").alias("size_bytes"),
            F.col("modificationTime").alias("landed_at"),
            F.current_timestamp().alias("_ingested_at"),
        )
    )
