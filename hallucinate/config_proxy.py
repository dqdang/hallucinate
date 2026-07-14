"""Intercepts the Riot Client's startup "client config" fetch.

When launched with `--client-config-url=http://127.0.0.1:<port>`, the Riot
Client fetches its configuration (region, chat server address, feature
flags, ...) from that URL instead of Riot's real endpoint. We proxy that
request through to the real endpoint unchanged, except we rewrite whichever
key(s) tell the client where to connect for chat, pointing it at our own
TLS proxy instead -- while remembering the real chat host/port so the TLS
proxy knows where to actually forward traffic.

Riot's client config is a flat, dot-namespaced JSON key/value document
(e.g. "chat.host", "chat.port"). Rather than hard-code exact key names that
may drift between client versions, we look for any "<prefix>.host" /
"<prefix>.port" pair where the prefix contains "chat".
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urljoin

import aiohttp
from aiohttp import web

log = logging.getLogger(__name__)

REAL_CLIENT_CONFIG_BASE = "https://clientconfig.rpg.riotgames.com"


@dataclass
class ChatEndpoint:
    host: str
    port: int


def _find_and_rewrite_chat_endpoint(config: dict, new_host: str, new_port: int) -> Optional[ChatEndpoint]:
    """Mutates `config` in place, returns the *original* chat host/port found."""
    host_key = port_key = None
    for key in config:
        if key.endswith(".host") and "chat" in key.lower():
            candidate_port_key = key[: -len(".host")] + ".port"
            if candidate_port_key in config:
                host_key, port_key = key, candidate_port_key
                break

    if host_key is None:
        return None

    original = ChatEndpoint(host=str(config[host_key]), port=int(config[port_key]))
    config[host_key] = new_host
    config[port_key] = new_port
    return original


class ConfigProxy:
    """A tiny local HTTP server the Riot Client points its config fetch at."""

    def __init__(self, on_real_chat_endpoint: Callable[[ChatEndpoint], None], proxy_chat_port: int, proxy_chat_host: str = "127.0.0.1"):
        self._on_real_chat_endpoint = on_real_chat_endpoint
        self._proxy_chat_port = proxy_chat_port
        self._proxy_chat_host = proxy_chat_host
        self._app = web.Application()
        self._app.router.add_route("*", "/{tail:.*}", self._handle)
        self._runner: Optional[web.AppRunner] = None

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host, port)
        await site.start()
        actual_port = site._server.sockets[0].getsockname()[1]  # type: ignore[attr-defined]
        log.info("Config proxy listening on %s:%s", host, actual_port)
        return actual_port

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    async def _handle(self, request: web.Request) -> web.Response:
        target_url = urljoin(REAL_CLIENT_CONFIG_BASE, request.path_qs)
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
        body = await request.read()

        async with aiohttp.ClientSession() as session:
            async with session.request(
                request.method, target_url, headers=headers, data=body or None
            ) as upstream_resp:
                raw = await upstream_resp.read()
                content_type = upstream_resp.headers.get("Content-Type", "")

        if "json" not in content_type:
            return web.Response(body=raw, status=upstream_resp.status, content_type=content_type or "application/octet-stream")

        try:
            config = json.loads(raw)
        except json.JSONDecodeError:
            return web.Response(body=raw, status=upstream_resp.status, content_type=content_type)

        if isinstance(config, dict):
            original = _find_and_rewrite_chat_endpoint(config, self._proxy_chat_host, self._proxy_chat_port)
            if original is not None:
                log.info("Redirecting chat connection: real endpoint is %s:%s", original.host, original.port)
                self._on_real_chat_endpoint(original)
            else:
                log.warning(
                    "Could not find a chat.*.host/.port pair in the client config response; "
                    "presence spoofing will not work for this session. See README for how to "
                    "adjust the key-matching logic if Riot has changed their schema."
                )

        return web.json_response(config, status=upstream_resp.status)
