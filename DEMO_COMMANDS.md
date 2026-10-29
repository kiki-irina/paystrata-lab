# PayStrata lab: commands in order

This sheet assumes macOS, Colima and the standalone `docker-compose`. If `docker compose`
(with a space) works for you, use it instead.

## Full run, start to finish (destroy, run, destroy)

Use this for the final rehearsal and for the real session. Open **Terminal 2** first and run
`./monitor.sh` (6 s per snapshot; `./monitor.sh 10` is slower, `./monitor.sh 8 keep` keeps every snapshot in the scrollback; Ctrl+S freezes the screen, Ctrl+Q resumes), then start the script in **Terminal 1**:

```bash
cd paystrata-lab
chmod +x run_all.sh monitor.sh
./run_all.sh
```

The script destroys any old containers and the data volume, starts Colima if needed, waits
until the database is healthy, runs DEV, the IODKU ramp, the redesign ramp, the combined ramp,
the chart, and finally destroys the containers again. To keep the database running at the end:

```bash
KEEP=1 ./run_all.sh
```

The chart step needs the virtual environment from section 0 (created once).

`docker-compose down -v` removes the container, the network and the data volume, so the
next start reloads the schema and the 19,000 seed rows from `sql/`.

**Copy-paste rule for the manual steps below:** paste one block at a time and wait for it to
finish. Do not paste several `docker-compose run` commands in one go, because they read from
the keyboard and can swallow the lines that follow. Everything long-running is already in
`run_all.sh`.

## 0. Environment setup (once) and checks

Docker runtime (Colima) with enough memory for MySQL plus 50 load sessions:

```bash
colima start --cpu 4 --memory 8
```

Check that everything is in place. Each command should succeed:

```bash
colima status
docker info --format 'CPUs: {{.NCPU}}  Memory: {{.MemTotal}}'
docker-compose version
python3 --version
```

Expected: Colima `Running`, at least 4 CPUs and about 8 GB (`MemTotal` ~ 8,000,000,000),
Compose 2.x, Python 3.

Python environment for the chart (once):

```bash
cd paystrata-lab
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install matplotlib
deactivate
```

Check the chart dependency and make the scripts executable:

```bash
.venv/bin/python -c "import matplotlib; print('matplotlib', matplotlib.__version__)"
chmod +x run_all.sh monitor.sh
```

Troubleshooting: if port 3307 is busy, change `3307:3306` in `docker-compose.yml`. If
`docker-compose` is not found, `brew install docker-compose`. If MySQL restarts or the load
test is killed, increase Colima memory with `colima stop` and `colima start --cpu 4 --memory 12`.

## 1. Start the database

```bash
cd paystrata-lab
docker-compose up -d db
docker-compose build loadgen
docker-compose ps
```

Repeat `docker-compose ps` until `db` shows `(healthy)`. Check the data:

```bash
docker exec -it paystrata-db mysql -uroot -ppaystrata paystrata -e "SELECT COUNT(*) FROM merchant_daily_stats;"
```

Expected: `19000`.

## 2. DEV: one session

```bash
docker-compose run --rm loadgen run --variant iodku --threads 1
```

Expected: about 100 payments/s, p95 around 10 ms, `deadlocks` = 0.

## 3. PROD: traffic ramps up (IODKU)

**Terminal 2** (open before the ramp, leave it visible): the live lock monitor.

```bash
cd paystrata-lab
./monitor.sh
```

If it says permission denied: `chmod +x monitor.sh`.

**Terminal 1**: the ramp.

```bash
docker-compose run --rm loadgen ramp --variants iodku
```

Each level (1, 5, 10, 25, 50 sessions) lasts 20 seconds and starts from freshly seeded data.
Watch panel 2 (who blocks whom), panel 3 (`X,INSERT_INTENTION` in `WAITING` state) and
panel 4 (deadlock counter growing).

## 4. Forensics: find the cause

Open a MySQL shell (Terminal 3, or stop the monitor):

```bash
docker exec -it paystrata-db mysql -uroot -ppaystrata paystrata
```

```sql
SHOW ENGINE INNODB STATUS\G
SELECT * FROM performance_schema.data_locks\G
SELECT * FROM sys.innodb_lock_waits\G
```

Look for `LATEST DETECTED DEADLOCK`. More queries are in `sql/diagnostics.sql` and
`sql/lock_modes.sql`.

Only the last deadlock, trimmed to fit on a slide:

