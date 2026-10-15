"""Assignment I, section 7: dashboard app (Dash). One process per dashboard.

    python dashboard_app.py Raw         -> http://127.0.0.1:8051  (energy_readings + meters)
    python dashboard_app.py Aggregate   -> http://127.0.0.1:8052  (continuous aggregates)

No query-result caching: each Refresh click re-runs the five panel queries.
Per-panel query durations are measured on the server (perf_counter around execute + fetchall).
The whole-dashboard time is measured in the browser, from the click until the response has
arrived and two animation frames have passed (approximation of "all five panels rendered").
Every refresh is appended to dashboard_timings.csv. Password: PGPASSWORD environment variable.
"""
import csv
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import psycopg2
from dash import Dash, Input, Output, State, dcc, html
from flask import jsonify, request

import dashboard_queries as dq

MODE = sys.argv[1] if len(sys.argv) > 1 else "Raw"
if MODE not in ("Raw", "Aggregate"):
    sys.exit("usage: python dashboard_app.py Raw|Aggregate")
PORT = {"Raw": 8051, "Aggregate": 8052}[MODE]
CAT = timezone(timedelta(hours=2), "CAT")
DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "YOUR_PASSWORD"))
LOG = "dashboard_timings.csv"
HEADER = ["mode", "logged_at_cat", "run_id", "start_date", "end_date", "meter_id",
          "panel1_ms", "panel2_ms", "panel3_ms", "panel4_ms", "panel5_ms",
          "server_total_ms", "client_elapsed_ms"]

conn = psycopg2.connect(**DB)
conn.autocommit = True
cur = conn.cursor()
db_lock = threading.Lock()
file_lock = threading.Lock()
RUNS = {}

ACCENT = "#2563eb" if MODE == "Raw" else "#059669"
REGIONS = [f"Region {i}" for i in range(1, 11)]
PALETTE = px.colors.qualitative.D3


def cat_naive(df, col="bucket"):
    df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert("Africa/Kigali").dt.tz_localize(None)
    return df


def figures(rows):
    d = {k: pd.DataFrame(rows[k], columns=dq.COLUMNS[k]) for k in rows}
    for k in (1, 2, 3, 4):
        cat_naive(d[k])
    # 7-day periods: readable text label instead of a continuous time axis
    d[3]["bucket"] = d[3]["bucket"].dt.round("s").dt.strftime("Start %Y-%m-%d")
    order = {"region": REGIONS}
    f1 = px.line(d[1], x="bucket", y="energy_kwh", color="region", category_orders=order,
                 color_discrete_sequence=PALETTE,
                 labels={"bucket": "Hour (CAT)", "energy_kwh": "Energy (kWh)"})
    f2 = px.bar(d[2], x="bucket", y="energy_kwh", color_discrete_sequence=[ACCENT],
                labels={"bucket": "Day (CAT)", "energy_kwh": "Energy (kWh)"})
    f3 = px.bar(d[3], x="bucket", y="energy_kwh", color_discrete_sequence=[ACCENT], text_auto=".4s",
                labels={"bucket": "7-day period (CAT)", "energy_kwh": "Energy (kWh)"})
    f4 = px.bar(d[4], x="bucket", y="energy_kwh", color_discrete_sequence=[ACCENT],
                labels={"bucket": "Day (CAT)", "energy_kwh": "Energy (kWh)"})
    f5 = px.bar(d[5], x="region", y="completeness_pct", category_orders=order,
                color_discrete_sequence=[ACCENT], text_auto=".2f",
                labels={"region": "Region", "completeness_pct": "Completeness (%)"})
    f5.update_yaxes(range=[90, 100])
    f5.update_xaxes(tickangle=-45)
    out = []
    for k, f in zip(range(1, 6), (f1, f2, f3, f4, f5)):
        f.update_layout(title=dict(text=dq.PANELS[k], font=dict(size=15)),
                        template="plotly_white", margin=dict(l=55, r=15, t=45, b=45),
                        legend=dict(font=dict(size=10)), font=dict(size=11))
        out.append(f)
    return out


CARD = {"background": "white", "borderRadius": "10px", "boxShadow": "0 1px 4px rgba(0,0,0,0.12)",
        "padding": "4px"}
GRAPH = {"height": "36vh"}
CFG = {"displayModeBar": False}
FIELD = {"color": "#111", "background": "white", "borderRadius": "6px",
         "padding": "6px", "border": "1px solid #ccc"}

