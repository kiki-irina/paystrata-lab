#!/usr/bin/env bash
# Rebuilds the lab environment from scratch. It does NOT run any test.
#   ./setup_env.sh
# Afterwards, run the tests yourself with the commands in test_commands.txt.
set -euo pipefail
cd "$(dirname "$0")"

if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi
step() { echo; echo "=== $* ==="; }

step "1. Destroy old containers, network and data volume"
$DC down -v </dev/null

step "2. Docker runtime (Colima), started only if it is not running"
if command -v colima >/dev/null 2>&1; then
  colima status >/dev/null 2>&1 || colima start --cpu 4 --memory 8
fi

step "3. Start the database and build the load generator"
$DC up -d db </dev/null
$DC build loadgen </dev/null

step "4. Wait until the database is healthy"
status=""
for _ in $(seq 1 60); do
  status="$(docker inspect -f '{{.State.Health.Status}}' paystrata-db 2>/dev/null || true)"
  [ "$status" = "healthy" ] && break
  sleep 3
done
[ "$status" = "healthy" ] || { echo "Database did not become healthy. Check: $DC logs db"; exit 1; }
echo "healthy"

step "5. Validate the data (expected: 19000)"
docker exec -i paystrata-db mysql -uroot -ppaystrata paystrata -e "SELECT COUNT(*) AS merchants FROM merchant_daily_stats;" 2>/dev/null </dev/null

echo
echo "Environment is ready. No test was run."
echo "Next: ./monitor.sh in a second terminal, then the commands from test_commands.txt."
