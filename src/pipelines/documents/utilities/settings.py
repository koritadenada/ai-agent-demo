"""Pipeline settings and the expense vocabulary the LLM steps classify into."""
import json

from pyspark.sql import SparkSession

spark = SparkSession.getActiveSession()

CATALOG = spark.conf.get("catalog")
SILVER = spark.conf.get("silver_schema")
DOCUMENTS_PATH = spark.conf.get("documents_path")
LLM_ENDPOINT = spark.conf.get("llm_endpoint")

# Every LLM result is paid for once. In production a full refresh must not reset these tables (it would call
# the models again for every page); row tracking lets the gold materialized views refresh incrementally.
AI_TABLE_PROPERTIES = {"pipelines.reset.allowed": spark.conf.get("allow_reset", "false"), "delta.enableRowTracking": "true"}

CURRENCIES = ["EUR", "USD", "GBP", "SGD", "AED", "CNY", "KRW", "BRL", "ZAR", "RON"]

# The vocabulary is data: it comes from the expense_category table replicated from Postgres,
# so a new expense type needs a new row there, not a prompt change.
_FALLBACK = {"Port dues": "Dues for using the port", "Pilotage": "Pilot services in and out"}


def expense_categories() -> dict:
    try:
        rows = spark.read.table(f"{CATALOG}.{SILVER}.expense_category").select("name", "description").collect()
        return {r.name: r.description for r in rows} or _FALLBACK
    except Exception:  # first run: the platform pipeline has not created the table yet
        return _FALLBACK


def sql_str(value: str) -> str:
    """Single-quoted SQL literal."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def json_literal(obj) -> str:
    return sql_str(json.dumps(obj))
