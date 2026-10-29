#!/usr/bin/env bash
# TEST 2: IODKU only (no redesign), REPEATABLE READ versus READ COMMITTED, ramp 1 -> 50 sessions.
# Rebuilds the environment from scratch, runs the ramp twice and draws results/test2.png
# (payments per second, p95, deadlocks).
#   ./test2.sh              leaves the database running at the end
#   DESTROY=1 ./test2.sh    destroys the containers at the end
# Tip: run ./monitor.sh in a second terminal before you start.
set -euo pipefail
cd "$(dirname "$0")"
if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi
step() { echo; echo "=== $* ==="; }

step "TEST 2, environment: rebuild from scratch"
./setup_env.sh

step "TEST 2a, IODKU with REPEATABLE READ (the default), 1 -> 50 sessions"
$DC run --rm -T loadgen ramp --variants iodku --out test2_rr </dev/null

step "TEST 2b, IODKU with READ COMMITTED, 1 -> 50 sessions"
$DC run --rm -T loadgen ramp --variants iodku --isolation "READ COMMITTED" --out test2_rc </dev/null

step "TEST 2, chart"
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python plot_isolation.py
  deactivate
else
  echo "No .venv found. Create it once: python3 -m venv .venv && source .venv/bin/activate && python3 -m pip install matplotlib"
fi

if [ "${DESTROY:-0}" = "1" ]; then step "Destroy containers and volume"; $DC down -v </dev/null; fi
echo; echo "Test 2 done. Numbers: results/test2_rr.csv and results/test2_rc.csv   Chart: results/test2.png"
