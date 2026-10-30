-- One row per document: how well parsing, classification, page mapping and extraction went.
CREATE OR REFRESH MATERIALIZED VIEW document_quality
COMMENT 'Per document: classified type vs how the platform linked it, pages, parse errors, mapped pages and mean confidence of each AI step'
AS
WITH pages AS (
  SELECT file_item_id, COUNT(*) AS pages_mapped, AVG(confidence) AS mean_map_confidence,
         COUNT(*) FILTER (WHERE llm_error IS NOT NULL) AS llm_errors
  FROM ${catalog}.${silver_schema}.page_expense_map GROUP BY ALL
),
lines AS (   -- invoice pages with an amount read
  SELECT file_item_id, COUNT(*) AS lines_extracted, AVG(confidence) AS mean_extract_confidence
  FROM ${catalog}.${silver_schema}.page_expense_map WHERE page_role = 'supporting_invoice' AND amount IS NOT NULL
  GROUP BY ALL
),
sof AS (SELECT DISTINCT file_item_id FROM ${catalog}.${silver_schema}.proforma_statement_of_facts)
SELECT
  d.file_item_id, d.proforma_id, d.entity, d.doc_type,
  CASE WHEN sof.file_item_id IS NOT NULL THEN 'statement_of_facts' ELSE 'pda_or_fda' END AS platform_link,
  (sof.file_item_id IS NOT NULL) = (d.doc_type = 'statement_of_facts') AS type_matches_link,
  d.page_count, SIZE(d.parse_errors) AS pages_with_errors,
  COALESCE(p.pages_mapped, 0) AS pages_mapped, p.mean_map_confidence, COALESCE(p.llm_errors, 0) AS llm_errors,
  COALESCE(l.lines_extracted, 0) AS lines_extracted, l.mean_extract_confidence,
  b.bank_confidence, d.size_bytes, d.landed_at, d.processed_at,
  DATE_TRUNC('MONTH', d.landed_at)::DATE AS landed_month
FROM ${catalog}.${silver_schema}.documents d
LEFT JOIN sof USING (file_item_id)
LEFT JOIN pages p USING (file_item_id)
LEFT JOIN lines l USING (file_item_id)
LEFT JOIN ${catalog}.${silver_schema}.doc_bank_details b USING (file_item_id);
