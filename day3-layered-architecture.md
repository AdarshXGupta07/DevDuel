# CodeDuel — Day 3 Brief
**Layered architecture, Pydantic, and the register endpoint**

> Today you build your first real API endpoint: `POST /api/auth/register`. The code is
> small. The point of today is the *shape* of the code — where each piece of logic is
> allowed to live, and why mixing them causes real bugs later.

---

## Why this day exists

Up to now everything has been plumbing — config, models, migrations. Today is the first
time you write logic that makes a decision ("is this email already taken?") and the first
time your API returns data to a caller. Two new failure modes appear the moment you do that:

1. **Returning the wrong data.** It is extremely easy to accidentally leak a password hash
   in an API response if you're not deliberate about what "the response" even is.
2. **Putting logic in the wrong place.** Validation, business rules, and database access
   all *feel* like they can live in one big function. They can — until you need to test one
   without the others, or reuse one from two different endpoints.

Today's architecture is the answer to both.

---

## 1. Concept study — 30 min

**Read/look up:**
1. Layered architecture: router → service → ORM. What job belongs to each layer.
2. Why an API response schema (Pydantic) is a **separate class** from a database model
   (SQLAlchemy), even when they look nearly identical.
3. Password hashing: what bcrypt actually does, why it's one-way, why a salt matters.
4. HTTP status codes for "this already exists" (you'll pick one and defend it).

**You must be able to answer, unaided:**

1. If your route function directly returns `user` (a SQLAlchemy `User` object) from
   `POST /register`, what's the actual risk? Walk through what FastAPI does when it
   serializes an ORM object it doesn't have an explicit schema for.
2. What's the difference between "validation" (is this a valid email shape?) and a
   "business rule" (is this email already registered?)? Which layer should each live in,
   and why does mixing them make the code harder to test?
3. Why can't you reverse a bcrypt hash back into the original password? What would it mean
   for your security if you *could*?
4. Two users register with the same email in the same second. What has to happen at the
   database level to guarantee only one of them succeeds — and where have you already built
   that guarantee? (Look back at Day 2.)
5. Should the API tell a user "this email is already registered" or something vaguer? Argue
   both sides — one is more helpful to a legitimate user, one leaks less information to an
   attacker probing which emails exist on your platform.

If you can't answer #1, don't start writing the router — that's the bug this whole day
exists to prevent.

---

## 2. Design doc — 20 min

Apply the five questions to **registration**, in `NOTES.md`.

1. **What is the actual problem?** No technology names. Something like: "a new person needs
   to establish an identity in the system, using a secret only they know."
2. **Inputs, outputs, invariants.** What comes in from the HTTP request? What goes back out?
   What must *never* be in that outgoing response? What must always be true afterward (e.g.
   "no two users share an email")?
3. **Where does state live, who owns it?** The `users` table owns identity. Does anything
   else need to know a user was just created, today? (No — that's Day 6+.)
4. **What breaks it?** Duplicate email. Malformed email. Empty password. A password that's
   technically valid but trivially weak. Two requests racing to register the same email at
   the same instant.
5. **Simplest thing that satisfies 1–4?**

Write one paragraph in `docs/decisions.md` (ADR-0010) on the status-code question from
concept question 5. This is a real, defensible product decision — pick one.

---

## 3. Build — 3 hrs

### 3.1 Two new dependencies

```
passlib[bcrypt]
```

Check its release date and open issues before installing — the Day 1 brief flagged this
library as old and occasionally friction-prone with newer `bcrypt` versions on some
platforms. If you hit install trouble, the fallback is the `bcrypt` package directly,
without passlib as a wrapper. Note whichever you land on in `docs/decisions.md`.

### 3.2 `app/schemas/user.py` — the Pydantic layer

This is **not** your SQLAlchemy `User` model. It's a new, separate set of classes whose
only job is describing what goes over HTTP.

You need at minimum:
- A **request** schema: what a client must send to register (email, password, name).
- A **response** schema: what the API sends back (id, email, name — **no password field
  of any kind**, hashed or not).

Look up "Pydantic `model_config` `from_attributes`" — this is what lets a Pydantic response
schema be built directly from a SQLAlchemy object's attributes, which is how you'll return
data without hand-copying every field.

### 3.3 `app/core/security.py` — hashing

One function to hash a plaintext password into a hash. One function to verify a plaintext
guess against a stored hash. This file does not know anything about HTTP, routes, or the
database — it only knows about passwords and hashes. That isolation is the point: Day 4
reuses this exact file for login, unchanged.

### 3.4 `app/services/auth_service.py` — the business logic

This is where "is this email already taken" and "hash the password" and "insert the user"
actually happen, using the database session from `session.py` and the security functions
from `security.py`. This file does not know anything about HTTP — no `Request`, no status
codes, no `Depends`. It takes plain Python values in, returns a plain Python object (or
raises an exception) out. That's what makes it testable without a running server.

### 3.5 `app/core/errors.py` — consistent error handling

Decide what happens when the service layer finds a duplicate email. Does it raise a plain
Python exception that the router catches and turns into an HTTP response? Look up FastAPI's
`HTTPException` and/or custom exception handlers — pick one pattern and use it consistently,
since you'll reuse it on every route for the rest of the month.

### 3.6 `app/routers/auth.py` — the thin layer

The route function's job: receive the request schema, call the service function, return the
response schema. It should be short — a handful of lines. If you find yourself writing
`if`/business logic here, that logic belongs one layer down, in the service.

### 3.7 Wire it into `main.py`

Register the router (`app.include_router(...)`) so `/api/auth/register` actually exists.

---

## 4. Test and verify — 45 min

- [ ] Register a new user — 201 (or your chosen success code), response contains no password
      field of any kind.
- [ ] Query the `users` table directly (same way we verified the schema on Day 2) and confirm
      the stored value is a bcrypt hash, not the plaintext password.
- [ ] Register the same email twice — second attempt returns your chosen 4xx, not a 500, and
      does **not** create a second row.
- [ ] Send a malformed email (`"not-an-email"`) — rejected before it reaches your service
      logic. Confirm this happens at the schema layer, not deep inside your database code.
- [ ] Send an empty or missing password — rejected the same way.
- [ ] Read the raw HTTP response body yourself, by eye, for the successful case — don't just
      trust that it "looks right" in a UI. Confirm no hash, no internal fields, nothing you
      didn't deliberately put in the response schema.

---

## 5. Definition of done

```
backend/
├── app/
│   ├── schemas/
│   │   └── user.py
│   ├── core/
│   │   ├── security.py
│   │   └── errors.py
│   ├── services/
│   │   └── auth_service.py
│   ├── routers/
│   │   └── auth.py
│   └── main.py          (router registered)
docs/
└── decisions.md          (+ ADR-0010: duplicate-email response wording/status)
```

Plus: real user in Supabase with a bcrypt hash, duplicate email properly rejected, response
body verified clean by hand.

---

## 6. Traps to expect

1. **Returning the SQLAlchemy model directly from the route.** FastAPI will often serialize
   it anyway using its `__dict__`, which can include the password hash. This is the exact
   bug Day 3 exists to prevent — always return through your response schema.
2. **Business logic leaking into the router.** If `auth.py` has an `if` statement checking
   business rules, it's grown past what a router should do.
3. **Catching the duplicate-email error in the wrong place**, or not at all — an unhandled
   database integrity error becomes an ugly 500 instead of a clean 4xx.
4. **Forgetting the response schema strips fields — only if you actually declare it as the
   route's `response_model`.** Just having a schema class doesn't help if the route doesn't
   use it.
5. **Testing only the happy path.** The interesting bugs are in the four rejection cases,
   not the one success case.

---

## 7. Bring to review

1. Answers to the five concept questions.
2. `docs/decisions.md` — ADR-0010.
3. A real HTTP request/response pair for both success and duplicate-email failure — paste
   the actual bodies, not a description.
4. `schemas/user.py`, `services/auth_service.py`, `routers/auth.py`.

Opening question: **what specifically stops `main.py` or `routers/auth.py` from ever seeing
a raw password hash?**

---

## 8. NOTES.md entry

```
## Day 3 — <date>
**Built:**
**Confused me:**
**Would do differently:**
**Open question for tomorrow:**
```

---

**Tomorrow (Day 4)** is JWTs and the login flow — reusing `security.py` unchanged, adding
token issuing and the access/refresh split. If you finish early today, read (don't write)
what a JWT's three parts actually contain, so tomorrow starts with the concept loaded.
