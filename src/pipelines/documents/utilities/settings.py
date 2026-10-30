"""Pipeline settings, the prompts of every model call, and the expense vocabulary."""
import json
import logging
from dataclasses import dataclass

from pyspark.sql import SparkSession

from utilities.prompts import DEFAULTS

spark = SparkSession.getActiveSession()
log = logging.getLogger(__name__)

CATALOG = spark.conf.get("catalog")
SILVER = spark.conf.get("silver_schema")
DOCUMENTS_PATH = spark.conf.get("documents_path")
DEFAULT_MODEL = spark.conf.get("llm_endpoint")
PROMPT_ALIAS = spark.conf.get("prompt_alias", "production")

# Every LLM result is paid for once. In production a full refresh must not reset these tables (it would call
# the models again for every page); row tracking lets the gold materialized views refresh incrementally.
AI_TABLE_PROPERTIES = {"pipelines.reset.allowed": spark.conf.get("allow_reset", "false"), "delta.enableRowTracking": "true"}

CURRENCIES = ["EUR", "USD", "GBP", "SGD", "AED", "CNY", "KRW", "BRL", "ZAR", "RON"]


@dataclass(frozen=True)
class Prompt:
    template: str
    model: str
    version: str  # recorded on every output row, for example page_map@production v3


def prompt(name: str) -> Prompt:
    """The prompt (and model) of one model call, from the MLflow Prompt Registry by alias.

    Loaded when the pipeline update starts, so a new version behind the alias is used from the next run, without
    a deploy. Falls back to the default in utilities/prompts.py when the registry has no such prompt yet."""
    default = DEFAULTS[name]
    try:
        import mlflow

        mlflow.set_registry_uri("databricks-uc")
        found = mlflow.genai.load_prompt(f"prompts:/{CATALOG}.{SILVER}.{name}@{PROMPT_ALIAS}")
        model = (found.tags or {}).get("model") or default["model"] or DEFAULT_MODEL
        return Prompt(found.template, model, f"{name}@{PROMPT_ALIAS} v{found.version}")
    except Exception as e:  # registry not seeded yet, or not reachable: keep the pipeline running
        log.warning("prompt %s not loaded from the registry (%s), using the repo default", name, e)
        return Prompt(default["template"], default["model"] or DEFAULT_MODEL, f"{name}@repo-default")


# The vocabulary is data: it comes from the expense_category table replicated from Postgres, so a new expense
# type needs a new row there, not a prompt change.
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
