import asyncio
import httpx
import socketio

BASE_URL = "http://127.0.0.1:8800"


async def get_real_token(email, password, name):
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/auth/register", json={"name": name, "email": email, "password": password})
        resp = await client.post("/auth/login", json={"email": email, "password": password})
        return resp.json()["access_token"]


async def make_client(label, token):
    sio = socketio.AsyncClient()
    state = {"queued": False, "duel_id": None}

    @sio.on("matchmaking:queued")
    async def queued(data):
        state["queued"] = True

    @sio.on("matchmaking:found")
    async def matched(data):
        state["duel_id"] = data["duel_id"]
        print(f"  {label}: matched! duel_id={data['duel_id']}")

    await sio.connect(BASE_URL, auth={"token": token}, wait_timeout=3)
    return sio, state


async def test_basic_match():
    print("=== TEST 1: two clients queue -> matched, same duel_id ===")
    token_a = await get_real_token("mm1_a@example.com", "pass123", "A")
    token_b = await get_real_token("mm1_b@example.com", "pass123", "B")
    a, sa = await make_client("A", token_a)
    b, sb = await make_client("B", token_b)

    await a.emit("matchmaking:find")
    await asyncio.sleep(0.3)
    await b.emit("matchmaking:find")
    await asyncio.sleep(0.5)

    ok = sa["duel_id"] is not None and sa["duel_id"] == sb["duel_id"]
    print(f"  PASS: {ok}\n")
    await a.disconnect()
    await b.disconnect()


async def test_cancel():
    print("=== TEST 2: cancel before matching -> never matched ===")
    token_c = await get_real_token("mm2_c@example.com", "pass123", "C")
    token_d = await get_real_token("mm2_d@example.com", "pass123", "D")
    c, sc = await make_client("C", token_c)

    await c.emit("matchmaking:find")
    await asyncio.sleep(0.2)
    await c.emit("matchmaking:cancel")
    await asyncio.sleep(0.2)

    d, sd = await make_client("D", token_d)
    await d.emit("matchmaking:find")
    await asyncio.sleep(0.5)

    ok = sc["duel_id"] is None and sd["duel_id"] is None
    print(f"  C never matched, D alone in queue -> PASS: {ok}\n")
    await c.disconnect()
    await d.disconnect()


async def test_disconnect_cleanup():
    print("=== TEST 3: disconnect while queued -> removed from queue ===")
    token_e = await get_real_token("mm3_e@example.com", "pass123", "E")
    token_f = await get_real_token("mm3_f@example.com", "pass123", "F")
    e, se = await make_client("E", token_e)

    await e.emit("matchmaking:find")
    await asyncio.sleep(0.2)
    await e.disconnect()
    await asyncio.sleep(0.3)

    f, sf = await make_client("F", token_f)
    await f.emit("matchmaking:find")
    await asyncio.sleep(0.5)

    ok = sf["duel_id"] is None
    print(f"  F stayed unmatched (E was cleaned up) -> PASS: {ok}\n")
    await f.disconnect()


async def test_duplicate_same_account():
    print("=== TEST 4: same account queues twice (two tabs) -> guard holds ===")
    token_g = await get_real_token("mm4_g@example.com", "pass123", "G")
    token_h = await get_real_token("mm4_h@example.com", "pass123", "H")

    g1, sg1 = await make_client("G-tab1", token_g)
    g2, sg2 = await make_client("G-tab2", token_g)

    await g1.emit("matchmaking:find")
    await asyncio.sleep(0.2)
    await g2.emit("matchmaking:find")
    await asyncio.sleep(0.2)

    h, sh = await make_client("H", token_h)
    await h.emit("matchmaking:find")
    await asyncio.sleep(0.5)

    tab1_matched = sg1["duel_id"] is not None
    tab2_matched = sg2["duel_id"] is not None
    ok = tab1_matched and not tab2_matched and sh["duel_id"] == sg1["duel_id"]
    print(f"  tab1 matched={tab1_matched}, tab2 matched={tab2_matched} (should be False) -> PASS: {ok}\n")
    await g1.disconnect()
    await g2.disconnect()
    await h.disconnect()


async def test_three_clients():
    print("=== TEST 5: three clients queue -> exactly two matched, one waits ===")
    token_i = await get_real_token("mm5_i@example.com", "pass123", "I")
    token_j = await get_real_token("mm5_j@example.com", "pass123", "J")
    token_k = await get_real_token("mm5_k@example.com", "pass123", "K")

    i, si = await make_client("I", token_i)
    j, sj = await make_client("J", token_j)
    k, sk = await make_client("K", token_k)

    await i.emit("matchmaking:find")
    await asyncio.sleep(0.2)
    await j.emit("matchmaking:find")
    await asyncio.sleep(0.2)
    await k.emit("matchmaking:find")
    await asyncio.sleep(0.5)

    matched_count = sum(1 for s in (si, sj, sk) if s["duel_id"] is not None)
    ok = matched_count == 2 and sk["duel_id"] is None
    print(f"  matched_count={matched_count} (should be 2), K unmatched -> PASS: {ok}\n")
    await i.disconnect()
    await j.disconnect()
    await k.disconnect()


async def main():
    await test_basic_match()
    await test_cancel()
    await test_disconnect_cleanup()
    await test_duplicate_same_account()
    await test_three_clients()


asyncio.run(main())
