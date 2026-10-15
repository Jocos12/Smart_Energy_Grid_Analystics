SELECT add_continuous_aggregate_policy('cagg_15m_region',
       start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '15 minutes');
SELECT add_continuous_aggregate_policy('cagg_hour_region',
       start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '15 minutes');
SELECT add_continuous_aggregate_policy('cagg_day_meter',
       start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '15 minutes');

\echo '--- Policy settings and job status ---'
SELECT j.job_id, j.proc_name, j.schedule_interval, j.scheduled,
       j.config->>'start_offset' AS start_offset, j.config->>'end_offset' AS end_offset
FROM timescaledb_information.jobs j
WHERE j.proc_name = 'policy_refresh_continuous_aggregate' ORDER BY j.job_id;

SELECT job_id, last_run_status, last_run_started_at, next_start, total_runs
FROM timescaledb_information.job_stats
WHERE job_id IN (SELECT job_id FROM timescaledb_information.jobs WHERE proc_name = 'policy_refresh_continuous_aggregate')
ORDER BY job_id;