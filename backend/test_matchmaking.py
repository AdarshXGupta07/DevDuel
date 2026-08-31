import asyncio
import httpx
import socketio

BASE_URL = "http://127.0.0.1:8000"


async def get_real_token(email, password, name):
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/auth/register", json={"name": name, "email": email, "password": password})
        resp = await client.post("/auth/login", json={"email": email, "password": password})
        return resp.json()["access_token"]


async def make_client(label, token):
    sio = socketio.AsyncClient()
    found = {}

    @sio.on("matchmaking:queued")
    async def queued(data):
        print(f"{label}: queued")

    @sio.on("matchmaking:found")
    async def matched(data):
        found["duel_id"] = data["duel_id"]
        print(f"{label}: matched! duel_id={data['duel_id']}")

    await sio.connect(BASE_URL, auth={"token": token}, wait_timeout=3)
    return sio, found


async def main():
    token_a = await get_real_token("mm_a@example.com", "pass123", "MM A")
    token_b = await get_real_token("mm_b@example.com", "pass123", "MM B")

    client_a, found_a = await make_client("A", token_a)
    client_b, found_b = await make_client("B", token_b)

    await client_a.emit("matchmaking:find")
    await asyncio.sleep(0.3)
    await client_b.emit("matchmaking:find")
    await asyncio.sleep(0.5)

    print()
    print("Same duel_id?", found_a.get("duel_id") == found_b.get("duel_id") and found_a.get("duel_id") is not None)

    await client_a.disconnect()
    await client_b.disconnect()


asyncio.run(main())
