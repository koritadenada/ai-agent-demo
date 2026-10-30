"""Silver: AUTO CDC turns each bronze change log into current state (SCD 1) or history (SCD 2).

One ordering rule for every table: full-load rows first, then the source version (when the table has one), then
the commit time. Full load must come first because DMS stamps full-load rows with their copy time but CDC rows
with their source commit time, so a change committed while the load ran can carry an earlier timestamp.
Op = 'D' deletes the row (for link tables: the pair was removed). Columns in column_renames get neutral names.
For SCD 2 tables __START_AT / __END_AT hold this ordering struct: read the time as __START_AT._commit_ts.
"""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import CATALOG, COLUMN_RENAMES, SILVER, SILVER_PROPERTIES, bronze_name, present_tables
from utilities.tables import COMMIT_TS, ENVELOPE, OP

HELPERS = ["_phase", "_version", "_commit_ts"]


def define_silver(t):
    changes = f"{t.name}_changes"

    @dp.temporary_view(name=changes)
    def ordered_changes():
        file_name = F.element_at(F.split("_source_file", "/"), -1)
        return (
            spark.readStream.table(bronze_name(t.name))
            .withColumnsRenamed(COLUMN_RENAMES.get(t.name, {}))
            .withColumns({
                "_phase": F.when(file_name.startswith("LOAD"), 0).otherwise(1),     # 0 full load, 1 CDC
                "_version": F.col("version") if t.versioned else F.lit(0),
                "_commit_ts": F.to_timestamp(COMMIT_TS),
            })
        )

    target = f"{CATALOG}.{SILVER}.{t.name}"
    dp.create_streaming_table(name=target, comment=t.comment or None, cluster_by_auto=True,
                              table_properties=SILVER_PROPERTIES)
    dp.create_auto_cdc_flow(
        target=target,
        source=changes,
        keys=list(t.keys),
        sequence_by=F.struct(*HELPERS),
        apply_as_deletes=F.expr(f"{OP} = 'D'"),
        except_column_list=[*ENVELOPE, *HELPERS],
        stored_as_scd_type=t.scd_type,
        track_history_column_list=list(t.track_history) or None,
        name=f"{t.name}_cdc",
    )


for table in present_tables():
    define_silver(table)
