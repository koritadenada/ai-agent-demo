"""Pipeline settings and which source tables exist in this environment."""
import json
import os

from pyspark.sql import SparkSession

from utilities.tables import TABLES

spark = SparkSession.getActiveSession()

CATALOG = spark.conf.get("catalog")
SILVER = spark.conf.get("silver_schema")
# build: this pipeline ingests the DMS files into its own bronze.
# existing: silver reads bronze tables that are already there (same envelope), for example a bronze you built before.
BRONZE_MODE = spark.conf.get("bronze_mode", "build")
BRONZE = spark.conf.get("bronze_schema")              # where this pipeline writes bronze (build mode)
BRONZE_SOURCE = spark.conf.get("bronze_source", "")   # catalog.schema of the existing bronze (existing mode)
DMS_PATH = spark.conf.get("dms_path")
SOURCE_SCHEMA = spark.conf.get("dms_source_schema")
# Source columns renamed to neutral names in silver, as JSON: {"table": {"source_column": "silver_column"}}
COLUMN_RENAMES = json.loads(spark.conf.get("column_renames", "{}") or "{}")


def bronze_name(table: str) -> str:
    if BRONZE_MODE == "existing":
        return f"{BRONZE_SOURCE}.{table}"
    return f"{CATALOG}.{BRONZE}.{table}"


def present_tables():
    """Tables with data in this environment: a DMS folder (build) or a bronze table (existing)."""
    if BRONZE_MODE == "existing":
        return [t for t in TABLES if spark.catalog.tableExists(bronze_name(t.name))]
    return [t for t in TABLES if os.path.isdir(f"{DMS_PATH}/{SOURCE_SCHEMA}/{t.name}")]
