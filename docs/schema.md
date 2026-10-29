# Source schema

The pipelines follow the bronze column reference of the DA database (source schema `da_schema`, landed by AWS DMS
with full load and CDC). The full table list, with keys and how each table is applied in silver, is in
[`src/pipelines/platform/utilities/tables.py`](../src/pipelines/platform/utilities/tables.py). The mock data writes
the same columns, in the same order and types ([`src/mock_data/source_schema.py`](../src/mock_data/source_schema.py)).

## Bronze envelope

Every bronze table starts with the two DMS columns and ends with three ingestion columns:

| Position | Column | Type | Meaning |
|---|---|---|---|
| first | `Op` | string | I insert, U update, D delete |
| second | `_dms_commit_ts` | string | Source commit time, cast before ordering |
| ... | source columns | | |
| last - 2 | `_rescued_data` | string | Values that did not match the schema |
| last - 1 | `_source_file` | string | DMS file the row came from |
| last | `_ingested_at` | timestamp | Bronze load time |

Bronze is a change log. Silver keeps one row per key (or per version for SCD 2): changes are ordered by
`(version, commit time)` where the table has a `version` column, else by commit time; `Op = 'D'` deletes the row,
and for link tables (no `id`, keyed by the pair of foreign keys) it means the pair was removed.

If a bronze with this envelope already exists, set `bronze_mode: existing` and `bronze_source: <catalog>.<schema>`:
silver reads it directly and this bundle does not ingest the files again.

## The DA flow

| Step | Tables | Joins |
|---|---|---|
| Request and quotes | `request_case`, `request_for_quotation`, `quotation`, `quotation_expense` | `request_case_id`, `request_for_quotation_id`, `quotation_id` |
| Port call | `port_call`, `port_call_request_case` | `port_call_id` + `request_case_id` |
| Appointment | `appointment` (SCD 2), `appointment_recipient`, `appointment_agent_recipient`, `appointment_vendor_recipient` | `port_call_id`, `appointment_id`; subtypes share `appointment_recipient.id` |
| PDA | `proforma` (SCD 2), `proforma_expense` | `appointment_id`, `proforma_id`, `quotation_id`, `quotation_expense_id` |
| FDA | `evaluation` (SCD 2), `expense_evaluation` | `proforma_id`, `evaluation_id`; each final line points to its quoted line through `proforma_expense_id` |
| Verification | `evaluation_verification`, `expense_evaluation_verification` | `evaluation_id`, `expense_evaluation_id` |
| Documents | `proforma_attachments`, `proforma_statement_of_facts`, `expense_evaluation_attachments` | `file_item_id` + the owning id |

The other 49 child tables (activities, comment history, claims, commissions, notes, inspections, signatures,
husbandry parameter options) are in `tables.py` with their keys, so they reach silver as soon as DMS lands them.

## Neutral names

Columns that carry a vendor or company name in the source are renamed in silver with the `column_renames`
bundle variable, so gold, the metric views and the agents only see neutral names:

```yaml
column_renames: '{"expense_evaluation": {"<source platform-fee column>": "is_platform_fee"}}'
```

## Assumed lookups (to confirm)

The DA tables reference tables outside the DA families. Until their columns are confirmed, the mock data and
the gold SQL assume:

| Table | Assumed columns | Used for |
|---|---|---|
| `vessel` | id, imo, name, vessel_type, gross_tonnage, dwt, flag | Vessel type and size band of benchmarks |
| `port` | id, unlocode, name, country, region, default_currency | Port and region dimensions |
| `buyer` | id, name, company_type, country | Buyer dimension |
| `supplier` | id, name, company_type, country, port_id | Agent name |
| `expense_category` | id, name, section, description | Expense vocabulary for the document pipeline |
| `bank_account` | id, supplier_id, bank_name, iban, account_number, swift, currency | Bank detail checks |
| `file_item` | id, s3_key, file_name, content_type, size_bytes, creation_date | Link from documents to DAs |

## Documents bucket

`proforma/<proforma_id>/<file_item_id>.pdf`, the key stored in `file_item.s3_key`. PDA quotes, final DA packs
(summary page, then one supplier invoice per line) and statements of facts all sit under their proforma; the
document pipeline classifies which is which.
