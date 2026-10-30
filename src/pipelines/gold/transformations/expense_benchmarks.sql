-- Benchmarks from final-line history (EUR), at three levels for a deterministic rule cascade:
--   exact   same port, vessel type and size band
--   region  nearby ports: same region, vessel type and size band
--   port    same port, any vessel (last: most port costs scale with the ship's size)
-- Consumers take the first level with at least ${min_benchmark_sample} lines. Also the regional minimum (lowest port
-- median in the region) and the local port minimum. Lines excluded from historical data and platform fees are left out.
CREATE OR REFRESH MATERIALIZED VIEW expense_benchmarks
COMMENT 'Final-cost benchmarks in EUR per expense category at three levels (exact, port, region), with regional and local port minimums'
AS
WITH lines AS (
  SELECT c.port_name, c.region, c.vessel_type, c.size_band, cat.name AS expense_category,
         (e.price_amount + COALESCE(e.price_surcharges, 0) - COALESCE(e.price_discount, 0)) * c.rate_eur AS amount_eur
  FROM port_call_costs c
  JOIN ${catalog}.${silver_schema}.expense_evaluation e ON e.evaluation_id = c.evaluation_id
  JOIN ${catalog}.${silver_schema}.expense_category cat ON cat.id = e.category_id
  WHERE c.evaluation_state IN ('APPROVED', 'PAID') AND NOT COALESCE(e.is_platform_fee, FALSE)
    AND NOT COALESCE(e.is_excluded_from_historical_data, FALSE)
    AND COALESCE(e.is_active, TRUE) AND e.deleted_on IS NULL AND e.merged_into_id IS NULL
),
levels AS (
  SELECT 'exact' AS benchmark_level, port_name, region, vessel_type, size_band, expense_category, amount_eur FROM lines
  UNION ALL
  SELECT 'port', port_name, region, NULL, NULL, expense_category, amount_eur FROM lines
  UNION ALL
  SELECT 'region', NULL, region, vessel_type, size_band, expense_category, amount_eur FROM lines
),
stats AS (
  SELECT benchmark_level, port_name, region, vessel_type, size_band, expense_category,
         COUNT(*)                               AS sample_size,
         ROUND(PERCENTILE(amount_eur, 0.25), 2) AS p25_eur,
         ROUND(MEDIAN(amount_eur), 2)           AS median_eur,
         ROUND(PERCENTILE(amount_eur, 0.75), 2) AS p75_eur,
         ROUND(MIN(amount_eur), 2)              AS minimum_eur
  FROM levels GROUP BY ALL
),
port_medians AS (
  SELECT region, expense_category, MIN(median_eur) AS region_min_median_eur
  FROM stats WHERE benchmark_level = 'port' GROUP BY ALL
),
port_minimums AS (
  SELECT port_name, expense_category, minimum_eur AS local_port_min_eur
  FROM stats WHERE benchmark_level = 'port'
)
SELECT s.*, pm.region_min_median_eur, lp.local_port_min_eur
FROM stats s
LEFT JOIN port_medians pm ON pm.region = s.region AND pm.expense_category = s.expense_category
LEFT JOIN port_minimums lp ON lp.port_name = s.port_name AND lp.expense_category = s.expense_category;
