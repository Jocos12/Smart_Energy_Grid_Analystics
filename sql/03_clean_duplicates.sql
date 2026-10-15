\timing on
\echo '--- BEFORE cleaning ---'
SELECT count(*) AS rows_before, sum(energy_kwh) AS sum_energy_kwh_before
FROM energy_readings;

\echo '--- Conflict check: duplicate pairs whose values differ (expected 0) ---'
SELECT count(*) AS conflicting_pairs
FROM (
  SELECT meter_id, event_time
  FROM energy_readings
  GROUP BY meter_id, event_time
  HAVING count(*) > 1
     AND count(DISTINCT ROW(received_time, power_kw, voltage_v,
                            current_a, frequency_hz, energy_kwh)) > 1
) t;

\echo '--- Deleting extra copies chunk by chunk (keeps one row per pair) ---'
DO $$
DECLARE
  conflicts bigint;
  c regclass;
  removed bigint := 0;
  n bigint;
BEGIN
  SELECT count(*) INTO conflicts FROM (
    SELECT meter_id, event_time
    FROM energy_readings
    GROUP BY meter_id, event_time
    HAVING count(*) > 1
       AND count(DISTINCT ROW(received_time, power_kw, voltage_v,
                              current_a, frequency_hz, energy_kwh)) > 1
  ) t;
  IF conflicts > 0 THEN
    RAISE EXCEPTION 'Found % conflicting duplicate pairs; investigate before deleting', conflicts;
  END IF;

  FOR c IN
    SELECT format('%I.%I', chunk_schema, chunk_name)::regclass
    FROM timescaledb_information.chunks
    WHERE hypertable_name = 'energy_readings'
    ORDER BY range_start
  LOOP
    EXECUTE format(
      'DELETE FROM %s WHERE ctid IN (
         SELECT ctid FROM (
           SELECT ctid, row_number() OVER (PARTITION BY meter_id, event_time ORDER BY ctid) AS rn
           FROM %s) x
         WHERE rn > 1)', c, c);
    GET DIAGNOSTICS n = ROW_COUNT;
    removed := removed + n;
  END LOOP;
  RAISE NOTICE 'Extra copies deleted: %', removed;
END $$;

\echo '--- AFTER cleaning ---'
SELECT count(*) AS rows_after, sum(energy_kwh) AS sum_energy_kwh_after
FROM energy_readings;

SELECT count(*) AS duplicate_pairs_remaining
FROM (SELECT 1 FROM energy_readings GROUP BY meter_id, event_time HAVING count(*) > 1) t;

SELECT (SELECT count(*) FROM energy_readings) = 10643735 AS matches_expected_unique_readings;