from datetime import datetime, timedelta

from app.sockets.server import sio
from app.services.duel_service import mark_ready, get_duel, NotAParticipant
from app.db.session import async_session_factory

COUNTDOWN_SECONDS = 5


@sio.on("duel:ready")
async def duel_ready(sid, data):
    duel_id = data["duel_id"]
    session = await sio.get_session(sid)
    user_id = session["user_id"]

    async with async_session_factory() as db:
        try:
            result = await mark_ready(db, duel_id, user_id)
        except NotAParticipant:
            return

        if result["started"]:
            starts_at = (datetime.utcnow() + timedelta(seconds=COUNTDOWN_SECONDS)).isoformat()
            await sio.emit("duel:start", {"duel_id": duel_id, "starts_at": starts_at}, room=duel_id)