```bash
docker exec paystrata-db mysql -uroot -ppaystrata paystrata -e "SHOW ENGINE INNODB STATUS\G" 2>/dev/null \
  | sed -n '/LATEST DETECTED DEADLOCK/,/WE ROLL BACK/p' | cut -c1-170
```

## 5. Redesign: UPDATE first, INSERT only if missing

Keep `./monitor.sh` running in Terminal 2.

```bash
docker-compose run --rm loadgen ramp --variants update_insert
```

Expected: payments/s grows almost linearly, p95 stays low, deadlocks near 0.

## 6. Reveal: both variants and the chart

```bash
docker-compose run --rm loadgen ramp
```

```bash
source .venv/bin/activate
python plot.py
deactivate
```

The chart is `results/ramp.png`, the numbers are in `results/latest.csv`.

## Utilities

Reseed the table (also done automatically before every level):

```bash
docker-compose run --rm loadgen reset
```

Throughput straight from the server, formula `TPS = commits in a window / seconds`.
Run it in a MySQL shell while a test is running:

```sql
SELECT VARIABLE_VALUE INTO @c1 FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Com_commit';
SELECT SLEEP(10);
SELECT VARIABLE_VALUE INTO @c2 FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Com_commit';
SELECT (@c2 - @c1) / 10 AS tps;
```

Full reset (deletes the database volume, then starts clean):

```bash
docker-compose down -v
docker-compose up -d db
docker-compose ps
```

Stop everything at the end:

```bash
docker-compose down -v
colima stop
```

## Validate the monitor before the session

**1. Idle check.** With the database up and no test running, take one snapshot:

```bash
./monitor.sh once
```

Expected: all 4 panels print without an error. Panel 2 and panel 3 are empty or show no
rows, panel 4 shows `deadlocks_total` (0 on a fresh database) and `waiting_right_now` 0.
If a panel fails, run its query in a MySQL shell to see the error text.

**2. Load check.** Terminal 2 runs the monitor, Terminal 1 runs a short test:

```bash
./monitor.sh 3
```

```bash
docker-compose run --rm loadgen run --variant iodku --threads 20 --duration 30
```

Expected during the 30 seconds:

| Panel | Pass criteria |
| --- | --- |
| 1 | `sessions` around 20 or more, some `transactions` in `LOCK WAIT` |
| 2 | one or more rows with `waiting_pid` and `blocking_pid` and the SQL text cut at 45 characters |
| 3 | rows with `X` or `X,INSERT_INTENTION` and `lock_status` `WAITING` |
| 4 | `deadlocks_total` increases between snapshots |

**3. Redesign check.** Same as above with `--variant update_insert`. Expected: panel 2 mostly
empty, panel 3 dominated by `X,REC_NOT_GAP` (`GRANTED`), `deadlocks_total` barely moves.

## Test results to expect (pass / fail)

Numbers vary by laptop (plus or minus 30%), the pattern must not.

| Test | Command | Pass criteria |
| --- | --- | --- |
| Seed | `SELECT COUNT(*) ...` | 19000 |
| DEV | `run --variant iodku --threads 1` | about 100 payments/s, p95 about 10 ms, 0 deadlocks |
| PROD, IODKU | `ramp --variants iodku` | deadlocks from 5 sessions; at 50 sessions about 200 payments/s and p95 above 400 ms |
| Redesign | `ramp --variants update_insert` | at 50 sessions about 3,000 payments/s, p95 below 50 ms, deadlocks 0 to a few |
| Chart | `python plot.py` | `results/ramp.png` created, red line far below green in panel 1 |

If IODKU shows no deadlocks at 5 to 10 sessions, rerun with `--think-ms 2` (the default) and
check that Colima has at least 4 CPUs. If `update_insert` also shows many deadlocks, sort the
merchant ids before updating (experiment 3 in `README.md`).

## What the monitor panels mean

| Panel | What students should see |
| --- | --- |
| 1. Sessions and transactions | More sessions, and transactions piling up in `LOCK WAIT` state |
| 2. Who blocks whom | Pairs of sessions waiting on each other, with the SQL text cut to 45 characters |
| 3. Locks by index and mode | IODKU: `X`, `X,GAP` and `X,INSERT_INTENTION` waiting. UPDATE first: mostly `X,REC_NOT_GAP` |
| 4. Deadlocks | `deadlocks_total` climbing during the IODKU ramp, barely moving after the redesign |

The counters in panel 4 are cumulative since the server started. Take a note of the value
before each ramp and subtract it, or restart the database for a clean zero.
