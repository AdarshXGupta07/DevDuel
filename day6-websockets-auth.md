# CodeDuel — Day 6 Brief
**WebSockets and socket authentication**

> This is Week 2's opening day and a real gear shift. Everything through Day 5 was
> request/response — a client asks, the server answers, the connection closes. Today
> you build a connection that **stays open**, and that single change is where most of
> the hard problems for the rest of the month come from.

---

## Why today matters

An HTTP server is, at its core, stateless between requests — it doesn't remember you
between one call and the next (that's *why* you built JWTs). A WebSocket server is the
opposite: the connection itself IS the state. The moment you accept a socket connection,
your server is now holding something open, in memory, for as long as that user is
connected. That's the root of nearly every hard problem in Weeks 2–3: memory usage,
what happens on disconnect, what happens if you ever run two server instances.

---

## 1. Concept study — 30 min

**Read/look up:**
1. HTTP request/response vs. a persistent connection — what actually changes at the
   TCP level, not just conceptually.
2. The WebSocket **upgrade handshake** — an HTTP request that asks to be "upgraded" to
   a different protocol. Read what the actual handshake headers look like.
3. Why realtime servers are described as **stateful**, and stateless servers as easier
   to scale. Connect this to something concrete: what would break if you ran two copies
   of your server right now, behind a load balancer, once sockets are involved?
4. Socket.IO specifically — what it adds on top of raw WebSockets: **rooms** (grouping
   connections), **ack** (a callback confirming a message was received), automatic
   **reconnection**, and fallback transports for networks that block WebSockets.

**You must be able to answer, unaided:**

1. In plain terms, what does "upgrading" a connection actually mean? What protocol does
   it start as, and what does it become?
2. Your FastAPI app handles one request, sends one response, done. A socket connection
   sits open for minutes or hours. What does that cost your server that a normal HTTP
   request doesn't?
3. If you scale to two server instances behind a load balancer, and User A connects to
   instance 1 while User B connects to instance 2 — can they be matched into the same
   duel right now, with what you're about to build? Why or why not? (You don't need to
   solve this today — just be able to explain the problem precisely. It's why Redis
   shows up in the "after Day 20" section of the plan.)
4. What is a Socket.IO "room," and how is it different from just keeping a list of
   connected user IDs yourself?
5. Why authenticate a socket **once, at connection time**, rather than checking a token
   on every single event the socket sends afterward?

If you can't answer #2, sit with it before writing code — it's the concept the rest of
Week 2 is built on top of.

---

## 2. Design doc — 20 min

Apply the five questions to **socket authentication**, in `NOTES.md`.

1. **What is the actual problem?** No technology names. Something like: "a long-lived
   connection needs to know, and continue trusting, who it belongs to — without asking
   again on every message."
2. **Inputs, outputs, invariants.** What does the client send during connection setup?
   What must be true before you accept the connection? What must **never** happen — an
   unauthenticated socket receiving any real event handler at all?
3. **Where does state live?** The authenticated user, once attached to a socket
   connection — is that in memory only, or does anything need to touch the database at
   connect time?
4. **What breaks it?** No token sent. Expired token. Tampered token. A token that was
   valid at connect-time but expires 10 minutes into a still-open connection — what do
   you do about that one? (You don't have to solve it today — decide and write down
   your answer, even if the answer is "punt to a later day.")
5. **Simplest thing that satisfies 1–4?**

