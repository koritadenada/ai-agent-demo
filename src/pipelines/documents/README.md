# Documents pipeline

Reads every PDF in the documents bucket once and turns it into facts with page citations: the text of each page,
which DA expense line each page evidences, the amounts, bank details, date and rate of exchange printed on it, and
the timeline of the port call.

```
documents bucket -> documents -> document_pages -> page_expense_map -> doc_line_items      -> gold checks
(raw layer, S3)     parse, type  one row per page  page to DA line     amount per page
                                                                   -> expense_page_evidence (pages per line)
                                                                   -> doc_bank_details      (summary page)
                                    document_pages -> port_call_events (statement of facts timeline)
```

There is no bronze copy of the PDFs: they never change, so the bucket is the raw layer and Auto Loader reads it
directly. Every model result is stored once, so nothing downstream calls a model again.

## Prompts: where they live and how to change them

Every model call takes its prompt from the MLflow Prompt Registry in Unity Catalog, in the silver schema, by alias
(`prompt_alias`, default `production`). For `ai_query` steps the model is a tag on the prompt version
(`model`); `ai_classify` and `ai_extract` use their built-in model, so for them the prompt is the instructions.

| Prompt | Used by | Step |
|---|---|---|
| `document_type` | `ai_classify` | Type of each document, from its first page |
| `page_map` | `ai_query` + model tag | Page of a final DA pack to the DA's expense line |
| `invoice_amount` | `ai_extract` | Amount and currency on a supporting invoice |
| `bank_details` | `ai_extract` | Bank details, total, date, rate of exchange; the field vocabulary (IBAN, Account no., BIC) |
| `sof_events` | `ai_query` + model tag | Timeline of a statement of facts |

To browse them: the MLflow experiment `portcall-prompts` (created by the bundle), **Prompts** tab.

**First deploy.** [`utilities/prompts.py`](utilities/prompts.py) holds the starting text of each prompt. The
`prompts` task of the setup job registers it as version 1 and points `production` at it, only when the prompt does
not exist yet. After that the registry is the source of truth: later deploys never overwrite a version, and the
file is only read again if the registry cannot be reached (rows then show `@repo-default`).

**Changing a prompt or its model.** Create a new version and move the `production` alias to it, in the Prompts tab
or in code. The model of an `ai_query` step is the `model` tag of the version, so a model change is a new version
with a different tag (in code, as below):

```python
import mlflow
mlflow.set_registry_uri("databricks-uc")
name = "<catalog>.<silver schema>.page_map"
v = mlflow.genai.register_prompt(name=name, template="...new text, same {{placeholders}}...",
                                 tags={"model": "databricks-claude-sonnet-4-5"}, commit_message="Clearer split rule")
mlflow.genai.set_prompt_alias(name=name, alias="production", version=v.version)
```

What happens next:

- **No deploy.** The next pipeline run loads the new version when it starts and uses it for that whole run.
- **New documents only.** Each page is processed once, so pages already done keep the result of the version that
  produced them. To re-run older documents with the new prompt, refresh that table on purpose (model calls are paid
  again; in production `allow_reset` keeps this from happening by accident).
- **Traceable.** Every row records the version that produced it (`prompt_version`, for example
  `page_map@production v2`); the version holds the text and the model, so results of different versions can be told
  apart and compared.
- **Measured.** `Agreement with analysts` in `expense_reconciliation_metrics` shows whether the new version agrees
  with the DA analysts as well as the old one.
- **Rollback.** Move `production` back to the previous version; the next run uses it again.
- **Try before switching.** Point a `challenger` alias at the new version and run a copy of the pipeline with
  `prompt_alias: challenger` on the same documents, then compare before moving `production`.
- **Keep the placeholders.** `page_map` needs `{{expense_lines}}`, `{{categories}}` and `{{page_text}}`;
  `sof_events` needs `{{document_text}}`. The JSON output schema is in the code, so a prompt change cannot break the
  table columns.

## The AI services, requirement by requirement

The services of the current platform and where each requirement is implemented. Status: **met**, **by design**
(met differently, on purpose), **gap** (not covered yet).

### Page extractor: page-accurate text from any PDF

| Requirement | Implemented in | Status |
|---|---|---|
| Page-accurate text from scanned or digital PDFs | [`documents.py`](transformations/documents.py): `ai_parse_document` | met |
| Page numbers for downstream citations | [`documents.py`](transformations/documents.py) `pages`, [`document_pages.py`](transformations/document_pages.py) | met |
| Works for every document family | Every PDF under the bucket is parsed; [`documents.py`](transformations/documents.py) `ai_classify` sets the type | met |
| One bad page never fails the document | Parse errors are kept per page (`page_error`); the other pages flow on | met |
| No API timeout on large PDFs | Runs as a pipeline when the file lands, not as a synchronous call; up to 500 pages per document | met |
| Stable output shape `[{page_number, extracted_text}]` | `documents.pages`, same fields | met |
| Rasterize, resize, retry, per-page concurrency | Done by `ai_parse_document`; no code to maintain | by design |

### Expense page mapper: map every page to the expense it evidences

