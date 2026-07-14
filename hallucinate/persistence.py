"""Small JSON-backed settings store

Keeps things dead simple on purpose: a dataclass of settings, loaded from
(and saved back to) a single JSON file in a per-OS "app data" directory.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


def data_dir() -> Path:
    """Return (and create) the per-user directory Hallucinate stores its data in."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = base / "Hallucinate"
    path.mkdir(parents=True, exist_ok=True)
    return path


SETTINGS_PATH = data_dir() / "settings.json"


@dataclass
class Settings:
    """User preferences that persist across runs."""

    # "lol", "lor", "valorant", or None (ask every time)
    remembered_game: Optional[str] = None
    # Status to present on startup: "online", "away", "offline", "mobile"
    default_status: str = "offline"
    # Explicit path to riotclientservices.exe / RiotClientServices, if the
    # auto-detected one isn't right.
    riot_client_path: Optional[str] = None
    # Extra args the user always wants passed through to the Riot Client.
    extra_riot_client_args: list = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        if not SETTINGS_PATH.exists():
            return cls()
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        SETTINGS_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
