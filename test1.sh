#!/usr/bin/env bash
# TEST 1: IODKU versus UPDATE first (the redesign), ramp 1 -> 50 sessions, REPEATABLE READ.
# Rebuilds the environment from scratch, runs the ramp for IODKU and then for the redesign,
# and draws results/test1.png (payments per second, p95, deadlocks).
#   ./test1.sh              leaves the database running at the end
#   DESTROY=1 ./test1.sh    destroys the containers at the end
# Tip: run ./monitor.sh in a second terminal before you start.
set -euo pipefail
cd "$(dirname "$0")"
if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi
step() { echo; echo "=== $* ==="; }

step "TEST 1, environment: rebuild from scratch"
./setup_env.sh

step "TEST 1, IODKU then redesign, 1 -> 50 sessions (rows appear as each level finishes)"
$DC run --rm -T loadgen ramp --out test1 </dev/null

step "TEST 1, chart"
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python plot.py
  deactivate
else
  echo "No .venv found. Create it once: python3 -m venv .venv && source .venv/bin/activate && python3 -m pip install matplotlib"
fi

if [ "${DESTROY:-0}" = "1" ]; then step "Destroy containers and volume"; $DC down -v </dev/null; fi
echo; echo "Test 1 done. Numbers: results/test1.csv   Chart: results/test1.png"
