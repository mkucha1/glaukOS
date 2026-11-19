"""Symulator czujników statkowych (ZAŚLEPKA — Maciej może ją zastąpić swoją wersją).

Publikuje co 2 s na MQTT  ship/{SHIP_ID}/sensors/{TAG}  (retained, QoS 1)
payload: {"tag": "CW_PUMP_2_P", "value": 1.9, "unit": "bar", "ts": "...Z", "quality": "good"}
Bez paho/MQTT — wysyła to samo przez HTTP POST {API_URL}/api/sensors.

Uruchom:  python -m sim.sensors        (w Dockerze robi to usługa `sensors`)
Scenariusz:  SCENARIO=mismatch  -> pompa nr 2 pokazuje 2.6 bar (wywoła pytanie o rozbieżność)
"""
from __future__ import annotations

import json
import math
import os
import random
import time
import urllib.request
from datetime import datetime, timezone

SHIP = os.getenv("SHIP_ID", "demo")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
API_URL = os.getenv("API_URL", "http://localhost:8000")
PERIOD = float(os.getenv("SENSOR_PERIOD_S", 2))
SCENARIO = os.getenv("SCENARIO", "demo")

# tag: (wartość bazowa, jednostka, amplituda szumu)
BASE = {
    "CW_PUMP_1_P": (2.4, "bar", 0.03),
    "CW_PUMP_2_P": (1.9 if SCENARIO != "mismatch" else 2.6, "bar", 0.03),
    "ME_LO_P": (4.2, "bar", 0.05),
    "ME_LO_T": (45.0, "°C", 0.4),
    "FO_PUR_1_T": (98.0, "°C", 0.5),
    "AE1_EXH_T": (380.0, "°C", 3.0),
    "AE2_EXH_T": (375.0, "°C", 3.0),
}


def reading(tag: str, t: float) -> dict:
    base, unit, amp = BASE[tag]
    v = base + amp * math.sin(t / 7 + hash(tag) % 10) + random.uniform(-amp, amp) / 2
    return {"tag": tag, "value": round(v, 2), "unit": unit,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "quality": "good"}


def main() -> None:
    client = None
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sensor-sim-{SHIP}", protocol=mqtt.MQTTv5)
        client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        client.loop_start()
        print(f"[sim] MQTT -> {MQTT_HOST}:{MQTT_PORT}")
    except Exception as e:
        print(f"[sim] MQTT niedostępne ({e!r}) — wysyłam przez HTTP {API_URL}/api/sensors")
    while True:
        t = time.time()
        batch = [reading(tag, t) for tag in BASE]
        if client is not None:
            for r in batch:
                client.publish(f"ship/{SHIP}/sensors/{r['tag']}", json.dumps(r), qos=1, retain=True)
        else:
            try:
                req = urllib.request.Request(f"{API_URL}/api/sensors", data=json.dumps(batch).encode(),
                                             headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=3).read()
            except Exception as e:
                print(f"[sim] HTTP error: {e!r}")
        time.sleep(PERIOD)


if __name__ == "__main__":
    main()
