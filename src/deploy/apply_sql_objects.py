"""Applies the SQL objects that bundles have no resource type for: UC functions and metric views.

Each file is idempotent (CREATE OR REPLACE), so the job can run on every refresh.
  --kind functions     src/uc_functions/*.sql
  --kind metric_views  src/metric_views/*.yaml, wrapped in CREATE OR REPLACE VIEW ... WITH METRICS
  --kind prompts       registers the default prompts of the document pipeline and of the app agents in the MLflow
                       Prompt Registry, only when a prompt has no version behind the alias yet (later versions are
                       never overwritten)
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


def seed_prompts(args):
    import importlib.util

    import mlflow

    defaults = {}  # name -> (schema, default): pipeline prompts in silver, app agent prompts in the app schema
    for path, schema in ((SRC / "pipelines" / "documents" / "utilities" / "prompts.py", args.silver_schema),
                         (SRC / "app" / "prompts.py", args.app_schema)):
        spec = importlib.util.spec_from_file_location(path.parent.name + "_prompts", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        defaults.update({name: (schema, p) for name, p in module.DEFAULTS.items()})
    mlflow.set_registry_uri("databricks-uc")
    for name, (schema, p) in defaults.items():
        full = f"{args.catalog}.{schema}.{name}"
        try:
            found = mlflow.genai.load_prompt(f"prompts:/{full}@{args.alias}")
            print(f"prompt {full}@{args.alias} is v{found.version}, kept")
            continue
        except Exception:
            pass
        tags = {"model": p["model"]} if p["model"] else {}
        version = mlflow.genai.register_prompt(name=full, template=p["template"], tags=tags,
                                               commit_message="Seeded from the repo default")
        mlflow.genai.set_prompt_alias(name=full, alias=args.alias, version=version.version)
        print(f"prompt {full}@{args.alias} registered as v{version.version}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["functions", "metric_views", "prompts"], required=True)
    ap.add_argument("--alias", default="production")
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--gold-schema", required=True)
    ap.add_argument("--silver-schema", required=True)
    ap.add_argument("--app-schema")
    args = ap.parse_args()
    spark = SparkSession.builder.getOrCreate()

    if args.kind == "prompts":
        seed_prompts(args)
        return

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
