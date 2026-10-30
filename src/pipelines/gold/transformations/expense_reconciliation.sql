-- One row per final line (expense_evaluation): its quoted line (proforma_expense_id), what its supporting invoice pages
-- say, the benchmark, a deterministic verdict with an explanation that cites the pages, and the DA analyst's verdict.
-- Rules, in order: currency mismatch (always flagged, converted only with a rate from the document, else the
-- platform, else the analysis stops for that line: no rate is ever invented), no evidence, invoice vs final beyond the
-- cent tolerance, over or under the quote beyond the tolerance, else match. An expense invoiced in parts (pilotage in
-- and out) has several pages mapped to the same line: they are summed. Thresholds come from the pipeline configuration.
CREATE OR REFRESH MATERIALIZED VIEW expense_reconciliation
COMMENT 'Per final line: quoted, final and invoiced amounts, cited invoice pages, rate of exchange used, benchmark, verdict with explanation, and the analyst verdict'
CLUSTER BY AUTO
AS
WITH lines AS (
  SELECT e.id AS expense_evaluation_id, e.evaluation_id, e.proforma_id, e.proforma_expense_id, e.name AS line_name,
         cat.name AS expense_category, cat.section AS expense_section,
         pe.full_amount AS quoted_amount,
         e.price_amount + COALESCE(e.price_surcharges, 0) - COALESCE(e.price_discount, 0) AS final_amount,
         e.price_currency
  FROM ${catalog}.${silver_schema}.expense_evaluation e
  LEFT JOIN ${catalog}.${silver_schema}.proforma_expense pe ON pe.id = e.proforma_expense_id
  LEFT JOIN ${catalog}.${silver_schema}.expense_category cat ON cat.id = e.category_id
  WHERE NOT COALESCE(e.is_platform_fee, FALSE) AND COALESCE(e.is_active, TRUE) AND e.deleted_on IS NULL AND e.merged_into_id IS NULL
),
packs AS (   -- final DA packs received and parsed, per proforma
  SELECT DISTINCT proforma_id FROM ${catalog}.${silver_schema}.documents WHERE doc_type = 'final_da_pack'
),
category_lines AS (   -- for the fallback below: lines per DA and category
  SELECT proforma_id, expense_category, MIN(expense_evaluation_id) AS only_line_id, COUNT(*) AS lines_in_category
  FROM lines GROUP BY ALL
),
evidence AS (   -- all pages mapped to the same DA line, summed (an expense invoiced in parts). When the model's line id
                -- was not one of the DA's lines, the page still counts if its category has exactly one line in that DA
  SELECT COALESCE(li.expense_evaluation_id, IF(cl.lines_in_category = 1, cl.only_line_id, NULL)) AS expense_evaluation_id,
         SUM(li.amount) AS invoiced_amount, MIN(li.currency) AS invoiced_currency,
         ARRAY_SORT(COLLECT_LIST(li.page_number)) AS evidence_pages, MIN(li.confidence) AS evidence_confidence,
         FIRST(li.file_item_id) AS file_item_id,
         IF(BOOL_AND(li.expense_evaluation_id IS NOT NULL), 'model', 'category fallback') AS line_match
  FROM ${catalog}.${silver_schema}.doc_line_items li
  LEFT JOIN category_lines cl ON cl.proforma_id = li.proforma_id AND cl.expense_category = li.expense_category
  GROUP BY 1
  HAVING expense_evaluation_id IS NOT NULL
),
printed_rate AS (   -- rate of exchange printed on the summary page: other-currency units per one document unit
  SELECT proforma_id, currency AS document_currency, exchange_currency, rate_of_exchange
  FROM ${catalog}.${silver_schema}.doc_bank_details
  WHERE rate_of_exchange > 0
  QUALIFY ROW_NUMBER() OVER (PARTITION BY proforma_id ORDER BY page_number) = 1
),
platform_rate AS (   -- the platform's own EUR rate per currency
  SELECT currency, AVG(rate_eur) AS rate_eur
  FROM ${catalog}.${silver_schema}.evaluation WHERE __END_AT IS NULL AND rate_eur > 0 GROUP BY ALL
),
bench AS (
  SELECT * FROM expense_benchmarks WHERE sample_size >= ${min_benchmark_sample}
),
analyst AS (
  SELECT expense_evaluation_id, discrepancy_type, discrepancy_amount
  FROM ${catalog}.${silver_schema}.expense_evaluation_verification
  QUALIFY ROW_NUMBER() OVER (PARTITION BY expense_evaluation_id ORDER BY version DESC, id DESC) = 1
),
linked AS (   -- the platform's own link between a final line and its supporting file
  SELECT DISTINCT expense_evaluation_id FROM ${catalog}.${silver_schema}.expense_evaluation_attachments
),
joined AS (
  SELECT c.port_call_id, c.port_name, c.unlocode, c.country, c.region, c.vessel_name, c.vessel_type, c.size_band,
         c.buyer_name, c.agent_name, c.call_month, c.rate_eur,
         l.*, packs.proforma_id IS NOT NULL AS has_documents, linked.expense_evaluation_id IS NOT NULL AS has_linked_attachment,
         ev.invoiced_amount, ev.invoiced_currency, ev.evidence_pages, ev.evidence_confidence, ev.file_item_id, ev.line_match,
         CASE
           WHEN ev.invoiced_currency IS NULL OR ev.invoiced_currency = l.price_currency THEN 1
           WHEN pr.document_currency = l.price_currency AND pr.exchange_currency = ev.invoiced_currency THEN 1 / pr.rate_of_exchange
           WHEN fx_inv.rate_eur IS NOT NULL AND fx_da.rate_eur IS NOT NULL THEN fx_inv.rate_eur / fx_da.rate_eur
         END AS to_da_currency,
         CASE
           WHEN ev.invoiced_currency IS NULL OR ev.invoiced_currency = l.price_currency THEN 'not needed'
           WHEN pr.document_currency = l.price_currency AND pr.exchange_currency = ev.invoiced_currency THEN 'document'
           WHEN fx_inv.rate_eur IS NOT NULL AND fx_da.rate_eur IS NOT NULL THEN 'platform'
         END AS roe_source,
         COALESCE(b1.median_eur, b2.median_eur, b3.median_eur) AS benchmark_median_eur,
         CASE WHEN b1.median_eur IS NOT NULL THEN 'exact' WHEN b2.median_eur IS NOT NULL THEN 'region'
              WHEN b3.median_eur IS NOT NULL THEN 'port' END AS benchmark_level,
         COALESCE(b1.sample_size, b2.sample_size, b3.sample_size) AS benchmark_sample_size,
         bp.region_min_median_eur, bp.local_port_min_eur,
         an.discrepancy_type AS analyst_discrepancy_type, an.discrepancy_amount AS analyst_discrepancy_amount
  FROM lines l
  JOIN port_call_costs c ON c.evaluation_id = l.evaluation_id
  LEFT JOIN packs ON packs.proforma_id = l.proforma_id
  LEFT JOIN evidence ev ON ev.expense_evaluation_id = l.expense_evaluation_id
  LEFT JOIN linked ON linked.expense_evaluation_id = l.expense_evaluation_id
  LEFT JOIN printed_rate pr ON pr.proforma_id = l.proforma_id
  LEFT JOIN platform_rate fx_inv ON fx_inv.currency = ev.invoiced_currency
  LEFT JOIN platform_rate fx_da ON fx_da.currency = l.price_currency
  LEFT JOIN bench b1 ON b1.benchmark_level = 'exact' AND b1.port_name = c.port_name AND b1.vessel_type = c.vessel_type
       AND b1.size_band = c.size_band AND b1.expense_category = l.expense_category
  LEFT JOIN bench b2 ON b2.benchmark_level = 'region' AND b2.region = c.region AND b2.vessel_type = c.vessel_type
       AND b2.size_band = c.size_band AND b2.expense_category = l.expense_category
  LEFT JOIN bench b3 ON b3.benchmark_level = 'port' AND b3.port_name = c.port_name AND b3.expense_category = l.expense_category
  LEFT JOIN expense_benchmarks bp ON bp.benchmark_level = 'port' AND bp.port_name = c.port_name
       AND bp.expense_category = l.expense_category
  LEFT JOIN analyst an ON an.expense_evaluation_id = l.expense_evaluation_id
),
scored AS (
  SELECT *,
         ROUND(invoiced_amount * to_da_currency, 2)                                    AS invoiced_in_da_currency,
         ROUND((final_amount - quoted_amount) / NULLIF(quoted_amount, 0) * 100, 2)     AS variance_vs_quote_pct,
         ARRAY_JOIN(TRANSFORM(evidence_pages, p -> CAST(p AS STRING)), ', ')            AS pages_text,
         CASE
           WHEN invoiced_currency IS NOT NULL AND invoiced_currency <> price_currency  THEN 'CURRENCY_MISMATCH'
           WHEN has_documents AND invoiced_amount IS NULL                            THEN 'NO_EVIDENCE'
           WHEN ABS(invoiced_amount - final_amount) > 0.01                           THEN 'INVOICE_MISMATCH'
           WHEN final_amount > quoted_amount * (1 + ${match_tolerance_pct} / 100)     THEN 'OVER_QUOTE'
           WHEN final_amount < quoted_amount * (1 - ${match_tolerance_pct} / 100)     THEN 'UNDER_QUOTE'
           ELSE 'MATCH'
         END AS verdict,
         CASE analyst_discrepancy_type
           WHEN 'NONE' THEN 'MATCH' WHEN 'OVERCHARGE' THEN 'OVER_QUOTE' WHEN 'UNDERCHARGE' THEN 'UNDER_QUOTE'
           WHEN 'AMOUNT_MISMATCH' THEN 'INVOICE_MISMATCH' WHEN 'MISSING_SUPPORTING_DOCUMENT' THEN 'NO_EVIDENCE'
           WHEN 'CURRENCY_MISMATCH' THEN 'CURRENCY_MISMATCH'
         END AS analyst_verdict
  FROM joined
)
SELECT
  expense_evaluation_id, evaluation_id, proforma_id, proforma_expense_id, port_call_id, file_item_id,
  port_name, unlocode, country, region, vessel_name, vessel_type, size_band, buyer_name, agent_name, call_month,
  expense_category, expense_section, line_name, price_currency AS currency,
  quoted_amount, final_amount, invoiced_amount, invoiced_currency, invoiced_in_da_currency, roe_source,
  ROUND(quoted_amount * rate_eur, 2) AS quoted_amount_eur,
  ROUND(final_amount * rate_eur, 2)  AS final_amount_eur,
  ROUND(final_amount - quoted_amount, 2) AS variance_vs_quote, variance_vs_quote_pct,
  has_documents, has_linked_attachment, evidence_pages, evidence_confidence, line_match, verdict,
  CASE
    WHEN NOT has_documents THEN 'NO_DOCUMENTS'
    WHEN verdict = 'CURRENCY_MISMATCH' AND roe_source IS NULL THEN 'NO_ROE'
    ELSE 'COMPLETE'
  END AS analysis_status,
  CASE verdict
    WHEN 'CURRENCY_MISMATCH' THEN FORMAT_STRING('Invoiced %s %s on page %s but the DA is in %s; %s',
      FORMAT_NUMBER(invoiced_amount, 2), invoiced_currency, pages_text, price_currency,
      CASE WHEN roe_source IS NULL THEN 'no rate of exchange on the document or the platform, analysis stopped'
           ELSE FORMAT_STRING('at the %s rate that is %s %s against a final %s', roe_source,
                              FORMAT_NUMBER(invoiced_in_da_currency, 2), price_currency, FORMAT_NUMBER(final_amount, 2)) END)
    WHEN 'NO_EVIDENCE' THEN FORMAT_STRING('No supporting invoice page for %s in the final DA pack', line_name)
    WHEN 'INVOICE_MISMATCH' THEN FORMAT_STRING('Invoice page %s shows %s %s, the final line says %s', pages_text,
      FORMAT_NUMBER(invoiced_amount, 2), invoiced_currency, FORMAT_NUMBER(final_amount, 2))
    ELSE FORMAT_STRING('Final %s %s vs quote %s (%+.1f%%)%s', FORMAT_NUMBER(final_amount, 2), price_currency,
      FORMAT_NUMBER(quoted_amount, 2), CAST(variance_vs_quote_pct AS DOUBLE),
      CASE WHEN pages_text <> '' THEN FORMAT_STRING('; invoice page %s shows %s', pages_text, FORMAT_NUMBER(invoiced_amount, 2))
           ELSE '' END)
  END AS explanation,
  CASE
    WHEN verdict IN ('CURRENCY_MISMATCH', 'NO_EVIDENCE', 'INVOICE_MISMATCH') THEN 'review'
    WHEN verdict = 'OVER_QUOTE' AND variance_vs_quote_pct > ${dispute_threshold_pct} THEN 'dispute'
    WHEN verdict = 'OVER_QUOTE' THEN 'review'
    ELSE 'accept'
  END AS review_action,
  CASE WHEN verdict = 'OVER_QUOTE' THEN ROUND((final_amount - quoted_amount) * rate_eur, 2) ELSE 0 END
    AS over_invoiced_amount_eur,
  analyst_discrepancy_type, analyst_verdict, analyst_discrepancy_amount,
  CASE WHEN analyst_verdict IS NOT NULL THEN verdict = analyst_verdict END AS agrees_with_analyst,
  benchmark_median_eur, benchmark_level, benchmark_sample_size, region_min_median_eur, local_port_min_eur,
  ROUND((final_amount * rate_eur / NULLIF(benchmark_median_eur, 0) - 1) * 100, 2) AS benchmark_gap_pct,
  ROUND(GREATEST(final_amount * rate_eur - benchmark_median_eur, 0), 2) AS potential_saving_eur
FROM scored;
