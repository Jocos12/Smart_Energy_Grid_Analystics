"""Assignment I, section 7: the five panel queries of the Raw and Aggregate dashboards.

Shared by dashboard_app.py (the two dashboards) and verify_dashboards.py (7.3 checks).
Raw mode reads energy_readings (joined to meters where needed); Aggregate mode reads
only the continuous aggregates (meters is queried only for registered meter counts).
"""
from datetime import date, timedelta

SLOTS_PER_DAY = 96
ORIGIN = "2026-09-01 00:00:00+02"   # first 7-day period starts on 1 September (as in 5.1)

PANELS = {
    1: "Hourly energy by region (kWh)",
    2: "Daily network energy (kWh)",
    3: "Network energy per 7-day period (kWh)",
    4: "Daily energy of the selected meter (kWh)",
    5: "Completeness by region (%)",
}
COLUMNS = {
    1: ["bucket", "region", "energy_kwh", "readings"],
    2: ["bucket", "energy_kwh", "readings"],
    3: ["bucket", "energy_kwh", "readings"],
    4: ["bucket", "energy_kwh", "readings"],
    5: ["region", "observed", "planned", "completeness_pct"],
}

RANGE_RAW = "er.event_time >= %(s)s AND er.event_time < %(e)s"
RANGE_AGG = "bucket >= %(s)s AND bucket < %(e)s"

Q = {
    "Raw": {
        1: f"""SELECT time_bucket('1 hour', er.event_time, 'Africa/Kigali') AS bucket, m.region,
                      sum(er.energy_kwh) AS energy_kwh, count(*) AS readings
               FROM energy_readings er JOIN meters m ON m.meter_id = er.meter_id
               WHERE {RANGE_RAW} GROUP BY 1, 2 ORDER BY 1, 2""",
        2: f"""SELECT time_bucket('1 day', er.event_time, 'Africa/Kigali') AS bucket,
                      sum(er.energy_kwh) AS energy_kwh, count(*) AS readings
               FROM energy_readings er WHERE {RANGE_RAW} GROUP BY 1 ORDER BY 1""",
        3: f"""SELECT time_bucket('7 days', er.event_time, 'Africa/Kigali', '{ORIGIN}'::timestamptz) AS bucket,
                      sum(er.energy_kwh) AS energy_kwh, count(*) AS readings
               FROM energy_readings er WHERE {RANGE_RAW} GROUP BY 1 ORDER BY 1""",
        4: f"""SELECT time_bucket('1 day', er.event_time, 'Africa/Kigali') AS bucket,
                      sum(er.energy_kwh) AS energy_kwh, count(*) AS readings
               FROM energy_readings er
               WHERE er.meter_id = %(m)s AND {RANGE_RAW} GROUP BY 1 ORDER BY 1""",
        5: f"""SELECT m.region, count(*) AS observed
               FROM energy_readings er JOIN meters m ON m.meter_id = er.meter_id
               WHERE {RANGE_RAW} GROUP BY 1""",
    },
    "Aggregate": {
        1: f"""SELECT bucket, region, energy_kwh_sum AS energy_kwh, reading_count AS readings
               FROM cagg_hour_region WHERE {RANGE_AGG} ORDER BY 1, 2""",
        2: f"""SELECT time_bucket('1 day', bucket, 'Africa/Kigali') AS bucket,
                      sum(energy_kwh_sum) AS energy_kwh, sum(reading_count) AS readings
               FROM cagg_15m_region WHERE {RANGE_AGG} GROUP BY 1 ORDER BY 1""",
        3: f"""SELECT time_bucket('7 days', bucket, 'Africa/Kigali', '{ORIGIN}'::timestamptz) AS bucket,
                      sum(energy_kwh_sum) AS energy_kwh, sum(reading_count) AS readings
               FROM cagg_15m_region WHERE {RANGE_AGG} GROUP BY 1 ORDER BY 1""",
        4: f"""SELECT bucket, energy_kwh_sum AS energy_kwh, reading_count AS readings
               FROM cagg_day_meter WHERE meter_id = %(m)s AND {RANGE_AGG} ORDER BY 1""",
        5: f"""SELECT region, sum(reading_count) AS observed
               FROM cagg_15m_region WHERE {RANGE_AGG} GROUP BY 1""",
    },
}


def make_params(start_date, end_date, meter_id):
    """Whole CAT days: start_date and end_date are both included."""
    d0, d1 = date.fromisoformat(str(start_date)[:10]), date.fromisoformat(str(end_date)[:10])
    return {"s": f"{d0.isoformat()} 00:00:00+02",
            "e": f"{(d1 + timedelta(days=1)).isoformat()} 00:00:00+02",
            "m": int(meter_id), "ndays": (d1 - d0).days + 1}


def run_panel(cur, mode, k, p):
    """Run one panel query and return the rows (panel 5 also reads meters for registered counts)."""
    if k == 5:
        cur.execute("SELECT region, count(*) FROM meters GROUP BY region")
        registered = dict(cur.fetchall())
        cur.execute(Q[mode][5], p)
        observed = {r: int(n) for r, n in cur.fetchall()}
        rows = []
        for region in sorted(registered, key=lambda r: int(r.split()[-1])):
            planned = registered[region] * p["ndays"] * SLOTS_PER_DAY
            obs = observed.get(region, 0)
            rows.append((region, obs, planned, 100.0 * obs / planned))
        return rows
    cur.execute(Q[mode][k], p)
    return cur.fetchall()
