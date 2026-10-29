"""Bronze: every DMS file, full load and CDC, appended as received; one streaming table per source table.

The envelope matches DMS plus Auto Loader: Op, _dms_commit_ts first; _rescued_data, _source_file, _ingested_at last.
Skipped when the pipeline runs on an existing bronze (bronze_mode = existing).
"""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import BRONZE_MODE, DMS_PATH, SOURCE_SCHEMA, bronze_name, present_tables
from utilities.tables import COMMIT_TS, OP


def define_bronze(table):
    @dp.table(
        name=bronze_name(table.name),
        comment=f"DMS change log of {SOURCE_SCHEMA}.{table.name}: one row per change, not current state. {table.comment}",
        cluster_by_auto=True,
    )
    @dp.expect_all({"valid_op": f"{OP} IN ('I', 'U', 'D')", "has_commit_ts": f"{COMMIT_TS} IS NOT NULL"})
    @dp.expect_all_or_drop({f"{k}_not_null": f"{k} IS NOT NULL" for k in table.keys})
    def bronze():
        raw = (
            spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "parquet")
            .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
            .option("rescuedDataColumn", "_rescued_data")
            .load(f"{DMS_PATH}/{SOURCE_SCHEMA}/{table.name}/")
        )
        source_columns = [c for c in raw.columns if c not in (OP, COMMIT_TS, "_rescued_data")]
        return raw.select(
            # Full load files have no Op unless IncludeOpForFullLoad is set: treat them as inserts
            F.coalesce(F.col(OP), F.lit("I")).alias(OP),
            F.col(COMMIT_TS).cast("string").alias(COMMIT_TS),
            *source_columns,
            "_rescued_data",
            F.col("_metadata.file_path").alias("_source_file"),
            F.current_timestamp().alias("_ingested_at"),
        )


if BRONZE_MODE == "build":
    for t in present_tables():
        define_bronze(t)
