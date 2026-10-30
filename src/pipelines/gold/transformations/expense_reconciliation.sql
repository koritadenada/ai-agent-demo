-- One row per final line (expense_evaluation): its quoted line (proforma_expense_id), what the supporting invoice page
-- says, the benchmark, a deterministic verdict, and what the DA analyst concluded (expense_evaluation_verification).
-- Same input, same verdict; thresholds come from the pipeline configuration.
CREATE OR REFRESH MATERIALIZED VIEW expense_reconciliation
COMMENT 'Per final line: quoted, final and invoiced amounts, cited invoice pages, benchmark, automated verdict and the analyst verdict'
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
evidence AS (
  SELECT li.proforma_id, li.expense_category,
         SUM(li.amount) AS invoiced_amount, MIN(li.currency) AS invoiced_currency,
         SORT_ARRAY(COLLECT_SET(li.page_number)) AS evidence_pages, MIN(li.confidence) AS evidence_confidence,
         FIRST(li.file_item_id) AS file_item_id
  FROM ${catalog}.${silver_schema}.doc_line_items li
  GROUP BY ALL
),
linked AS (  -- the platform's own link between a final line and its supporting file
  SELECT DISTINCT expense_evaluation_id FROM ${catalog}.${silver_schema}.expense_evaluation_attachments
),
analyst AS (
  SELECT expense_evaluation_id, discrepancy_type, discrepancy_amount, verification_date
  FROM ${catalog}.${silver_schema}.expense_evaluation_verification
  QUALIFY ROW_NUMBER() OVER (PARTITION BY expense_evaluation_id ORDER BY version DESC, id DESC) = 1
),
joined AS (
  SELECT c.port_call_id, c.port_name, c.unlocode, c.country, c.region, c.vessel_name, c.vessel_type, c.size_band,
         c.buyer_name, c.agent_name, c.call_month, c.currency, c.rate_eur, c.evaluation_state,
         l.*, packs.proforma_id IS NOT NULL AS has_documents, linked.expense_evaluation_id IS NOT NULL AS has_linked_attachment,
         ev.invoiced_amount, ev.invoiced_currency, ev.evidence_pages, ev.evidence_confidence, ev.file_item_id,
         b.median_eur AS benchmark_median_eur, b.region_min_median_eur, b.sample_size AS benchmark_sample_size,
         an.discrepancy_type AS analyst_discrepancy_type, an.discrepancy_amount AS analyst_discrepancy_amount
  FROM lines l
  JOIN port_call_costs c ON c.evaluation_id = l.evaluation_id
  LEFT JOIN packs ON packs.proforma_id = l.proforma_id
  LEFT JOIN evidence ev ON ev.proforma_id = l.proforma_id AND ev.expense_category = l.expense_category
  LEFT JOIN linked ON linked.expense_evaluation_id = l.expense_evaluation_id
  LEFT JOIN expense_benchmarks b ON b.port_name = c.port_name AND b.vessel_type = c.vessel_type
       AND b.size_band = c.size_band AND b.expense_category = l.expense_category
  LEFT JOIN analyst an ON an.expense_evaluation_id = l.expense_evaluation_id
),
scored AS (
  SELECT *,
         ROUND((final_amount - quoted_amount) / NULLIF(quoted_amount, 0) * 100, 2) AS variance_vs_quote_pct,
         CASE
           WHEN invoiced_currency IS NOT NULL AND invoiced_currency <> price_currency     THEN 'CURRENCY_MISMATCH'
           WHEN has_documents AND invoiced_amount IS NULL                              THEN 'NO_EVIDENCE'
           WHEN ABS(invoiced_amount - final_amount) > 0.01                             THEN 'INVOICE_MISMATCH'
           WHEN final_amount > quoted_amount * (1 + ${match_tolerance_pct} / 100)       THEN 'OVER_QUOTE'
           WHEN final_amount < quoted_amount * (1 - ${match_tolerance_pct} / 100)       THEN 'UNDER_QUOTE'
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
  quoted_amount, final_amount, invoiced_amount, invoiced_currency,
  ROUND(quoted_amount * rate_eur, 2) AS quoted_amount_eur,
  ROUND(final_amount * rate_eur, 2)  AS final_amount_eur,
  ROUND(final_amount - quoted_amount, 2) AS variance_vs_quote, variance_vs_quote_pct,
  has_documents, has_linked_attachment, evidence_pages, evidence_confidence, verdict,
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
  benchmark_median_eur, region_min_median_eur, benchmark_sample_size,
  ROUND((final_amount * rate_eur / NULLIF(benchmark_median_eur, 0) - 1) * 100, 2) AS benchmark_gap_pct,
  ROUND(GREATEST(final_amount * rate_eur - benchmark_median_eur, 0), 2) AS potential_saving_eur
FROM scored;
