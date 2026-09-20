"""The Socket.IO server object, and nothing else.

Deliberately free of imports from `app.services` so that services may import `sio` for
emitting without creating an import cycle. Connection handlers live in `lifecycle.py`.
"""

import socketio

from app.config import settings

# ADR-0022: '*' was a development convenience that would have shipped. Credentialed
# sockets with a wildcard origin let any page on the internet open an authenticated
# connection on a logged-in user's behalf.
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origin_list,
    ping_interval=20,
    ping_timeout=25,
)
