# Costs

What the pipelines cost, what drives it, and what is built in to keep it low. Numbers are from the demo
(mock data: 420 port calls, 72 PDFs, about 280 pages), read from `system.billing.usage` at list price.

## Measured on the demo

| Item | DBU | List price | Notes |
|---|---|---|---|
| Platform pipeline, per update | about 0.3 | about 0.16 USD | 25 tables, serverless |
| Documents pipeline, per update | about 0.4 | about 0.20 USD | pipeline compute only |
| Gold pipeline, per update | about 0.2 | about 0.10 USD | 7 materialized views |
| AI Functions and model calls, per page | | about 0.006 USD | paid once per page, when the PDF lands |

Two consequences:

- **The schedule is the biggest lever.** One refresh of the three pipelines is about 0.9 DBU even when little has
  changed. Hourly, every day of the month, that is roughly 650 DBU a month; daily, about 30. Match the
  schedule to the freshness each table really needs.
- **The AI cost scales with documents, not with time.** Each page is parsed, mapped and read once and the result
  is stored, so re-reading it costs nothing. At about 0.006 USD a page, 10,000 pages a month is about 60 USD.

Real volumes are larger than the demo: the platform pipeline only processes new DMS files on each update, so its
cost grows with the change rate, not with the size of the database.

These are the full amounts Databricks billed (AI Functions and model serving in `system.billing.usage`, at list
price): there is no separate markup to add, and contract discounts apply on top. Per function, on the demo:

| Function | Used for | Share of AI spend |
|---|---|---|
| `ai_parse_document` | Text of every page | 47% |
| `ai_extract` | Amount on each invoice page, bank details on the summary page (since then, invoice amounts come from the page map call) | 44% |
| `ai_query` (`databricks-gpt-5-mini`) | Page to expense map, statement of facts timeline | 7% |
| `ai_classify` | Document type, first page only | 2% |

Parsing and extraction dominate; the model choice for `ai_query` matters least.

## Built in

| Where | What | Why |
|---|---|---|
| Jobs | `performance_target: STANDARD` | Standard mode uses fewer DBUs for a few minutes of extra start-up; right for hourly or daily batch |
| Refresh job | Pipelines only; UC functions and metric views run in the `setup` job after a deploy | No serverless tasks re-creating objects every hour |
| Refresh job | Schedule is a variable (`refresh_cron`) | Hourly matches today's freshness; daily is enough for most dashboards |
| All pipelines | Serverless, triggered, incremental (Auto Loader, AUTO CDC, streaming tables) | Only new files and changes are processed on each update |
| Platform pipeline | A table gets bronze and silver only when its DMS folder exists | The full table list costs nothing until DMS lands it |
| Silver and AI tables | `delta.enableRowTracking` | Lets the gold materialized views refresh incrementally instead of recomputing |
| Bronze and AI tables | `pipelines.reset.allowed` from `allow_reset` (false in prod) | A full refresh cannot re-run every LLM call or drop the DMS change log |
| Documents | No bronze copy of the PDFs: Auto Loader reads the bucket directly | The PDFs are not stored twice and streams do not move their bytes |
| `ai_parse_document` | Figure descriptions off | No generated text that nothing uses |
| `ai_classify` | First page only | One cheap call per document to decide which branch runs |
| Page map and extraction | Final DA packs only; one call per page that also reads the invoice amount (no second `ai_extract` pass, about 40% of AI spend); bank details from the summary page only | Proformas need no LLM: their amounts are already in `proforma_expense` |
| Gold rules | Plain SQL and UC functions | No model calls in the checks or in the metric views |
| Everything | `tags` (`project`, `layer` / `workload`) | Labels every job and pipeline; for billing attribution of serverless spend use a budget policy |

## Next levers, when needed

- **Split the schedule by freshness**: the few near real time tables in a separate continuous or 5-minute
  pipeline, everything else daily.
- **Trigger on data, not on the clock**: a file-arrival trigger on the documents location runs the document
  pipeline only when PDFs land (nights and weekends cost nothing).
- **A smaller model** for `ai_query` (`llm_endpoint`): small saving, same acceptance check.
- **A budget policy** (`budget_policy_id` on jobs and pipelines) to cap and alert on serverless spend.

## Watch it

Daily cost of this project's pipelines and jobs, with AI Functions split by function:

```sql
WITH p AS (SELECT pipeline_id FROM system.lakeflow.pipelines WHERE name LIKE '%portcall-%'
           QUALIFY ROW_NUMBER() OVER (PARTITION BY pipeline_id ORDER BY change_time DESC) = 1),
     j AS (SELECT job_id FROM system.lakeflow.jobs WHERE name LIKE '%portcall-%'
           QUALIFY ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY change_time DESC) = 1)
SELECT u.usage_date, u.billing_origin_product,
       COALESCE(CAST(u.product_features.ai_functions.ai_function AS STRING), '') AS ai_function,
       ROUND(SUM(u.usage_quantity), 2) AS dbu,
       ROUND(SUM(u.usage_quantity * lp.pricing.effective_list.default), 2) AS usd_list
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices lp ON lp.sku_name = u.sku_name AND u.usage_start_time >= lp.price_start_time
     AND (lp.price_end_time IS NULL OR u.usage_start_time < lp.price_end_time)
WHERE u.usage_date >= current_date() - INTERVAL 30 DAYS
  AND (u.usage_metadata.dlt_pipeline_id IN (SELECT pipeline_id FROM p) OR u.usage_metadata.job_id IN (SELECT job_id FROM j))
GROUP BY ALL
ORDER BY usage_date DESC, usd_list DESC
```
