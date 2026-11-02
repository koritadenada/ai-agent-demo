-- The lines of one open quote against the benchmark.
-- @param gold STRING = korita_catalog.portcall_gold
-- @param proforma_id BIGINT = 50419
SELECT q.expense_name, q.quoted_amount_eur, ROUND(q.benchmark_median_eur, 2) AS benchmark_median_eur,
       q.benchmark_sample_size, ROUND(q.gap_to_benchmark_pct, 1) AS gap_to_benchmark_pct, q.flagged,
       ROUND(q.potential_saving_eur, 2) AS potential_saving_eur, q.reasoning,
       c.port_name, c.vessel_name, c.vessel_type, c.size_band, c.agent_name, c.buyer_name, CAST(c.call_month AS STRING) AS call_month
FROM IDENTIFIER(:gold || '.quote_benchmark_flags') q
JOIN IDENTIFIER(:gold || '.port_call_costs') c ON c.proforma_id = q.proforma_id
WHERE q.proforma_id = :proforma_id ORDER BY q.flagged DESC, q.potential_saving_eur DESC
