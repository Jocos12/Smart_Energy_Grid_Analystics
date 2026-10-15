-- Assignment I, section 3.1: three chunk-interval configurations of the cleaned dataset
\timing on

\echo '--- Replace the default index so all three tables carry identical explicit indexes ---'
DROP INDEX IF EXISTS energy_readings_event_time_idx;

\echo '--- Create the 3-hour and 1-week hypertables ---'
CREATE TABLE IF NOT EXISTS energy_readings_3h (LIKE energy_readings);
SELECT create_hypertable('energy_readings_3h', 'event_time',
       chunk_time_interval => INTERVAL '3 hours', create_default_indexes => FALSE, if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS energy_readings_week (LIKE energy_readings);
SELECT create_hypertable('energy_readings_week', 'event_time',
       chunk_time_interval => INTERVAL '7 days', create_default_indexes => FALSE, if_not_exists => TRUE);

\echo '--- Copy cleaned rows ---'
INSERT INTO energy_readings_3h   SELECT * FROM energy_readings;
INSERT INTO energy_readings_week SELECT * FROM energy_readings;

\echo '--- Identical non-unique indexes on all three tables ---'
CREATE INDEX IF NOT EXISTS idx_er_event_time     ON energy_readings      (event_time);
CREATE INDEX IF NOT EXISTS idx_er_meter_time     ON energy_readings      (meter_id, event_time);
CREATE INDEX IF NOT EXISTS idx_er3h_event_time   ON energy_readings_3h   (event_time);
CREATE INDEX IF NOT EXISTS idx_er3h_meter_time   ON energy_readings_3h   (meter_id, event_time);
CREATE INDEX IF NOT EXISTS idx_erweek_event_time ON energy_readings_week (event_time);
CREATE INDEX IF NOT EXISTS idx_erweek_meter_time ON energy_readings_week (meter_id, event_time);

\echo '--- Refresh statistics ---'
ANALYZE energy_readings;
ANALYZE energy_readings_3h;
ANALYZE energy_readings_week;
