"""Assignment I, section 1.2: load the 4,000 meter metadata rows into PostgreSQL."""
import psycopg2
from psycopg2.extras import execute_values
import smart_meter_simulator as s

DB = dict(host="localhost", port=5432, dbname="energy_grid",
          user="postgres", password="123")

rows = s.meter_metadata()
cols = ["meter_id", "region", "customer_type", "base_power_kw", "power_factor"]
values = [tuple(r[c] for c in cols) for r in rows]

with psycopg2.connect(**DB) as conn:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE meters")
        execute_values(
            cur,
            "INSERT INTO meters (meter_id, region, customer_type, base_power_kw, power_factor) VALUES %s",
            values,
        )

print("Inserted", len(values), "rows into meters")
