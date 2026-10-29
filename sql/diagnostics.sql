-- Diagnostics while the load test is running (open a second terminal):
--   docker exec -it paystrata-db mysql -uroot -ppaystrata paystrata

-- 1) The last deadlock InnoDB detected: look for "LATEST DETECTED DEADLOCK"
--    Read: which two transactions, which statements, which locks each HOLDS and WAITS FOR.
SHOW ENGINE INNODB STATUS\G

-- 2) Every lock held or requested right now
SELECT engine_transaction_id, index_name, lock_type, lock_mode, lock_status, lock_data
FROM performance_schema.data_locks
WHERE object_name = 'merchant_daily_stats'
ORDER BY engine_transaction_id, index_name;

-- 3) Only the sessions that are WAITING to insert into a locked gap
SELECT engine_transaction_id, index_name, lock_mode, lock_status, lock_data
FROM performance_schema.data_locks
WHERE lock_mode LIKE '%INSERT_INTENTION%';

-- 4) Who is blocking whom (readable summary)
SELECT wait_age, locked_index, locked_type,
       waiting_query, waiting_lock_mode,
       blocking_query, blocking_lock_mode
FROM sys.innodb_lock_waits\G

-- 5) Total deadlocks since server start
SELECT name, count FROM information_schema.INNODB_METRICS WHERE name = 'lock_deadlocks';
