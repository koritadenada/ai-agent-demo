# ai-agent-demo

A reference implementation of a port-call data platform that AI agents can work on. Two sources land in S3:

- **Platform data**: the DA database (Aurora PostgreSQL), replicated by AWS DMS (full load plus CDC, Parquet).
- **Documents**: PDFs (PDA quotes, final DA packs with supplier invoices, statements of facts) in a second bucket.

Both go through Lakeflow Spark Declarative Pipelines into silver, meet in one gold layer on the expense line, and
are exposed through Unity Catalog metric views to Genie agents.

**Architecture (animated):** https://koritadenada.github.io/ai-agent-demo/architecture.html
Click or use the arrow keys; `?mode=auto` loops it. Tabs: the agent use case, the platform pipeline and the source
schema, the document pipeline and its step graph, gold with a worked example, Genie, one line end to end, a glossary.

## What is in the repo

```
databricks.yml                 bundle: variables and the two targets (demo, prod)
resources/                     everything the bundle deploys
  schemas.yml                  landing, bronze, silver, gold schemas and the two landing volumes
  platform.pipeline.yml        DMS files -> bronze -> silver (AUTO CDC)
  documents.pipeline.yml       PDFs -> silver (AI Functions, prompts from the MLflow Prompt Registry)
  gold.pipeline.yml            joined gold tables (materialized views, plain SQL)
  refresh.job.yml              scheduled refresh: platform, documents, gold, in that order
  setup.job.yml                run after a deploy: UC functions, prompt seeding, one refresh, metric views
  mock_data.job.yml            writes mock DMS files and PDFs into the landing volumes (demo)
  prompts.experiment.yml       MLflow experiment whose Prompts tab shows the prompt registry
src/
  pipelines/platform/          bronze + silver for every DMS table, driven by utilities/tables.py   (README)
  pipelines/documents/         parse, pages, page map, amounts, bank details, events; prompt loader   (README)
  pipelines/gold/              reconciliation, port bill analysis, payment validation, benchmarks, quote flags,
                               port call costs, quotes, workflow, document quality
  uc_functions/                deterministic bank checks (IBAN or domestic tail, SWIFT 8 vs 11) and masking
  metric_views/                seven metric views (YAML), one per KPI group
  deploy/apply_sql_objects.py  applies UC functions and metric views, seeds the prompts (no bundle resource for them)
  mock_data/                   generator: the DA tables as DMS Parquet (full load or a CDC batch) and the PDFs
infra/terraform/               the AWS side: IAM role for Unity Catalog and the storage credential
docs/                          architecture page and costs
```

Each pipeline has its own README: the [platform pipeline](src/pipelines/platform/README.md) (why the view, full load
vs CDC, how it runs, adapting it to your schema) and the [document pipeline](src/pipelines/documents/README.md)
(prompts, and every requirement of the current AI services mapped to the file that implements it).

## How the pieces fit

| Layer | Platform data | Documents |
|---|---|---|
| Landing | DMS writes `da_schema/<table>/LOAD*.parquet`, then CDC files | `proforma/<proforma_id>/<file_item_id>.pdf` |
| Bronze | Auto Loader, one change-log table per source table (`Op`, `_dms_commit_ts` ... `_source_file`) | None: the bucket is the raw layer |
| Silver | AUTO CDC: full load first, then version, then commit time; deletes on `Op = 'D'`; SCD 2 where history matters | `ai_parse_document` per file, `ai_classify` the type, `ai_query` page to the DA's expense line, `ai_extract` amounts, bank details and rate of exchange, `ai_query` statement of facts timeline |
| Gold | Joined on the expense line: final line to its quote (`proforma_expense_id`), to its invoice pages, to the analyst's verification; bank checks, benchmarks, quote flags, costs, workflow | |
| Semantic | Metric views per KPI group, for the Genie agents | |

| Job | When | What |
|---|---|---|
| `portcall-refresh` | Schedule (`refresh_cron`, hourly; paused in the demo) | Platform, then documents (they need the expense vocabulary), then gold |
| `portcall-setup` | After a deploy, by hand or as the CI step after `bundle deploy` | UC functions, seeds missing prompts, one refresh, metric views |
| `portcall-mock-data` | Demo only | Full load and PDFs, or one CDC batch (`mode=cdc`) |

Design choices worth knowing:

- **Model output is written once.** Every AI Function runs in a streaming table, so a document is processed once
  when it lands; gold and Genie only read Delta.
- **No model in the math.** Verdicts (`MATCH`, `OVER_QUOTE`, `UNDER_QUOTE`, `INVOICE_MISMATCH`, `CURRENCY_MISMATCH`,
  `NO_EVIDENCE`), tolerances, the rate of exchange order (document, platform, else stop), the benchmark cascade and
  the bank rules are SQL and UC functions. A low-confidence extraction can never produce a bank MATCH.
