"""Assignment I, 7.3: display the dashboards and save the three screenshots.

    python capture_7_3.py            -> paired, raw, aggregate (in this order)
    python capture_7_3.py paired     -> only 7.3_paired_dashboard_outputs.png
    python capture_7_3.py raw        -> only 7.3_paired_dashboard_outputs_raw.png
    python capture_7_3.py aggregate  -> only 7.3_paired_dashboard_outputs_aggregate.png
    python capture_7_3.py all --delay 20   (20 s to click Refresh before each capture)

Prerequisites: both dashboards running (ports 8051 and 8052), and  pip install pillow
The screenshot is the FULL screen, so the taskbar and the clock are visible.
"""
import argparse
import ctypes
import os
import subprocess
import tempfile
import time
import webbrowser
from pathlib import Path

from PIL import ImageGrab

RAW_URL = "http://127.0.0.1:8051"
AGG_URL = "http://127.0.0.1:8052"
OUT_DIR = Path("screenshots")
FILES = {
    "paired": "7.3_paired_dashboard_outputs.png",
    "raw": "7.3_paired_dashboard_outputs_raw.png",
    "aggregate": "7.3_paired_dashboard_outputs_aggregate.png",
}
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

# Side-by-side page: each dashboard is rendered at a desktop width, then scaled down.
# Change --s (0.5 = 50 %, 0.6 = 60 %) if the text is too small or the panels are cut.
PAIRED_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>7.3 Raw vs Aggregate</title>
<style>
  :root { --s: 0.5; }
  html, body { margin: 0; height: 100%%; background: #f3f4f6; overflow: hidden; }
  .row { display: flex; height: 100vh; }
  .cell { width: 50%%; height: 100vh; overflow: hidden; position: relative; }
  .cell + .cell { border-left: 3px solid #111; }
  iframe { border: 0; position: absolute; top: 0; left: 0;
           width: calc(100%% / var(--s)); height: calc(100vh / var(--s));
           transform: scale(var(--s)); transform-origin: top left; }
</style></head>
<body><div class="row">
  <div class="cell"><iframe src="%(raw)s"></iframe></div>
  <div class="cell"><iframe src="%(agg)s"></iframe></div>
</div></body></html>
"""


def chrome_path():
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    return None


def open_page(url):
    exe = chrome_path()
    if exe:
        subprocess.Popen([exe, "--new-window", "--start-maximized", url])
    else:
        webbrowser.open(url)


def paired_url():
    path = Path(tempfile.gettempdir()) / "paired_view_7_3.html"
    path.write_text(PAIRED_HTML % {"raw": RAW_URL, "agg": AGG_URL}, encoding="utf-8")
    return path.as_uri()


def countdown(seconds, text):
    print(text)
    for s in range(seconds, 0, -1):
        print(f"  capture in {s:2d} s ", end="\r", flush=True)
        time.sleep(1)
    print(" " * 30, end="\r")


def shoot(kind, delay):
    if kind == "paired":
        url = paired_url()
        msg = "Click Refresh in the Raw frame (left) AND in the Aggregate frame (right)."
    elif kind == "raw":
        url = RAW_URL
        msg = "Click Refresh in Raw and wait for the 'Whole dashboard ... ms' line."
    else:
        url = AGG_URL
        msg = "Click Refresh in Aggregate and wait for the 'Whole dashboard ... ms' line."
    open_page(url)
    countdown(delay, f"[{kind}] {msg}")
    OUT_DIR.mkdir(exist_ok=True)
    target = OUT_DIR / FILES[kind]
    ImageGrab.grab(all_screens=False).save(target)
    print(f"  saved: {target}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="?", default="all", choices=["all", "paired", "raw", "aggregate"])
    ap.add_argument("--delay", type=int, default=15, help="seconds to click Refresh before the capture")
    a = ap.parse_args()
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # full-resolution capture on scaled displays
    except Exception:
        pass
    kinds = ["paired", "raw", "aggregate"] if a.what == "all" else [a.what]
    for k in kinds:
        shoot(k, a.delay)
        time.sleep(1)
    print("Done. Check that the taskbar, the clock and the 'Whole dashboard' lines are visible.")


if __name__ == "__main__":
    main()
