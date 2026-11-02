-- Open PDA quotes against the benchmark.
-- @param gold STRING = korita_catalog.portcall_gold
-- @param app STRING = korita_catalog.portcall_app
SELECT q.proforma_id, q.port_name, q.agent_name, q.buyer_name, q.vessel_type, q.size_band,
       CAST(q.call_month AS STRING) AS call_month, c.vessel_name, COUNT(*) AS lines,
       COUNT_IF(q.flagged) AS flagged_lines, ROUND(SUM(q.quoted_amount_eur), 2) AS quoted_eur,
       ROUND(SUM(q.potential_saving_eur) FILTER (WHERE q.flagged), 2) AS saving_eur,
       MAX(n.created_at) IS NOT NULL AS has_draft
FROM IDENTIFIER(:gold || '.quote_benchmark_flags') q
JOIN IDENTIFIER(:gold || '.port_call_costs') c ON c.proforma_id = q.proforma_id
LEFT JOIN IDENTIFIER(:app || '.negotiation_drafts') n ON n.proforma_id = q.proforma_id
WHERE q.proforma_state = 'SUBMITTED'
GROUP BY ALL ORDER BY flagged_lines DESC, saving_eur DESC NULLS LAST
