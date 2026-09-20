"""Connection lifecycle: authenticate, track presence, and handle vanishing players."""

import logging
import uuid

from jose import JWTError
from socketio.exceptions import ConnectionRefusedError

from app.config import settings
from app.core.security import decode_token
from app.db.models import User
from app.db.session import async_session_factory
from app.services import duel_runtime, matchmaking_service, presence
from app.services.duel_service import (
    abandon_duel,
    find_active_duel_for_user,
    serialize_duel,
)
from app.sockets.server import sio

logger = logging.getLogger(__name__)


@sio.event
async def connect(sid, environ, auth):
    """Authenticate on every connect — including a reconnect.

    Socket.IO reconnects the *transport* automatically, but the server learns nothing
    from that: `connect` runs again, with no memory of the previous session, so the
    client must present its token again exactly as it did the first time.
    """
    if not auth or "token" not in auth:
        raise ConnectionRefusedError("Authentication token is required.")

    try:
        payload = decode_token(auth["token"])
    except JWTError:
        raise ConnectionRefusedError("Invalid token.")

    if payload.get("type") != "access":
        raise ConnectionRefusedError("Invalid token type.")

    user_id = payload.get("sub")
    if user_id is None:
        raise ConnectionRefusedError("Invalid token.")

    async with async_session_factory() as db:
        user = await db.get(User, uuid.UUID(str(user_id)))
        if user is None or user.deleted_at is not None:
            raise ConnectionRefusedError("Unknown user.")
        if user.is_banned:
            raise ConnectionRefusedError("Account suspended.")

        await sio.save_session(
            sid,
            {
                "user_id": str(user.id),
                "name": user.name,
                "rating": user.rating,
                "plan": user.plan,
                "is_paid": user.is_paid,
            },
        )
        presence.register(user.id, sid)

        # --- reconnect handling (Day 10) ---
        duel = await find_active_duel_for_user(db, user.id)
        if duel is None:
            return

        await sio.enter_room(sid, str(duel.id))

        # Full state resync rather than replaying missed events: one payload that is
        # the complete current truth, which the client renders over whatever it thought.
        await sio.emit("duel:state", serialize_duel(duel), to=sid)

        if duel_runtime.cancel_grace_timer(duel.id, user.id):
            logger.info("player %s reconnected within grace for duel %s", user.id, duel.id)
            await sio.emit(
                "duel:opponent_reconnect",
                {"duel_id": str(duel.id), "user_id": str(user.id)},
                room=str(duel.id),
                skip_sid=sid,
            )


@sio.event
async def whoami(sid):
    session = await sio.get_session(sid)
    await sio.emit("whoami_response", session, to=sid)


@sio.event
async def disconnect(sid):
    user_id, remaining = presence.unregister(sid)
    if user_id is None:
        return

    # A second tab closing is not a disconnect. Only act when the player has no
    # sockets left at all — otherwise a refresh in one tab forfeits their duel.
    if remaining > 0:
        return

    matchmaking_service.remove_from_queue(user_id)

    async with async_session_factory() as db:
        duel = await find_active_duel_for_user(db, user_id)
        if duel is None:
            return

        if duel.status == "active":
            # Notify the opponent and start the clock. ADR-0018: a disconnect is a
            # grace period, then a forfeit — not an instant loss (a 10-second tunnel
            # should not cost a match) and not a free pause (or every losing player
            # would pull their cable).
            await sio.emit(
                "duel:opponent_disconnect",
                {
                    "duel_id": str(duel.id),
                    "user_id": str(user_id),
                    "grace_seconds": settings.disconnect_grace_seconds,
                },
                room=str(duel.id),
            )
            duel_runtime.start_grace_timer(duel.id, user_id)
            logger.info("grace timer started for %s in duel %s", user_id, duel.id)
        else:
            # Never went live — nobody forfeits a match that had not begun.
            abandoned = await abandon_duel(db, duel.id, "abandoned")
            if abandoned is not None:
                if abandoned.mode == "ranked":
                    for player_id in (abandoned.player1_id, abandoned.player2_id):
                        await matchmaking_service.release_ranked_slot(db, player_id)
                await sio.emit("duel:abandoned", serialize_duel(abandoned), room=str(duel.id))
