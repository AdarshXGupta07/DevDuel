from app.sockets.server import sio
from app.services.matchmaking_service import add_to_queue, remove_from_queue, is_queued, try_match
from app.services.duel_service import create_duel, transition_duel
from app.db.session import async_session_factory

# TODO Day 14: real problem selection. For now, paste in a real problem id
# from your `problems` table (see the INSERT you ran earlier).
PLACEHOLDER_PROBLEM_ID = "eeb1c0bd-965f-45d0-be0b-1d8cabed7c0e"


@sio.on("matchmaking:find")
async def matchmaking_find(sid):
    session = await sio.get_session(sid)
    user_id = session["user_id"]

    if is_queued(user_id):
        return

    add_to_queue(user_id, sid)
    await sio.emit("matchmaking:queued", {}, to=sid)

    match = try_match()
    if match:
        duel_id = match["duel_id"]

        async with async_session_factory() as db:
            await create_duel(
                db,
                player1_id=match["player1"]["user_id"],
                player2_id=match["player2"]["user_id"],
                problem_id=PLACEHOLDER_PROBLEM_ID,
                duel_id=duel_id,
            )
            await transition_duel(db, duel_id, "ready")

        for player in (match["player1"], match["player2"]):
            await sio.enter_room(player["sid"], duel_id)
        await sio.emit("matchmaking:found", {"duel_id": duel_id}, room=duel_id)


@sio.on("matchmaking:cancel")
async def matchmaking_cancel(sid):
    session = await sio.get_session(sid)
    user_id = session["user_id"]
    remove_from_queue(user_id)
