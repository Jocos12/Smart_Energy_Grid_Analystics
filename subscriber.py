import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt
import psycopg2

CAT = timezone(timedelta(hours=2), "CAT")
DB = dict(host="localhost", port=5432, dbname="energy_grid", user="postgres",
          password=os.environ.get("PGPASSWORD", "YOUR_PASSWORD"))
BROKER, PORT = "localhost", 1883
TOPIC = "energy/meters/#"
IDLE_SECONDS = 10
FIELDS = ("meter_id", "event_time", "received_time", "power_kw", "voltage_v",
          "current_a", "frequency_hz", "energy_kwh")
SQL = ("INSERT INTO energy_live (" + ",".join(FIELDS) + ") VALUES ("
       + ",".join(["%s"] * len(FIELDS)) + ")")

conn = psycopg2.connect(**DB)
lock = threading.Lock()
stats = {"received": 0, "inserted": 0, "parse_errors": 0,
         "insert_errors": 0, "redelivered": 0, "last": None}


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"[{now()}] connected, reason={reason_code}; subscribing to {TOPIC} at QoS 1")
    client.subscribe(TOPIC, qos=1)


def on_message(client, userdata, msg):
    with lock:
        stats["received"] += 1
        stats["last"] = time.time()
        if msg.dup:
            stats["redelivered"] += 1
            print(f"[{now()}] DUP flag on message {msg.mid} topic={msg.topic}")
        try:
            record = json.loads(msg.payload.decode("utf-8"))
            row = tuple(record[f] for f in FIELDS)
        except Exception as exc:
            stats["parse_errors"] += 1
            print(f"[{now()}] PARSE ERROR on {msg.topic}: {exc}")
            return
        try:
            with conn.cursor() as cur:
                cur.execute(SQL, row)
            conn.commit()
            stats["inserted"] += 1
        except Exception as exc:
            conn.rollback()
            stats["insert_errors"] += 1
            print(f"[{now()}] INSERT ERROR: {exc}")
        if stats["received"] % 500 == 0:
            print(f"[{now()}] received={stats['received']} inserted={stats['inserted']}")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="energy_pilot_subscriber",
                     protocol=mqtt.MQTTv311, clean_session=False)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()
print(f"[{now()}] subscriber started; waiting for messages (Ctrl+C to stop)")

try:
    while True:
        time.sleep(1)
        with lock:
            last = stats["last"]
        if last is not None and time.time() - last > IDLE_SECONDS:
            break
except KeyboardInterrupt:
    pass

client.loop_stop()
client.disconnect()
with conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM energy_live")
    in_db = cur.fetchone()[0]
conn.close()
print(f"[{now()}] SUBSCRIBER DONE")
print(f"  messages received      : {stats['received']}")
print(f"  rows inserted (commit) : {stats['inserted']}")
print(f"  parse errors           : {stats['parse_errors']}")
print(f"  insert errors          : {stats['insert_errors']}")
print(f"  redelivered (DUP flag) : {stats['redelivered']}")
print(f"  rows in energy_live    : {in_db}")