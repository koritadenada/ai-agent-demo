-- Benchmarks from final-line history (EUR): per port, expense category, vessel type and size band, plus the
-- regional minimum. Lines flagged is_excluded_from_historical_data and platform fees are left out.
CREATE OR REFRESH MATERIALIZED VIEW expense_benchmarks
COMMENT 'Final-cost benchmarks in EUR per port, expense category, vessel type and size band, with the regional minimum median'
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
per_port AS (
  SELECT port_name, region, vessel_type, size_band, expense_category,
         COUNT(*)                               AS sample_size,
         ROUND(PERCENTILE(amount_eur, 0.25), 2) AS p25_eur,
         ROUND(MEDIAN(amount_eur), 2)           AS median_eur,
         ROUND(PERCENTILE(amount_eur, 0.75), 2) AS p75_eur,
         ROUND(MIN(amount_eur), 2)              AS port_min_eur
  FROM lines GROUP BY ALL
)
SELECT *, MIN(median_eur) OVER (PARTITION BY region, vessel_type, size_band, expense_category) AS region_min_median_eur
FROM per_port;
