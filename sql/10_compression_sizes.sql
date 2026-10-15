\echo '--- Baseline: energy_readings (1-day, uncompressed) ---'
SELECT 'energy_readings' AS tbl,
       pg_size_pretty(table_bytes) AS data, pg_size_pretty(index_bytes) AS idx,
       pg_size_pretty(toast_bytes) AS toast, pg_size_pretty(total_bytes) AS total,
       total_bytes
FROM hypertable_detailed_size('energy_readings');

\echo '--- Compressed tables (all chunks, compressed + uncompressed, with indexes) ---'
SELECT 'energy_time_compressed' AS tbl,
       pg_size_pretty(table_bytes) AS data, pg_size_pretty(index_bytes) AS idx,
       pg_size_pretty(toast_bytes) AS toast, pg_size_pretty(total_bytes) AS total,
       total_bytes
FROM hypertable_detailed_size('energy_time_compressed');
SELECT 'energy_meter_compressed' AS tbl,
       pg_size_pretty(table_bytes) AS data, pg_size_pretty(index_bytes) AS idx,
       pg_size_pretty(toast_bytes) AS toast, pg_size_pretty(total_bytes) AS total,
       total_bytes
FROM hypertable_detailed_size('energy_meter_compressed');

\echo '--- Ratios and percentage saved ---'
WITH s AS (
  SELECT 'energy_readings' AS tbl, total_bytes FROM hypertable_detailed_size('energy_readings')
  UNION ALL SELECT 'energy_time_compressed', total_bytes FROM hypertable_detailed_size('energy_time_compressed')
  UNION ALL SELECT 'energy_meter_compressed', total_bytes FROM hypertable_detailed_size('energy_meter_compressed')
), b AS (SELECT total_bytes AS base FROM s WHERE tbl = 'energy_readings')
SELECT s.tbl, s.total_bytes,
       round(b.base::numeric / s.total_bytes, 2) AS compression_ratio,
       round(100 * (b.base - s.total_bytes)::numeric / b.base, 1) AS pct_saved
FROM s, b ORDER BY s.total_bytes DESC;

\echo '--- Compressed chunks out of total ---'
SELECT hypertable_name, count(*) AS total_chunks,
       count(*) FILTER (WHERE is_compressed) AS compressed_chunks
FROM timescaledb_information.chunks
WHERE hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
GROUP BY 1 ORDER BY 1;