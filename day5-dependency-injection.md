# CodeDuel — Day 5 Brief
**Dependency injection, protected routes, and your first test suite**

> Today closes Week 1. By the end: a `get_current_user` dependency that protects routes,
> real profile endpoints, and a pytest suite that proves the whole auth flow works —
> including the first deliberate attempt to break your own authorization.

---

## Why today matters

Every route you've built so far is public — anyone can call `/register` or `/login`
without proving anything first. Today you build the mechanism that says "this route
requires a valid, logged-in user" — and then you try to break it. Not "does it work,"
but "can user A see or edit user B's data by changing an ID."

That distinction — **authentication** (who are you) vs **authorization** (are you allowed
to do *this specific thing*) — is the entire point of today. You already built
authentication (Day 3/4). Today is authorization, and it's the one most real APIs get
wrong at least once.

---

## 1. Concept study — 30 min

**Read/look up:**
1. FastAPI's dependency injection system — what `Depends(...)` actually does, generally
   (you've used it for `get_db` all week without the full picture).
2. Middleware vs per-route dependencies — two different ways to intercept a request, and
   why FastAPI favors dependencies for auth specifically.
3. pytest fixtures — what a fixture is, why tests share setup code through them instead of
   repeating it.
4. `httpx`'s async test client — how you call your FastAPI app in a test without actually
   starting a running server.

**You must be able to answer, unaided:**

1. What's the actual difference between **authentication** and **authorization**? Give an
   example of a bug that's an authentication failure, and a separate example that's an
   authorization failure.
2. Where should the token come from on an incoming request — the `Authorization` header,
   a cookie, or either? The old reference repo accepted both. Is that convenient or sloppy?
   Argue it, then decide.
3. `get_db` and the dependency you're building today (`get_current_user`) will likely be
   *stacked* — one dependency depending on another. Walk through what FastAPI does when a
   route depends on `get_current_user`, which itself depends on `get_db`.
4. Why use a **separate test database** (or at least separate test data) instead of hitting
   your real Supabase project during tests? What actually goes wrong if you don't?
5. If `get_current_user` successfully decodes a token but the user ID inside it doesn't
   exist in the database anymore (deleted account, tampered token), what should happen?

If you can't answer #1 with a concrete example for each, that's the concept to nail before
writing `get_current_user` — it's the one this whole day is testing your grasp of.

---

## 2. Design doc — 20 min

Apply the five questions to **route protection**, in `NOTES.md`.

1. **What is the actual problem?** No technology names. Something like: "some actions
   should only be performable by the person who is currently proven to be a specific user."
2. **Inputs, outputs, invariants.** What goes into `get_current_user` (a request, implicitly
   a token)? What comes out (a `User` object, or a rejection)? What must never happen — a
   route executing its logic for a user who was never actually authenticated?
3. **Where does state live?** The token is stateless (Day 4). The *user* it refers to lives
   in the database. What has to be checked against the database on every protected request,
   and what can be trusted from the token alone?
4. **What breaks it?** No token sent. Malformed token. Expired token. Valid token, deleted
   user. Valid token for user A, but the request tries to act on user B's data.
5. **Simplest thing that satisfies 1–4?**

No new ADR required today — Day 5 is more about proving Week 1's decisions hold up than
making new ones. But if the `Authorization`-header-vs-cookie question (concept #2) reveals
you want to change something from Day 4, write that as ADR-0013.

---

## 3. Build — 3 hrs

### 3.1 `app/core/dependencies.py` — `get_current_user`

This function will:
- Extract the token from the incoming request (decide: header, cookie, or both — per your
  concept-question-2 answer)
- Decode it using `decode_token` from `security.py` (unchanged from Day 4)
- Look up the user in the database by the `sub` field in the payload
- Return the `User` object if everything checks out
- Raise an appropriate error (look up FastAPI's `HTTPException` with `401`) if the token is
  missing, invalid, expired, or the user no longer exists

Look up **`OAuth2PasswordBearer`** or a plain custom header-reading dependency — FastAPI has
a built-in helper for the "read a Bearer token from the Authorization header" pattern, but
you can also write this by hand. Either is fine; know why you picked it.

This dependency needs `db: AsyncSession = Depends(get_db)` as one of its own parameters —
that's the "stacked dependency" from concept question 3, made real.

### 3.2 Protect the routes

- `GET /api/auth/me` — new route, returns the current user's own data. Trivial once
  `get_current_user` exists: the route barely does anything besides depend on it and
  return the result.
- `PUT /api/users/profile` — update your own name/email.
- `PUT /api/users/password` — change your own password (reuse `hash_password`/
  `verify_password` from Day 3, requiring the *current* password to change it).
- `DELETE /api/users/account` — delete your own account.

Every one of these takes `current_user: User = Depends(get_current_user)` as a parameter.
None of them should take a user ID from the URL or request body to know *whose* data to
touch — the ID always comes from the authenticated token, never from something the client
could tamper with. This is the actual authorization guarantee, and it's a design decision,
not an afterthought.

### 3.3 First pytest suite

New dependency:
```
pytest
pytest-asyncio
httpx
```

Structure:
- `tests/conftest.py` — shared fixtures. At minimum: a test client (via `httpx`'s
  `AsyncClient` pointed at your FastAPI app), and a way to get a valid auth token for a
  test user (register + login inside the fixture, or a lower-level helper).
- `tests/test_auth.py` — covers the full flow: register, login, access `/me` with the
  token, access `/me` with no token, access `/me` with a garbage token.

Decide on the test-database question from concept #4 now, not after tests are already
written against your production Supabase data.

---

## 4. Test and verify — 45 min

Beyond `pytest` passing:

- [ ] Protected route with no token → 401.
- [ ] Protected route with a valid token → 200, correct user's data.
- [ ] Protected route with another user's valid token → returns *that* user's data, not a
      mix-up. (Register two users, confirm each token only ever sees its own account.)
- [ ] **The actual authorization bug hunt:** try to update user B's profile while
      authenticated as user A — by attempting to pass a different user ID in the request
      body/URL, if your route accepts one at all. Confirm it's rejected or simply ignored
      (the route should never trust a client-supplied ID over the token's).
- [ ] Delete your own account, then try to use the same access token again — what happens?
      (Decide and test: should this fail immediately, or only after the token naturally
      expires? Either is defensible, but know which you built.)

---

## 5. Definition of done

```
backend/
├── app/
│   ├── core/dependencies.py     (get_current_user)
│   ├── routes/auth.py            (+ GET /me)
│   └── routes/users.py           (PUT /profile, PUT /password, DELETE /account)
tests/
├── conftest.py
└── test_auth.py
```

Plus: `pytest` green, all five verification checks above passing, and the authorization
bug hunt genuinely attempted (not skipped) with a written note on what you found.

---

## 6. Traps to expect

1. **Trusting a client-supplied user ID over the token.** The single most common real-world
   authorization bug — a route reads `user_id` from the request body and updates *that*
   user, instead of always using `current_user.id` from the dependency.
2. **Forgetting `get_current_user` needs `get_db` too** — stacked dependencies still each
   need their own requirements declared.
3. **Testing against your real Supabase data** and leaving test users scattered in it
   (you've already done this once, Day 3 — `day3test3@example.com` is still sitting there).
4. **A 500 instead of a 401** for a malformed/missing token — same "clean error, not a
   crash" discipline as every day this week.
5. **Not actually trying to break your own authorization.** It's tempting to only test that
   the happy path works. The bug hunt in §4 is the actual point of the day.

---

## 7. Bring to review

1. Answers to the five concept questions, especially #1 with concrete examples.
2. `pytest` output — full pass.
3. The authorization bug-hunt result — what you tried, what happened, paste the response.
4. `dependencies.py` and one protected route.

Opening question: **two different users, two different tokens — walk me through exactly
what stops user A's token from ever returning user B's data, at the code level.**

---

## 8. NOTES.md entry

```
## Day 5 — <date>
**Built:**
**Confused me:**
**Would do differently:**
**Open question for tomorrow:**
```

---

## Week 1 milestone

If today closes clean, you have a production-shaped auth service with tests — the thing
the original plan calls the Week 1 milestone. Before moving into Week 2 (realtime,
matchmaking), this is the natural point to:
- File the still-outstanding ADRs in `docs/decisions.md` (none exist yet)
- Clean up stray test data
- Do a real review pass across all of Week 1, since you asked for exactly this after Day 5

**Tomorrow (Day 6)** is WebSockets and socket authentication — a different transport
entirely, but the same authentication logic gets reused, not rebuilt.
