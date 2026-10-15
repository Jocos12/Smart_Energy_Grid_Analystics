\timing on
\echo '--- Manual refresh of the whole generated period, one view at a time ---'
CALL refresh_continuous_aggregate('cagg_15m_region',  '2026-09-01 00:00:00+02', '2026-09-29 00:00:00+02');
CALL refresh_continuous_aggregate('cagg_hour_region', '2026-09-01 00:00:00+02', '2026-09-29 00:00:00+02');
CALL refresh_continuous_aggregate('cagg_day_meter',   '2026-09-01 00:00:00+02', '2026-09-29 00:00:00+02');
\timing off

\echo '--- Sample populated rows ---'
SELECT * FROM cagg_15m_region  ORDER BY bucket, region LIMIT 5;
SELECT * FROM cagg_hour_region ORDER BY bucket, region LIMIT 5;
SELECT * FROM cagg_day_meter   ORDER BY bucket, meter_id LIMIT 5;

\echo '--- Row counts and totals (expected: 26880 / 6720 / 112000 rows; 10643735 readings; 3853704.3468 kWh) ---'
SELECT 'cagg_15m_region' AS view, count(*) AS rows, sum(reading_count) AS readings, sum(energy_kwh_sum) AS kwh FROM cagg_15m_region
UNION ALL SELECT 'cagg_hour_region', count(*), sum(reading_count), sum(energy_kwh_sum) FROM cagg_hour_region
UNION ALL SELECT 'cagg_day_meter',   count(*), sum(reading_count), sum(energy_kwh_sum) FROM cagg_day_meter;

\echo '--- Materialized data and index size per view ---'
SELECT c.view_name,
       pg_size_pretty(s.table_bytes) AS data,
       pg_size_pretty(s.index_bytes) AS indexes,
       pg_size_pretty(s.total_bytes) AS total
FROM timescaledb_information.continuous_aggregates c,
     LATERAL hypertable_detailed_size(
       format('%I.%I', c.materialization_hypertable_schema, c.materialization_hypertable_name)::regclass) s
WHERE c.view_name LIKE 'cagg_%' ORDER BY c.view_name;