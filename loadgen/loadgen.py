#!/usr/bin/env python3
"""
PayStrata lab: IODKU vs UPDATE-then-INSERT under growing concurrency.

Each simulated payment is ONE transaction that updates the daily stats of 3 merchants
(think: a marketplace payment split between sellers). Keys are touched in random order,
as a real application does. Most rows already exist; a few (the "first payment of the
day") do not and must be inserted.

Usage (inside the lab):
  docker compose run --rm loadgen reset
  docker compose run --rm loadgen run  --variant iodku        --threads 50
  docker compose run --rm loadgen run  --variant update_insert --threads 50
  docker compose run --rm loadgen ramp                      # both variants, 1..50 threads
"""
import argparse
import csv
import os
import random
import threading
import time

import pymysql
from pymysql.constants import CLIENT

STAT_DATE = "2026-03-01"
N_MERCHANTS = 20000
HOT_MERCHANTS = 1000      # 80% of traffic goes to the first 1,000 merchants ...
HOT_SHARE = 0.80          # ... like real traffic: a few merchants are very busy
NEW_KEY_SHARE = 0.05      # 5% of operations target a key that may not exist yet
MAX_RETRIES = 3           # an application retries a payment after a deadlock

IODKU_SQL = (
    "INSERT INTO merchant_daily_stats (merchant_id, stat_date, txn_count, total_amount) "
    "VALUES (%s, %s, 1, %s) AS incoming "
    "ON DUPLICATE KEY UPDATE "
    "txn_count = merchant_daily_stats.txn_count + 1, "
    "total_amount = merchant_daily_stats.total_amount + incoming.total_amount"
)
UPDATE_SQL = (
    "UPDATE merchant_daily_stats "
    "SET txn_count = txn_count + 1, total_amount = total_amount + %s "
    "WHERE merchant_id = %s AND stat_date = %s"
)
INSERT_SQL = (
    "INSERT INTO merchant_daily_stats (merchant_id, stat_date, txn_count, total_amount) "
    "VALUES (%s, %s, 1, %s)"
)

ISOLATION_LEVELS = {"REPEATABLE READ", "READ COMMITTED"}


def connect(isolation):
    conn = pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "paystrata"),
        database=os.environ.get("DB_NAME", "paystrata"),
        autocommit=False,
        client_flag=CLIENT.FOUND_ROWS,  # UPDATE reports matched rows, not changed rows
        connect_timeout=10,
    )
    with conn.cursor() as cur:
        cur.execute(f"SET SESSION TRANSACTION ISOLATION LEVEL {isolation}")
    return conn


# --- the two variants being compared -------------------------------------------------

def upsert_iodku(cur, merchant_id, amount):
    cur.execute(IODKU_SQL, (merchant_id, STAT_DATE, amount))


def upsert_update_insert(cur, merchant_id, amount):
    # 1) the common case: the row exists -> UPDATE takes one record lock
    if cur.execute(UPDATE_SQL, (amount, merchant_id, STAT_DATE)) == 0:
        # 2) the rare case: the row does not exist -> INSERT it
        try:
            cur.execute(INSERT_SQL, (merchant_id, STAT_DATE, amount))
        except pymysql.err.IntegrityError as exc:
            if exc.args[0] != 1062:
                raise
            # another session inserted it between our UPDATE and INSERT -> UPDATE again
            cur.execute(UPDATE_SQL, (amount, merchant_id, STAT_DATE))


VARIANTS = {"iodku": upsert_iodku, "update_insert": upsert_update_insert}


# --- workload ------------------------------------------------------------------------

