"""Creates what the bundle has no resource type for on the agent side, idempotently (safe on every setup run):

  1. the Port Assistant's tools as UC functions (src/agents/tools/*.sql): document search and port call timeline
  2. the tables the app writes to (src/agents/state.sql): analyst decisions and negotiation drafts
  3. the app's service principal may read the app prompts (app schema); everything else in the app runs as the user

The agents themselves are code in the app (src/app/backend); the Genie agents are bundle resources.
"""
import argparse
import inspect
import pathlib

from pyspark.sql import SparkSession

SRC = pathlib.Path(inspect.currentframe().f_code.co_filename).resolve().parent.parent


def render(text: str, a) -> str:
    return (text.replace("{catalog}", a.catalog).replace("{gold_schema}", a.gold_schema)
                .replace("{silver_schema}", a.silver_schema).replace("{app_schema}", a.app_schema))


def main():
    ap = argparse.ArgumentParser()
    for name in ("catalog", "gold-schema", "silver-schema", "app-schema", "app-service-principal"):
        ap.add_argument(f"--{name}", required=True)
    a = ap.parse_args()
    spark = SparkSession.builder.getOrCreate()
    for f in [*sorted((SRC / "agents" / "tools").glob("*.sql")), SRC / "agents" / "state.sql"]:
        for statement in [s for s in render(f.read_text(), a).split(";\n") if s.strip()]:
            spark.sql(statement)
        print(f"applied {f.relative_to(SRC)}")
    sp = f"`{a.app_service_principal}`"
    spark.sql(f"GRANT USE CATALOG ON CATALOG {a.catalog} TO {sp}")
    # the privileges the prompt registry asks for, on the app schema only
    spark.sql(f"GRANT USE SCHEMA, CREATE FUNCTION, EXECUTE, MANAGE ON SCHEMA {a.catalog}.{a.app_schema} TO {sp}")
    print(f"granted the app prompts to the app service principal {a.app_service_principal}")


if __name__ == "__main__":
    main()
