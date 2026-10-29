-- One row per port call: the current PDA (proforma) and FDA (evaluation), quoted vs final in DA currency and EUR.
-- Final lines exclude deleted, inactive, merged and platform-fee lines; the platform fee is reported separately.
CREATE OR REFRESH MATERIALIZED VIEW port_call_costs
COMMENT 'One row per port call: vessel, port, buyer, appointed agent, quoted (PDA) vs final (FDA) cost in DA currency and EUR, workflow dates'
CLUSTER BY AUTO
AS
WITH pda AS (
  SELECT * FROM ${catalog}.${silver_schema}.proforma
  WHERE __END_AT IS NULL AND type = 'PDA'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY port_call_id ORDER BY revision DESC, id DESC) = 1
),
fda AS (
  SELECT * FROM ${catalog}.${silver_schema}.evaluation
  WHERE __END_AT IS NULL AND deletion_date IS NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY proforma_id ORDER BY creation_date DESC, id DESC) = 1
),
quoted AS (
  SELECT proforma_id, SUM(full_amount) AS amount, COUNT(*) AS lines
  FROM ${catalog}.${silver_schema}.proforma_expense WHERE NOT COALESCE(deleted, FALSE) GROUP BY ALL
),
final AS (
  SELECT evaluation_id,
         SUM(price_amount + COALESCE(price_surcharges, 0) - COALESCE(price_discount, 0)) FILTER (WHERE NOT COALESCE(is_platform_fee, FALSE)) AS amount,
         SUM(price_amount) FILTER (WHERE COALESCE(is_platform_fee, FALSE)) AS platform_fee,
         COUNT(*) FILTER (WHERE NOT COALESCE(is_platform_fee, FALSE)) AS lines
  FROM ${catalog}.${silver_schema}.expense_evaluation
  WHERE COALESCE(is_active, TRUE) AND deleted_on IS NULL AND merged_into_id IS NULL
  GROUP BY ALL
),
agent AS (
  SELECT r.appointment_id, s.id AS supplier_id, s.name AS agent_name
  FROM ${catalog}.${silver_schema}.appointment_recipient r
  JOIN ${catalog}.${silver_schema}.supplier s ON s.id = r.supplier_id
  WHERE r.company_type = 'AGENT'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY r.appointment_id ORDER BY r.id) = 1
)
SELECT
  pc.id AS port_call_id, a.id AS appointment_id, pda.id AS proforma_id, fda.id AS evaluation_id,
  prc.request_case_id,
  v.name AS vessel_name, v.imo, v.vessel_type, v.gross_tonnage,
  CASE WHEN v.gross_tonnage < 10000 THEN '<10k GT' WHEN v.gross_tonnage < 25000 THEN '10-25k GT'
       WHEN v.gross_tonnage < 50000 THEN '25-50k GT' WHEN v.gross_tonnage < 100000 THEN '50-100k GT'
       ELSE '>100k GT' END                                              AS size_band,
  p.name AS port_name, p.unlocode, p.country, p.region,
  b.name AS buyer_name, agent.supplier_id AS agent_id, agent.agent_name,
  pc.state AS port_call_state, a.state AS appointment_state, a.cancellation_reason,
  pc.schedule_date_in, pc.schedule_date_out, DATE_TRUNC('MONTH', pc.schedule_date_in)::DATE AS call_month,
  ROUND((unix_timestamp(pc.schedule_date_out) - unix_timestamp(pc.schedule_date_in)) / 3600, 1) AS port_stay_hours,
  COALESCE(fda.currency, pda.currency) AS currency, COALESCE(fda.rate_eur, pda.rate_eur) AS rate_eur,
  pda.state AS proforma_state, fda.state AS evaluation_state, fda.bank_account_id,
  quoted.amount AS quoted_amount, final.amount AS final_amount,
  ROUND(quoted.amount * pda.rate_eur, 2)                                AS quoted_amount_eur,
  ROUND(final.amount * fda.rate_eur, 2)                                 AS final_amount_eur,
  ROUND(final.platform_fee * fda.rate_eur, 2)                           AS platform_fee_eur,
  ROUND(final.amount - quoted.amount, 2)                                AS variance_amount,
  ROUND((final.amount - quoted.amount) / NULLIF(quoted.amount, 0) * 100, 2) AS variance_pct,
  a.creation_date AS appointment_created_at, pda.submission_date AS pda_submitted_at,
  fda.creation_date AS fda_created_at, fda.approval_date AS fda_approved_at,
  ROUND((unix_timestamp(fda.approval_date) - unix_timestamp(fda.creation_date)) / 3600, 1) AS fda_approval_hours,
  final.lines AS fda_lines
FROM ${catalog}.${silver_schema}.port_call pc
LEFT JOIN (SELECT port_call_id, MIN(request_case_id) AS request_case_id
           FROM ${catalog}.${silver_schema}.port_call_request_case GROUP BY ALL) prc ON prc.port_call_id = pc.id
JOIN ${catalog}.${silver_schema}.vessel v ON v.id = pc.vessel_id
JOIN ${catalog}.${silver_schema}.port p ON p.id = pc.port_id
LEFT JOIN ${catalog}.${silver_schema}.buyer b ON b.id = pc.buyer_id
LEFT JOIN ${catalog}.${silver_schema}.appointment a ON a.port_call_id = pc.id AND a.__END_AT IS NULL
LEFT JOIN agent ON agent.appointment_id = a.id
LEFT JOIN pda ON pda.port_call_id = pc.id
LEFT JOIN fda ON fda.proforma_id = pda.id
LEFT JOIN quoted ON quoted.proforma_id = pda.id
LEFT JOIN final ON final.evaluation_id = fda.id;
