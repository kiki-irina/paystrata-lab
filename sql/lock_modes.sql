-- Lock X-ray: which locks does ONE statement take on an existing row?
-- Run in a single mysql session:
--   docker exec -it paystrata-db mysql -uroot -ppaystrata paystrata
-- Merchant 101 exists. Merchant 100 does NOT exist (it is a "multiple of 20" gap key).

-- A) IODKU on an existing row -----------------------------------------------------
BEGIN;

INSERT INTO merchant_daily_stats (merchant_id, stat_date, txn_count, total_amount)
VALUES (101, '2026-03-01', 1, 10.00) AS incoming
ON DUPLICATE KEY UPDATE txn_count = merchant_daily_stats.txn_count + 1;

SELECT index_name, lock_type, lock_mode, lock_status, lock_data
FROM performance_schema.data_locks
WHERE object_name = 'merchant_daily_stats';

ROLLBACK;

-- B) UPDATE on the same existing row -----------------------------------------------
BEGIN;

UPDATE merchant_daily_stats
SET txn_count = txn_count + 1
WHERE merchant_id = 101 AND stat_date = '2026-03-01';

SELECT index_name, lock_type, lock_mode, lock_status, lock_data
FROM performance_schema.data_locks
WHERE object_name = 'merchant_daily_stats';

ROLLBACK;

-- Read the lock_mode column:
--   X                  = next-key lock: the record AND the gap before it
--   X,REC_NOT_GAP      = record lock only
--   X,GAP,INSERT_INTENTION = a session waiting to insert into a locked gap
