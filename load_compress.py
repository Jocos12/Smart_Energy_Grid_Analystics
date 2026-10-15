import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg2

CAT = timezone(timedelta(hours=2), "CAT")
DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "YOUR_PASSWORD"))
SOURCE = "energy_readings"
TARGETS = ["energy_time_compressed", "energy_meter_compressed"]


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


conn = psycopg2.connect(**DB)
conn.autocommit = True
cur = conn.cursor()

for t in TARGETS:
    cur.execute(f"SELECT count(*) FROM {t}")
    if cur.fetchone()[0] != 0:
        sys.exit(f"{t} is not empty. TRUNCATE it first (the experiment needs empty tables).")

start = datetime.now(CAT)
cutoff = start - timedelta(hours=48)
with open("compression_cutoff.txt", "w") as f:
    f.write(cutoff.isoformat())
print(f"[{now()}] experiment start = {start.isoformat()}  cutoff = {cutoff.isoformat()}")

cur.execute("""SELECT range_start, range_end FROM timescaledb_information.chunks
               WHERE hypertable_name = %s ORDER BY range_start""", (SOURCE,))
chunks = cur.fetchall()
print(f"[{now()}] {len(chunks)} source chunks")

log = []
for t in TARGETS:
    for rs, re_ in chunks:
        t0 = time.perf_counter()
        cur.execute(f"INSERT INTO {t} SELECT * FROM {SOURCE} WHERE event_time >= %s AND event_time < %s",
                    (rs, re_))
        n = cur.rowcount
        load_s = time.perf_counter() - t0

        cur.execute("""SELECT format('%%I.%%I', chunk_schema, chunk_name)
                       FROM timescaledb_information.chunks
                       WHERE hypertable_name = %s AND range_start = %s""", (t, rs))
        chunk = cur.fetchone()[0]

        compressed, comp_s = False, 0.0
        if re_ <= cutoff:
            t1 = time.perf_counter()
            cur.execute("SELECT compress_chunk(%s::regclass)", (chunk,))
            comp_s = time.perf_counter() - t1
            compressed = True
        log.append([t, chunk, rs.isoformat(), re_.isoformat(), n, round(load_s, 3), compressed, round(comp_s, 3)])
        print(f"[{now()}] {t:24s} {rs:%Y-%m-%d %H:%M} rows={n:7d} load={load_s:6.1f}s "
              f"compressed={compressed} compress={comp_s:6.1f}s")

for t in TARGETS:
    cur.execute(f"ANALYZE {t}")

with open("compression_chunk_log.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["table", "chunk", "range_start", "range_end", "original_rows",
                "load_seconds", "compressed", "compress_seconds"])
    w.writerows(log)

print("\n=== SUMMARY ===")
for t in TARGETS:
    rows = [r for r in log if r[0] == t]
    comp = [r for r in rows if r[6]]
    print(f"{t}: chunks={len(rows)} compressed={len(comp)} "
          f"rows_total={sum(r[4] for r in rows)} rows_in_compressed={sum(r[4] for r in comp)} "
          f"load_seconds={sum(r[5] for r in rows):.1f} compression_seconds={sum(r[7] for r in comp):.1f}")
conn.close()
print(f"[{now()}] done")