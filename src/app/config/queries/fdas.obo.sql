-- Every checked final DA with its line check, payment check and the latest analyst decision.
-- @param gold STRING = korita_catalog.portcall_gold
-- @param app STRING = korita_catalog.portcall_app
SELECT b.evaluation_id, b.port_call_id, b.proforma_id, b.port_name, b.agent_name, b.buyer_name,
       CAST(b.call_month AS STRING) AS call_month, b.currency, b.lines_checked, b.lines_flagged, c.vessel_name,
       ROUND(c.final_amount, 2) AS final_amount, p.hold_payment, d.decision
FROM IDENTIFIER(:gold || '.port_bill_analysis') b
JOIN IDENTIFIER(:gold || '.port_call_costs') c ON c.evaluation_id = b.evaluation_id
LEFT JOIN IDENTIFIER(:gold || '.payment_validation') p ON p.evaluation_id = b.evaluation_id
LEFT JOIN (SELECT * FROM IDENTIFIER(:app || '.analyst_decisions') QUALIFY ROW_NUMBER() OVER (PARTITION BY evaluation_id ORDER BY decided_at DESC) = 1) d ON d.evaluation_id = b.evaluation_id
WHERE b.analysis_status <> 'NO_DOCUMENTS'
ORDER BY d.decision IS NOT NULL, p.hold_payment DESC, b.lines_flagged DESC, b.port_call_id DESC
