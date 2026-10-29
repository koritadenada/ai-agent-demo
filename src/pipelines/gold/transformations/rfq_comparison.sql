-- Per request case and expense category: every agent's quoted amount vs the one the buyer accepted (EUR).
CREATE OR REFRESH MATERIALIZED VIEW rfq_comparison
COMMENT 'Quotations compared per request case and expense category: accepted vs lowest and highest quote, in EUR'
AS
WITH quotes AS (
  SELECT q.request_case_id, q.id AS quotation_id, q.quoter_id, q.state AS quotation_state, cat.name AS expense_category,
         SUM(qe.amount) AS amount
  FROM ${catalog}.${silver_schema}.quotation q
  JOIN ${catalog}.${silver_schema}.quotation_expense qe ON qe.quotation_id = q.id
  LEFT JOIN ${catalog}.${silver_schema}.expense_category cat ON cat.id = qe.category_id
  WHERE NOT COALESCE(qe.is_excluded, FALSE)
  GROUP BY ALL
)
SELECT
  rc.id AS request_case_id, p.name AS port_name, p.region, v.vessel_type,
  CASE WHEN v.gross_tonnage < 10000 THEN '<10k GT' WHEN v.gross_tonnage < 25000 THEN '10-25k GT'
       WHEN v.gross_tonnage < 50000 THEN '25-50k GT' WHEN v.gross_tonnage < 100000 THEN '50-100k GT'
       ELSE '>100k GT' END AS size_band,
  b.name AS buyer_name, DATE_TRUNC('MONTH', rc.date_in)::DATE AS call_month, q.expense_category,
  COUNT(*)                                                                  AS quotes_received,
  ROUND(MAX(q.amount * rc.rate) FILTER (WHERE q.quotation_state = 'ACCEPTED'), 2) AS accepted_amount_eur,
  ROUND(MIN(q.amount * rc.rate), 2)                                         AS lowest_amount_eur,
  ROUND(MAX(q.amount * rc.rate), 2)                                         AS highest_amount_eur
FROM quotes q
JOIN ${catalog}.${silver_schema}.request_case rc ON rc.id = q.request_case_id
JOIN ${catalog}.${silver_schema}.port p ON p.id = rc.port_id
JOIN ${catalog}.${silver_schema}.vessel v ON v.id = rc.vessel_id
LEFT JOIN ${catalog}.${silver_schema}.buyer b ON b.id = rc.buyer_id
GROUP BY ALL;
