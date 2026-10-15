import os
from datetime import datetime, timedelta, timezone

import psycopg2

CAT = timezone(timedelta(hours=2), "CAT")
DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "YOUR_PASSWORD"))
HOUR = timedelta(hours=1)

conn = psycopg2.connect(**DB)
conn.autocommit = True
cur = conn.cursor()


def pause(msg):
    input(f"\n>>> {msg}  (take the screenshot, then press Enter) ")
    print("\n" * 2)


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


def fmt(t):
    return t.astimezone(CAT).strftime("%Y-%m-%d %H:%M CAT")


def raw(label, start):
    cur.execute("SELECT coalesce(sum(energy_kwh), 0), count(*) FROM test_fresh "
                "WHERE event_time >= %s AND event_time < %s", (start, start + HOUR))
    kwh, n = cur.fetchone()
    print(f"  RAW table   {label:8s} {fmt(start)}: {kwh:.3f} kWh, {n} rows")


def agg(label, start):
    cur.execute("SELECT energy_kwh_sum, row_count FROM test_fresh_hourly WHERE bucket = %s", (start,))
    r = cur.fetchone()
    txt = f"{r[0]:.3f} kWh, {r[1]} rows" if r else "no bucket returned"
    print(f"  AGGREGATE   {label:8s} {fmt(start)}: {txt}")


def both(title):
    print(f"--- {title} ---")
    raw("older", O); raw("hour H", H)
    agg("older", O); agg("hour H", H)


# ---------- Stage 0: objects and test times ----------
test_time = datetime.now(CAT)
H = test_time.replace(minute=0, second=0, microsecond=0) - HOUR      # start of last completed CAT hour
O = H - timedelta(hours=48)                                           # H minus 48 hours
E1, E2, E3 = O + timedelta(minutes=10), O + timedelta(minutes=25), H + timedelta(minutes=10)

cur.execute("DROP MATERIALIZED VIEW IF EXISTS test_fresh_hourly")
cur.execute("DROP TABLE IF EXISTS test_fresh")
cur.execute("CREATE TABLE test_fresh (event_time TIMESTAMPTZ NOT NULL, energy_kwh DOUBLE PRECISION)")
cur.execute("SELECT create_hypertable('test_fresh', 'event_time')")
cur.execute("""CREATE MATERIALIZED VIEW test_fresh_hourly
               WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
               SELECT time_bucket('1 hour', event_time, 'Africa/Kigali') AS bucket,
                      sum(energy_kwh) AS energy_kwh_sum, count(*) AS row_count
               FROM test_fresh GROUP BY 1 WITH NO DATA""")
print(f"[{now()}] 6.2 freshness and delayed-arrival test")
print(f"  actual test time              : {fmt(test_time)}")
print(f"  H (last completed CAT hour)   : {fmt(H)}")
print(f"  H minus 48 hours (older hour) : {fmt(O)}")
print(f"  event_time of insert 1 (1.0 kWh): {fmt(E1)}  (older hour)")
print(f"  event_time of insert 2 (0.5 kWh): {fmt(E2)}  (older hour)")
print(f"  event_time of insert 3 (2.0 kWh): {fmt(E3)}  (hour H)")
cur.execute("SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'test_fresh' ORDER BY ordinal_position")
print("  test_fresh columns:", cur.fetchall())
cur.execute("SELECT column_name, time_interval FROM timescaledb_information.dimensions "
            "WHERE hypertable_name = 'test_fresh'")
print("  hypertable dimension:", cur.fetchall())
cur.execute("SELECT view_name, materialized_only, view_definition FROM timescaledb_information.continuous_aggregates "
            "WHERE view_name = 'test_fresh_hourly'")
print("  aggregate (view_name, materialized_only, definition):", cur.fetchone())
cur.execute("SELECT count(*) FROM timescaledb_information.jobs j JOIN timescaledb_information.continuous_aggregates c "
            "ON j.hypertable_name = c.materialization_hypertable_name WHERE c.view_name = 'test_fresh_hourly'")
print("  refresh jobs on the test aggregate (expected 0):", cur.fetchone()[0])
pause("STAGE 0: table, view definition, real-time OFF, no refresh policy")

# ---------- Stage 1: insert 1 kWh in the older hour, refresh ONLY that hour ----------
cur.execute("INSERT INTO test_fresh VALUES (%s, 1.0)", (E1,))
print(f"[{now()}] inserted 1.0 kWh at {fmt(E1)}")
cur.execute("CALL refresh_continuous_aggregate('test_fresh_hourly', %s, %s)", (O, O + HOUR))
print(f"[{now()}] refreshed only the older hour [{fmt(O)}, {fmt(O + HOUR)})")
both("STAGE 1: after the initial older-hour refresh, real-time OFF")
pause("STAGE 1")

# ---------- Stage 2: two new inserts, no refresh, real-time still OFF ----------
cur.execute("INSERT INTO test_fresh VALUES (%s, 0.5)", (E2,))
cur.execute("INSERT INTO test_fresh VALUES (%s, 2.0)", (E3,))
print(f"[{now()}] inserted 0.5 kWh at {fmt(E2)} and 2.0 kWh at {fmt(E3)}")
both("STAGE 2: after both new inserts, before any refresh, real-time OFF")
pause("STAGE 2")

# ---------- Stage 3: real-time ON, still no refresh ----------
cur.execute("ALTER MATERIALIZED VIEW test_fresh_hourly SET (timescaledb.materialized_only = false)")
cur.execute("SELECT materialized_only FROM timescaledb_information.continuous_aggregates WHERE view_name = 'test_fresh_hourly'")
print(f"[{now()}] real-time aggregation enabled (materialized_only = {cur.fetchone()[0]})")
both("STAGE 3: real-time ON, still before the refresh")
pause("STAGE 3")

# ---------- Stage 4: refresh both complete hours ----------
cur.execute("CALL refresh_continuous_aggregate('test_fresh_hourly', %s, %s)", (O, O + HOUR))
cur.execute("CALL refresh_continuous_aggregate('test_fresh_hourly', %s, %s)", (H, H + HOUR))
print(f"[{now()}] refreshed both complete hours")
both("STAGE 4: after the manual refresh of both hours")
print("\nExpected: older hour 1.5 kWh / 2 rows, hour H 2.0 kWh / 1 row; raw table 1.5 / 2 and 2.0 / 1 in every stage.")
print(f"Test time {fmt(test_time)}: policy window of 6.1 = [now - 3 days, now - 1 hour)")
print(f"  older hour {fmt(O)} lies inside that window -> a policy like 6.1's could refresh it")
print(f"  hour H {fmt(H)} ends at {fmt(H + HOUR)}, which is after now - 1 hour -> a policy like 6.1's could NOT refresh it yet")
conn.close()