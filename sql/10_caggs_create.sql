\echo '--- Three continuous aggregates, created WITH NO DATA, real-time aggregation disabled ---'
CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_15m_region
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket('15 minutes', er.event_time) AS bucket,
       m.region                                 AS region,
       sum(er.energy_kwh)                       AS energy_kwh_sum,
       sum(er.power_kw)                         AS power_kw_sum,
       count(*)                                 AS reading_count
FROM energy_readings er
JOIN meters m ON m.meter_id = er.meter_id
GROUP BY 1, 2
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_hour_region
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket('1 hour', er.event_time, 'Africa/Kigali') AS bucket,
       m.region                                 AS region,
       sum(er.energy_kwh)                       AS energy_kwh_sum,
       sum(er.power_kw)                         AS power_kw_sum,
       count(*)                                 AS reading_count
FROM energy_readings er
JOIN meters m ON m.meter_id = er.meter_id
GROUP BY 1, 2
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_day_meter
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket('1 day', event_time, 'Africa/Kigali') AS bucket,
       meter_id,
       sum(energy_kwh)                          AS energy_kwh_sum,
       sum(power_kw)                            AS power_kw_sum,
       count(*)                                 AS reading_count
FROM energy_readings
GROUP BY 1, 2
WITH NO DATA;

\echo '--- Definitions and settings ---'
SELECT view_name, materialized_only, finalized, view_definition
FROM timescaledb_information.continuous_aggregates
WHERE view_name LIKE 'cagg_%' ORDER BY view_name;

\echo '--- Rows before the first refresh (expected 0) ---'
SELECT 'cagg_15m_region' AS view, count(*) FROM cagg_15m_region
UNION ALL SELECT 'cagg_hour_region', count(*) FROM cagg_hour_region
UNION ALL SELECT 'cagg_day_meter', count(*) FROM cagg_day_meter;