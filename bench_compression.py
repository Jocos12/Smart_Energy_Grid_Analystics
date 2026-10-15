import csv
import os
import socket
import statistics
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg2

CAT = timezone(timedelta(hours=2), "CAT")
DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "YOUR_PASSWORD"))
TABLES = ["energy_readings", "energy_time_compressed", "energy_meter_compressed"]
MACHINE = socket.gethostname()
CLIENT = "Python 3.12 + psycopg2 2.9, time.perf_counter()"
WARMUPS, RUNS = 1, 5
TOL = 0.001

W22_29 = "event_time >= '2026-09-22 00:00:00+02' AND event_time < '2026-09-29 00:00:00+02'"
QUERIES = {
    "Q1": ("SELECT time_bucket('1 hour', event_time, 'Africa/Kigali') AS hour_cat, avg(power_kw) "
           "FROM {t} WHERE event_time >= '2026-09-21 00:00:00+02' AND event_time < '2026-09-22 00:00:00+02' "
           "GROUP BY 1 ORDER BY 1"),
    "Q2": (f"SELECT event_time, sum(power_kw) AS total_power_kw FROM {{t}} WHERE {W22_29} "
           "GROUP BY event_time ORDER BY total_power_kw DESC, event_time ASC LIMIT 10"),
    "Q3": "SELECT meter_id, sum(energy_kwh) FROM {t} GROUP BY meter_id ORDER BY meter_id",
    "Q4": (f"SELECT sum(energy_kwh), avg(power_kw), max(power_kw) FROM {{t}} "
           f"WHERE meter_id = 1000000000 AND {W22_29}"),
    "Q5": "SELECT count(*), sum(energy_kwh), avg(power_kw), min(power_kw), max(power_kw) FROM {t}",
}


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " CAT"


def run(cur, sql):
    start = now()
    t0 = time.perf_counter()
    cur.execute(sql)
    rows = cur.fetchall()
    ms = (time.perf_counter() - t0) * 1000
    return ms, rows, start, now()


def num(v):
    return float(v) if isinstance(v, (Decimal, float, int)) and not isinstance(v, bool) else v


def same(a, b):
    if len(a) != len(b):
        return False
    for ra, rb in zip(a, b):
        for x, y in zip(ra, rb):
            x, y = num(x), num(y)
            if isinstance(x, float) or isinstance(y, float):
                if abs(x - y) > TOL:
                    return False
            elif x != y:
                return False
    return True


conn = psycopg2.connect(**DB)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SHOW timezone")
print(f"[{now()}] machine={MACHINE} client={CLIENT} session timezone={cur.fetchone()[0]}")

runs_rows, summary_rows, reference = [], [], {}
for q, template in QUERIES.items():
    for table in TABLES:
        sql = template.format(t=table)
        session_start = time.perf_counter()
        run(cur, sql)  # warm-up (not recorded in the statistics)
        times, last_rows = [], None
        for i in range(1, RUNS + 1):
            ms, rows, start, end = run(cur, sql)
            times.append(ms)
            last_rows = rows
            runs_rows.append([q, table, i, start, end, round(ms, 3), MACHINE, CLIENT])
        session_seconds = time.perf_counter() - session_start
        if table == TABLES[0]:
            reference[q] = last_rows
        ok = same(reference[q], last_rows)
        summary_rows.append([q, table, round(statistics.median(times), 3), round(min(times), 3),
                             round(max(times), 3), round(session_seconds, 2), ok])
        print(f"[{now()}] {q} {table:24s} median={statistics.median(times):10.1f} ms "
              f"min={min(times):10.1f} max={max(times):10.1f} session={session_seconds:6.1f}s match={ok}")

with open("benchmark_compression_runs.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["query", "table", "run", "start_cat", "end_cat", "duration_ms", "machine", "client"])
    w.writerows(runs_rows)
with open("benchmark_compression_summary.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["query", "table", "median_ms", "min_ms", "max_ms", "session_seconds", "results_match_reference"])
    w.writerows(summary_rows)

print("\nQuery  Table                    Median(ms)   Min(ms)    Max(ms)  Session(s)  Match")
for r in summary_rows:
    print(f"{r[0]:5s}  {r[1]:24s} {r[2]:10.1f} {r[3]:10.1f} {r[4]:10.1f} {r[5]:10.1f}  {r[6]}")

for q in ["Q2", "Q4"]:
    for table in TABLES:
        cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + QUERIES[q].format(t=table))
        plan = "\n".join(r[0] for r in cur.fetchall())
        with open(f"explain_{q}_{table}.txt", "w") as f:
            f.write(plan)
        print(f"\n=== EXPLAIN (ANALYZE, BUFFERS) {q} on {table} ===\n{plan}")
conn.close()
print(f"\n[{now()}] benchmark finished")