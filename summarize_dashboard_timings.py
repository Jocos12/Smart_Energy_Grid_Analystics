"""Assignment I, section 7.4: summarise dashboard_timings.csv.

For each mode, takes the last 11 logged refreshes: the first is the warm-up (dropped),
the other 10 are the measured refreshes. Reports median, min and max in milliseconds
for each panel (server-side query duration) and for the whole dashboard (browser time).
"""
import csv
import statistics

rows = list(csv.DictReader(open("dashboard_timings.csv")))
out = [["mode", "item", "median_ms", "min_ms", "max_ms", "measured_runs"]]
print(f"{'Mode':10s}{'Item':34s}{'median':>10s}{'min':>10s}{'max':>10s}{'runs':>6s}")
for mode in ("Raw", "Aggregate"):
    r = [x for x in rows if x["mode"] == mode and x["client_elapsed_ms"]][-11:]
    r = r[1:]  # drop the warm-up
    if len(r) < 10:
        print(f"{mode}: only {len(r)} measured refreshes found (need 10 after one warm-up)")
    items = [(f"Panel {i} query", f"panel{i}_ms") for i in range(1, 6)] + \
            [("Server total (queries + figures)", "server_total_ms"), ("Whole dashboard (browser)", "client_elapsed_ms")]
    for label, col in items:
        v = [float(x[col]) for x in r]
        line = [mode, label, round(statistics.median(v), 1), round(min(v), 1), round(max(v), 1), len(v)]
        out.append(line)
        print(f"{mode:10s}{label:34s}{line[2]:>10.1f}{line[3]:>10.1f}{line[4]:>10.1f}{len(v):>6d}")
with open("dashboard_timings_summary.csv", "w", newline="") as f:
    csv.writer(f).writerows(out)
