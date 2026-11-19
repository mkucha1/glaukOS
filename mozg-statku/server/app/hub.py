"""Komunikacja w czasie rzeczywistym po sieci statku — bez chmury.

Jeden punkt `Hub.publish(topic, payload)` rozsyła wiadomość:
  1. do Mosquitto (MQTT 5, QoS 1) — główna ścieżka; PWA łączy się przez wss://<serwer>/mqtt,
  2. do klientów SSE (GET /api/stream) — fallback, gdy MQTT.js/WebSocket sprawia kłopot.

Zasada: MQTT/SSE to „dzwonek”, a prawda jest w rejestrze (REST). Po ponownym połączeniu
klient zawsze dociąga stan przez REST (albo SSE z ?since_seq=), więc zgubiony dzwonek nic nie psuje.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Callable


def topic_matches(pattern: str, topic: str) -> bool:
    """Dopasowanie w stylu MQTT: '+' = jeden poziom, '#' = reszta."""
    p, t = pattern.split("/"), topic.split("/")
    for i, part in enumerate(p):
        if part == "#":
            return True
        if i >= len(t):
            return False
        if part != "+" and part != t[i]:
            return False
    return len(p) == len(t)


class _Sub:
    __slots__ = ("patterns", "queue", "loop")

    def __init__(self, patterns: list[str], loop: asyncio.AbstractEventLoop):
        self.patterns = patterns
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.loop = loop


class MqttBridge:
    """Cienka warstwa na paho-mqtt. Sam się łączy ponownie; gdy broker leży — serwer działa dalej."""

    def __init__(self, host: str, port: int, client_id: str, on_message: Callable[[str, Any], None],
                 subscriptions: list[str]):
        import paho.mqtt.client as mqtt  # import tutaj: brak paho != brak serwera

        self.connected = False
        self._subs = subscriptions
        self._on_message = on_message
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id,
                                  protocol=mqtt.MQTTv5)
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.on_connect = self._connected
        self.client.on_disconnect = self._disconnected
        self.client.on_message = self._message
        self.client.connect_async(host, port, keepalive=30)
        self.client.loop_start()

    def _connected(self, client, userdata, flags, reason_code, properties=None):
        self.connected = not getattr(reason_code, "is_failure", False)
        print(f"[mqtt] connected: {reason_code}")
        for s in self._subs:
            client.subscribe(s, qos=1)

    def _disconnected(self, client, userdata, *args):
        self.connected = False
        print("[mqtt] disconnected — paho ponowi połączenie automatycznie")

    def _message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            payload = msg.payload.decode("utf-8", "replace")
        self._on_message(msg.topic, payload)

    def publish(self, topic: str, payload: dict, retain: bool = False, qos: int = 1) -> None:
        self.client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=qos, retain=retain)

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


class Hub:
    def __init__(self) -> None:
        self._subs: list[_Sub] = []
        self._lock = threading.Lock()
        self._retained: dict[str, dict] = {}
        self._handlers: list[tuple[str, Callable[[str, Any], None]]] = []
        self.mqtt: MqttBridge | None = None
        self.published = 0

    # ---------------------------------------------------------------- MQTT
    def start_mqtt(self, host: str, port: int, client_id: str, subscriptions: list[str]) -> None:
        try:
            self.mqtt = MqttBridge(host, port, client_id, self._incoming, subscriptions)
            print(f"[mqtt] łączę z {host}:{port}")
        except ImportError:
            print("[mqtt] paho-mqtt nie jest zainstalowane — działa tylko SSE")
        except Exception as e:
            print(f"[mqtt] start nieudany ({e!r}) — działa tylko SSE")

    def on(self, pattern: str, handler: Callable[[str, Any], None]) -> None:
        """Rejestruje obsługę wiadomości przychodzących (np. czujniki)."""
        self._handlers.append((pattern, handler))

    def _incoming(self, topic: str, payload: Any) -> None:
        for pattern, h in self._handlers:
            if topic_matches(pattern, topic):
                try:
                    h(topic, payload)
                except Exception as e:
                    print(f"[hub] handler error on {topic}: {e!r}")

    # ---------------------------------------------------------------- publikacja
    def publish(self, topic: str, payload: dict, retain: bool = False) -> None:
        self.published += 1
        if retain:
            self._retained[topic] = payload
        if self.mqtt is not None:
            try:
                self.mqtt.publish(topic, payload, retain=retain)
            except Exception as e:
                print(f"[mqtt] publish error: {e!r}")
        with self._lock:
            subs = list(self._subs)
        for s in subs:
            if any(topic_matches(p, topic) for p in s.patterns):
                s.loop.call_soon_threadsafe(self._put, s, topic, payload)

    @staticmethod
    def _put(s: _Sub, topic: str, payload: dict) -> None:
        try:
            s.queue.put_nowait((topic, payload))
        except asyncio.QueueFull:
            pass  # wolny klient — i tak dociągnie stan przez REST

    # ---------------------------------------------------------------- SSE
    def subscribe(self, patterns: list[str]) -> _Sub:
        s = _Sub(patterns, asyncio.get_running_loop())
        with self._lock:
            self._subs.append(s)
        for topic, payload in list(self._retained.items()):
            if any(topic_matches(p, topic) for p in patterns):
                s.queue.put_nowait((topic, payload))
        return s

    def unsubscribe(self, s: _Sub) -> None:
        with self._lock:
            if s in self._subs:
                self._subs.remove(s)

    def status(self) -> dict:
        return {"mqtt": None if self.mqtt is None else ("connected" if self.mqtt.connected else "reconnecting"),
                "sse_clients": len(self._subs), "published": self.published}

    def close(self) -> None:
        if self.mqtt:
            self.mqtt.close()
