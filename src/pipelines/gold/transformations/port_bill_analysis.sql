-- One row per final DA: the reconciliation in the shape {analysis_status, amount_checks[{expense, verdict, pages,
-- explanation}]}. ABORTED_NO_ROE when a line in another currency has no rate of exchange on the document or the platform.
CREATE OR REFRESH MATERIALIZED VIEW port_bill_analysis
COMMENT 'Per final DA (evaluation): analysis status and every amount check with verdict, cited pages and explanation'
AS
SELECT
  evaluation_id, proforma_id, port_call_id, port_name, agent_name, buyer_name, call_month, currency,
  CASE
    WHEN MAX(CASE WHEN analysis_status = 'NO_ROE' THEN 1 ELSE 0 END) = 1 THEN 'ABORTED_NO_ROE'
    WHEN BOOL_AND(NOT has_documents) THEN 'NO_DOCUMENTS'
    ELSE 'COMPLETE'
  END AS analysis_status,
  COUNT(*) AS lines_checked,
  COUNT(*) FILTER (WHERE verdict <> 'MATCH') AS lines_flagged,
  ARRAY_SORT(COLLECT_LIST(NAMED_STRUCT(
    'expense_name', line_name, 'expense_category', expense_category, 'verdict', verdict,
    'pages', evidence_pages, 'explanation', explanation))) AS amount_checks
FROM expense_reconciliation
GROUP BY ALL;
