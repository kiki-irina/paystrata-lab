#!/usr/bin/env python3
"""TEST 2 chart: IODKU under REPEATABLE READ versus READ COMMITTED, ramp 1 -> 50 sessions.
Panels: payments per second, p95 latency, deadlocks. No redesign in this test.

  python plot_isolation.py     reads results/test2_rr.csv and results/test2_rc.csv,
                               writes results/test2.png

First run:
  docker-compose run --rm loadgen ramp --variants iodku --out test2_rr
  docker-compose run --rm loadgen ramp --variants iodku --isolation "READ COMMITTED" --out test2_rc
"""
import csv

import matplotlib.pyplot as plt


def load(path):
    return [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["variant"] == "iodku"]


runs = [("REPEATABLE READ (MySQL default)", load("results/test2_rr.csv"), "#2F5DA8"),
        ("READ COMMITTED", load("results/test2_rc.csv"), "#F59E0B")]
panels = [("payments_per_s", "Payments per second", "higher is better", "{:,.0f}"),
          ("p95_ms", "p95 latency (ms)", "lower is better", "{:,.0f} ms"),
          ("deadlocks", "Deadlocks per 20 s level", "lower is better", "{:,.0f}")]

fig, axes = plt.subplots(1, 3, figsize=(16, 5.2))
for ax, (col, title, hint, fmt) in zip(axes, panels):
    for label, data, color in runs:
        xs = [int(d["threads"]) for d in data]
        ys = [float(d[col]) for d in data]
        ax.plot(xs, ys, marker="o", lw=2.4, color=color, label=label)
        ax.annotate(fmt.format(ys[-1]), (xs[-1], ys[-1]), textcoords="offset points",
                    xytext=(8, 0), ha="left", va="center", fontsize=11, fontweight="bold", color=color)
    ax.set_title(f"{title}\n({hint})", fontsize=12)
    ax.set_xlabel("concurrent sessions")
    ax.set_xticks([1, 5, 10, 25, 50])
    ax.grid(alpha=0.3)
    ax.set_ylim(bottom=0)
    ax.set_xlim(0, 64)

handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, fontsize=12,
           bbox_to_anchor=(0.5, 0.05))
fig.suptitle("Same IODKU statement: only the isolation level changed",
             fontsize=15, fontweight="bold")
fig.text(0.5, 0.01,
         "Lab reproduction (PayStrata demo, Percona Server 8.4 in Docker): 20 s per level, single run. "
         "Compare the ratios, not the absolute numbers.",
         ha="center", fontsize=9, color="#555")
plt.tight_layout(rect=[0, 0.1, 1, 0.94])
plt.savefig("results/test2.png", dpi=160)
print("Saved results/test2.png")
