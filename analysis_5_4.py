import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import psycopg2

import smart_meter_simulator as s

CAT = timezone(timedelta(hours=2), "CAT")
DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "123"))

# ---- Detection rule, fixed BEFORE the labels are read ----
# baseline_kw = median power of the same meter, same 15-minute slot of the day,
#               same day type (weekday / weekend), over the 28 days
# ratio       = power_kw / baseline_kw
# spike if ratio > UPPER, drop if ratio < LOWER
UPPER, LOWER, MIN_N = 1.8, 0.4, 5
EDGES = [0.1, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.8, 2.5]


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


t_all = time.perf_counter()
conn = psycopg2.connect(**DB)
conn.autocommit = True
cur = conn.cursor()

# ================= STAGE 1: detection on cleaned readings (no labels used) =================
print(f"[{now()}] STAGE 1: scoring every cleaned reading against its meter baseline")
cur.execute("""
CREATE TEMP TABLE scored AS
WITH r AS (
  SELECT meter_id, event_time, power_kw,
         extract(hour   FROM event_time AT TIME ZONE 'Africa/Kigali')::int * 4
       + extract(minute FROM event_time AT TIME ZONE 'Africa/Kigali')::int / 15 AS slot,
         extract(isodow FROM event_time AT TIME ZONE 'Africa/Kigali')::int >= 6  AS weekend
  FROM energy_readings
), base AS (
  SELECT meter_id, slot, weekend,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY power_kw) AS med,
         count(*) AS n
  FROM r GROUP BY meter_id, slot, weekend
)
SELECT r.meter_id, r.event_time, r.power_kw, b.med AS baseline_kw, b.n AS baseline_n,
       r.power_kw / NULLIF(b.med, 0) AS ratio
FROM r JOIN base b USING (meter_id, slot, weekend)
""")
cur.execute("SELECT count(*) FROM scored")
n_scored = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM scored WHERE baseline_n < %s", (MIN_N,))
n_nobase = cur.fetchone()[0]
print(f"[{now()}] scored readings: {n_scored:,}  (without enough baseline, not scored: {n_nobase:,})")

print("\nHistogram of ratio = power_kw / meter baseline (all scored readings)")
print(f"{'ratio range':>14s}{'readings':>14s}{'min':>10s}{'max':>10s}")
cur.execute("""SELECT width_bucket(ratio, %s::float8[]) AS b, count(*), min(ratio), max(ratio)
               FROM scored WHERE baseline_n >= %s GROUP BY 1 ORDER BY 1""", (EDGES, MIN_N))
for b, n, lo_v, hi_v in cur.fetchall():
    lo = "0" if b == 0 else str(EDGES[b - 1])
    hi = str(EDGES[b]) if b < len(EDGES) else "inf"
    print(f"{lo + ' - ' + hi:>14s}{n:>14,d}{lo_v:>10.3f}{hi_v:>10.3f}")

print(f"\nRule: spike if ratio > {UPPER}, drop if ratio < {LOWER}, baseline needs >= {MIN_N} observations")
cur.execute("DROP TABLE IF EXISTS anomaly_flags")
cur.execute("""CREATE TABLE anomaly_flags AS
               SELECT meter_id, event_time, power_kw, baseline_kw, ratio,
                      CASE WHEN ratio > %s THEN 'spike' ELSE 'drop' END AS flag_type
               FROM scored
               WHERE baseline_n >= %s AND (ratio > %s OR ratio < %s)""", (UPPER, MIN_N, UPPER, LOWER))
cur.execute("SELECT flag_type, count(*), count(DISTINCT meter_id) FROM anomaly_flags GROUP BY 1 ORDER BY 1")
tot_flags = 0
for ft, n, m in cur.fetchall():
    tot_flags += n
    print(f"  flags of type {ft:5s}: {n:,} readings on {m} meters")
cur.execute("SELECT count(DISTINCT meter_id) FROM anomaly_flags")
print(f"  total flags: {tot_flags:,} on {cur.fetchone()[0]} distinct meters")
print("\nSample of flagged readings (meter_id, event_time):")
print(f"{'meter_id':>12s}  {'event_time':25s}{'power_kw':>10s}{'baseline':>10s}{'ratio':>8s}  type")
cur.execute("SELECT meter_id, event_time, power_kw, baseline_kw, ratio, flag_type "
            "FROM anomaly_flags ORDER BY meter_id, event_time LIMIT 12")
