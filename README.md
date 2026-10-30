# ai-agent-demo

A reference implementation of a port-call data platform that AI agents can work on. Two sources land in S3:

- **Platform data**: the DA database (Aurora PostgreSQL), replicated by AWS DMS (full load plus CDC, Parquet).
- **Documents**: PDFs (PDA quotes, final DA packs with supplier invoices, statements of facts) in a second bucket.

Both go bronze to silver to gold with Lakeflow Spark Declarative Pipelines, meet in one gold layer on the
expense line, and are exposed through Unity Catalog metric views to Genie agents.

**Architecture (animated):** https://koritadenada.github.io/ai-agent-demo/architecture.html
Click or use the arrow keys; `?mode=auto` loops it. Tabs: the agent use case, 1b source schema, 2b document pipeline graph,
3b a worked gold example, and a glossary of the shipping and data terms.

## What is in the repo

```
databricks.yml                 bundle: variables and the two targets (demo, prod)
resources/                     everything the bundle deploys
  schemas.yml                  landing, bronze, silver, gold schemas and the two landing volumes
  platform.pipeline.yml        DMS files -> bronze -> silver (AUTO CDC)
  documents.pipeline.yml       PDFs -> bronze -> silver (AI Functions)
  gold.pipeline.yml            joined gold tables (materialized views, plain SQL)
  refresh.job.yml              the scheduled refresh: platform, documents, gold pipelines
  setup.job.yml                run after each deploy: UC functions, one refresh, metric views
  mock_data.job.yml            writes mock DMS files and PDFs into the landing volumes
src/
  pipelines/platform/          bronze.py + silver.py, driven by utilities/tables.py (all 69 tables, one line each)
  pipelines/documents/         one file per table: parse, pages, page map, line items, bank details, events
  pipelines/gold/              port_call_costs, expense_reconciliation, expense_benchmarks, payment_validation,
                               rfq_comparison, da_workflow, document_quality
  uc_functions/                deterministic bank checks (IBAN / domestic tail, SWIFT 8 vs 11) and masking
  metric_views/                seven metric views (YAML), one per KPI group
  deploy/apply_sql_objects.py  applies the UC functions and metric views (no bundle resource type for them)
  mock_data/                   generator: the DA tables as DMS Parquet (full load or a CDC batch) and PDFs
infra/terraform/               the AWS side: IAM role for Unity Catalog and the storage credential
docs/                          architecture page, costs (docs/costs.md)
```

## How the pieces fit

| Layer | Platform data | Documents |
|---|---|---|
| Landing | DMS writes `da_schema/<table>/LOAD*.parquet` and CDC files | `proforma/<proforma_id>/<file_item_id>.pdf` |
| Bronze | Auto Loader, one change-log streaming table per source table (Op, _dms_commit_ts ... _source_file) | Auto Loader `binaryFile`, proforma_id and file_item_id parsed from the key |
| Silver | AUTO CDC ordered full load first, then version, then commit time; deletes on `Op = 'D'`, SCD 2 where history matters | `ai_parse_document` once per file, `ai_classify` the type, pages, `ai_query` page to expense, `ai_extract` amounts and bank details, `ai_query` event timeline |
| Gold | joined on the expense line: final line to its quote (`proforma_expense_id`), to its invoice page, to the analyst verification; plus bank checks, benchmarks, quotes and workflow | |
| Semantic | metric views per KPI group, ready for Genie agents | |

Design choices worth knowing:

- **LLM output is written once.** Every AI Function runs in a streaming table, so a document is processed once
  when it lands; gold and Genie only read Delta.
- **No LLM in the math.** Verdicts (`MATCH`, `OVER_QUOTE`, `UNDER_QUOTE`, `INVOICE_MISMATCH`, `CURRENCY_MISMATCH`,
  `NO_EVIDENCE`), tolerances and the bank rules are SQL and UC functions. A low-confidence extraction can never
  produce a bank MATCH.
- **Scored against the analysts.** Each verdict sits next to the analyst's own verification
  (`expense_evaluation_verification.discrepancy_type`), so agreement is a measure, not a claim.
- **The vocabulary is data.** Page mapping and extraction use the categories in `expense_category`
  (replicated from Postgres), so a new expense type is a new row, not a prompt change. That is also why the
  documents pipeline runs after the platform pipeline.
- **Gold never stores a full account number** (`mask_account`); full values stay in silver.
- **Neutral names.** Vendor-named source columns are renamed in silver (`column_renames`), see the
  [platform pipeline README](src/pipelines/platform/README.md).
- **Built with cost in mind**: standard serverless mode, incremental everywhere, LLM results paid once and
  protected from resets, measured numbers and levers in [docs/costs.md](docs/costs.md).
- **Thresholds are variables** (`match_tolerance_pct`, `dispute_threshold_pct`); the defaults are an example policy.

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
databricks bundle run setup -t demo $V                           # UC functions, pipelines, metric views
# then simulate DMS CDC: cancels appointment 88213, approves 3 FDAs, changes a bank account, deletes a quoted line,
# and replays a change committed while the full load was running
databricks bundle run mock_data -t demo $V --params mode=cdc
databricks bundle run refresh -t demo $V                         # pipelines only
```

The demo target creates `portcall_landing`, `portcall_bronze`, `portcall_silver` and `portcall_gold` in `<catalog>`. It uses
`databricks-gpt-5-mini` for `ai_query`; change `llm_endpoint` to any chat endpoint you have.

## Run it on your AWS account

1. `infra/terraform`: copy `terraform.tfvars.example` to `terraform.tfvars`, fill in the two existing buckets,
   then `terraform init && terraform apply`. It creates the IAM role Unity Catalog assumes and the storage credential.
2. Deploy the bundle with the outputs:

   ```bash
   databricks bundle deploy -t prod --profile <profile> \
     --var storage_credential_name=<output> --var dms_bucket_url=s3://<dms-bucket>/ \
     --var documents_bucket_url=s3://<documents-bucket>/
   ```

   The prod target creates the catalog, the two external locations (read only) and external volumes on the
   buckets, so the pipelines read your files in place with the same code as the demo. The hourly refresh job
   is unpaused.
3. Confirm the assumed lookup tables in the [platform pipeline README](src/pipelines/platform/README.md) and set
   `column_renames`. If your bronze already exists with the same envelope, add
   `--var bronze_mode=existing --var bronze_source=<catalog>.<schema>`.

For the near real time tables later, switch the platform pipeline to `continuous: true` and enable file events
on the external location.
