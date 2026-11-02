# ai-agent-demo

A reference port-call data platform on Databricks, with AI agents on top. Two sources land in S3: the DA database
(Aurora PostgreSQL, copied by AWS DMS as full load plus CDC) and the PDFs (PDA quotes, final DA packs, statements of
facts). They meet in one gold layer, which three Genie agents, a supervisor agent (HAL-9000) and an agents app use.

- **Architecture (animated):** https://koritadenada.github.io/ai-agent-demo/architecture.html (arrow keys or click;
  `?mode=auto` loops)
- **More detail:** [platform pipeline](src/pipelines/platform/README.md) · [document pipeline](src/pipelines/documents/README.md)
  (every AI service requirement mapped to its file) · [agents app](src/app/README.md) · [costs](docs/costs.md)

## How it works

| Step | Platform data | Documents |
|---|---|---|
| Land | DMS Parquet in the DMS bucket | PDFs in the documents bucket |
| Silver | Auto Loader, then AUTO CDC (full load first, history where it matters) | Parsed, classified and read with AI Functions, once per file |
| Gold | Joined on the final DA line: its quote, its invoice page, the analyst's check; plain SQL rules | |
| Agents | 7 metric views, 3 Genie agents, HAL-9000, the agents app | |

| Agent | Built as | Does |
|---|---|---|
| Port costs and benchmarks | Genie agent | Cost per call, savings against the benchmark, competing and flagged quotes |
| DA audit | Genie agent | Final lines against quote and invoice, analyst agreement, payments on hold |
| DA operations | Genie agent | Workflow durations, cancellations, statement of facts events |
| HAL-9000 | Supervisor agent | Routes each question to a Genie agent, document search or the port call timeline |
| AI Negotiator | Agent in the app | Drafts the email for an open quote; every amount checked against the data |
| DA Event Summarizer | Model call in the app | Writes the account of a port call, with page citations |

Everything answers with the signed-in user's permissions and writes nothing without a confirm.

## What is in the repo

```
databricks.yml       bundle variables and targets (demo, prod)
resources/           what the bundle deploys: schemas, 3 pipelines, jobs, Genie agents, app, prompt experiments
src/pipelines/       platform, documents and gold pipelines
src/uc_functions/    bank checks and account masking
src/metric_views/    the seven metric views
src/agents/          HAL-9000 tools (document search, port call timeline) and the app tables
src/app/             the agents app
src/deploy/          what bundles cannot deploy: UC functions, metric views, prompts, HAL-9000
src/mock_data/       generator for the demo: DMS files and PDFs
infra/terraform/     AWS side only: IAM role and storage credential
docs/                architecture page, costs
tests/               end-to-end test of the deployed app
```

Jobs: `portcall-refresh` runs the pipelines in order (hourly, paused in the demo); `portcall-setup` runs after a
deploy (functions, prompts, one refresh, metric views, HAL-9000); `portcall-mock-data` fills the demo.

## Run the demo (no AWS needed)

Managed volumes stand in for the buckets.

```bash
V=(--profile <profile> --var catalog=<catalog>)    # an array: works in bash and zsh
databricks bundle deploy -t demo "${V[@]}"
databricks bundle run mock_data -t demo "${V[@]}"     # full load + 72 PDFs
databricks bundle run setup -t demo "${V[@]}"         # functions, prompts, pipelines, metric views, HAL-9000
databricks bundle run agents_app -t demo "${V[@]}"    # the agents app
# optional: one DMS CDC batch (cancellation, approvals, a bank account change, a delete), then refresh
databricks bundle run mock_data -t demo "${V[@]}" --params mode=cdc
databricks bundle run refresh -t demo "${V[@]}"
```

## Run it on your AWS account

1. In `infra/terraform`, fill in `terraform.tfvars` (copy the example) with the two buckets and apply: it creates the
   IAM role and the storage credential.
2. Deploy with its outputs and run setup:

   ```bash
   databricks bundle deploy -t prod --profile <profile> --var storage_credential_name=<output> \
     --var dms_bucket_url=s3://<dms-bucket>/ --var documents_bucket_url=s3://<documents-bucket>/
   databricks bundle run setup -t prod --profile <profile>
   databricks bundle run agents_app -t prod --profile <profile>
   ```

   The prod target reads the buckets in place (read-only external locations and volumes), unpauses the refresh and
   protects bronze and the AI tables from a full refresh.
3. Check the assumed lookup tables and `column_renames` in the
   [platform pipeline README](src/pipelines/platform/README.md#adapting-it-to-your-environment).

## Design choices

- **The AI reads, SQL decides.** Models read the PDFs once, when they land; verdicts, tolerances, exchange rates,
  benchmarks and bank checks are plain SQL and UC functions.
- **Scored against the analysts.** Every verdict sits next to the analyst's own check (`Agreement with analysts`),
  which is how a prompt or model change is judged.
- **Prompts change without a deploy.** Every model call loads its prompt from the MLflow Prompt Registry by alias.
- **Safe by default.** Gold stores masked account numbers only; the app runs as the user; thresholds are variables.
- **Cost in mind.** Serverless standard mode, incremental everywhere, one model call per page; see
  [docs/costs.md](docs/costs.md).
