"""Konfiguracja serwera pokładowego — wszystko z env, z rozsądnymi wartościami domyślnymi."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # .../server


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    ship_id: str = "demo"
    data_dir: Path = ROOT / "data"
    config_dir: Path = ROOT / "config"

    # HTTP
    host: str = "0.0.0.0"
    port: int = 8000
    max_upload_mb: int = 25

    # MQTT (Mosquitto). Gdy broker niedostępny — serwer działa dalej, SSE jest fallbackiem.
    mqtt_enabled: bool = True
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    # Kolejka na ląd (store-and-forward)
    shore_url: str = "http://localhost:9000"
    shore_token: str = "demo-token"
    sync_interval_s: float = 2.0
    sync_batch: int = 50
    sat_kbps: float = 0.0          # symulowana przepustowość łącza (0 = bez limitu)
    sat_link_default: bool = True  # stan przełącznika przy pierwszym starcie

    # Pipeline AI
    max_clarify_rounds: int = 2
    # Zgłoszenie idzie do oficera tylko przy małej pewności (form.confidence < próg),
    # rozbieżności z czujnikiem albo pytaniu bez odpowiedzi. Próg > 1 = zawsze oficer.
    auto_approve_confidence: float = 0.9
    plugin_retries: int = 2
    force_stubs: set[str] = field(default_factory=set)  # np. {"stt","brain"} — plan B na scenie

    @property
    def db_path(self) -> Path:
        return self.data_dir / "events.db"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls()
        s.ship_id = os.getenv("SHIP_ID", s.ship_id)
        s.data_dir = Path(os.getenv("DATA_DIR", str(s.data_dir)))
        s.config_dir = Path(os.getenv("CONFIG_DIR", str(s.config_dir)))
        s.host = os.getenv("HOST", s.host)
        s.port = int(os.getenv("PORT", s.port))
        s.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", s.max_upload_mb))
        s.mqtt_enabled = _bool("MQTT_ENABLED", s.mqtt_enabled)
        s.mqtt_host = os.getenv("MQTT_HOST", s.mqtt_host)
        s.mqtt_port = int(os.getenv("MQTT_PORT", s.mqtt_port))
        s.shore_url = os.getenv("SHORE_URL", s.shore_url).rstrip("/")
        s.shore_token = os.getenv("SHORE_TOKEN", s.shore_token)
        s.sync_interval_s = float(os.getenv("SYNC_INTERVAL_S", s.sync_interval_s))
        s.sync_batch = int(os.getenv("SYNC_BATCH", s.sync_batch))
        s.sat_kbps = float(os.getenv("SAT_KBPS", s.sat_kbps))
        s.sat_link_default = _bool("SAT_LINK_DEFAULT", s.sat_link_default)
        s.max_clarify_rounds = int(os.getenv("MAX_CLARIFY_ROUNDS", s.max_clarify_rounds))
        s.auto_approve_confidence = float(os.getenv("AUTO_APPROVE_CONFIDENCE", s.auto_approve_confidence))
        s.plugin_retries = int(os.getenv("PLUGIN_RETRIES", s.plugin_retries))
        stubs = os.getenv("USE_STUBS", "")
        s.force_stubs = {x.strip() for x in stubs.split(",") if x.strip()}
        return s

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