**Write ADR-0014**: your decision on question 4 above (expired token mid-connection —
kill the socket immediately, or let it live until the client's next reconnect?). There's
no universally correct answer; defend whichever you pick.

---

## 3. The bug to read about before you write a line of code

The original reference repo (`D:\Hackathons\Dev\Duel\Duel\backend\src\socket\auth.socket.ts`)
has a real vulnerability worth understanding by name, even though you're not copying its
code: when JWT **verification** fails, it falls back to `jwt.decode()` — which reads a
token's payload **without checking the signature at all**. That means anyone can hand-craft
a JSON payload claiming to be any user ID, and the fallback path will accept it as truth,
because decoding (reading the data) and verifying (proving the data is trustworthy) are
two completely different operations that only sound similar.

Open that file, read the fallback logic, and understand precisely why it's exploitable.
Then write in `NOTES.md`, in your own words: what's the difference between "decode" and
"verify," and what would someone need to do to exploit that fallback?

You already have the correct pattern — `decode_token` in your own `security.py` only ever
uses `jwt.decode(token, secret, algorithms=[...])`, which verifies the signature as part
of decoding. There is no unverified fallback anywhere in your code. Today's job is
connecting that same trustworthy function to a new transport (sockets), not weakening it.

---

## 4. Build — 3 hrs

### 4.1 New dependency

```
python-socketio
```

### 4.2 `app/sockets/server.py` — mount Socket.IO alongside FastAPI

Socket.IO needs to run as its own ASGI application, mounted next to your existing FastAPI
app — not replacing it. Look up **"python-socketio asgi fastapi mount"** for the exact
pattern; the shape is roughly: create a `socketio.AsyncServer`, wrap it in a
`socketio.ASGIApp` alongside your FastAPI `app`, and that combined object is what uvicorn
actually runs instead of `app` directly.

This means `main.py` changes — the object uvicorn points at is no longer just your FastAPI
`app`, but something that can route to either FastAPI or Socket.IO depending on the
incoming connection type.

### 4.3 Authenticate at `connect`

Socket.IO gives you a `connect` event handler that fires once, when a client first
connects — this is your equivalent of `get_current_user`, but for sockets instead of HTTP
routes.

The client needs to send its access token as part of the connection attempt (Socket.IO
supports an `auth` payload during connect specifically for this). In your `connect`
handler:
- Pull the token out of the connection's auth data
- Reuse `decode_token` from `security.py`, unchanged — this is the same function you
  already trust
- If it's missing, invalid, or expired: **reject the connection**. Look up how Socket.IO
  lets a `connect` handler refuse a connection (raising a specific exception, or returning
  `False` — check your library version's docs).
- If valid: attach the user's identity to the session somehow, so later event handlers
  can know who's connected without re-decoding the token every time. Look up Socket.IO's
  `save_session` / `get_session` for this — it's the mechanism for "remember something
  about this specific connection."

### 4.4 A trivial authenticated event, to prove it works

Add one more event handler — doesn't need to do anything meaningful yet — that reads the
session data saved in 4.3 and confirms it can see who the connected user is. This is your
proof that authentication actually attached correctly, not just that the connection was
accepted.

---

## 5. Test and verify — 45 min

You can't easily test WebSockets with `curl` the way you've tested HTTP all week — you'll
need a small Python script using `python-socketio`'s **client** (not server) to actually
connect, or the browser's dev console with a raw JS Socket.IO client. Either is fine.

- [ ] Connect with a valid, real access token → connection accepted, you receive whatever
      "connected" confirmation you built.
- [ ] Connect with **no token at all** → rejected. Confirm this happens *before* any event
      handler beyond `connect` itself runs — an unauthenticated client should never be
      able to trigger any other event.
- [ ] Connect with an **expired** token (you can construct one by hand with a past `exp`,
      same trick as Day 4) → rejected.
- [ ] Connect with a **tampered** token (flip one character) → rejected.
- [ ] Open two separate connections, authenticated as two different users (two tokens) →
      confirm each connection's session correctly reports its own user, never the other's.
      This is the socket-transport version of Day 5's authorization bug hunt — do it for
      real, don't skip it because it's "probably fine."

---

## 6. Definition of done

```
backend/
├── app/
│   ├── sockets/
│   │   └── server.py
│   └── main.py          (mounts the combined FastAPI + Socket.IO app)
docs/
└── decisions.md          (+ ADR-0014)
```

Plus: four rejection cases proven (no token, expired, tampered, and confirmed two
concurrent authenticated connections never cross-contaminate).

---

## 7. Traps to expect

1. **Authenticating per-event instead of once at connect.** More code, more places to get
   it wrong, and it's not how the rest of this month's plan expects sockets to work.
2. **The exact vulnerability from §3** — falling back to unverified decoding "just to be
   safe" when verification fails. If verification fails, the connection is rejected, full
   stop. There is no safe fallback.
3. **Forgetting `main.py` needs to change** — uvicorn needs to run the combined
   FastAPI+Socket.IO object, not your original bare FastAPI `app`. If you forget this,
   your existing HTTP routes might still work while sockets silently don't, or vice versa.
4. **Testing only the accept path.** The four rejection cases in §5 are where the real
   bugs hide, same pattern as every day this week.
5. **Assuming a still-open socket means a still-valid token.** You wrote ADR-0014 for a
   reason — a token can expire while the socket stays connected, and "the socket is open"
   is not the same guarantee as "the token is still good."

---

## 8. Bring to review

1. Answers to the five concept questions, especially #2 and #3.
2. `docs/decisions.md` — ADR-0014.
3. Your notes on the reference repo's `jwt.decode()` fallback bug, in your own words.
4. The four rejection-case test results, with what you actually observed.

Opening question: **walk me through, step by step, what happens between a client sending
a connection request with a bad token and that connection being fully rejected — where
exactly does the bad token get caught, and what does the client see?**

---

## 9. NOTES.md entry

```
## Day 6 — <date>
**Built:**
**Confused me:**
**Would do differently:**
**Open question for tomorrow:**
```

---

**Tomorrow (Day 7)** is the matchmaking queue — the first genuinely stateful, in-memory
data structure of the project, and the first day you'll explicitly reason about what
happens when two things try to happen at the exact same moment (two people queuing,
someone disconnecting mid-match). Day 6's authenticated socket connection is the
foundation everything in Week 2 sits on top of.