def pick_key():
    r = random.random()
    if r < NEW_KEY_SHARE:
        return 20 * random.randint(1, N_MERCHANTS // 20)   # a key that starts out missing
    if r < NEW_KEY_SHARE + HOT_SHARE * (1 - NEW_KEY_SHARE):
        return random.randint(1, HOT_MERCHANTS)
    return random.randint(1, N_MERCHANTS)


class WorkerStats:
    def __init__(self):
        self.latencies = []
        self.deadlocks = 0
        self.timeouts = 0
        self.failed = 0


def run_payment(conn, upsert, batch, think_s, stats):
    keys = list({pick_key() for _ in range(batch)})
    random.shuffle(keys)                                  # NOT sorted: like a real app
    start = time.perf_counter()
    for attempt in range(MAX_RETRIES + 1):
        try:
            with conn.cursor() as cur:
                for merchant_id in keys:
                    upsert(cur, merchant_id, round(random.uniform(1, 100), 2))
                    if think_s:
                        time.sleep(think_s)               # application work between statements
            conn.commit()
            stats.latencies.append(time.perf_counter() - start)
            return
        except pymysql.err.OperationalError as exc:
            conn.rollback()
            code = exc.args[0]
            if code == 1213:
                stats.deadlocks += 1
            elif code == 1205:
                stats.timeouts += 1
            else:
                raise
    stats.failed += 1


def worker(conn, upsert, batch, think_s, stop_at, start_gate, stats):
    start_gate.wait()
    while time.monotonic() < stop_at:
        run_payment(conn, upsert, batch, think_s, stats)


def percentile(sorted_values, p):
    if not sorted_values:
        return 0.0
    return sorted_values[min(len(sorted_values) - 1, int(p * (len(sorted_values) - 1)))]


def reset_data():
    conn = connect("REPEATABLE READ")
    with open("/sql/02_seed.sql", encoding="utf-8") as fh:
        text = "\n".join(l for l in fh.read().splitlines() if not l.strip().startswith("--"))
    with conn.cursor() as cur:
        for statement in [s.strip() for s in text.split(";") if s.strip()]:
            cur.execute(statement)
    conn.commit()
    conn.close()


def run_level(variant, threads, duration, think_ms, batch, isolation):
    reset_data()
    conns = [connect(isolation) for _ in range(threads)]
    all_stats = [WorkerStats() for _ in range(threads)]
    gate = threading.Event()
    stop_at = time.monotonic() + duration + 0.5            # small margin for the start gate
    pool = [
        threading.Thread(
            target=worker,
            args=(c, VARIANTS[variant], batch, think_ms / 1000.0, stop_at, gate, s),
            daemon=True,
        )
        for c, s in zip(conns, all_stats)
    ]
    for t in pool:
        t.start()
    started = time.monotonic()
    gate.set()
    for t in pool:
        t.join()
    elapsed = max(time.monotonic() - started, 0.001)
    for c in conns:
        c.close()

    lats = sorted(l for s in all_stats for l in s.latencies)
    return {
        "variant": variant,
        "isolation": isolation,
        "threads": threads,
        "payments_per_s": round(len(lats) / elapsed, 1),
        "p50_ms": round(percentile(lats, 0.50) * 1000, 1),
        "p95_ms": round(percentile(lats, 0.95) * 1000, 1),
        "p99_ms": round(percentile(lats, 0.99) * 1000, 1),
        "deadlocks": sum(s.deadlocks for s in all_stats),
        "lock_timeouts": sum(s.timeouts for s in all_stats),
        "failed_payments": sum(s.failed for s in all_stats),
    }


COLUMNS = ["variant", "isolation", "threads", "payments_per_s", "p50_ms", "p95_ms", "p99_ms",
           "deadlocks", "lock_timeouts", "failed_payments"]


def print_row(row, cols=COLUMNS):
    print("  ".join(f"{str(row[c]):>18}" if c == "isolation" else f"{str(row[c]):>15}" for c in cols), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("reset", help="empty and reseed merchant_daily_stats")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--duration", type=int, default=20, help="seconds per level (default 20)")
    common.add_argument("--think-ms", type=float, default=2.0,
                        help="application time between statements, keeps locks open longer (default 2)")
    common.add_argument("--batch", type=int, default=3, help="merchants updated per payment (default 3)")
    common.add_argument("--isolation", default="REPEATABLE READ", choices=sorted(ISOLATION_LEVELS))

    run = sub.add_parser("run", parents=[common], help="one variant at one concurrency level")
    run.add_argument("--variant", choices=sorted(VARIANTS), required=True)
    run.add_argument("--threads", type=int, default=10)

    ramp = sub.add_parser("ramp", parents=[common], help="both variants at growing concurrency")
    ramp.add_argument("--levels", default="1,5,10,25,50")
    ramp.add_argument("--variants", default="iodku,update_insert")
    ramp.add_argument("--out", default="", help="also save the results as results/NAME.csv")

    args = parser.parse_args()

    if args.cmd == "reset":
        reset_data()
        print("merchant_daily_stats reseeded.")
        return

    if args.cmd == "run":
        print_row(dict(zip(COLUMNS, COLUMNS)))
        print_row(run_level(args.variant, args.threads, args.duration, args.think_ms, args.batch, args.isolation))
        return

    rows = []
    print_row(dict(zip(COLUMNS, COLUMNS)))
    for variant in args.variants.split(","):
        for level in [int(x) for x in args.levels.split(",")]:
            row = run_level(variant, level, args.duration, args.think_ms, args.batch, args.isolation)
            rows.append(row)
            print_row(row)
    os.makedirs("/results", exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    targets = [f"/results/ramp-{stamp}.csv", "/results/latest.csv"]
    if args.out:
        targets.append(f"/results/{args.out}.csv")
    for name in targets:
        with open(name, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    print("\nSaved results/latest.csv" + (f" and results/{args.out}.csv" if args.out else ""))


if __name__ == "__main__":
    main()
