"""Assignment I, section 2.1: capture the full stream as CSV batches, then COPY into energy_readings.

Password comes from the PGPASSWORD environment variable.
"""
import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg2

import smart_meter_simulator as s

CAT = timezone(timedelta(hours=2), "CAT")
DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "YOUR_PASSWORD"))
OUT_DIR = "csv_batches"
BATCH_ROWS = 500_000
FIELDS = s.dataset_info()["reading_fields"]


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


info = s.dataset_info()
expected = info["expected_counts"]["emitted_readings"]
print(f"[{now()}] dataset_info(): planned={info['planned_readings']:,} expected emitted={expected:,}")
print(f"  full expected_counts: {info['expected_counts']}")

conn = psycopg2.connect(**DB)
with conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM energy_readings")
    if cur.fetchone()[0] != 0:
        sys.exit("energy_readings is not empty. Run TRUNCATE energy_readings first.")
conn.commit()

os.makedirs(OUT_DIR, exist_ok=True)

# ---------- Phase 1: generate CSV batches ----------
t_total = time.perf_counter()
t_gen = time.perf_counter()
print(f"[{now()}] PHASE 1: generating CSV batches")
consumed = 0
csv_rows = 0
files = []
batch_no = 0
f = None
writer = None
rows_in_batch = 0
for rec in s.iter_readings():
    if f is None:
        batch_no += 1
        path = os.path.join(OUT_DIR, f"batch_{batch_no:04d}.csv")
        files.append(path)
        f = open(path, "w", newline="", encoding="utf-8")
        writer = csv.writer(f)
        rows_in_batch = 0
    writer.writerow([rec[k] for k in FIELDS])
    consumed += 1
    csv_rows += 1
    rows_in_batch += 1
    if rows_in_batch == BATCH_ROWS:
        f.close()
        f = None
        print(f"[{now()}] consumed={consumed:,} ({100 * consumed / expected:.1f}%) files={len(files)}")
if f is not None:
    f.close()
gen_seconds = time.perf_counter() - t_gen
print(f"[{now()}] generation done: consumed={consumed:,} csv_rows={csv_rows:,} in {gen_seconds:.1f} s")

# ---------- Phase 2: COPY into energy_readings ----------
print(f"[{now()}] PHASE 2: loading with COPY")
t_load = time.perf_counter()
cols = ",".join(FIELDS)
for i, path in enumerate(files, 1):
    with open(path, "r", encoding="utf-8") as fh, conn.cursor() as cur:
        cur.copy_expert(f"COPY energy_readings ({cols}) FROM STDIN WITH (FORMAT csv)", fh)
    conn.commit()
    print(f"[{now()}] loaded file {i}/{len(files)}")
load_seconds = time.perf_counter() - t_load
total_seconds = time.perf_counter() - t_total

with conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM energy_readings")
    in_db = cur.fetchone()[0]
conn.close()

print(f"[{now()}] DONE")
print(f"  expected emitted_readings  : {expected:,}")
print(f"  dictionaries consumed      : {consumed:,}")
print(f"  CSV data rows              : {csv_rows:,}")
print(f"  committed rows in table    : {in_db:,}")
print(f"  all agree                  : {consumed == csv_rows == in_db == expected}")
print(f"  CSV generation seconds     : {gen_seconds:.1f}")
print(f"  database load seconds      : {load_seconds:.1f}")
print(f"  total elapsed seconds      : {total_seconds:.1f}")
