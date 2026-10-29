#!/usr/bin/env bash
# Both tests, each on a freshly rebuilt environment, then destroy everything.
#   ./run_all.sh
# Run ./monitor.sh in a second terminal first.
set -euo pipefail
cd "$(dirname "$0")"
if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi

./test1.sh
./test2.sh

echo; echo "=== Destroy containers and the data volume ==="
$DC down -v </dev/null
echo; echo "All done. Charts: results/test1.png and results/test2.png"
