# CodeDuel — Day 4 Brief
**JWT, sessions, and the login flow**

> Today: `POST /api/auth/login`, `POST /api/auth/refresh`, `POST /api/auth/logout`.
> You reuse `security.py` unchanged for password verification, and add token
> issuing on top of it. The hard part today isn't the code — it's the reasoning
> about what a token can and can't do once it's issued.

---

## Why today matters

Once you hand someone a JWT, you cannot take it back. It's not like a session ID sitting
in your database that you can delete. That one fact drives almost every design decision
today — access vs refresh tokens, why refresh tokens live server-side, what "logout"
actually means when the thing you issued is unrevokable by nature.

---

## 1. Concept study — 30 min

**Read/look up:**
1. Stateless vs stateful auth — what "stateless" actually buys you, and what it costs.
2. What a JWT physically is: header.payload.signature. Decode one by hand (base64, not a
   library) and *read* what's inside the payload.
3. Access tokens vs refresh tokens — why two tokens instead of one.
4. Cookies vs `localStorage` for storing a token client-side: XSS risk vs CSRF risk,
   `httpOnly`, `SameSite`.

**You must be able to answer, unaided:**

1. A JWT's payload is base64-encoded, not encrypted. What does that mean for anyone who
   intercepts the token, or anyone with browser dev tools open? What must you therefore
   never put in a JWT payload?
2. If a JWT can't be revoked, how do you actually log someone out for real? Think through
   what "logout" has to mean given that constraint.
3. Why store the refresh token server-side but *not* the access token? What's the blast
   radius if your access-token signing secret leaks, versus your refresh-token secret?
