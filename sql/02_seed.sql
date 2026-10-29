-- Seed: merchants 1..20000 for one day, EXCEPT every 20th merchant (20, 40, 60, ...).
-- Those missing keys are the "first payment of the day" inserts that traffic will create.
-- Safe to re-run: it empties the table first.
TRUNCATE TABLE merchant_daily_stats;

SET SESSION cte_max_recursion_depth = 100000;

INSERT INTO merchant_daily_stats (merchant_id, stat_date, txn_count, total_amount)
WITH RECURSIVE seq (n) AS (
  SELECT 1
  UNION ALL
  SELECT n + 1 FROM seq WHERE n < 20000
)
SELECT n, '2026-03-01', 0, 0.00 FROM seq WHERE n % 20 <> 0;
