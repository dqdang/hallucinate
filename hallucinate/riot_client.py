"""Finding and launching RiotClientServices, pointed at our config proxy.

Riot's installer records where the Riot Client lives in a small JSON
manifest (RiotClientInstalls.json) rather than anything you need to
hunt for through the registry. We read that, then launch the client with
`--client-config-url` pointing at our local ConfigProxy so it fetches its
startup configuration (and, transparently, its chat server address) through
us instead of talking to Riot directly.
"""
from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path
from typing import Optional

# Product/patchline codes the Riot Client expects on the command line.
# These are widely documented in the third-party Riot tooling community;
# override via Settings.riot_client_path / extra args if Riot ever changes them.
LAUNCH_PRODUCTS = {
    "lol": ("league_of_legends", "live"),
    "lor": ("bacon", "live"),  # Legends of Runeterra's internal codename
    "valorant": ("valorant", "live"),
}


def _candidate_install_manifests() -> list[Path]:
    system = platform.system()
    if system == "Windows":
        return [Path(r"C:\ProgramData\Riot Games\RiotClientInstalls.json")]
    if system == "Darwin":
        return [Path("/Users/Shared/Riot Games/RiotClientInstalls.json")]
    # Linux isn't officially supported by Riot's client; left here for
    # completeness in case someone's running it under a compatibility layer.
    return [Path.home() / ".config" / "Riot Games" / "RiotClientInstalls.json"]


def find_riot_client_path() -> Optional[str]:
    """Best-effort lookup of RiotClientServices' executable path."""
    for manifest_path in _candidate_install_manifests():
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        # Manifest looks like {"rc_default": "C:\\...\\RiotClientServices.exe", "rc_live": "...", ...}
        for key in ("rc_default", "rc_live", "rc_beta"):
            path = manifest.get(key)
            if path and Path(path).exists():
                return path
        for path in manifest.values():
            if isinstance(path, str) and Path(path).exists():
                return path
    return None


def launch_riot_client(
    game: str,
    config_proxy_port: int,
    riot_client_path: Optional[str] = None,
    extra_args: Optional[list[str]] = None,
) -> subprocess.Popen:
    """Start the Riot Client for `game` ("lol" | "lor" | "valorant"), via our proxy."""
    path = riot_client_path or find_riot_client_path()
    if not path:
        raise FileNotFoundError(
            "Couldn't locate RiotClientServices. Launch any Riot game once normally so "
            "Riot's installer records its path, or pass --riot-client-path explicitly."
        )
    if game not in LAUNCH_PRODUCTS:
        raise ValueError(f"Unknown game {game!r}; expected one of {list(LAUNCH_PRODUCTS)}")

    product, patchline = LAUNCH_PRODUCTS[game]
    args = [
        path,
        f'--client-config-url=http://127.0.0.1:{config_proxy_port}',
        f"--launch-product={product}",
        f"--launch-patchline={patchline}",
        *(extra_args or []),
    ]
    return subprocess.Popen(args)
