# Documents pipeline

Reads every PDF that lands in the documents bucket once, and turns it into facts with page citations: which
expense each page evidences, the amounts and bank details printed on it, and the timeline of the port call.

```
documents bucket -> documents -> document_pages -> page_expense_map -> doc_line_items
(raw layer, S3)     parse, type    one row per page  page to expense     amount per invoice page
                                                                     -> doc_bank_details
                                                                        bank details, total
                                   document_pages -> port_call_events
                                                     statement of facts timeline
```

There is no bronze copy of the PDFs: the files never change, so the bucket is the raw layer and Auto Loader reads
it directly. Every AI result is stored once in a streaming table, so nothing downstream calls a model again.

## AI agents and where they are implemented

The agents on the Use case tab of the architecture page, and the files that implement each part. The DA auditor
and the payment check run today as pipeline steps; the quote advisor and the chat assistant are the next phase.

| Agent | Capability | Implemented in | AI Function |
|---|---|---|---|
| DA auditor | Read every page of a PDF, with page numbers | [`transformations/documents.py`](transformations/documents.py), [`transformations/document_pages.py`](transformations/document_pages.py) | `ai_parse_document` |
| DA auditor | Tell a PDA quote, a final DA pack and a statement of facts apart | [`transformations/documents.py`](transformations/documents.py) | `ai_classify` (first page only) |
| DA auditor | Map each page of a final DA pack to the expense it evidences | [`transformations/page_expense_map.py`](transformations/page_expense_map.py) | `ai_query` with a JSON schema |
| DA auditor | Read the amount on each supporting invoice | [`transformations/doc_line_items.py`](transformations/doc_line_items.py) | `ai_extract` (v2.1, confidence) |
| DA auditor | Turn a statement of facts into an ordered timeline | [`transformations/port_call_events.py`](transformations/port_call_events.py) | `ai_query` with a JSON schema |
| DA auditor | Check each final line against its quote, its invoice page and the benchmark | [`../gold/transformations/expense_reconciliation.sql`](../gold/transformations/expense_reconciliation.sql), [`../gold/transformations/expense_benchmarks.sql`](../gold/transformations/expense_benchmarks.sql) | none: plain SQL |
| Payment check | Read the bank details and total printed on the summary page | [`transformations/doc_bank_details.py`](transformations/doc_bank_details.py) | `ai_extract` (v2.1, confidence) |
| Payment check | Compare them with the bank account on the platform, hold on mismatch | [`../gold/transformations/payment_validation.sql`](../gold/transformations/payment_validation.sql), [`../../uc_functions/`](../../uc_functions/) | none: SQL and UC functions |
| Quote advisor (next phase) | Compare quotes and the PDA with past final costs | [`../gold/transformations/rfq_comparison.sql`](../gold/transformations/rfq_comparison.sql), [`../gold/transformations/expense_benchmarks.sql`](../gold/transformations/expense_benchmarks.sql) | none yet: drafting the email is the agent part |
| Chat assistant (next phase) | Answer questions on the results | [`../../metric_views/`](../../metric_views/) | none yet: Genie agents and a supervisor |

Shared settings and the expense vocabulary (read from `expense_category`, so new expense types are data, not
prompt changes) are in [`utilities/settings.py`](utilities/settings.py).

## What keeps the cost down

- Each PDF is parsed once, when it lands; a full refresh cannot reset these tables in production.
- `ai_classify` reads the first page only and decides which branch runs; proformas need no further model calls
  because their amounts are already in `proforma_expense`.
- The page map and the extraction only run on final DA packs, one call per page.
- Measured costs and further levers: [`docs/costs.md`](../../../docs/costs.md).
