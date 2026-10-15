import os
from datetime import datetime, timedelta, timezone

import psycopg2

CAT = timezone(timedelta(hours=2), "CAT")
DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "123"))
DAYS, PER_DAY = 28, 96
D_START = "2026-09-21 00:00:00+02"
D_END = "2026-09-22 00:00:00+02"


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


conn = psycopg2.connect(**DB)
conn.autocommit = True
cur = conn.cursor()
print(f"[{now()}] 5.3 reporting quality on cleaned energy_readings")

# 1. Completeness: network and per region
cur.execute("SELECT region, count(*) FROM meters GROUP BY 1")
meters = dict(cur.fetchall())
cur.execute("""SELECT m.region, count(*) FROM energy_readings r
               JOIN meters m ON m.meter_id = r.meter_id GROUP BY 1""")
observed = dict(cur.fetchall())


def natural(name):
    digits = "".join(c for c in name if c.isdigit())
    return int(digits) if digits else 0


print("\n=== Completeness over all 28 days ===")
print(f"{'Scope':12s}{'Meters':>8s}{'Planned':>12s}{'Observed':>12s}{'Missing':>10s}{'Completeness %':>16s}")
tot_m = tot_p = tot_o = 0
for region in sorted(meters, key=natural):
    planned = meters[region] * DAYS * PER_DAY
    obs = observed.get(region, 0)
    tot_m += meters[region]; tot_p += planned; tot_o += obs
    print(f"{region:12s}{meters[region]:>8d}{planned:>12,d}{obs:>12,d}{planned - obs:>10,d}{100 * obs / planned:>16.4f}")
print(f"{'Network':12s}{tot_m:>8d}{tot_p:>12,d}{tot_o:>12,d}{tot_p - tot_o:>10,d}{100 * tot_o / tot_p:>16.4f}")
print("Expected network: planned 10,752,000, observed 10,643,735, missing 108,265")

# 2. Daily total for 21 September: cut-off at 00:00 on 22 September vs all arrivals
cur.execute(f"""SELECT sum(energy_kwh) FILTER (WHERE received_time <= '{D_END}'),
                       sum(energy_kwh),
                       count(*) FILTER (WHERE received_time <= '{D_END}'),
                       count(*)
                FROM energy_readings
                WHERE event_time >= '{D_START}' AND event_time < '{D_END}'""")
early, final, n_early, n_final = cur.fetchone()
early, final = float(early), float(final)
diff = final - early
print("\n=== Energy for event_time on 21 September (CAT) ===")
print(f"Received by 00:00 on 22 Sep : {early:14,.3f} kWh  ({n_early:,} readings)")
print(f"All arrivals (final)        : {final:14,.3f} kWh  ({n_final:,} readings)")
print(f"Difference                  : {diff:14,.3f} kWh  = {100 * diff / final:.4f} % of the final total")
print(f"Readings not yet received   : {n_final - n_early:,}")
planned_day = tot_m * PER_DAY
print(f"Planned readings that day   : {planned_day:,}  -> never generated: {planned_day - n_final:,} "
      f"({100 * (planned_day - n_final) / planned_day:.3f} %)")

cur.execute(f"""SELECT extract(hour FROM event_time AT TIME ZONE 'Africa/Kigali')::int AS h,
                       count(*), sum(energy_kwh)
                FROM energy_readings
                WHERE event_time >= '{D_START}' AND event_time < '{D_END}'
                  AND received_time > '{D_END}'
                GROUP BY 1 ORDER BY 1""")
print("\nReadings of 21 Sep arriving after midnight, by event hour (CAT):")
print(f"{'Hour':>6s}{'Readings':>12s}{'kWh':>14s}")
for h, n, e in cur.fetchall():
    print(f"{h:>6d}{n:>12,d}{float(e):>14,.3f}")
conn.close()
print(f"\n[{now()}] done")