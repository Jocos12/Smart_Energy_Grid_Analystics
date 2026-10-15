\timing on
\echo '--- Q1: counts and percentages (before cleaning) ---'
WITH u AS (
  SELECT meter_id, event_time,
         min(received_time) AS received_time,
         count(*) AS copies
  FROM energy_readings
  GROUP BY meter_id, event_time
)
SELECT count(*)                                              AS unique_readings,
       sum(copies) - count(*)                                AS extra_copies,
       sum(copies)                                           AS emitted_check,
       10752000 - count(*)                                   AS missing_readings,
       count(*) FILTER (WHERE received_time > event_time + interval '15 minutes') AS delayed_unique,
       round(100.0 * (10752000 - count(*)) / 10752000, 4)    AS missing_pct,
       round(100.0 * (sum(copies) - count(*)) / count(*), 4) AS duplicate_pct,
       round(100.0 * count(*) FILTER (WHERE received_time > event_time + interval '15 minutes') / count(*), 4) AS delayed_pct,
       round(100.0 * count(*) / 10752000, 4)                 AS completeness_pct
FROM u;

\echo '--- Q2: five meters with the most missing readings ---'
SELECT meter_id, 2688 - count(DISTINCT event_time) AS missing_readings
FROM energy_readings
GROUP BY meter_id
ORDER BY missing_readings DESC, meter_id
LIMIT 5;