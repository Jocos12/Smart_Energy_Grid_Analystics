-- Assignment I, section 3.1: verify the three configurations
\echo '--- Chunk interval per table ---'
SELECT hypertable_name, column_name, time_interval
FROM timescaledb_information.dimensions
WHERE hypertable_name LIKE 'energy_readings%' ORDER BY hypertable_name;

\echo '--- Chunk count and date range per table ---'
SELECT hypertable_name, count(*) AS chunks, min(range_start) AS first_start, max(range_end) AS last_end
FROM timescaledb_information.chunks
WHERE hypertable_name LIKE 'energy_readings%' GROUP BY hypertable_name ORDER BY hypertable_name;

\echo '--- Indexes ---'
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('energy_readings','energy_readings_3h','energy_readings_week')
ORDER BY tablename, indexname;

\echo '--- Data match checks (expected: 10643735 rows, 4000 meters, identical dates, sums within 0.001) ---'
SELECT 'energy_readings' AS tbl, count(*) AS n, count(DISTINCT meter_id) AS meters,
       min(event_time) AS earliest, max(event_time) AS latest,
       sum(power_kw) AS sum_power_kw, sum(energy_kwh) AS sum_energy_kwh FROM energy_readings
UNION ALL
SELECT 'energy_readings_3h', count(*), count(DISTINCT meter_id), min(event_time), max(event_time),
       sum(power_kw), sum(energy_kwh) FROM energy_readings_3h
UNION ALL
SELECT 'energy_readings_week', count(*), count(DISTINCT meter_id), min(event_time), max(event_time),
       sum(power_kw), sum(energy_kwh) FROM energy_readings_week;
