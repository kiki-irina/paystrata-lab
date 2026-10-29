# PayStrata Lab: the bottleneck that only appears at peak hours

Lab for Session 1 of *Database Reliability & High Availability in Production*.

**The story.** PayStrata counts payments per merchant per day with
`INSERT ... ON DUPLICATE KEY UPDATE` (IODKU). Every test in DEV and QA passes and every
query is fast. As traffic grows during the day, PROD slows down. You will reproduce it,
find the cause with MySQL's own tools, and redesign the statement.

## Requirements

- Docker Desktop (or Colima) with at least 4 GB of RAM
- Optional: Python 3 + `matplotlib` on your laptop for the chart

## Quick start

```bash
docker compose up -d db          # Percona Server 8.4, port 3307 on your machine
docker compose build loadgen     # builds the small Python load generator
docker compose ps                # wait until db is "healthy"
```

Connect any time:

```bash
docker exec -it paystrata-db mysql -uroot -ppaystrata paystrata
```

## The schema

```sql
CREATE TABLE merchant_daily_stats (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  merchant_id  INT UNSIGNED    NOT NULL,
  stat_date    DATE            NOT NULL,
  txn_count    INT UNSIGNED    NOT NULL DEFAULT 0,
  total_amount DECIMAL(18,2)   NOT NULL DEFAULT 0.00,
  PRIMARY KEY (id),
  UNIQUE KEY uq_merchant_day (merchant_id, stat_date)
) ENGINE=InnoDB;
```

20,000 merchants, except every 20th one (20, 40, 60 ...): those are the "first payment
of the day" rows that traffic will have to insert.

## Step 1: DEV and QA, one session

```bash
docker compose run --rm loadgen run --variant iodku --threads 1
```

One session at a time. Fast and correct. This is all that DEV and QA ever see.

## Step 2: PROD, traffic growing during the day

```bash
docker compose run --rm loadgen ramp --variants iodku
```

The load generator repeats the workload with 1, 5, 10, 25 and 50 concurrent sessions.
Each payment is one transaction that updates 3 merchants in random order, like a
marketplace payment split between sellers.

Watch the columns `payments_per_s`, `p95_ms` and `deadlocks`.

## Step 3: find the cause

While the ramp runs, use a second terminal and the queries in `sql/diagnostics.sql`:

```bash
docker exec -it paystrata-db mysql -uroot -ppaystrata paystrata
```

- `SHOW ENGINE INNODB STATUS\G` shows the last deadlock: who held what, who waited for what.
- `performance_schema.data_locks` lists every lock. Look at the `lock_mode` column.
- `sys.innodb_lock_waits` shows who blocks whom.

Then run `sql/lock_modes.sql` and compare the locks taken by one IODKU against one
`UPDATE` on the same row.

### Two-terminal experiment (2 minutes)

Merchant 101 exists. Merchant 100 does not.

| Terminal A | Terminal B |
| --- | --- |
| `BEGIN;` | |
| `INSERT ... VALUES (101, '2026-03-01', 1, 10) AS incoming ON DUPLICATE KEY UPDATE txn_count = merchant_daily_stats.txn_count + 1;` | |
| | `INSERT INTO merchant_daily_stats (merchant_id, stat_date) VALUES (100, '2026-03-01');` |
| (leave the transaction open) | What happens? Check `data_locks` from a third terminal. |
| `ROLLBACK;` | |

Repeat with `UPDATE ... WHERE merchant_id = 101 ...` in terminal A instead of IODKU.

## Step 4: the redesign

Same workload, different statements:

```bash
docker compose run --rm loadgen ramp --variants update_insert
```

`UPDATE` first, because most rows already exist; `INSERT` only when the row is missing;
retry the `UPDATE` if another session inserted it first (duplicate-key error 1062).
The code is in `loadgen/loadgen.py`, functions `upsert_iodku` and `upsert_update_insert`.

Run both variants in one go and plot the curves:

```bash
docker compose run --rm loadgen ramp
pip install matplotlib && python plot.py     # creates results/ramp.png
```

## Experiments to try on your own

1. `--isolation "READ COMMITTED"`: what happens to the deadlocks of each variant?
2. `--think-ms 0` vs `--think-ms 10`: why does the time between statements matter in production?
3. Sort the 3 merchant ids before updating (look for `random.shuffle` in `run_payment`). What changes, and why?
4. Set `MAX_RETRIES = 0` in `loadgen.py`: how many payments now end in `failed_payments`, and what would your customers see?

## Mini-challenge (for points)

Rewrite this statement as UPDATE-then-INSERT and explain, in 5 lines, which locks disappear
and which race condition you must still handle:

```sql
INSERT INTO merchant_daily_stats (merchant_id, stat_date, txn_count, total_amount)
VALUES (4242, '2026-03-01', 1, 55.00) AS incoming
ON DUPLICATE KEY UPDATE
  txn_count = merchant_daily_stats.txn_count + 1,
  total_amount = merchant_daily_stats.total_amount + incoming.total_amount;
```

## Clean up

```bash
docker compose down -v
```

## Troubleshooting

- `Can't connect`: wait until `docker compose ps` shows `db` as healthy.
- Port 3307 busy: change the left side of `3307:3306` in `docker-compose.yml`.
- Apple Silicon (M1/M2/M3): no special tag needed, `percona/percona-server:8.4` is multi-arch.
  To pin a version, use `PS_TAG=8.4.10 docker compose up -d db`.
- Colima: start it with `colima start --cpu 4 --memory 8`. If `docker compose` is not found,
  use `docker-compose` (same arguments).
