\timing on
\echo '--- Two empty 1-day hypertables, same 8 columns ---'
CREATE TABLE IF NOT EXISTS energy_time_compressed  (LIKE energy_readings);
CREATE TABLE IF NOT EXISTS energy_meter_compressed (LIKE energy_readings);
SELECT create_hypertable('energy_time_compressed',  'event_time', chunk_time_interval => INTERVAL '1 day',
                         create_default_indexes => FALSE, if_not_exists => TRUE);
SELECT create_hypertable('energy_meter_compressed', 'event_time', chunk_time_interval => INTERVAL '1 day',
                         create_default_indexes => FALSE, if_not_exists => TRUE);

\echo '--- Matching indexes ---'
CREATE INDEX IF NOT EXISTS idx_etc_event_time ON energy_time_compressed  (event_time);
CREATE INDEX IF NOT EXISTS idx_etc_meter_time ON energy_time_compressed  (meter_id, event_time);
CREATE INDEX IF NOT EXISTS idx_emc_event_time ON energy_meter_compressed (event_time);
CREATE INDEX IF NOT EXISTS idx_emc_meter_time ON energy_meter_compressed (meter_id, event_time);

\echo '--- Compression settings: same ordering, segmentation only on the meter table ---'
ALTER TABLE energy_time_compressed SET (
  timescaledb.compress,
  timescaledb.compress_orderby   = 'event_time DESC',
  timescaledb.compress_segmentby = '');
ALTER TABLE energy_meter_compressed SET (
  timescaledb.compress,
  timescaledb.compress_orderby   = 'event_time DESC',
  timescaledb.compress_segmentby = 'meter_id');

\echo '--- Policies: compress chunks whose end is more than 48 hours old ---'
SELECT add_compression_policy('energy_time_compressed',  compress_after => INTERVAL '48 hours', if_not_exists => TRUE);
SELECT add_compression_policy('energy_meter_compressed', compress_after => INTERVAL '48 hours', if_not_exists => TRUE);

\echo '--- Pause both policies until the measurements of 4.3 are complete ---'
SELECT alter_job(job_id, scheduled => false)
FROM timescaledb_information.jobs
WHERE hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed');

\echo '--- Verify policies (scheduled must be f) ---'
SELECT job_id, hypertable_name, proc_name, scheduled, config
FROM timescaledb_information.jobs
WHERE hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
ORDER BY hypertable_name;

\echo '--- Verify compression settings ---'
SELECT * FROM timescaledb_information.hypertable_compression_settings
WHERE hypertable::text IN ('energy_time_compressed', 'energy_meter_compressed');