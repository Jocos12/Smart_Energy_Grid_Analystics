import csv
import os
import re
from datetime import datetime, timedelta, timezone

import matplotlib.pyplot as plt
import psycopg2

CAT = timezone(timedelta(hours=2), "CAT")
DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "123"))


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


def natural(name):
    m = re.search(r"\d+", name)
    return (int(m.group()) if m else 0, name)


conn = psycopg2.connect(**DB)
conn.autocommit = True
cur = conn.cursor()
print(f"[{now()}] 5.2 regions and customer types (cleaned energy_readings JOIN meters)")

cur.execute("SELECT sum(energy_kwh), count(*) FROM energy_readings")
net_kwh, net_rows = cur.fetchone()
net_kwh = float(net_kwh)
cur.execute("SELECT count(*) FROM meters")
net_meters = cur.fetchone()[0]
net_per_meter = net_kwh / net_meters


def analyse(col, sort_key):
    cur.execute(f"SELECT {col}, count(*) FROM meters GROUP BY 1")
    counts = dict(cur.fetchall())
    cur.execute(f"""SELECT m.{col}, sum(r.energy_kwh), count(*), avg(r.power_kw)
                    FROM energy_readings r JOIN meters m ON m.meter_id = r.meter_id
                    GROUP BY 1""")
    rows = []
    for g, e, n, p in cur.fetchall():
        e = float(e)
        rows.append(dict(group=g, meters=counts[g], energy=e, per_meter=e / counts[g],
                         readings=n, readings_per_meter=n / counts[g],
                         kwh_per_reading=e / n, avg_kw=float(p),
                         vs_network=100 * (e / counts[g] - net_per_meter) / net_per_meter))
    rows.sort(key=lambda r: sort_key(r["group"]))
    return rows


def show(title, rows):
    print(f"\n=== {title} ===")
    print(f"{'Group':16s}{'Meters':>8s}{'Energy kWh':>16s}{'kWh/meter':>12s}{'vs net %':>10s}"
          f"{'Readings/meter':>16s}{'kWh/reading':>13s}")
    for r in rows:
        print(f"{str(r['group']):16s}{r['meters']:>8d}{r['energy']:>16,.1f}{r['per_meter']:>12,.1f}"
              f"{r['vs_network']:>10.1f}{r['readings_per_meter']:>16,.1f}{r['kwh_per_reading']:>13.4f}")
    print(f"{'Sum / check':16s}{sum(r['meters'] for r in rows):>8d}{sum(r['energy'] for r in rows):>16,.1f}")


regions = analyse("region", natural)
types = analyse("customer_type", lambda g: g)

print(f"\nNetwork: {net_meters} meters, {net_kwh:,.1f} kWh, {net_per_meter:,.1f} kWh per meter, {net_rows:,} readings")
show("Energy by region (28 days)", regions)
show("Energy by customer type (28 days)", types)

lo = min(regions, key=lambda r: r["per_meter"]); hi = max(regions, key=lambda r: r["per_meter"])
print(f"\nRegions: lowest per meter {lo['group']} {lo['per_meter']:,.1f}, highest {hi['group']} {hi['per_meter']:,.1f} "
      f"(ratio {hi['per_meter']/lo['per_meter']:.3f})")
lo = min(types, key=lambda r: r["per_meter"]); hi = max(types, key=lambda r: r["per_meter"])
print(f"Types  : lowest per meter {lo['group']} {lo['per_meter']:,.1f}, highest {hi['group']} {hi['per_meter']:,.1f} "
      f"(ratio {hi['per_meter']/lo['per_meter']:.3f})")

for name, rows in (("region", regions), ("customer_type", types)):
    with open(f"analysis_5_2_{name}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([name, "meters", "energy_kwh", "kwh_per_meter", "pct_vs_network_per_meter",
                    "readings", "readings_per_meter", "kwh_per_reading"])
        for r in rows:
            w.writerow([r["group"], r["meters"], round(r["energy"], 3), round(r["per_meter"], 3),
                        round(r["vs_network"], 2), r["readings"], round(r["readings_per_meter"], 2),
                        round(r["kwh_per_reading"], 5)])

fig, ax = plt.subplots(2, 2, figsize=(16, 9))
for j, (title, rows) in enumerate((("region", regions), ("customer type", types))):
    names = [str(r["group"]) for r in rows]
    ax[0, j].bar(names, [r["energy"] / 1000 for r in rows], color="#2b7bba")
    ax[0, j].set_title(f"Total energy by {title}"); ax[0, j].set_ylabel("Energy (MWh)")
    ax[1, j].bar(names, [r["per_meter"] for r in rows], color="#e08a1e")
    ax[1, j].axhline(net_per_meter, color="red", ls="--", label="Network average")
    ax[1, j].set_title(f"Energy per registered meter by {title}"); ax[1, j].set_ylabel("kWh per meter")
    ax[1, j].legend()
    for a in (ax[0, j], ax[1, j]):
        a.tick_params(axis="x", rotation=45)
fig.suptitle(f"Section 5.2 - generated {now()}")
fig.tight_layout()
fig.savefig("analysis_5_2_charts.png", dpi=150)
print("\nSaved: analysis_5_2_charts.png, analysis_5_2_region.csv, analysis_5_2_customer_type.csv")
conn.close()
plt.show()