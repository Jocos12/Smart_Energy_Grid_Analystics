\echo '--- Chunk interval and chunk count ---'
SELECT d.hypertable_name, d.time_interval, count(c.*) AS chunks,
       count(*) FILTER (WHERE c.is_compressed) AS compressed_chunks
FROM timescaledb_information.dimensions d
JOIN timescaledb_information.chunks c USING (hypertable_name)
WHERE d.hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
GROUP BY d.hypertable_name, d.time_interval ORDER BY 1;

\echo '--- Compressed chunk list, both tables side by side ---'
SELECT coalesce(a.range_start, b.range_start) AS chunk_start,
       coalesce(a.range_end, b.range_end)     AS chunk_end,
       a.is_compressed AS time_tbl_compressed,
       b.is_compressed AS meter_tbl_compressed
FROM (SELECT range_start, range_end, is_compressed FROM timescaledb_information.chunks
      WHERE hypertable_name = 'energy_time_compressed') a
FULL JOIN (SELECT range_start, range_end, is_compressed FROM timescaledb_information.chunks
           WHERE hypertable_name = 'energy_meter_compressed') b USING (range_start)
ORDER BY 1;

\echo '--- Chunks compressed in one table but not the other (expected 0) ---'
SELECT count(*) AS mismatches
FROM (SELECT range_start, is_compressed FROM timescaledb_information.chunks
      WHERE hypertable_name = 'energy_time_compressed') a
FULL JOIN (SELECT range_start, is_compressed FROM timescaledb_information.chunks
           WHERE hypertable_name = 'energy_meter_compressed') b USING (range_start)
WHERE a.is_compressed IS DISTINCT FROM b.is_compressed;

\echo '--- Data checks on all five tables (expected 10643735 rows, 4000 meters, sums within 0.001) ---'
SELECT 'energy_readings' AS tbl, count(*) AS n, count(DISTINCT meter_id) AS meters, min(event_time) AS earliest,
       max(event_time) AS latest, sum(power_kw) AS sum_power_kw, sum(energy_kwh) AS sum_energy_kwh FROM energy_readings
UNION ALL SELECT 'energy_readings_3h', count(*), count(DISTINCT meter_id), min(event_time), max(event_time), sum(power_kw), sum(energy_kwh) FROM energy_readings_3h
UNION ALL SELECT 'energy_readings_week', count(*), count(DISTINCT meter_id), min(event_time), max(event_time), sum(power_kw), sum(energy_kwh) FROM energy_readings_week
UNION ALL SELECT 'energy_time_compressed', count(*), count(DISTINCT meter_id), min(event_time), max(event_time), sum(power_kw), sum(energy_kwh) FROM energy_time_compressed
UNION ALL SELECT 'energy_meter_compressed', count(*), count(DISTINCT meter_id), min(event_time), max(event_time), sum(power_kw), sum(energy_kwh) FROM energy_meter_compressed;