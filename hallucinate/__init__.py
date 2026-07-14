"""
Hallucinate
=====================

Appear offline for League of Legends, VALORANT, and Legends of Runeterra.

1. A tiny local HTTP proxy sits in front of the Riot Client's
   "client-config" service and rewrites the chat server address it hands
   back, pointing the client at our own TLS proxy instead.
2. The TLS proxy terminates the client's connection, opens its own TLS
   connection to the *real* chat server, and pipes traffic between the two,
   rewriting only the client's global presence broadcasts so friends see you
   as offline while lobby/queue/chat functionality keeps working normally.
3. A system tray icon lets you flip your visible status and (re)launch a
   game through the proxy.

See README.md for setup, and for the one thing this port can't fully match:
the original ships a CA-signed certificate for a domain its author owns;
this port generates and trusts a local certificate instead.
"""

__version__ = "0.1.0"
