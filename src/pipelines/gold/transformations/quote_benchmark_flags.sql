-- One row per quoted line of the current PDA: the quote against past final costs, with a deterministic rule cascade
-- (exact port, vessel type and size; then nearby ports in the region, same vessel type and size; then the port with
-- any vessel), the regional minimum and the
-- local port minimum. Flagged when the quote is above the benchmark median by more than ${quote_flag_pct} percent.
-- This is the input of the quote advisor agent; the negotiation email itself is the agent's job, not the pipeline's.
CREATE OR REFRESH MATERIALIZED VIEW quote_benchmark_flags
COMMENT 'Per quoted PDA line: benchmark median (exact, port or region level), regional and local port minimum, flag and reasoning'
AS
WITH quoted AS (
  SELECT c.port_call_id, c.proforma_id, c.port_name, c.region, c.country, c.vessel_type, c.size_band, c.agent_name,
         c.buyer_name, c.call_month, c.proforma_state, pe.id AS proforma_expense_id, pe.name AS expense_name,
         cat.name AS expense_category, pe.price_currency AS currency, pe.full_amount AS quoted_amount,
         ROUND(pe.full_amount * c.rate_eur, 2) AS quoted_amount_eur
  FROM port_call_costs c
  JOIN ${catalog}.${silver_schema}.proforma_expense pe ON pe.proforma_id = c.proforma_id
  LEFT JOIN ${catalog}.${silver_schema}.expense_category cat ON cat.id = pe.category_id
  WHERE NOT COALESCE(pe.deleted, FALSE)
),
bench AS (SELECT * FROM expense_benchmarks WHERE sample_size >= ${min_benchmark_sample}),
matched AS (
  SELECT q.*,
         COALESCE(b1.median_eur, b2.median_eur, b3.median_eur) AS benchmark_median_eur,
         CASE WHEN b1.median_eur IS NOT NULL THEN 'exact' WHEN b2.median_eur IS NOT NULL THEN 'region'
              WHEN b3.median_eur IS NOT NULL THEN 'port' END AS benchmark_level,
         COALESCE(b1.sample_size, b2.sample_size, b3.sample_size) AS benchmark_sample_size,
         bp.region_min_median_eur, bp.local_port_min_eur
  FROM quoted q
  LEFT JOIN bench b1 ON b1.benchmark_level = 'exact' AND b1.port_name = q.port_name AND b1.vessel_type = q.vessel_type
       AND b1.size_band = q.size_band AND b1.expense_category = q.expense_category
  LEFT JOIN bench b2 ON b2.benchmark_level = 'region' AND b2.region = q.region AND b2.vessel_type = q.vessel_type
       AND b2.size_band = q.size_band AND b2.expense_category = q.expense_category
  LEFT JOIN bench b3 ON b3.benchmark_level = 'port' AND b3.port_name = q.port_name AND b3.expense_category = q.expense_category
  LEFT JOIN expense_benchmarks bp ON bp.benchmark_level = 'port' AND bp.port_name = q.port_name
       AND bp.expense_category = q.expense_category
)
SELECT *,
       ROUND((quoted_amount_eur / NULLIF(benchmark_median_eur, 0) - 1) * 100, 1) AS gap_to_benchmark_pct,
       quoted_amount_eur > benchmark_median_eur * (1 + ${quote_flag_pct} / 100) AS flagged,
       ROUND(GREATEST(quoted_amount_eur - benchmark_median_eur, 0), 2) AS potential_saving_eur,
       CASE WHEN benchmark_median_eur IS NULL THEN 'Not enough history for this port and expense'
            ELSE FORMAT_STRING('Quoted %s EUR is %+.1f%% against the %s median of %s EUR (%d past calls); regional minimum %s EUR, lowest at this port %s EUR',
                               FORMAT_NUMBER(quoted_amount_eur, 2), CAST((quoted_amount_eur / benchmark_median_eur - 1) * 100 AS DOUBLE),
                               benchmark_level, FORMAT_NUMBER(benchmark_median_eur, 2), benchmark_sample_size,
                               FORMAT_NUMBER(region_min_median_eur, 2), FORMAT_NUMBER(local_port_min_eur, 2))
       END AS reasoning
FROM matched;
