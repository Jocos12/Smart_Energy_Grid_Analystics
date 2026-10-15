import csv
import os
from datetime import datetime, timedelta, timezone

import matplotlib.pyplot as plt
import psycopg2

CAT = timezone(timedelta(hours=2), "CAT")
DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "123"))
TZ = "Africa/Kigali"


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


conn = psycopg2.connect(**DB)
conn.autocommit = True
cur = conn.cursor()
print(f"[{now()}] 5.1 demand patterns on cleaned energy_readings")

# 1. Energy per CAT day
cur.execute(f"""SELECT time_bucket('1 day', event_time, '{TZ}') AS day_cat,
                       sum(energy_kwh), count(*)
                FROM energy_readings GROUP BY 1 ORDER BY 1""")
daily = [(d.astimezone(CAT), float(e), n) for d, e, n in cur.fetchall()]

# 2. Energy per seven-day period (1, 8, 15, 22 September)
cur.execute(f"""SELECT ((event_time AT TIME ZONE '{TZ}')::date - DATE '2026-09-01') / 7 AS p,
                       sum(energy_kwh), count(*)
                FROM energy_readings GROUP BY 1 ORDER BY 1""")
weekly = [(date_start, float(e), n) for (p, e, n), date_start in
          zip(cur.fetchall(), ["1 Sep-7 Sep", "8 Sep-14 Sep", "15 Sep-21 Sep", "22 Sep-28 Sep"])]

# 3. Network demand per 15-minute interval (kW)
cur.execute("""SELECT event_time, sum(power_kw), count(*)
               FROM energy_readings GROUP BY event_time ORDER BY event_time""")
demand = [(t.astimezone(CAT), float(kw), n) for t, kw, n in cur.fetchall()]
top3 = sorted(demand, key=lambda r: (-r[1], r[0]))[:3]

# 4. Average network demand by CAT hour of day (for the pattern discussion)
hourly = {}
for t, kw, _ in demand:
    hourly.setdefault(t.hour, []).append(kw)
hour_profile = [(h, sum(v) / len(v)) for h, v in sorted(hourly.items())]

# Checks
total_all = sum(r[1] for r in daily)
print(f"\nSum of daily totals   : {total_all:,.3f} kWh")
print(f"Sum of weekly totals  : {sum(r[1] for r in weekly):,.3f} kWh")
cur.execute("SELECT sum(energy_kwh), count(*) FROM energy_readings")
t_all, n_all = cur.fetchone()
print(f"Whole table           : {float(t_all):,.3f} kWh over {n_all:,} rows")

print("\n=== Energy per CAT day (kWh) ===")
for d, e, n in daily:
    print(f"{d:%Y-%m-%d} {d:%a}  {e:14,.1f} kWh  readings={n}")

print("\n=== Energy per seven-day period (kWh) ===")
for label, e, n in weekly:
    print(f"{label:14s} {e:14,.1f} kWh  readings={n}")

print("\n=== Three highest 15-minute network demand intervals ===")
for i, (t, kw, n) in enumerate(top3, 1):
    print(f"#{i}  {t:%Y-%m-%d %a %H:%M} CAT   {kw:12,.1f} kW   meters reporting={n}")

weekday = [e for d, e, _ in daily if d.weekday() < 5]
weekend = [e for d, e, _ in daily if d.weekday() >= 5]
print(f"\nAverage weekday energy: {sum(weekday)/len(weekday):,.1f} kWh/day ({len(weekday)} days)")
print(f"Average weekend energy: {sum(weekend)/len(weekend):,.1f} kWh/day ({len(weekend)} days)")
low = min(hour_profile, key=lambda r: r[1])
high = max(hour_profile, key=lambda r: r[1])
print(f"Average demand lowest at {low[0]:02d}:00 ({low[1]:,.0f} kW), highest at {high[0]:02d}:00 ({high[1]:,.0f} kW)")

# CSV outputs
with open("analysis_5_1_daily.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["day_cat", "weekday", "energy_kwh", "readings"])
    w.writerows([[f"{d:%Y-%m-%d}", f"{d:%a}", round(e, 3), n] for d, e, n in daily])
with open("analysis_5_1_weekly.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["period", "energy_kwh", "readings"])
    w.writerows([[l, round(e, 3), n] for l, e, n in weekly])
with open("analysis_5_1_top3_demand.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["rank", "event_time_cat", "network_kw", "meters_reporting"])
    w.writerows([[i, f"{t:%Y-%m-%d %H:%M}", round(kw, 3), n] for i, (t, kw, n) in enumerate(top3, 1)])

# Charts
fig, ax = plt.subplots(2, 2, figsize=(16, 9))
ax[0, 0].bar([f"{d:%d}" for d, _, _ in daily], [e / 1000 for _, e, _ in daily], color="#2b7bba")
ax[0, 0].set_title("Network energy per CAT day (September 2026)")
ax[0, 0].set_xlabel("Day of September"); ax[0, 0].set_ylabel("Energy (MWh)")

ax[0, 1].bar([l for l, _, _ in weekly], [e / 1000 for _, e, _ in weekly], color="#e08a1e")
ax[0, 1].set_title("Network energy per seven-day period")
ax[0, 1].set_ylabel("Energy (MWh)")

ax[1, 0].plot([h for h, _ in hour_profile], [kw for _, kw in hour_profile], marker="o", color="#2a9d5c")
ax[1, 0].set_title("Average network demand by CAT hour of day")
ax[1, 0].set_xlabel("Hour (CAT)"); ax[1, 0].set_ylabel("Demand (kW)")
ax[1, 0].set_xticks(range(0, 24, 2))

ax[1, 1].plot([t for t, _, _ in demand], [kw for _, kw, _ in demand], lw=0.6, color="#555555")
ax[1, 1].scatter([t for t, _, _ in top3], [kw for _, kw, _ in top3], color="red", zorder=3, label="Top 3 peaks")
ax[1, 1].set_title("Network demand per 15-minute interval")
ax[1, 1].set_ylabel("Demand (kW)"); ax[1, 1].legend()
fig.autofmt_xdate()
fig.suptitle(f"Section 5.1 - generated {now()}")
fig.tight_layout()
fig.savefig("analysis_5_1_charts.png", dpi=150)
print("\nSaved: analysis_5_1_charts.png and three CSV files")
conn.close()
plt.show()