import asyncio
import httpx
import socketio

BASE_URL = "http://127.0.0.1:8901"


async def get_token(email, password, name):
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/auth/register", json={"name": name, "email": email, "password": password})
        resp = await client.post("/auth/login", json={"email": email, "password": password})
        return resp.json()["access_token"]


async def make_client(label, token):
    sio = socketio.AsyncClient()
    state = {"duel_id": None, "start_events": []}

    @sio.on("matchmaking:found")
    async def found(data):
        state["duel_id"] = data["duel_id"]

    @sio.on("duel:start")
    async def start(data):
        state["start_events"].append(data)

    await sio.connect(BASE_URL, auth={"token": token}, wait_timeout=3)
    return sio, state


async def main():
    print("=== TEST: only one player ready -> never starts ===")
    token_a = await get_token("only1_a@example.com", "pass123", "Only1 A")
    token_b = await get_token("only1_b@example.com", "pass123", "Only1 B")
    a, sa = await make_client("A", token_a)
    b, sb = await make_client("B", token_b)

    await a.emit("matchmaking:find")
    await asyncio.sleep(0.2)
    await b.emit("matchmaking:find")
    await asyncio.sleep(0.5)

    duel_id = sa["duel_id"]
    await a.emit("duel:ready", {"duel_id": duel_id})
    await asyncio.sleep(0.5)

    print("A start_events (should be 0):", len(sa["start_events"]))
    print("B start_events (should be 0):", len(sb["start_events"]))

    print("\n=== TEST: duel:ready on an already-active duel -> rejected cleanly, no crash ===")
    await b.emit("duel:ready", {"duel_id": duel_id})
    await asyncio.sleep(0.3)
    print("A start_events after B ready (should be 1 now):", len(sa["start_events"]))

    await a.emit("duel:ready", {"duel_id": duel_id})
    await asyncio.sleep(0.3)
    print("A start_events after re-sending ready on active duel (should still be 1):", len(sa["start_events"]))

    await a.disconnect()
    await b.disconnect()


asyncio.run(main())