| Requirement | Implemented in | Status |
|---|---|---|
| Map each page to the specific expense line of that DA | [`page_expense_map.py`](transformations/page_expense_map.py): the DA's own final lines are in the prompt; the returned id is checked against them. If the id is not one of them, gold falls back to the only line of the page's category (`line_match`) | met |
| Port expenses and husbandry, different taxonomies | The section of each line and the category vocabulary are in the prompt | met |
| Confidence and a justification per assignment | `confidence`, `explanation` | met |
| Output per expense `{pages, confidence, explanation}` | [`expense_page_evidence.py`](transformations/expense_page_evidence.py) | met |
| The taxonomy is data, not a hand-maintained file | Read from `expense_category` (Postgres), aliases included | met |
| Port and husbandry in parallel to bound latency | One call per page covers both; pages are processed in parallel batches | by design |
| Second model as judge | Not a model: the amount on the page is checked against the final line in gold (deterministic) | by design |
| Evaluation harness for the mapping | `Agreement with analysts` in `expense_reconciliation_metrics`, against the analysts' verifications | met |

### Event summarizer: the timeline of the port call

| Requirement | Implemented in | Status |
|---|---|---|
| A coherent chronological account of the port call | [`port_call_events.py`](transformations/port_call_events.py): one row per event, in order, from the statement of facts | by design: structured events that Genie and the agents query; a narrative is written on demand by the chat assistant, not stored |
| Prompt and model change without a deploy | Prompt registry (`sof_events`) | met |
| Retry on transient failures | `failOnError => false`: a failed call is stored with its error and never fails the run | gap: failed rows are not retried automatically yet |
| Request and response tracing | `prompt_version` per row | gap: AI Gateway inference tables for full request logs |

### Port bill analysis: reconcile the quote against the final bill

| Requirement | Implemented in | Status |
|---|---|---|
| Reconcile every quoted line against the final bill | [`../gold/transformations/expense_reconciliation.sql`](../gold/transformations/expense_reconciliation.sql): final line to its quoted line (`proforma_expense_id`) and to its invoice pages | met |
| Flag currency mismatches explicitly | Verdict `CURRENCY_MISMATCH`, always | met |
| Cite a document and page for every finding | `evidence_pages`, `file_item_id`, `explanation` | met |
| Rate of exchange: document, then platform, else stop, never invent | `roe_source` (`document` from [`doc_bank_details.py`](transformations/doc_bank_details.py), else `platform`), else `analysis_status = NO_ROE` | met |
| Cent tolerance, combined In/Out lines | 0.01 tolerance; all pages mapped to one line are summed | met |
| Output `{analysisStatus, amountChecks[...]}` | [`../gold/transformations/port_bill_analysis.sql`](../gold/transformations/port_bill_analysis.sql) | met |
| A/B test model and effort without a redeploy | The rulebook is SQL, not a model call: same input, same verdict; thresholds are bundle variables | by design |

### PDA/FDA validator: check bank details, amounts and dates before money moves

| Requirement | Implemented in | Status |
|---|---|---|
| Bank account, amount and date against the system of record | [`doc_bank_details.py`](transformations/doc_bank_details.py) reads them; [`../gold/transformations/payment_validation.sql`](../gold/transformations/payment_validation.sql) checks them | met |
| IBAN, domestic account and SWIFT formats | [`../../uc_functions/`](../../uc_functions/): anchored IBAN tail, SWIFT 8 vs 11 | met |
| A false MATCH is worse than a false NO_MATCH, in code | Confidence floor 0.8 in the UC functions: low confidence is always NO_MATCH | met |
| Formal fields never rely on the model alone | The model reads, deterministic rules decide | met |
| New template vocabulary is data, not a prompt rewrite | Field labels (IBAN, Account no., BIC...) are in the `bank_details` prompt in the registry | met |
| Per-field verdicts with confidence and explanation | `field_checks` | met |

### Negotiator: flag overpriced quotes against history

| Requirement | Implemented in | Status |
|---|---|---|
| Compare every quoted expense with history for the port | [`../gold/transformations/quote_benchmark_flags.sql`](../gold/transformations/quote_benchmark_flags.sql) | met |
| Deterministic rule cascade, no model in the math | [`../gold/transformations/expense_benchmarks.sql`](../gold/transformations/expense_benchmarks.sql): exact (port, vessel type, size), then nearby ports (region, same type and size), then the port with any vessel; each level needs `min_benchmark_sample` past lines | met |
| Regional and local port minimum | `region_min_median_eur`, `local_port_min_eur` | met |
| Reconcile expense names across agency templates | The platform's `category_id` on every quoted and final line; no model needed | by design |
| Draft a citation-backed negotiation email | `reasoning` gives the facts to cite | gap: the email is the quote advisor agent (next phase) |

### Chat assistant: questions in plain language

| Requirement | Implemented in | Status |
|---|---|---|
| Answer with the user's own permissions | Genie agents on the metric views, governed by Unity Catalog | gap: next phase |
| Never write without explicit confirmation | Agent tools with confirmation | gap: next phase |

Shared settings, the prompt loader and the expense vocabulary are in [`utilities/settings.py`](utilities/settings.py).
Costs: [`docs/costs.md`](../../../docs/costs.md).
