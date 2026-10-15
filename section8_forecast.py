"""Assignment I, section 8: next-day hourly regional forecast (kWh).

    python -m pip install scikit-learn matplotlib
    python section8_forecast.py

Reads the cleaned energy_readings + meters (password: PGPASSWORD), builds one row per region and
CAT hour, then runs 8.1 (dataset, splits, features), 8.2 (previous-day baseline),
8.3 (one regression model, several configurations) and 8.4 (comparison).
Outputs: forecast_dataset.csv, forecast_predictions.csv, forecast_validation.csv,
forecast_metrics.csv, forecast_peaks.csv, forecast_plot_Region_1.png
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg2
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "YOUR_PASSWORD"))
REGIONS = [f"Region {i}" for i in range(1, 11)]
PLOT_REGION = "Region 1"
SPLITS = {"train": ("2026-09-01", "2026-09-14"),
          "validation": ("2026-09-15", "2026-09-21"),
          "test": ("2026-09-22", "2026-09-28")}
NUM = ["lag_24", "lag_48", "prev_day_mean", "hour", "dow", "is_weekend"]
CONFIGS = {
    "C1": dict(max_iter=100, learning_rate=0.05, max_depth=3),
    "C2": dict(max_iter=300, learning_rate=0.05, max_depth=5),
    "C3": dict(max_iter=300, learning_rate=0.10, max_depth=None),
}
LOOKBACK_H = 48  # longest lag used by any feature

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


def banner(t):
    print("\n" + "=" * 8 + " " + t + " " + "=" * 8)


def mae(e):
    return float(np.mean(np.abs(e)))


def rmse(e):
    return float(np.sqrt(np.mean(np.square(e))))


# ------------------------------------------------------------------ 8.1
banner("8.1 Dataset: one row per region and CAT hour")
conn = psycopg2.connect(**DB)
cur = conn.cursor()
cur.execute("""
    SELECT time_bucket('1 hour', er.event_time, 'Africa/Kigali') AS hour, m.region,
           sum(er.energy_kwh) AS energy_kwh, count(*) AS readings
    FROM energy_readings er JOIN meters m ON m.meter_id = er.meter_id
    GROUP BY 1, 2 ORDER BY 2, 1""")
obs = pd.DataFrame(cur.fetchall(), columns=["hour", "region", "energy_kwh", "readings"])
conn.close()
obs["hour"] = pd.to_datetime(obs["hour"], utc=True).dt.tz_convert("Africa/Kigali").dt.tz_localize(None)
obs["energy_kwh"] = obs["energy_kwh"].astype(float)

hours = pd.date_range("2026-09-01 00:00", "2026-09-28 23:00", freq="h")
grid = pd.MultiIndex.from_product([REGIONS, hours], names=["region", "hour"]).to_frame(index=False)
d = grid.merge(obs, on=["region", "hour"], how="left")
d["readings"] = d["readings"].fillna(0).astype(int)
print(f"Observed region-hours: {obs.shape[0]} of {d.shape[0]} planned (10 regions x 672 h)")
print(f"Absent region-hours (no readings): {int((d['readings'] == 0).sum())}"
      f"  -> target kept as NaN, row excluded from training and evaluation")
print(f"Reading count per region-hour: min={obs['readings'].min()}, median={obs['readings'].median():.0f}, "
      f"max={obs['readings'].max()} (400 meters x 4 intervals = 1600 if complete)")

d = d.sort_values(["region", "hour"]).reset_index(drop=True)
d["date"] = d["hour"].dt.normalize()
d["origin"] = d["date"]  # forecast origin = 00:00 CAT of the target day
g = d.groupby("region")["energy_kwh"]
d["lag_24"] = g.shift(24)
d["lag_48"] = g.shift(48)
daily_mean = d.groupby(["region", "date"])["energy_kwh"].mean()
prev_idx = pd.MultiIndex.from_arrays([d["region"], d["date"] - pd.Timedelta(days=1)])
d["prev_day_mean"] = daily_mean.reindex(prev_idx).to_numpy()
d["hour_feat"] = d["hour"].dt.hour          # 'hour' stays the timestamp; 'hour_feat' is the numeric hour 0-23
d["dow"] = d["hour"].dt.dayofweek
d["is_weekend"] = (d["dow"] >= 5).astype(int)
FEATURES_NUM = ["lag_24", "lag_48", "prev_day_mean", "hour_feat", "dow", "is_weekend"]

# splits by target timestamp
d["split"] = None
for name, (a, b) in SPLITS.items():
    m = (d["hour"] >= pd.Timestamp(a)) & (d["hour"] < pd.Timestamp(b) + pd.Timedelta(days=1))
    d.loc[m, "split"] = name
print("\nSplits (by target timestamp, CAT):")
rows = []
for name, (a, b) in SPLITS.items():
    s = d[d["split"] == name]
    rows.append((name, len(s), s["hour"].min(), s["hour"].max(), int(s["energy_kwh"].notna().sum())))
print(pd.DataFrame(rows, columns=["split", "rows", "first_hour", "last_hour", "rows_with_target"]).to_string(index=False))

# features: name, lag/window, earliest usable target
start = pd.Timestamp("2026-09-01 00:00")
feat_info = pd.DataFrame([
    ("lag_24", "lag 24 h (same hour, previous day)", 24),
    ("lag_48", "lag 48 h (same hour, two days earlier)", 48),
    ("prev_day_mean", "window 24 h (mean of the previous calendar day)", 24),
    ("hour_feat", "calendar, no lookback", 0),
    ("dow", "calendar, no lookback", 0),
    ("is_weekend", "calendar, no lookback", 0),
], columns=["feature", "lag_or_window", "hours"])
feat_info["earliest_usable_target"] = [
    (start + pd.Timedelta(hours=int(h))).strftime("%Y-%m-%d %H:%M") if h else start.strftime("%Y-%m-%d %H:%M")
    for h in feat_info["hours"]]
# prev_day_mean needs the complete previous day: earliest target is 2026-09-02 00:00
feat_info.loc[feat_info["feature"] == "prev_day_mean", "earliest_usable_target"] = "2026-09-02 00:00"
print("\nFeatures:")
print(feat_info[["feature", "lag_or_window", "earliest_usable_target"]].to_string(index=False))

first_usable = start + pd.Timedelta(hours=LOOKBACK_H)
print(f"\nChosen initial lookback: {LOOKBACK_H} h -> training rows start at {first_usable}")
train_all = d[d["split"] == "train"]
excluded_time = train_all[train_all["hour"] < first_usable]
train = train_all[(train_all["hour"] >= first_usable) & train_all["energy_kwh"].notna()].copy()
val = d[(d["split"] == "validation") & d["energy_kwh"].notna()].copy()
test = d[(d["split"] == "test") & d["energy_kwh"].notna()].copy()
print(f"Training rows before lookback exclusions: {len(train_all)}")
print(f"Excluded (before {first_usable.date()}): {len(excluded_time)}")
print(f"Excluded (absent target): {int(((train_all['hour'] >= first_usable) & train_all['energy_kwh'].isna()).sum())}")
print(f"Retained training rows: {len(train)} (same rows for every model configuration)")
print(f"Validation rows: {len(val)} | Test rows: {len(test)}")

banner("8.1 Check: every lag source timestamp precedes its forecast origin")
chk = d[d["hour"] >= first_usable].copy()
chk["src_lag_24"] = chk["hour"] - pd.Timedelta(hours=24)
chk["src_lag_48"] = chk["hour"] - pd.Timedelta(hours=48)
chk["src_prev_day_last"] = chk["origin"] - pd.Timedelta(hours=1)  # last hour inside prev_day_mean window
ok = ((chk["src_lag_24"] < chk["origin"]) & (chk["src_lag_48"] < chk["origin"])
      & (chk["src_prev_day_last"] < chk["origin"])).all()
print(f"Rows checked: {len(chk)} | all lag sources < forecast origin: {ok}")
assert ok
print("\nFeature examples (Region 1, test day 2026-09-22):")
ex = d[(d["region"] == "Region 1") & (d["date"] == "2026-09-22")].head(6)
print(ex[["hour", "origin", "energy_kwh", "lag_24", "lag_48", "prev_day_mean", "hour_feat", "dow", "is_weekend"]]
      .to_string(index=False))
d.drop(columns=["origin"]).to_csv("forecast_dataset.csv", index=False)

# ------------------------------------------------------------------ 8.2
banner("8.2 Previous-day baseline")
fill = train.groupby(["region", "hour_feat"])["energy_kwh"].median().rename("train_median").reset_index()
test = test.merge(fill, on=["region", "hour_feat"], how="left")
n_fill = int(test["lag_24"].isna().sum())
test["baseline"] = test["lag_24"].fillna(test["train_median"])
print(f"Baseline predictions: {len(test)} (expected 1680) | lag_24 absent, filled with training median: {n_fill}")
err_b = test["baseline"] - test["energy_kwh"]
print(f"Baseline test MAE = {mae(err_b):.3f} kWh | RMSE = {rmse(err_b):.3f} kWh")
print("\nSample baseline predictions:")
print(test[["region", "hour", "energy_kwh", "baseline"]].head(8).to_string(index=False))

# ------------------------------------------------------------------ 8.3
banner("8.3 Regression model: HistGradientBoostingRegressor, three configurations")


def make(cfg):
    pre = ColumnTransformer([
        ("region", OneHotEncoder(handle_unknown="ignore"), ["region"]),
        ("num", SimpleImputer(strategy="median"), FEATURES_NUM)])  # imputer fitted on training only
    return Pipeline([("pre", pre), ("model", HistGradientBoostingRegressor(random_state=0, **cfg))])


X_cols = ["region"] + FEATURES_NUM
print("Shared predictors:", X_cols)
res, fitted = [], {}
for cid, cfg in CONFIGS.items():
    p = make(cfg).fit(train[X_cols], train["energy_kwh"])
    e = p.predict(val[X_cols]) - val["energy_kwh"].to_numpy()
    fitted[cid] = p
    res.append((cid, str(cfg), len(train), len(val), mae(e), rmse(e)))
    print(f"{cid} trained | validation MAE = {mae(e):.3f} kWh")
vt = pd.DataFrame(res, columns=["config_id", "settings", "train_rows", "validation_rows",
                                "validation_MAE_kWh", "validation_RMSE_kWh"])
print("\nValidation table:")
print(vt.to_string(index=False))
vt.to_csv("forecast_validation.csv", index=False)
best = vt.sort_values("validation_MAE_kWh").iloc[0]["config_id"]
print(f"\nSelected configuration (lowest validation MAE): {best} {CONFIGS[best]}")
final = fitted[best]  # frozen: fitted on training only, never refitted on test days
test["model"] = final.predict(test[X_cols])
print(f"Model predictions on test: {len(test)} (expected 1680)")
print("\nSample test predictions:")
print(test[["region", "hour", "energy_kwh", "baseline", "model"]].head(8).round(2).to_string(index=False))
test[["region", "hour", "energy_kwh", "baseline", "model"]].to_csv("forecast_predictions.csv", index=False)

# ------------------------------------------------------------------ 8.4
banner("8.4 Baseline vs model (error = predicted - actual, kWh)")
test["err_b"] = test["baseline"] - test["energy_kwh"]
test["err_m"] = test["model"] - test["energy_kwh"]
rows = [("ALL (1680)", len(test), mae(test["err_b"]), rmse(test["err_b"]), mae(test["err_m"]), rmse(test["err_m"]))]
for r in REGIONS:
    s = test[test["region"] == r]
    rows.append((r, len(s), mae(s["err_b"]), rmse(s["err_b"]), mae(s["err_m"]), rmse(s["err_m"])))
mt = pd.DataFrame(rows, columns=["scope", "n", "base_MAE", "base_RMSE", "model_MAE", "model_RMSE"])
mt["MAE_change_%"] = 100 * (mt["base_MAE"] - mt["model_MAE"]) / mt["base_MAE"]
print(mt.round(3).to_string(index=False))
mt.to_csv("forecast_metrics.csv", index=False)
print("\n(MAE_change_% > 0 means the model improves on the baseline.)")

banner("8.4 Highest actual test hour per region (ties: earliest)")
pk = (test.sort_values(["region", "energy_kwh", "hour"], ascending=[True, False, True])
      .groupby("region").head(1).copy())
pk["abs_err_base"] = pk["err_b"].abs()
pk["abs_err_model"] = pk["err_m"].abs()
pk["region_n"] = pk["region"].str.extract(r"(\d+)")[0].astype(int)
pk = pk.sort_values("region_n")
print(pk[["region", "hour", "energy_kwh", "baseline", "abs_err_base", "model", "abs_err_model"]]
      .round(2).to_string(index=False))
pk[["region", "hour", "energy_kwh", "baseline", "abs_err_base", "model", "abs_err_model"]].to_csv(
    "forecast_peaks.csv", index=False)

s = test[test["region"] == PLOT_REGION].sort_values("hour")
fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(s["hour"], s["energy_kwh"], label="Actual", color="black", lw=2)
ax.plot(s["hour"], s["baseline"], label="Baseline (previous day)", color="#d62728", lw=1.3)
ax.plot(s["hour"], s["model"], label=f"Model ({best})", color="#2563eb", lw=1.3)
ax.set_title(f"{PLOT_REGION}: actual vs forecasts, 22-28 September 2026")
ax.set_xlabel("Hour (CAT)")
ax.set_ylabel("Energy (kWh)")
ax.grid(alpha=0.3)
ax.legend()
fig.autofmt_xdate()
fig.tight_layout()
fig.savefig("forecast_plot_Region_1.png", dpi=130)
print("\nPlot saved: forecast_plot_Region_1.png")
