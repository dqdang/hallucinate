"""Streaming XMPP stanza boundary detection and presence rewriting.

The chat protocol Riot's client speaks is plain XMPP over TLS: a single
never-closed `<stream:stream>` root element, with each "stanza" (presence,
message, iq, ...) sent as a complete child element. There's no
length-prefix framing, so to intercept and selectively rewrite presence
broadcasts we need to find stanza boundaries ourselves as bytes stream in.

We use a small hand-rolled tag scanner rather than a full XML parser:
it's enough to track nesting depth via '<tag>' / '<tag/>' / '</tag>'
tokens (respecting quoted attribute values), which is all that's needed
to know where one top-level stanza ends and the next begins. Anything we
don't recognize is passed through untouched -- correctness for the
"leave everything alone" case matters more here than parsing every edge
case of XML.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

# Matches a single tag: <name ...>, <name .../>, or </name>
_TAG_RE = re.compile(
    rb"""<
        (?P<closing>/)?
        (?P<name>[^\s/>]+)
        (?P<attrs>(?:[^"'>]|"[^"]*"|'[^']*')*)
        (?P<selfclose>/)?
        >""",
    re.VERBOSE | re.DOTALL,
)

_ATTR_RE = re.compile(
    rb"""(?P<key>[\w:-]+)\s*=\s*(?:"(?P<v1>[^"]*)"|'(?P<v2>[^']*)')"""
)

Status = str  # "online" | "away" | "offline" | "mobile"


def _local_name(tag: bytes) -> bytes:
    return tag.split(b":")[-1]


def _parse_attrs(raw: bytes) -> dict:
    return {
        m.group("key").decode(): (m.group("v1") or m.group("v2") or b"").decode()
        for m in _ATTR_RE.finditer(raw)
    }


@dataclass
class Stanza:
    """A complete top-level stanza, as raw bytes plus a bit of parsed metadata."""

    raw: bytes
    tag: bytes
    attrs: dict


class StanzaSplitter:
    """Feed it bytes; it calls back with each complete top-level stanza.

    Bytes belonging to the opening `<stream:stream ...>` tag (which is
    never closed) and any partial/stray data are passed through via
    `on_passthrough` immediately, since there's nothing to rewrite there.
    """

    def __init__(self, on_stanza: Callable[[Stanza], None], on_passthrough: Callable[[bytes], None]):
        self._on_stanza = on_stanza
        self._on_passthrough = on_passthrough
        self._buffer = bytearray()
        self._depth = 0
        self._stanza_start: Optional[int] = None
        self._stanza_root_name = b""

    def feed(self, data: bytes) -> None:
        self._buffer.extend(data)
        pos = 0
        buf = self._buffer

        while True:
            match = _TAG_RE.search(buf, pos)
            if not match:
                break

            if match.start() != pos and self._depth == 0 and self._stanza_start is None:
                # Stray bytes before any stanza has started (whitespace
                # keep-alives etc). Flush them straight through.
                self._on_passthrough(bytes(buf[pos:match.start()]))

            is_closing = match.group("closing") is not None
            is_selfclose = match.group("selfclose") is not None
            name = match.group("name")

            if self._depth == 0 and self._stanza_start is None:
                if not is_closing:
                    if _local_name(name) == b"stream" and not is_selfclose:
                        # The root <stream:stream> open tag: never closed,
                        # nothing to buffer as a "stanza" -- pass through.
                        self._on_passthrough(bytes(buf[match.start():match.end()]))
                        pos = match.end()
                        continue
                    # Start of a new top-level stanza.
                    self._stanza_start = match.start()
                    self._depth = 1
                    self._stanza_root_name = name
                    if is_selfclose:
                        self._emit_stanza(buf, match)
                        pos = match.end()
                        continue
                else:
                    # A stray closing tag with nothing open (e.g. </stream:stream>).
                    self._on_passthrough(bytes(buf[match.start():match.end()]))
                    pos = match.end()
                    continue
            else:
                if is_selfclose:
                    pass  # depth unchanged, nested self-closed element
                elif is_closing:
                    self._depth -= 1
                    if self._depth == 0:
                        self._emit_stanza(buf, match)
                        pos = match.end()
                        continue
                else:
                    self._depth += 1

            pos = match.end()

        # Drop everything we've fully consumed; keep the unparsed tail.
        del self._buffer[:pos]

    def _emit_stanza(self, buf: bytearray, end_match: "re.Match") -> None:
        raw = bytes(buf[self._stanza_start:end_match.end()])
        open_tag_match = _TAG_RE.match(raw)
        attrs = _parse_attrs(open_tag_match.group("attrs")) if open_tag_match else {}
        self._on_stanza(Stanza(raw=raw, tag=_local_name(self._stanza_root_name), attrs=attrs))
        self._stanza_start = None
        self._depth = 0


def rewrite_presence(stanza: Stanza, status: Status) -> bytes:
    """Rewrite a global presence stanza to reflect the desired visible status.

    Only called for <presence> stanzas with no `to` attribute -- i.e. the
    broadcast that tells your whole friends list your status, as opposed
    to directed presence sent into a specific lobby/chatroom (which we
    never touch, so lobbies/champ-select keep working normally).
    """
    if status == "online":
        return stanza.raw  # nothing to hide

    if status == "offline":
        stanza_id = stanza.attrs.get("id")
        id_attr = f' id="{stanza_id}"' if stanza_id else ""
        return f'<presence{id_attr} type="unavailable"/>'.encode("utf-8")

    # "away" / "mobile": best-effort -- keep the stanza (so rich presence
    # like current game/rank keeps working for people who still see you),
    # but override or insert the <show/> element that drives the little
    # status dot everyone else sees.
    show_value = {"away": "away", "mobile": "dnd"}.get(status, "away")
    body = stanza.raw
    if re.search(rb"<show>.*?</show>", body, re.DOTALL):
        body = re.sub(rb"<show>.*?</show>", f"<show>{show_value}</show>".encode(), body, count=1)
    else:
        open_tag_match = _TAG_RE.match(body)
        insert_at = open_tag_match.end()
        body = body[:insert_at] + f"<show>{show_value}</show>".encode() + body[insert_at:]
    return body


def process_outgoing_stanza(stanza: Stanza, status: Status) -> bytes:
    """Decide whether a stanza needs rewriting and return the bytes to send on."""
    is_global_presence = stanza.tag == b"presence" and not stanza.attrs.get("to")
    if is_global_presence:
        return rewrite_presence(stanza, status)
    return stanza.raw
