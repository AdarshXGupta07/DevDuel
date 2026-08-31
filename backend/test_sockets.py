import asyncio
import httpx
import socketio

BASE_URL = "http://127.0.0.1:8000"


async def get_real_token(email, password, name):
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/auth/register", json={"name": name, "email": email, "password": password})
        resp = await client.post("/auth/login", json={"email": email, "password": password})
        return resp.json()["access_token"]


async def try_connect(label, auth_payload):
    sio = socketio.AsyncClient()

    @sio.event
    async def connect():
        print(f"{label}: CONNECTED")

    @sio.event
    async def connect_error(data):
        print(f"{label}: REJECTED -> {data}")

    @sio.on("whoami_response")
    async def on_whoami(data):
        print(f"{label}: whoami says -> {data}")

    try:
        await sio.connect(BASE_URL, auth=auth_payload, wait_timeout=3)
        await sio.emit("whoami")
        await asyncio.sleep(0.5)
        await sio.disconnect()
    except Exception as e:
        print(f"{label}: FAILED TO CONNECT -> {e}")


async def main():
    token_a = await get_real_token("sockettest_a@example.com", "sockpass123", "Socket Test A")
    token_b = await get_real_token("sockettest_b@example.com", "sockpass456", "Socket Test B")

    print("--- valid token (user A) ---")
    await try_connect("A", {"token": token_a})

    print("--- no token ---")
    await try_connect("no token", None)

    print("--- garbage token ---")
    await try_connect("garbage", {"token": "not.a.real.token"})

    print("--- both users, confirm sessions never cross ---")
    await try_connect("A again", {"token": token_a})
    await try_connect("B", {"token": token_b})


asyncio.run(main())
