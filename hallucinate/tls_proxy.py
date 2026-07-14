"""The TLS proxy that sits between the Riot Client and the real chat server.

For each incoming TCP connection (from the Riot Client, believing it's
talking directly to the chat server):

  1. We TLS-wrap the incoming socket as a *server*, presenting a leaf cert
     for the real chat hostname signed by our local CA (see certs.py).
  2. We open our own TLS connection *out* to the real chat server.
  3. We pipe bytes in both directions. On the client -> server direction we
     run everything through the stanza splitter and rewrite global presence
     broadcasts according to the currently selected status; everything else
     (server -> client, and any non-presence client -> server traffic) is
     forwarded byte-for-byte, unexamined.
"""
from __future__ import annotations

import asyncio
import logging
import ssl
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import certs
from .xmpp_stanza import StanzaSplitter, process_outgoing_stanza

log = logging.getLogger(__name__)

StatusGetter = Callable[[], str]


@dataclass
class ProxyTarget:
    """Where a given incoming connection should actually be forwarded to."""

    host: str
    port: int


@dataclass
class ChatProxyServer:
    """Owns the listening socket and hands off each connection to a handler."""

    listen_host: str
    listen_port: int
    upstream: ProxyTarget
    get_status: StatusGetter
    on_connection_error: Optional[Callable[[BaseException], None]] = None

    _server: Optional[asyncio.base_events.Server] = field(default=None, init=False)

    async def start(self) -> int:
        cert_path, key_path = certs.issue_leaf_certificate(self.upstream.host)
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(str(cert_path), str(key_path))

        self._server = await asyncio.start_server(
            self._handle_client, self.listen_host, self.listen_port, ssl=server_ctx
        )
        actual_port = self._server.sockets[0].getsockname()[1]
        log.info(
            "Chat proxy listening on %s:%s, forwarding to %s:%s",
            self.listen_host,
            actual_port,
            self.upstream.host,
            self.upstream.port,
        )
        return actual_port

    async def serve_forever(self) -> None:
        assert self._server is not None, "call start() first"
        async with self._server:
            await self._server.serve_forever()

    def close(self) -> None:
        if self._server is not None:
            self._server.close()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        log.debug("Incoming connection from %s", peer)
        try:
            client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            client_ctx.check_hostname = False
            client_ctx.verify_mode = ssl.CERT_NONE  # we already trust Riot's own chain
            upstream_reader, upstream_writer = await asyncio.open_connection(
                self.upstream.host, self.upstream.port, ssl=client_ctx, server_hostname=self.upstream.host
            )
        except OSError as exc:
            log.warning("Failed to connect upstream to %s:%s: %s", self.upstream.host, self.upstream.port, exc)
            writer.close()
            if self.on_connection_error:
                self.on_connection_error(exc)
            return

        client_to_server = asyncio.create_task(
            self._pump_client_to_server(reader, upstream_writer)
        )
        server_to_client = asyncio.create_task(self._pump_verbatim(upstream_reader, writer))

        try:
            await asyncio.wait(
                {client_to_server, server_to_client}, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for task in (client_to_server, server_to_client):
                task.cancel()
            for closer in (writer, upstream_writer):
                try:
                    closer.close()
                except OSError:
                    pass

    async def _pump_client_to_server(
        self, reader: asyncio.StreamReader, upstream_writer: asyncio.StreamWriter
    ) -> None:
        """Client -> real server, rewriting global presence along the way."""

        def emit(data: bytes) -> None:
            upstream_writer.write(data)

        def on_stanza(stanza) -> None:
            emit(process_outgoing_stanza(stanza, self.get_status()))

        splitter = StanzaSplitter(on_stanza=on_stanza, on_passthrough=emit)

        try:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                splitter.feed(chunk)
                await upstream_writer.drain()
        except (asyncio.CancelledError, ConnectionError):
            pass

    async def _pump_verbatim(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Real server -> client, untouched."""
        try:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
        except (asyncio.CancelledError, ConnectionError):
            pass
