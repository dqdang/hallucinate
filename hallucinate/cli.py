"""Command-line entry point: wires the config proxy, TLS proxy, tray icon,
and Riot Client launcher together.

Usage:
    python -m hallucinate [lol|lor|valorant] [--status {online,away,offline,mobile}]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading

from .config_proxy import ChatEndpoint, ConfigProxy
from .persistence import Settings
from .riot_client import LAUNCH_PRODUCTS, launch_riot_client
from .tls_proxy import ChatProxyServer, ProxyTarget
from .tray import TrayApp

log = logging.getLogger("hallucinate")


class SharedStatus:
    """The single piece of state the tray thread and the asyncio side share."""

    def __init__(self, initial: str):
        self._lock = threading.Lock()
        self._status = initial

    def get(self) -> str:
        with self._lock:
            return self._status

    def set(self, value: str) -> None:
        with self._lock:
            self._status = value


class HallucinateApp:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.status = SharedStatus(settings.default_status)
        self.config_proxy_port: int | None = None
        self.chat_proxy: ChatProxyServer | None = None
        self.tray: TrayApp | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def run(self, initial_game: str | None) -> None:
        self._loop = asyncio.get_running_loop()

        config_proxy = ConfigProxy(on_real_chat_endpoint=self._on_real_chat_endpoint, proxy_chat_port=0)
        self.config_proxy_port = await config_proxy.start()

        self.tray = TrayApp(
            initial_status=self.status.get(),
            on_status_change=self._on_status_change,
            on_launch_game=self._on_launch_game,
            on_quit=self._on_quit,
        )
        self.tray.run_in_background()

        if initial_game:
            self._on_launch_game(initial_game)

        try:
            await asyncio.Event().wait()  # run until _on_quit stops the loop
        finally:
            await config_proxy.stop()
            if self.chat_proxy:
                self.chat_proxy.close()

    def _on_real_chat_endpoint(self, endpoint: ChatEndpoint) -> None:
        # Called from within the config proxy's request handler, i.e. already
        # running on the event loop -- safe to schedule a task directly.
        assert self._loop is not None
        self._loop.create_task(self._ensure_chat_proxy(endpoint))

    async def _ensure_chat_proxy(self, endpoint: ChatEndpoint) -> None:
        if self.chat_proxy is not None:
            return  # already proxying; real chat endpoint is stable per session
        self.chat_proxy = ChatProxyServer(
            listen_host="127.0.0.1",
            listen_port=0,
            upstream=ProxyTarget(host=endpoint.host, port=endpoint.port),
            get_status=self.status.get,
        )
        await self.chat_proxy.start()
        asyncio.create_task(self.chat_proxy.serve_forever())

    def _on_status_change(self, status: str) -> None:
        self.status.set(status)
        self.settings.default_status = status
        self.settings.save()
        log.info("Visible status changed to %s", status)

    def _on_launch_game(self, game: str) -> None:
        assert self.config_proxy_port is not None
        try:
            launch_riot_client(
                game,
                self.config_proxy_port,
                riot_client_path=self.settings.riot_client_path,
                extra_args=self.settings.extra_riot_client_args,
            )
            self.settings.remembered_game = game
            self.settings.save()
        except (FileNotFoundError, ValueError) as exc:
            log.error("Couldn't launch %s: %s", game, exc)
            if self.tray:
                self.tray.notify(str(exc), title="Hallucinate - launch failed")

    def _on_quit(self) -> None:
        assert self._loop is not None
        self._loop.call_soon_threadsafe(self._loop.stop)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="hallucinate", description=__doc__)
    parser.add_argument("game", nargs="?", choices=list(LAUNCH_PRODUCTS), help="Game to launch immediately")
    parser.add_argument("--status", choices=["online", "away", "offline", "mobile"], help="Visible status to start with")
    parser.add_argument("--riot-client-path", help="Explicit path to RiotClientServices, if auto-detection fails")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = Settings.load()
    if args.status:
        settings.default_status = args.status
    if args.riot_client_path:
        settings.riot_client_path = args.riot_client_path

    app = HallucinateApp(settings)
    try:
        asyncio.run(app.run(args.game or settings.remembered_game))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
