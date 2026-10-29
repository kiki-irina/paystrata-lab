TEST 1: IODKU VERSUS THE REDESIGN
=================================

QUESTION
--------
The same server, the same data and the same traffic. Only the SQL statement changes.
What happens when the number of concurrent sessions grows from 1 to 50?

  BEFORE:  INSERT ... ON DUPLICATE KEY UPDATE   (IODKU)
  AFTER:   UPDATE first, INSERT only if the row is missing, retry the UPDATE on error 1062

Isolation level: REPEATABLE READ (the MySQL default) for both.


HOW TO RUN
----------
Optional, in a second terminal (live locks):

    ./monitor.sh

Then:

    ./test1.sh

It takes about 4 minutes of load plus the environment setup. To destroy the containers at
the end:

    DESTROY=1 ./test1.sh

The same thing by hand:

    ./setup_env.sh
    docker-compose run --rm loadgen ramp --out test1
    source .venv/bin/activate
    python plot.py
    deactivate


WHAT THE SCRIPT DOES
--------------------
1. Rebuilds the environment from scratch (./setup_env.sh): destroys containers and data,
   starts Colima if needed, starts Percona Server 8.4, waits until it is healthy and checks
   that the table has 19,000 merchants. No test runs in this step.

2. Runs the ramp: IODKU at 1, 5, 10, 25 and 50 sessions, then the redesign at the same five
   levels. Each level lasts 20 seconds. Before every level the table is emptied and reloaded,
   so every level starts from the same data. A row is printed as soon as a level finishes.

3. Draws the chart from results/test1.csv.

What one session ("payment") does: one transaction that updates 3 merchants, in random
order, with a 2 ms pause between statements. 80% of the traffic goes to the first 1,000
merchants and 5% of the keys do not exist yet. On a deadlock the payment is rolled back and
retried, up to 3 more times.


FILES IT PRODUCES
-----------------
  results/test1.csv   the numbers, one row per variant and level
  results/test1.png   the chart


HOW TO READ THE TABLE
---------------------
  payments_per_s   payments completed per second (higher is better)
  p95_ms           95% of payments finished at or below this time, retries included
  deadlocks        how many times a deadlock happened (attempts, not payments)
  failed_payments  payments that still failed after the retries


HOW TO READ THE CHART
---------------------
Three panels, 1 to 50 concurrent sessions on the horizontal axis. Red is IODKU, green is the
redesign.

  Payments per second   IODKU stays almost flat; the redesign keeps growing.
  p95 latency           IODKU climbs toward several hundred ms; the redesign stays low.
  Deadlocks             IODKU shows thousands per level; the redesign almost none.


WHAT YOU SHOULD SEE
-------------------
Numbers vary by laptop and by run, plus or minus 30%. The pattern must not change.
One real run (REPEATABLE READ, 20 s per level):

  sessions           1       5      10      25      50
  IODKU  pay/s     107     128     134     181     250
         p95 ms     12      65     130     297     506
         deadlocks   0   3,433   6,150  10,286  11,219
  Redesign pay/s    97     621   1,251   2,759   2,907
         p95 ms     14       9      10      12      27
         deadlocks   0       0       0       4       4

At 50 sessions: about 12 times more payments per second, p95 about 19 times lower, failed
payments 1,505 to 0. With 1 session both variants are the same.


WHAT TO SAY
-----------
- One session looks perfect. That is what DEV and QA see.
- The query did not become slower. Fifty sessions wait for each other: the locks are the
  bottleneck, not the CPU and not the query.
- With the live monitor you can show the transactions piling up in LOCK WAIT, and the
  X,GAP and X,INSERT_INTENTION locks waiting during the IODKU part.
- UPDATE first works because most rows already exist, so the UPDATE takes one record lock and
  no gap lock. The rare INSERT is the only place where a gap lock can still appear.


CAVEATS
-------
- Lab reproduction in Docker on a laptop, one run per level. Compare the ratios, not the
  absolute numbers. Do not mix these numbers with the production result of the real case.
- The workload is deliberately aggressive (hot merchants, 2 ms think time, 5% new keys) to
  make the problem visible in 20 seconds.
- The deadlock count is not monotonic: it can drop at 50 sessions because more transactions
  wait in line instead of deadlocking.
