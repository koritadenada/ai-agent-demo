"""Silver: AUTO CDC turns each bronze change log into current state (SCD 1) or history (SCD 2).

Changes are ordered by (version, commit time) when the table has a version column, as the source does, else by
commit time. SCD 2 tables are ordered by commit time so __START_AT / __END_AT are timestamps.
Op = 'D' deletes the row (for link tables: the pair was removed). Columns listed in column_renames get their
neutral silver name here.
"""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import CATALOG, COLUMN_RENAMES, SILVER, bronze_name, present_tables
from utilities.tables import COMMIT_TS, ENVELOPE, OP


def define_silver(t):
    changes = f"{t.name}_changes"

    @dp.temporary_view(name=changes)
    def cast_commit_ts():
        df = spark.readStream.table(bronze_name(t.name)).withColumn("_commit_ts", F.to_timestamp(COMMIT_TS))
        return df.withColumnsRenamed(COLUMN_RENAMES.get(t.name, {}))

    if t.versioned and t.scd_type == 1:
        sequence = F.struct("version", "_commit_ts")
    else:
        sequence = F.col("_commit_ts")

    target = f"{CATALOG}.{SILVER}.{t.name}"
    dp.create_streaming_table(name=target, comment=t.comment or None, cluster_by_auto=True)
    dp.create_auto_cdc_flow(
        target=target,
        source=changes,
        keys=list(t.keys),
        sequence_by=sequence,
        apply_as_deletes=F.expr(f"{OP} = 'D'"),
        except_column_list=[*ENVELOPE, "_commit_ts"],
        stored_as_scd_type=t.scd_type,
        track_history_column_list=list(t.track_history) or None,
        name=f"{t.name}_cdc",
    )


for table in present_tables():
    define_silver(table)