4. What is "refresh token reuse detection," and what attack is it defending against? (Look
   this up — it's a specific, named pattern, not something to guess at.)
5. `httpOnly` on a cookie stops JavaScript from reading it. Why does that matter for XSS
   specifically? What attack does `httpOnly` do nothing against?

If you can't answer #1, stop — that's the single most common real-world JWT bug (putting a
password hash or other sensitive data in the payload "just to be convenient").

---

## 2. Design doc — 20 min

Apply the five questions to **login and session management**, in `NOTES.md`.

1. **What is the actual problem?** No technology names. Something like: "once someone has
   proven who they are once, the system needs to keep recognizing them for a while, without
   asking again on every request."
2. **Inputs, outputs, invariants.** What goes in (email + password)? What comes out (two
   tokens, or one)? What must never happen — a token issued for the wrong user, a token that
   never expires, a revoked session still being accepted?
3. **Where does state live, who owns it?** Which token is fully self-contained (stateless)?
   Which one needs a database row to be meaningful? Why the difference?
4. **What breaks it?** Wrong password. Expired access token. Expired refresh token. A
   refresh token used twice. A tampered token (one character changed). The signing secret
   itself leaking.
5. **Simplest thing that satisfies 1–4?**

Write ADR-0011 in `docs/decisions.md`: your token lifetime choices (how long does an access
token live? a refresh token?) and your reasoning. There's no universally correct number —
defend whatever you pick against the tradeoffs in question 2 above.

---

## 3. Build — 3 hrs

### 3.1 New dependency

```
python-jose[cryptography]
```

This is what actually signs and verifies JWTs.

### 3.2 Extend `app/core/security.py`

This file already has `hash_password`/`verify_password` from Day 3 — don't touch those,
just add to the file. You need functions to:
- create an access token (short-lived, encodes the user's id, has an expiry)
- create a refresh token (longer-lived, same idea)
- decode/verify a token, handling the case where it's expired or tampered with

Look up `jose.jwt.encode` / `jose.jwt.decode` — the shape is: give it a payload dict, a
secret, an algorithm, get back a token string (encode); give it a token string and the
secret, get back the payload dict or an exception (decode).

**Where does the signing secret come from?** Not hardcoded, not a new random guess — it
belongs in `config.py`, same "one door" rule as every secret this month. Add a required
field to your `Settings` class for it, and generate a real random secret for `.env` (look
up how to generate a secure random string — don't just type something memorable).

### 3.3 Refresh token persistence

Refresh tokens need to be revocable, which means the database needs to know about them.
Decide: a new table (`refresh_tokens`) storing which tokens are valid per user, or a column
on `users`? A dedicated table is usually cleaner — it naturally supports a user having
multiple active sessions (multiple devices) and makes "revoke this one session" possible.
Your call — write it as ADR-0012.

If you add a table, that's a new Alembic migration. Same process as Day 2: write the model,
autogenerate, **read the SQL**, apply.

### 3.4 `app/services/auth_service.py` — add login logic

A new function: given email + password, verify the password against the stored hash
(`verify_password`, already built), and if correct, issue both tokens. If the refresh token
needs to be checked against the database (for reuse detection later), the logic that stores
it belongs here too.

### 3.5 `app/routers/auth.py` (or `routes/auth.py`, your existing naming) — three new routes

- `POST /login` — email + password in, both tokens out
- `POST /refresh` — refresh token in, new access token (and possibly rotated refresh token)
  out
- `POST /logout` — invalidates the refresh token server-side

Decide where tokens are set: response body, or `httpOnly` cookies? This connects straight
to concept question 5. Whichever you pick, be consistent — don't mix approaches across the
three routes.

---

## 4. Test and verify — 45 min

- [ ] Login with correct credentials — receive both tokens.
- [ ] Login with wrong password — rejected, no tokens issued, no hint about which field was
      wrong (email vs password) beyond what you decided the response should say.
- [ ] Decode the access token yourself (by hand or a jwt.io-style tool) — confirm it
      contains exactly what you intended, nothing sensitive.
- [ ] Wait for (or fake) an expired access token — confirm a protected check rejects it.
      (You don't have a protected route yet — Day 5 — but you can test `decode` directly
      with a token you construct with a past expiry.)
- [ ] Tamper with one character of a real token — confirm decode rejects it.
- [ ] Call `/refresh` with a valid refresh token — get a new access token.
- [ ] Call `/logout`, then try to use the same refresh token again — rejected.

---

## 5. Definition of done

```
backend/
├── app/
│   ├── core/security.py       (extended: token create/decode)
│   ├── config.py               (+ JWT secret field)
│   ├── db/models.py            (+ RefreshToken, if you chose a table)
│   ├── services/auth_service.py (+ login logic)
│   └── routes/auth.py          (+ /login, /refresh, /logout)
├── alembic/versions/           (+ migration, if a new table was added)
docs/
└── decisions.md                (+ ADR-0011 token lifetimes, ADR-0012 refresh storage)
```

---

## 6. Traps to expect

1. **Putting the wrong secret in the wrong config field**, or reusing your database
   password as the JWT secret. They're unrelated secrets with unrelated blast radii — keep
   them separate.
2. **Forgetting `exp` (expiry) in the token payload entirely.** A JWT with no expiry never
   expires — that's not "stateless," that's a permanent credential.
3. **Storing the plaintext refresh token in the database.** If your database is ever
   breached, a plaintext token is instantly usable by the attacker. Consider storing a hash
   of it instead (same idea as passwords, different reason).
4. **Async/sync mismatch again** — JWT signing/decoding with `python-jose` is CPU-bound and
   synchronous, same category as bcrypt yesterday. Decide if it's fast enough to not bother
   wrapping (JWT operations are typically much faster than bcrypt, microseconds not
   hundreds of milliseconds) — but know *why* you're making that call, don't just guess.
5. **Testing only the happy path** — the interesting bugs today are in expiry, tampering,
   and reuse, not in "login with the right password once."

---

## 7. Bring to review

1. Answers to the five concept questions.
2. `docs/decisions.md` — ADR-0011, ADR-0012.
3. A decoded access token payload, pasted — show me exactly what's in it.
4. The reuse-detection test — paste what happened when you tried the same refresh token
   twice.

Opening question: **your access token just leaked — someone found it in a browser
extension's logs. Walk me through the actual damage, and how long it lasts.**

---

## 8. NOTES.md entry

```
## Day 4 — <date>
**Built:**
**Confused me:**
**Would do differently:**
**Open question for tomorrow:**
```

---

**Tomorrow (Day 5)** is dependency injection and protected routes — `get_current_user`,
your first pytest suite, and the first authorization bug hunt (can user A edit user B's
profile by changing an ID in the request?). This is the day Week 1's milestone closes.
