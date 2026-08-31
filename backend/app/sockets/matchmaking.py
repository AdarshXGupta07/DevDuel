from app.sockets.server import sio
from app.services.matchmaking_service import add_to_queue, remove_from_queue, is_queued, try_match


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
        for player in (match["player1"], match["player2"]):
            await sio.enter_room(player["sid"], duel_id)
        await sio.emit("matchmaking:found", {"duel_id": duel_id}, room=duel_id)


@sio.on("matchmaking:cancel")
async def matchmaking_cancel(sid):
    session = await sio.get_session(sid)
    user_id = session["user_id"]
    remove_from_queue(user_id)
