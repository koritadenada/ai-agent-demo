-- One row per port call: how the DA moved through the platform and how long each step took.
CREATE OR REFRESH MATERIALIZED VIEW da_workflow
COMMENT 'Per port call: appointment, PDA, FDA and verification states and the hours between steps'
AS
WITH sign_off AS (
  SELECT evaluation_id, MIN(creation_date) AS verification_started_at, MAX(verification_date) AS verified_at,
         MAX(sign_off_role) AS sign_off_role, MAX(department) AS department
  FROM ${catalog}.${silver_schema}.evaluation_verification GROUP BY ALL
),
rfq AS (
  SELECT request_case_id, COUNT(*) AS quotes_received, SUM(observer_pokes) AS quotation_reminders
  FROM ${catalog}.${silver_schema}.quotation GROUP BY ALL
)
SELECT
  c.port_call_id, c.port_name, c.region, c.buyer_name, c.agent_name, c.call_month,
  c.port_call_state, c.appointment_state, c.cancellation_reason, c.proforma_state, c.evaluation_state,
  rfq.quotes_received, rfq.quotation_reminders, s.sign_off_role, s.department,
  ROUND((unix_timestamp(c.pda_submitted_at) - unix_timestamp(c.appointment_created_at)) / 3600, 1) AS hours_appointment_to_pda,
  ROUND((unix_timestamp(c.fda_created_at) - unix_timestamp(c.schedule_date_out)) / 3600, 1)       AS hours_sailing_to_fda,
  c.fda_approval_hours,
  ROUND((unix_timestamp(s.verified_at) - unix_timestamp(s.verification_started_at)) / 3600, 1)     AS hours_to_verify
FROM port_call_costs c
LEFT JOIN rfq ON rfq.request_case_id = c.request_case_id
LEFT JOIN sign_off s ON s.evaluation_id = c.evaluation_id;
