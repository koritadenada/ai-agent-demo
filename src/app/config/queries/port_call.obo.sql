-- One port call: vessel, port, agent, schedule and amounts.
-- @param gold STRING = korita_catalog.portcall_gold
-- @param port_call_id BIGINT = 20400
SELECT port_call_id, proforma_id, evaluation_id, vessel_name, imo, vessel_type, gross_tonnage, port_name, agent_name,
       buyer_name, currency, CAST(schedule_date_in AS STRING) AS schedule_date_in,
       CAST(schedule_date_out AS STRING) AS schedule_date_out, ROUND(port_stay_hours, 1) AS port_stay_hours,
       ROUND(quoted_amount, 2) AS quoted_amount, ROUND(final_amount, 2) AS final_amount,
       ROUND(fda_approval_hours, 1) AS fda_approval_hours, CAST(call_month AS STRING) AS call_month
FROM IDENTIFIER(:gold || '.port_call_costs') WHERE port_call_id = :port_call_id
