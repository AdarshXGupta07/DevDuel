import asyncio
import httpx
import socketio

BASE_URL = "http://127.0.0.1:8900"


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
        print(f"  {label}: duel:start received -> starts_at={data['starts_at']}")

    await sio.connect(BASE_URL, auth={"token": token}, wait_timeout=3)
    return sio, state


async def main():
    token_a = await get_token("ready_a@example.com", "pass123", "Ready A")
    token_b = await get_token("ready_b@example.com", "pass123", "Ready B")

    a, sa = await make_client("A", token_a)
    b, sb = await make_client("B", token_b)

    await a.emit("matchmaking:find")
    await asyncio.sleep(0.2)
    await b.emit("matchmaking:find")
    await asyncio.sleep(0.5)

    duel_id = sa["duel_id"]
    print(f"duel_id: {duel_id}\n")

    print("=== simultaneous ready clicks ===")
    await asyncio.gather(
        a.emit("duel:ready", {"duel_id": duel_id}),
        b.emit("duel:ready", {"duel_id": duel_id}),
    )
    await asyncio.sleep(0.5)

    print()
    print("A got duel:start count:", len(sa["start_events"]))
    print("B got duel:start count:", len(sb["start_events"]))
    same_time = (
        len(sa["start_events"]) == 1
        and len(sb["start_events"]) == 1
        and sa["start_events"][0]["starts_at"] == sb["start_events"][0]["starts_at"]
    )
    print("Exactly one each, same starts_at:", same_time)

    print("\n=== double-click: A sends duel:ready again ===")
    await a.emit("duel:ready", {"duel_id": duel_id})
    await asyncio.sleep(0.3)
    print("A got duel:start count now (should still be 1):", len(sa["start_events"]))

    await a.disconnect()
    await b.disconnect()


asyncio.run(main())
