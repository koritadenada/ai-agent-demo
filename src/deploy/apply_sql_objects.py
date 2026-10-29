"""Applies the SQL objects that bundles have no resource type for: UC functions and metric views.

Each file is idempotent (CREATE OR REPLACE), so the job can run on every refresh.
  --kind functions     src/uc_functions/*.sql
  --kind metric_views  src/metric_views/*.yaml, wrapped in CREATE OR REPLACE VIEW ... WITH METRICS
"""
import argparse
import inspect
import pathlib

import yaml
from pyspark.sql import SparkSession

# Serverless jobs run the script without __file__; the code object still knows its path
SRC = pathlib.Path(inspect.currentframe().f_code.co_filename).resolve().parent.parent


def render(text: str, args) -> str:
    return (text.replace("{catalog}", args.catalog)
                .replace("{gold_schema}", args.gold_schema)
                .replace("{silver_schema}", args.silver_schema))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["functions", "metric_views"], required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--gold-schema", required=True)
    ap.add_argument("--silver-schema", required=True)
    args = ap.parse_args()
    spark = SparkSession.builder.getOrCreate()

    if args.kind == "functions":
        for f in sorted((SRC / "uc_functions").glob("*.sql")):
            spark.sql(render(f.read_text(), args))
            print(f"applied function {f.stem}")
        return

    for f in sorted((SRC / "metric_views").glob("*.yaml")):
        body = render(f.read_text(), args)
        yaml.safe_load(body)  # fail fast with a clear YAML error before Spark sees it
        name = f"{args.catalog}.{args.gold_schema}.{f.stem}"
        spark.sql(f"CREATE OR REPLACE VIEW {name} WITH METRICS LANGUAGE YAML AS $$\n{body}\n$$")
        print(f"applied metric view {name}")


if __name__ == "__main__":
    main()
