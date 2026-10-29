#!/usr/bin/env python3
"""TEST 1 chart: IODKU versus UPDATE first, ramp 1 -> 50 sessions.
Panels: payments per second, p95 latency, deadlocks.

  python plot.py                                   reads results/test1.csv, writes results/test1.png
  python plot.py results/latest.csv results/x.png  any other CSV and output name

First run:  docker-compose run --rm loadgen ramp --out test1
"""
import csv
import sys
from collections import defaultdict

import matplotlib.pyplot as plt

src = sys.argv[1] if len(sys.argv) > 1 else "results/test1.csv"
dst = sys.argv[2] if len(sys.argv) > 2 else "results/test1.png"

rows = list(csv.DictReader(open(src, encoding="utf-8")))
series = defaultdict(list)
for r in rows:
    series[r["variant"]].append(r)

panels = [("payments_per_s", "Payments per second", "higher is better", "{:,.0f}"),
          ("p95_ms", "p95 latency (ms)", "lower is better", "{:,.0f} ms"),
          ("deadlocks", "Deadlocks per 20 s level", "lower is better", "{:,.0f}")]
styles = {
    "iodku": ("BEFORE: INSERT ... ON DUPLICATE KEY UPDATE", "#d9534f"),
    "update_insert": ("AFTER: UPDATE first, INSERT only if missing", "#2e9e5b"),
}

fig, axes = plt.subplots(1, 3, figsize=(16, 5.2))
for ax, (col, title, hint, fmt) in zip(axes, panels):
    for variant, data in series.items():
        label, color = styles.get(variant, (variant, None))
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
    ax.set_xlim(0, 64)   # room on the right for the end-value labels

handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, fontsize=12,
           bbox_to_anchor=(0.5, 0.05))
fig.suptitle("Same server, same data, same traffic: only the SQL statement changed",
             fontsize=15, fontweight="bold")
fig.text(0.5, 0.01,
         "Lab reproduction (PayStrata demo, Percona Server 8.4 in Docker): 20 s per level, single run. "
         "Compare the ratios, not the absolute numbers.",
         ha="center", fontsize=9, color="#555")
plt.tight_layout(rect=[0, 0.1, 1, 0.94])
plt.savefig(dst, dpi=160)
print(f"Saved {dst}")
