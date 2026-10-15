"""Assignment I, section 7.3: compare the numerical data behind the five panels of Raw and Aggregate.

Period 22 Sep 00:00 to 29 Sep 00:00 CAT (exclusive), all regions, meter 1000000000.
Requirements: identical keys and reading counts, energy differences <= 0.001 kWh,
completeness differences <= 0.000001 percentage points (before rounding).
Writes dashboard_export_<mode>_panel<k>.csv and dashboard_verification.csv.
"""
import csv
import os

import psycopg2

import dashboard_queries as dq

DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "YOUR_PASSWORD"))
P = dq.make_params("2026-09-22", "2026-09-28", 1000000000)

conn = psycopg2.connect(**DB)
conn.autocommit = True
cur = conn.cursor()

data = {}
for mode in ("Raw", "Aggregate"):
    for k in range(1, 6):
        rows = dq.run_panel(cur, mode, k, P)
        data[(mode, k)] = rows
        with open(f"dashboard_export_{mode}_panel{k}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(dq.COLUMNS[k])
            w.writerows(rows)


def keyed(k, rows):
    kl = 2 if k == 1 else 1
    return {tuple(r[:kl]): r[kl:] for r in rows}


print(f"{'Panel':45s}{'rows':>6s}{'keys':>8s}{'counts':>8s}{'max |dE| kWh':>16s}{'max |dC| pp':>14s}  result")
out = [["panel", "compared_rows", "identical_keys", "identical_counts", "max_abs_energy_diff_kwh",
        "max_abs_completeness_diff_pp", "pass"]]
for k in range(1, 6):
    a, b = keyed(k, data[("Raw", k)]), keyed(k, data[("Aggregate", k)])
    same_keys = set(a) == set(b)
    max_e = max_c = 0.0
    same_counts = True
    for key in set(a) & set(b):
        ra, rb = a[key], b[key]
        if k < 5:
            max_e = max(max_e, abs(float(ra[0]) - float(rb[0])))
            same_counts &= int(ra[1]) == int(rb[1])
        else:
            same_counts &= int(ra[0]) == int(rb[0]) and int(ra[1]) == int(rb[1])
            max_c = max(max_c, abs(float(ra[2]) - float(rb[2])))
    ok = same_keys and same_counts and max_e <= 0.001 and max_c <= 0.000001
    print(f"{dq.PANELS[k]:45s}{len(a):>6d}{str(same_keys):>8s}{str(same_counts):>8s}{max_e:>16.9f}{max_c:>14.9f}  {'PASS' if ok else 'FAIL'}")
    out.append([dq.PANELS[k], len(a), same_keys, same_counts, f"{max_e:.9f}", f"{max_c:.9f}", ok])

with open("dashboard_verification.csv", "w", newline="") as f:
    csv.writer(f).writerows(out)
print("\nPanel 5 (Raw) sample:")
for r in data[("Raw", 5)][:3]:
    print("  ", r)
print("Panel 5 (Aggregate) sample:")
for r in data[("Aggregate", 5)][:3]:
    print("  ", r)
conn.close()