app = Dash(__name__, title=MODE)
app.layout = html.Div(
    style={"fontFamily": "Segoe UI, Arial", "background": "#f3f4f6",
           "padding": "8px 16px", "minHeight": "100vh"},
    children=[
        # ---- header bar with filters ----
        html.Div(
            style={"display": "flex", "alignItems": "center", "gap": "18px", "flexWrap": "wrap",
                   "background": ACCENT, "color": "white", "padding": "8px 16px",
                   "borderRadius": "10px"},
            children=[
                html.H2(MODE, style={"margin": "0", "fontSize": "26px"}),
                html.Span("Days (CAT, both included):"),
                dcc.Input(id="start", type="text", value="2026-09-22", debounce=True,
                          style={**FIELD, "width": "120px"}),
                html.Span("to"),
                dcc.Input(id="end", type="text", value="2026-09-28", debounce=True,
                          style={**FIELD, "width": "120px"}),
                html.Span("Meter:"),
                dcc.Input(id="meter", type="text", value="1000000000", debounce=True,
                          style={**FIELD, "width": "190px"}),
                html.Button("Refresh", id="btn", n_clicks=0,
                            style={"padding": "6px 18px", "fontWeight": "bold", "cursor": "pointer"}),
            ],
        ),
        html.Div(id="server_txt", style={"marginTop": "6px", "fontSize": "13px"}),
        html.Div(id="client_txt", style={"fontSize": "13px", "marginBottom": "6px"}),
        dcc.Store(id="run"),
        dcc.Store(id="t0"),
        # ---- five panels ----
        html.Div(
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "10px"},
            children=[
                html.Div(dcc.Graph(id="g1", style=GRAPH, config=CFG), style={**CARD, "gridColumn": "span 2"}),
                html.Div(dcc.Graph(id="g5", style=GRAPH, config=CFG), style=CARD),
                html.Div(dcc.Graph(id="g2", style=GRAPH, config=CFG), style=CARD),
                html.Div(dcc.Graph(id="g3", style=GRAPH, config=CFG), style=CARD),
                html.Div(dcc.Graph(id="g4", style=GRAPH, config=CFG), style=CARD),
            ],
        ),
    ],
)


@app.callback([Output(f"g{i}", "figure") for i in range(1, 6)] + [Output("run", "data"), Output("server_txt", "children")],
              Input("btn", "n_clicks"),
              State("start", "value"), State("end", "value"), State("meter", "value"))
def refresh(n, start_date, end_date, meter):
    p = dq.make_params(start_date, end_date, int(meter or 1000000000))
    rows, ms = {}, []
    t_all = time.perf_counter()
    with db_lock:
        for k in range(1, 6):
            t0 = time.perf_counter()
            rows[k] = dq.run_panel(cur, MODE, k, p)
            ms.append((time.perf_counter() - t0) * 1000)
    figs = figures(rows)
    server_ms = (time.perf_counter() - t_all) * 1000
    run_id = uuid.uuid4().hex[:8]
    RUNS[run_id] = dict(start=str(start_date)[:10], end=str(end_date)[:10], meter=p["m"], ms=ms, server_ms=server_ms)
    text = "Server query ms per panel: " + ", ".join(f"P{i + 1}={v:.1f}" for i, v in enumerate(ms)) + \
           f"  |  server total (queries + figures) = {server_ms:.1f} ms"
    return figs + [{"id": run_id}, text]


app.clientside_callback(
    "function(n) { return performance.now(); }",
    Output("t0", "data"), Input("btn", "n_clicks"), prevent_initial_call=True)

app.clientside_callback(
    """
    function(run, t0, n) {
      if (!run || !n) { return window.dash_clientside.no_update; }
      return new Promise(function(resolve) {
        requestAnimationFrame(function() { requestAnimationFrame(function() {
          var elapsed = performance.now() - t0;
          fetch('/log_client', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({id: run.id, client_ms: elapsed})});
          resolve('Whole dashboard, click to rendered: ' + elapsed.toFixed(1) + ' ms');
        }); });
      });
    }
    """,
    Output("client_txt", "children"), Input("run", "data"), State("t0", "data"), State("btn", "n_clicks"))


@app.server.route("/log_client", methods=["POST"])
def log_client():
    data = request.get_json()
    r = RUNS.get(data["id"])
    if r:
        with file_lock:
            new = not os.path.exists(LOG)
            with open(LOG, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(HEADER)
                w.writerow([MODE, datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " CAT", data["id"],
                            r["start"], r["end"], r["meter"]] + [round(v, 3) for v in r["ms"]] +
                           [round(r["server_ms"], 3), round(data["client_ms"], 3)])
    return jsonify(ok=True)


if __name__ == "__main__":
    print(f"{MODE} dashboard on http://127.0.0.1:{PORT}")
    app.run(host="127.0.0.1", port=PORT, debug=False)