for m, t, p, bl, rt, ft in cur.fetchall():
    print(f"{m:>12d}  {t.strftime('%Y-%m-%d %H:%M:%S%z'):25s}{p:>10.3f}{bl:>10.3f}{rt:>8.2f}  {ft}")

# ================= STAGE 2: evaluation against the injected events (labels used only here) =================
print(f"\n[{now()}] STAGE 2: comparing the flags with anomaly_events()")
events = s.anomaly_events()
for e in events:
    e["start"] = datetime.fromisoformat(e["start_time"])
    e["end"] = datetime.fromisoformat(e["end_time"])
events_by_meter = defaultdict(list)
for e in events:
    events_by_meter[e["meter_id"]].append(e)

cur.execute("SELECT meter_id, event_time FROM anomaly_flags")
flags = cur.fetchall()
flags_by_meter = defaultdict(list)
for m, t in flags:
    flags_by_meter[m].append(t)

print(f"\n{'#':>3s} {'type':14s}{'meter_id':>12s}  {'start':20s}{'end':20s}{'flags':>6s}  result")
detected, missed, inside_rows = 0, [], 0
by_type = defaultdict(lambda: [0, 0])
for i, e in enumerate(events, 1):
    hits = [t for t in flags_by_meter.get(e["meter_id"], []) if e["start"] <= t < e["end"]]
    ok = len(hits) > 0
    detected += ok
    by_type[e["event_type"]][1] += 1
    by_type[e["event_type"]][0] += ok
    if not ok:
        missed.append(e)
    cur.execute("SELECT count(*) FROM energy_readings WHERE meter_id=%s AND event_time>=%s AND event_time<%s",
                (e["meter_id"], e["start"], e["end"]))
    inside_rows += cur.fetchone()[0]
    print(f"{i:>3d} {e['event_type']:14s}{e['meter_id']:>12d}  {e['start'].strftime('%m-%d %H:%M'):20s}"
          f"{e['end'].strftime('%m-%d %H:%M'):20s}{len(hits):>6d}  {'DETECTED' if ok else 'MISSED'}")

print(f"\nDetected events : {detected} / {len(events)}")
print(f"Missed events   : {len(missed)} / {len(events)}")
for t, (d, n) in sorted(by_type.items()):
    print(f"  {t:14s}: {d} detected out of {n}")
for e in missed:
    cur.execute("SELECT count(*), min(ratio), max(ratio) FROM scored WHERE meter_id=%s AND event_time>=%s AND event_time<%s",
                (e["meter_id"], e["start"], e["end"]))
    n, lo, hi = cur.fetchone()
    print(f"  missed: meter {e['meter_id']} {e['event_type']} {e['start']:%m-%d %H:%M}: "
          f"{n} readings, ratio min={lo} max={hi}")

false_flags = [(m, t) for m, t in flags
               if not any(e["start"] <= t < e["end"] for e in events_by_meter.get(m, []))]
cur.execute("SELECT count(*) FROM energy_readings")
total_rows = cur.fetchone()[0]
outside = total_rows - inside_rows
fmeters = {m for m, _ in false_flags}
print(f"\nObserved readings in total              : {total_rows:,}")
print(f"Observed readings inside injected events : {inside_rows:,}")
print(f"Observed readings outside injected events: {outside:,}")
print(f"False flags (outside every injected interval of the meter): {len(false_flags):,}")
print(f"False flags as % of readings outside injected intervals  : {100 * len(false_flags) / outside:.6f} %")
print(f"Meters with at least one false flag: {len(fmeters)}")
print(f"Percentage of meters affected by false flags: {100 * len(fmeters) / 4000:.4f} %  (meters / 4000 x 100)")
if false_flags:
    print("\nFirst false flags:")
    for m, t in false_flags[:10]:
        print(f"  meter {m}  {t:%Y-%m-%d %H:%M}")
conn.close()
print(f"\n[{now()}] done in {time.perf_counter() - t_all:.0f} s")