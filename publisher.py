import json
import time
from datetime import datetime, timedelta, timezone
from itertools import islice

import paho.mqtt.client as mqtt

import smart_meter_simulator as s

CAT = timezone(timedelta(hours=2), "CAT")
BROKER, PORT = "localhost", 1883
N = 2000
PAUSE_SECONDS = 0.01   # pacing between messages (about 100 messages per second)


def now():
    return datetime.now(CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


acked = 0


def on_publish(client, userdata, mid, reason_code, properties):
    global acked
    acked += 1


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="energy_pilot_publisher",
                     protocol=mqtt.MQTTv311)
client.on_publish = on_publish
client.max_queued_messages_set(0)      # unlimited local queue
client.max_inflight_messages_set(50)
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()

print(f"[{now()}] publisher started")
generated = 0
infos = []
for record in islice(s.iter_readings(), N):
    generated += 1
    topic = f"energy/meters/{record['meter_id']}"
    infos.append(client.publish(topic, json.dumps(record), qos=1, retain=False))
    time.sleep(PAUSE_SECONDS)
    if generated % 500 == 0:
        print(f"[{now()}] generated={generated}")

failed = 0
for info in infos:
    info.wait_for_publish(timeout=60)
    if not info.is_published():
        failed += 1

client.loop_stop()
client.disconnect()
print(f"[{now()}] PUBLISHER DONE")
print(f"  dictionaries from generator : {generated}")
print(f"  acknowledged by broker      : {acked}")
print(f"  not acknowledged            : {failed}")