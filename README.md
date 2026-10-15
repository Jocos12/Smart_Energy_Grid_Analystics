# Smart Energy Grid Analytics

**Advanced Big Data Analytics – Assignment I (October 2026)**
Ingestion, storage benchmarking, continuous aggregates, dashboards and next-day demand forecasting for a 4,000-meter electricity network.

| Member | Student ID |
|---|---|
| HITAYEZU James | 101381 |
| Joseph Courbon | 101493 |
| Mylene MANIRAKIZA | 101403 |

- Report (PDF): `Assignment_I_Smart_Energy_Grid_Report_FINAL.pdf`
- Repository: https://github.com/Jocos12/Smart_Energy_Grid_Analystics
- Assignment brief: `Assignment_I_October_2026.pdf`
- All dates and times are **CAT** (Africa/Kigali, UTC+02:00).

---

## Table of contents

1. [Results at a glance](#1-results-at-a-glance)
2. [Repository content](#2-repository-content)
3. [Environment](#3-environment)
4. [Setup, secrets and connection settings](#4-setup-secrets-and-connection-settings)
5. [Execution order and commands](#5-execution-order-and-commands)
6. [Pilot run and the four counts of section 1.3](#6-pilot-run-and-the-four-counts-of-section-13)
7. [Regenerating the dataset locally](#7-regenerating-the-dataset-locally)
8. [Recorded results and output files](#8-recorded-results-and-output-files)
9. [Troubleshooting](#9-troubleshooting)
10. [Notes on method](#10-notes-on-method)

---

## 1. Results at a glance

| Topic | Result | Report section |
|---|---|---|
| Dataset | 10,643,735 unique readings after cleaning (10,696,848 emitted, 53,113 duplicates removed) · 4,000 meters · 3,853,704.35 kWh | §2 |
| Reporting quality | Completeness 98.9931 % (108,265 of 10,752,000 readings missing); 2.0 % delayed | §2.2, §5.3 |
| Demand | Weekdays 141–152 MWh/day, weekends 112–119 MWh/day (−21 %); highest 15-minute demand 7,993.7 kW on 28 Sept at 13:00 | §5.1 |
| Customer mix | Industrial meters (10 % of meters) use 58 % of the energy, 17.5× more per meter than residential ones | §5.2 |
| Anomaly detection | 40 / 40 injected events detected, 0 false flags | §5.4 |
| Chunk intervals | Fastest median: 3 h on Q1, 1 day on Q2, 1 week on Q3 and Q4; 3 h chunks 5.9× slower on Q3. **1 day** chosen | §3 |
| Compression | 1,344 MB → 439 MB (ratio 3.06) without segmentation, 502 MB (ratio 2.68) segmented by `meter_id`; compression time 27.2 s vs 46.9 s | §4 |
| Dashboards | Median whole dashboard 2,780.3 ms (Raw) → 610.8 ms (Aggregate), ≈ 4.6× faster; all five panels identical | §7 |
| Forecast | Previous-day baseline MAE 42.708 kWh, RMSE 79.403 kWh; gradient-boosting model MAE 7.489 kWh, RMSE 11.299 kWh (1,680 test predictions) | §8 |

## 2. Repository content

```text
.
├── smart_meter_simulator.py        Supplied generator, UNCHANGED (identical to the issued copy)
├── load_meters.py                  §1.2  loads the 4,000 meters rows with meter_metadata()
├── publisher.py                    §1.3  MQTT publisher (2,000 messages, QoS 1, no retain)
├── subscriber.py                   §1.3  MQTT subscriber (energy/meters/#, QoS 1) -> energy_live
├── load_full.py                    §2.1  captures the full stream, loads energy_readings in batches
├── sql/                            numbered SQL files (tables, cleaning, chunk configurations and checks,
│                                   compression sizes, continuous aggregates and policies);
│                                   e.g. 05_chunk_checks.sql, 10_compression_sizes.sql, 12_caggs_policies.sql
├── bench_chunks.py                 §3    Q1-Q5 on the 1-day, 3-hour and 1-week hypertables
├── load_compress.py                §4    compressed tables, cutoff, per-chunk compression log
├── bench_compression.py            §4    Q1-Q5 on the five tables
├── analysis_5_1.py ... 5_4.py      §5    demand patterns, regions/customer types, reporting quality, anomalies
├── test_freshness.py               §6.2  freshness and delayed-arrival test
├── dashboard_app.py                §7    Raw and Aggregate dashboards (Dash), one process per dashboard
├── dashboard_queries.py            §7    the five panel queries of each dashboard
├── verify_dashboards.py            §7.3  compares the five panels of the two dashboards
├── summarize_dashboard_timings.py  §7.4  median / min / max from dashboard_timings.csv
├── capture_7_3.py                  §7.3  helper that saves the paired dashboard screenshots
├── section8_forecast.py            §8    dataset, baseline, regression model, evaluation, plot
├── section8_output.txt             §8    recorded output of section8_forecast.py
├── forecast_plot_Region_1.png      §8.4  actual vs baseline vs model, Region 1, 22-28 September
├── benchmark_*  /  compression_*   recorded benchmark timings, compression cutoff and per-chunk log
├── explain_Q*_*.txt                EXPLAIN (ANALYZE, BUFFERS) plans per configuration
├── dashboard_timings.csv, dashboard_export_*, dashboard_verification
│                                   recorded dashboard timings and the data behind every panel
├── screenshots/                    evidence screenshots used in the report
└── Assignment_I_Smart_Energy_Grid_Report_FINAL.pdf
```

The full generated dataset (about 10 GB of tables) stays **local** and is not committed (see `.gitignore`). Section 7 explains how to regenerate and load it.

## 3. Environment

| Item | Version used |
|---|---|
| Hardware | Intel Core i7-1355U (10 cores, 12 logical processors), 15.7 GB RAM, KIOXIA SSD (≈ 1 TB) |
| OS | Windows 11 Pro 10.0.26200 |
| PostgreSQL | 18.6, native Windows service `postgresql-x64-18` (no container, no CPU/RAM limit) |
| TimescaleDB | 2.30.2 (Community Edition) |
| EMQX | 5.8.9, Docker image `emqx/emqx:5.8.9` (no `--cpus` / `--memory` option) |
| Python | 3.12.1 |
| PostgreSQL settings | `shared_buffers` 4023MB · `work_mem` 10730kB · `max_parallel_workers_per_gather` 6 · `jit` off |
| Free disk space | about 10 GB |

## 4. Setup, secrets and connection settings

Install the Python packages once:

```powershell
python -m pip install paho-mqtt psycopg2-binary pandas numpy matplotlib plotly dash flask scikit-learn pillow
```

**No password is stored in the repository.** Set it in each PowerShell window before running a program (placeholder shown):

```powershell
$env:PGPASSWORD="<YOUR_PASSWORD>"
```

Connection used by the programs: host `localhost`, port `5432`, database `energy_grid`, user `postgres`. If your installation differs, edit the connection settings at the top of the program.

Throughout this file `psql` stands for:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d energy_grid
```

## 5. Execution order and commands

Run every command from the repository folder.

### Step 0 – Services and database

```powershell
# Database, TimescaleDB extension and CAT session time zone (once)
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE DATABASE energy_grid;"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d energy_grid -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "ALTER DATABASE energy_grid SET timezone TO 'Africa/Kigali';"

# EMQX broker (Docker Desktop running)
docker pull emqx/emqx:5.8.9
docker run -d --name emqx -p 1883:1883 -p 8083:8083 -p 8084:8084 -p 8883:8883 -p 18083:18083 emqx/emqx:5.8.9
docker exec emqx emqx ctl status          # Node 'emqx@...' 5.8.9 is started
Test-NetConnection localhost -Port 1883   # TcpTestSucceeded : True
```

### Step 1 – Tables and metadata (§1.2)

Run the table-creation files of `sql/` in numeric order (`energy_live` regular table, `energy_readings` hypertable with 1-day chunks, `meters`), then:

```powershell
python load_meters.py
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d energy_grid -c "SELECT count(*) FROM meters;"   # expected: 4000
```

### Step 2 – Pilot stream (§1.3)

Follow [section 6](#6-pilot-run-and-the-four-counts-of-section-13).

### Step 3 – Full dataset, data quality and cleaning (§2)

```powershell
python load_full.py     # captures the whole stream and loads energy_readings in batches
```

Expected counts: planned 10,752,000 · emitted 10,696,848 · unique 10,643,735 · duplicates 53,113 · delayed 213,090 · missing 108,265. Then run the quality and cleaning files of `sql/` in numeric order and check:

```sql
SELECT count(*), count(DISTINCT meter_id), min(event_time), max(event_time), sum(energy_kwh)
FROM energy_readings;
-- expected: 10643735 | 4000 | 2026-09-01 00:00:00+02 | 2026-09-28 23:45:00+02 | 3853704.3468...
```

### Step 4 – Chunk intervals (§3)

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d energy_grid -f sql\05_chunk_checks.sql
python bench_chunks.py        # writes benchmark_chunks_runs.csv and benchmark_chunks_summary.csv
Import-Csv benchmark_chunks_summary.csv | Format-Table -AutoSize
```

`energy_readings_3h` and `energy_readings_week` are filled with the cleaned rows and carry the same two B-tree indexes (`event_time`; `meter_id, event_time`); run `ANALYZE` after loading. Close competing programs during the timing runs.

### Step 5 – Compression (§4)

```powershell
python load_compress.py       # experiment start, cutoff = start - 48 h (compression_cutoff.txt), per-chunk log
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d energy_grid -f sql\10_compression_sizes.sql
python bench_compression.py   # writes benchmark_compression_runs.csv and benchmark_compression_summary.csv
```

The two compression policies (chunks older than 48 hours) stay paused until the measurements are complete, then are resumed.

### Step 6 – Analysis (§5)

```powershell
python analysis_5_1.py    # demand patterns, three highest 15-minute intervals
python analysis_5_2.py    # regions and customer types, energy per meter
python analysis_5_3.py    # completeness, 21 September totals (received by midnight vs all arrivals)
python analysis_5_4.py    # anomaly rule and comparison with anomaly_events()
```

### Step 7 – Continuous aggregates and freshness test (§6)

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d energy_grid -f sql\12_caggs_policies.sql
python test_freshness.py
```

The three views (`cagg_15m_region`, `cagg_hour_region`, `cagg_day_meter`) are created empty with `timescaledb.materialized_only = true`, refreshed manually over the whole period, and only then given refresh policies (3-day start offset, 1-hour end offset, 15-minute schedule). The policies alone do not populate the older September data.

### Step 8 – Dashboards (§7)

Two PowerShell windows, one dashboard per process:

```powershell
python dashboard_app.py Raw          # http://127.0.0.1:8051  (energy_readings + meters)
python dashboard_app.py Aggregate    # http://127.0.0.1:8052  (continuous aggregates)
```

Filters: days 2026-09-22 to 2026-09-28 (both included) and meter 1000000000. Then:

```powershell
python verify_dashboards.py              # keys, counts, energy and completeness of the five panels
python summarize_dashboard_timings.py    # median, min, max from dashboard_timings.csv
```

Timing procedure (§7.4): pause the background jobs, run **one server at a time**, click Refresh once as warm-up and ten times for the measurements (each refresh is appended to `dashboard_timings.csv`), then resume the jobs:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d energy_grid -c "SELECT job_id, alter_job(job_id, scheduled => false) FROM timescaledb_information.jobs WHERE job_id >= 1000;"
# ... measurements ...
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d energy_grid -c "SELECT job_id, alter_job(job_id, scheduled => true) FROM timescaledb_information.jobs WHERE job_id >= 1000;"
```

### Step 9 – Forecast (§8)

```powershell
python section8_forecast.py | Tee-Object section8_output.txt
```

Writes `forecast_dataset.csv`, `forecast_predictions.csv`, `forecast_validation.csv`, `forecast_metrics.csv`, `forecast_peaks.csv` and `forecast_plot_Region_1.png`. Training 1–14 September, validation 15–21 September, test 22–28 September; features: `lag_24`, `lag_48`, `prev_day_mean`, `hour_feat`, `dow`, `is_weekend` and the region.

## 6. Pilot run and the four counts of section 1.3

The pilot replays the first 2,000 dictionaries of `iter_readings()` through MQTT (topic `energy/meters/{meter_id}`, QoS 1, no retained messages). Start the subscriber **before** the publisher and begin with an empty `energy_live`.

```powershell
# window 1 - empty the pilot table, then start the subscriber (energy/meters/#, QoS 1)
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d energy_grid -c "TRUNCATE energy_live;"
python subscriber.py

# window 2 - once the subscriber is waiting
python publisher.py

# window 3 - after all inserts are committed
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d energy_grid -c "SELECT count(*) FROM energy_live;"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d energy_grid -c "SELECT * FROM energy_live ORDER BY event_time, meter_id LIMIT 5;"
```

Verify the four counts. Each has a target of 2,000; deliberate generator duplicates count as separate messages and rows.

| Stage | Where to read it | Target |
|---|---|---|
| Dictionaries taken from the generator | publisher output | 2,000 |
| Messages acknowledged by the broker (PUBACK) | publisher output | 2,000 |
| Messages received by the subscriber | subscriber output | 2,000 |
| Rows committed in `energy_live` | `SELECT count(*) FROM energy_live;` | 2,000 |

Any difference must be explained with the program logs (loss, redelivery, parsing error, failed insert), corrected, and the pilot repeated.

## 7. Regenerating the dataset locally

The generator is deterministic and works in memory only: every call of `iter_readings()` restarts the same dataset (4,000 meters, one reading per 15 minutes, 1 September 00:00 to 29 September 00:00 exclusive). To rebuild the data:

1. Complete Step 0 and Step 1.
2. Run `python load_full.py`. The number of consumed dictionaries, the committed row count and `dataset_info()["expected_counts"]["emitted_readings"]` must all equal 10,696,848.
3. Run the cleaning files of `sql/` (Step 3) and check that 10,643,735 rows remain and that no duplicate (`meter_id`, `event_time`) pair is left. Missing intervals stay as gaps and are never replaced by zero.
4. Fill the other hypertables with the files of `sql/` and the programs of Steps 4 and 5.

Intermediate CSV files, if any, may be deleted once the load is verified; the programs above regenerate them.

## 8. Recorded results and output files

| File | Content |
|---|---|
| `benchmark_chunks_runs.csv`, `benchmark_chunks_summary.csv` | Q1–Q5 timings (median, min, max, session seconds, result check) on the three chunk configurations |
| `benchmark_compression_runs.csv`, `benchmark_compression_summary.csv` | Q1–Q5 timings on the five table configurations |
| `compression_cutoff.txt`, `compression_chunk_log` | Compression cutoff (experiment start − 48 h) and per-chunk load and compression times |
| `explain_Q2_*.txt`, `explain_Q4_*.txt` | Execution plans (EXPLAIN ANALYZE, BUFFERS) per configuration |
| `dashboard_timings.csv` | One row per dashboard refresh: per-panel query ms, server total, browser time |
| `dashboard_export_*`, `dashboard_verification` | Data behind every panel and the Raw-versus-Aggregate comparison |
| `section8_output.txt`, `forecast_*.csv` | Forecast dataset, predictions, validation table, metrics and peak-hour errors |

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| Programs cannot connect to PostgreSQL | Set `$env:PGPASSWORD` in the same PowerShell window; check the service `postgresql-x64-18` is running |
| Dashboard shows an old layout or the port is busy | Stop the previous server (`Ctrl+C`, or `taskkill /F /IM python.exe`), restart it, then reload the page with `Ctrl+F5` |
| `Whole dashboard ... ms` line is missing | It appears after a click on **Refresh**, not after the first page load |
| `energy_live` is not empty before the pilot | `TRUNCATE energy_live;` and repeat the pilot |
| `w32tm` error 0x80070426 | The Windows Time service is not started; the machine clock was read from `Get-Date` and the taskbar (UTC+02:00) |

## 10. Notes on method

- The generator `smart_meter_simulator.py` is never modified; all processing and database code is ours.
- Benchmarks are **warm-cache**: one warm-up, then five measured executions per query and table (§3, §4); one warm-up, then ten refreshes per dashboard mode (§7.4). PostgreSQL is not restarted and caches are not cleared between runs.
- Dashboard query-result caching is disabled; the Aggregate dashboard reads only the continuous aggregates (and `meters` for labels and registered counts).
- Forecasts are offline: hourly regional totals of cleaned readings are treated as finalised; the remaining missing readings and the effect of delayed arrivals on a live forecast are discussed in the report (§8.4).
- Measured results, observations and judgements are in the PDF report.
