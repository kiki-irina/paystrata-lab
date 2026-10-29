TEST 2: IODKU WITH REPEATABLE READ VERSUS READ COMMITTED
=========================================================

QUESTION
--------
The same IODKU statement, the same data and the same traffic. Only the isolation level
changes. There is no redesign in this test.

  REPEATABLE READ   the MySQL default
  READ COMMITTED

Is the problem the statement, or the locks that REPEATABLE READ takes for it?


HOW TO RUN
----------
Optional, in a second terminal (live locks):

    ./monitor.sh

Then:

    ./test2.sh

It takes about 4 minutes of load plus the environment setup. To destroy the containers at
the end:

    DESTROY=1 ./test2.sh

The same thing by hand:

    ./setup_env.sh
    docker-compose run --rm loadgen ramp --variants iodku --out test2_rr
    docker-compose run --rm loadgen ramp --variants iodku --isolation "READ COMMITTED" --out test2_rc
    source .venv/bin/activate
    python plot_isolation.py
    deactivate


WHAT THE SCRIPT DOES
--------------------
1. Rebuilds the environment from scratch (./setup_env.sh): destroys containers and data,
   starts Colima if needed, starts Percona Server 8.4, waits until it is healthy and checks
   that the table has 19,000 merchants. No test runs in this step.

2. Ramp A: IODKU with REPEATABLE READ at 1, 5, 10, 25 and 50 sessions.

3. Ramp B: IODKU with READ COMMITTED at the same five levels. Every session sets the
   isolation level with SET SESSION TRANSACTION ISOLATION LEVEL before it starts working.

4. Draws the chart from the two CSV files.

Each level lasts 20 seconds. Before every level the table is emptied and reloaded, so
every level starts from the same data. A row is printed as soon as a level finishes, and
the column "isolation" tells the two ramps apart.

What one session ("payment") does: one transaction that updates 3 merchants, in random
order, with a 2 ms pause between statements. 80% of the traffic goes to the first 1,000
merchants and 5% of the keys do not exist yet. On a deadlock the payment is rolled back and
retried, up to 3 more times.


FILES IT PRODUCES
-----------------
  results/test2_rr.csv   IODKU with REPEATABLE READ
  results/test2_rc.csv   IODKU with READ COMMITTED
  results/test2.png      the chart


HOW TO READ THE CHART
---------------------
Three panels, 1 to 50 concurrent sessions on the horizontal axis. Blue is REPEATABLE READ,
orange is READ COMMITTED.

  Payments per second   higher is better
  p95 latency           lower is better
  Deadlocks             lower is better


WHAT WE SAW
-----------
One real run (20 s per level). Numbers vary by laptop and by run, plus or minus 30%; the
pattern must not change.

  sessions                1       5      10      25      50
  REPEATABLE READ
    payments/s          103     115     134     166     255
    p95 ms               13      75     124     292     465
    deadlocks             0   2,867   6,442   7,400  12,881
  READ COMMITTED
    payments/s          113     641   1,267   1,826   2,838
    p95 ms               10       8       9      25      28
    deadlocks             0       0       0       0       2

At 50 sessions: about 11 times more payments per second, p95 about 17 times lower, failed
payments 1,817 to 0. With 1 session both are the same.

READ COMMITTED brings IODKU close to the redesign from Test 1 (2,907 payments/s, p95 27 ms
at 50 sessions). At 25 sessions it was behind (1,826 against 2,759 payments/s); it is one run,
so do not over-read it.


WHY
---
Under REPEATABLE READ, InnoDB takes next-key and gap locks for IODKU. Two sessions that
insert into the same gap block each other, and the cycle ends as a deadlock. READ COMMITTED
does not take gap locks for searches and index scans, so most of that blocking disappears.
Gap locks remain for foreign-key checks and duplicate-key checks, which is why a few
deadlocks are still possible (9 in the run above).


WHAT TO SAY
-----------
- The root cause is the combination of the statement and the isolation level.
- READ COMMITTED is not a free fix. It changes what every transaction in the application
  can see (non-repeatable reads and phantoms), and with binary log replication it requires
  binlog_format=ROW. It is a configuration change that has to be tested on the whole system.
- Changing the statement (Test 1) solves the problem without changing the rules for the rest
  of the application.
- The live monitor shows the difference: under REPEATABLE READ the lock table has X, X,GAP
  and X,INSERT_INTENTION waiting; under READ COMMITTED there are far fewer waiting locks.


CAVEATS
-------
- Lab reproduction in Docker on a laptop, one run per level. Compare the ratios, not the
  absolute numbers.
- The workload is deliberately aggressive (hot merchants, 2 ms think time, 5% new keys).
- READ COMMITTED with the redesign is not part of this test. To try it:

    docker-compose run --rm loadgen run --variant update_insert --threads 50 --duration 30 --isolation "READ COMMITTED"
