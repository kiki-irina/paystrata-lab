#!/usr/bin/env bash
# Live lock monitor for the PayStrata lab. Run it in a SECOND terminal while the load test runs.
#   ./monitor.sh          refresh every 6 seconds (default)
#   ./monitor.sh 2        refresh every 2 seconds
# Stop with Ctrl+C.
#
# Defaults to 6 seconds per snapshot, so there is time to explain what is on screen.
#   ./monitor.sh once        one snapshot and exit (use it to validate the monitor)
#   ./monitor.sh 10          refresh every 10 seconds
#   ./monitor.sh 8 keep      do not clear the screen: every snapshot stays in the scrollback
# To freeze the screen while you talk: Ctrl+S (resume with Ctrl+Q).

INTERVAL="${1:-6}"
MODE="${2:-}"

while true; do
  [ "$MODE" = "keep" ] || clear
  echo
  echo "PayStrata lab monitor   $(date '+%H:%M:%S')   (refresh ${INTERVAL}s, Ctrl+C to stop)"
  docker exec -i paystrata-db mysql -uroot -ppaystrata paystrata -t 2>/dev/null <<'SQL'

SELECT '1. SESSIONS AND TRANSACTIONS' AS section;
SELECT COUNT(*)                   AS sessions,
       SUM(COMMAND = 'Query')     AS running_a_statement,
       SUM(COMMAND = 'Sleep')     AS idle
FROM performance_schema.processlist;
SELECT trx_state,
       COUNT(*)                                           AS transactions,
       MAX(TIMESTAMPDIFF(SECOND, trx_started, NOW()))     AS oldest_sec
FROM information_schema.innodb_trx
GROUP BY trx_state;

SELECT '2. WHO BLOCKS WHOM (longest waits first)' AS section;
SELECT wait_age_secs               AS waiting_s,
       waiting_pid,
       blocking_pid,
       LEFT(waiting_query, 45)     AS waiting_query,
       LEFT(blocking_query, 45)    AS blocking_query
FROM sys.innodb_lock_waits
ORDER BY wait_age_secs DESC
LIMIT 5;

SELECT '3. LOCKS, GROUPED BY INDEX AND MODE' AS section;
SELECT index_name, lock_mode, lock_status, COUNT(*) AS locks
FROM performance_schema.data_locks
GROUP BY index_name, lock_mode, lock_status
ORDER BY locks DESC
LIMIT 8;

SELECT '4. DEADLOCKS AND LOCK WAITS (since server start)' AS section;
SELECT (SELECT count FROM information_schema.innodb_metrics
         WHERE name = 'lock_deadlocks')                        AS deadlocks_total,
       (SELECT VARIABLE_VALUE FROM performance_schema.global_status
         WHERE VARIABLE_NAME = 'Innodb_row_lock_waits')        AS row_lock_waits_total,
       (SELECT VARIABLE_VALUE FROM performance_schema.global_status
         WHERE VARIABLE_NAME = 'Innodb_row_lock_current_waits') AS waiting_right_now;
SQL
  [ "$INTERVAL" = "once" ] && break
  sleep "$INTERVAL"
done