- **Prompts and models change without a deploy.** Every model call loads its prompt (and model) from the MLflow
  Prompt Registry by alias; every output row records the version. See the
  [document pipeline README](src/pipelines/documents/README.md#prompts-where-they-live-and-how-to-change-them).
- **Scored against the analysts.** Each verdict sits next to the DA analyst's own verification, so agreement is a
  measure (`Agreement with analysts`), not a claim, and it is how a prompt or model change is judged.
- **The vocabulary is data.** Page mapping uses the DA's own expense lines and the categories in `expense_category`
  (with the aliases agencies use), so a new expense type is a new row, not a prompt change.
- **Gold never stores a full account number** (`mask_account`); full values stay in silver.
- **Neutral names.** Vendor-named source columns are renamed in silver (`column_renames`).
- **Built with cost in mind**: standard serverless mode, incremental everywhere, model results paid once and
  protected from resets, no copy of the PDFs; measured numbers and levers in [docs/costs.md](docs/costs.md).
- **Thresholds are variables** (`match_tolerance_pct`, `dispute_threshold_pct`, `min_benchmark_sample`,
  `quote_flag_pct`); the defaults are an example policy.

### Metric views

| Metric view | Source | Example measures | Genie agent |
|---|---|---|---|
| `port_call_cost_metrics` | `port_call_costs` | Cost per call EUR, Final vs quote pct, Average FDA approval hours | Port cost analyst |
| `benchmark_savings_metrics` | `expense_reconciliation` | Potential savings EUR, Gap to benchmark pct | Port cost analyst |
| `rfq_quote_metrics` | `rfq_comparison` | Premium over lowest EUR, Spread between quotes EUR | Port cost analyst |
| `expense_reconciliation_metrics` | `expense_reconciliation` | Over-invoiced amount EUR, Mismatch rate, Agreement with analysts | DA audit |
| `payment_validation_metrics` | `payment_validation` | Bank detail mismatches, Payments on hold | DA audit |
| `document_quality_metrics` | `document_quality` | Parse error rate, Mean extraction confidence | DA audit |
| `da_workflow_metrics` | `da_workflow` | Hours FDA to approval, Cancelled appointments | DA operations |

Each view has comments and synonyms so Genie maps business phrasing to the right measure. The Genie agents and
the supervisor agent are the next phase.

## Run the demo (no AWS needed)

Managed volumes stand in for the two buckets and the generator fills them.

```bash
V="--profile <profile> --var catalog=<catalog>"
databricks bundle deploy -t demo $V
databricks bundle run mock_data -t demo $V                       # full load + 72 PDFs
databricks bundle run setup -t demo $V                           # UC functions, prompts, pipelines, metric views
# then simulate DMS CDC: cancels appointment 88213, approves 3 FDAs, changes a bank account, deletes a quoted line,
# and replays a change committed while the full load was running
databricks bundle run mock_data -t demo $V --params mode=cdc
databricks bundle run refresh -t demo $V                         # pipelines only
```

The demo target creates `portcall_landing`, `portcall_bronze`, `portcall_silver` and `portcall_gold` in `<catalog>`,
and the prompts in `portcall_silver`. The `ai_query` steps default to `databricks-gpt-5-mini` (the `model` tag of
each prompt version; `llm_endpoint` when a version has none).

## Run it on your AWS account

1. `infra/terraform`: copy `terraform.tfvars.example` to `terraform.tfvars`, fill in the two existing buckets,
   then `terraform init && terraform apply`. It creates the IAM role Unity Catalog assumes and the storage credential.
2. Deploy the bundle with the outputs, then run the setup job once:

   ```bash
   databricks bundle deploy -t prod --profile <profile> \
     --var storage_credential_name=<output> --var dms_bucket_url=s3://<dms-bucket>/ \
     --var documents_bucket_url=s3://<documents-bucket>/
   databricks bundle run setup -t prod --profile <profile>
   ```

   The prod target creates the catalog, the two external locations (read only) and external volumes on the
   buckets, so the pipelines read your files in place with the same code as the demo. The refresh job is unpaused,
   and bronze and the AI tables cannot be reset by a full refresh (`allow_reset: false`).
3. Confirm the assumed lookup tables in the [platform pipeline README](src/pipelines/platform/README.md#adapting-it-to-your-environment)
   and set `column_renames`. If your bronze already exists with the same envelope, add
   `--var bronze_mode=existing --var bronze_source=<catalog>.<schema>`.

For the near real time tables later, run them in a separate continuous pipeline and enable file events on the
external location; everything else can stay on the scheduled refresh.
