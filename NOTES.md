# CodeDuel — Build Notes

## Day 1 — 2026-08-29
**Built:** FastAPI app skeleton (`app/main.py`), config loading from `.env` via
pydantic-settings (`app/config.py`), `/health` endpoint. Confirmed the app refuses to
boot with a missing required env var (fail-fast, per ADR-0002).

**Confused me:** Basic Python syntax more than the concepts — `from X import Y` order,
dictionary vs tuple brackets, decorator syntax (`@app.get(...)`). Also lost time to a
non-activated venv and to running uvicorn from the wrong directory (`app.main:app` needs
to be run from `backend/`).

**Would do differently:** Read one working example (FastAPI's own "First Steps" tutorial)
*before* attempting to write a file from memory, instead of guessing at syntax first and
fixing errors after.

**Open question for tomorrow:** Which Supabase connection string to use for Alembic —
direct connection vs pooler.

---

## Day 2 — 2026-08-30
**Built:** Full schema — `users`, `problems`, `test_cases`, `duels`, `submissions` —
designed on paper first, then as SQLAlchemy 2.0 models (`app/db/models.py`). Alembic set
up with async support (`alembic/env.py` rewritten for `asyncpg`). Three migrations applied
to Supabase: initial tables, self-duel check constraint (`player1_id != player2_id`),
server-side column defaults.

**Confused me:** A lot, and most of it was infrastructure, not the relational-modeling
concepts themselves:
- Alembic's `env.py` needs models explicitly imported (not just `Base`) or autogenerate
  silently produces an empty migration — no error, just nothing detected.
- `config.set_main_option()` routes the DB URL through Python's `configparser`, which
  treats `%` as special syntax — collided badly with a URL-encoded `@` in the DB password
  (`%40`). Fixed by bypassing the ini-config path entirely and handing the URL straight to
  the engine.
- Alembic's autogenerate does **not** detect `server_default` changes by default — has to
  be written by hand as raw `op.execute(...)` SQL.
- **Unresolved:** in one migration, only the *first* of eight `op.execute()` statements
  actually took effect on the real database, even though Alembic reported success with no
  error. Worked around by applying the remaining statements directly via a script with an
  explicit commit. Root cause still unknown — worth revisiting.

**Would do differently:** Test a migration with 2 statements before writing one with 8 —
would have caught the silent-partial-execution bug on statement 2 instead of statement 8.
Also: verify `alembic/env.py`'s model import immediately after `alembic init`, before
writing any real migration.

**Open question for tomorrow:** Why did only the first `op.execute()` in a migration
persist? (Suspect something in the async `run_sync` bridge in `env.py`.)

---

## Day 3 — 2026-08-30
**Built:** `POST /auth/register` end to end — `schemas/user.py` (Pydantic:
`UserAccept`/`UserResponse`), `core/security.py` (password hashing), `services/auth_service.py`
(business logic: duplicate-email check, hash, insert), `routes/auth.py` (thin HTTP layer).
Verified the response body contains no password field, and that a duplicate email returns
409, not 500.

**Confused me:** This was the most bug-dense day so far — one bug from nearly every
category:
- Empty file (`security.py` had never actually been written).
- Wrong import path (`from app.schemas import X` vs `from app.schemas.user import X`) plus
  a class-name mismatch (`UserCreate` referenced but the real class was `UserAccept`).
- A schema field (`created_at: Field(...)`) missing its type annotation entirely.
- Parameter name mismatch inside a function — route param named `user`, function body
  referenced `payload`, which didn't exist there. Real `NameError` waiting to happen.
- **passlib 1.7.4 is incompatible with bcrypt 5.0** — passlib's internal version-detection
  code references `bcrypt.__about__`, which newer bcrypt versions removed. This was flagged
  as a real risk back on Day 1. Fixed by dropping passlib and calling `bcrypt` directly.
- `await hash_password(...)` — tried to `await` a plain (non-async) function's return value.
  `hash_password` is a regular `def`, so it returns its result immediately; there's nothing
  to await. Fixed with `asyncio.to_thread(hash_password, password)`, which runs the
  blocking bcrypt call on a separate thread so it doesn't freeze the event loop for every
  other connected user while hashing (~100–300ms, deliberately slow).
- Response schema (`UserResponse.id: str`) didn't match the real data type (`uuid.UUID`
  from the database) — FastAPI's response validation caught this and refused to serialize,
  rather than silently coercing it.

**Would do differently:** Test each layer in isolation before wiring the next one on top
(hash function alone → service function alone → route). Several of today's bugs would have
surfaced one layer earlier and been faster to diagnose. Also: read one real error message
fully, bottom-up, before assuming a fix worked — several "fixes" today didn't actually get
saved to the file the first time.

**Open question for tomorrow:** Day 4 is JWT + login — reuses `security.py` unchanged for
password verification, adds token issuing (access + refresh split) and the reuse-detection
question for refresh tokens.

---

## Still open / not yet done
- ADR-0010 (duplicate-email status code / message wording) — not yet written to
  `docs/decisions.md`.
- Stray test user row (`day3test3@example.com`) left in the database from a debugging
  session where registration succeeded but the response failed to serialize — harmless,
  not yet cleaned up.
- The Day 2 partial-migration-execution bug (see above) — unresolved.
- `README.md` and full `docs/decisions.md` (ADR-0001 through ADR-0010) still need to be
  written up properly — most decisions were made and discussed in the moment but not all
  filed to the doc yet.

---

## Day 11 — 2026-09-19 (production pass, Days 11–20 scope)

**Built:**
- **P0 defect fixes (§3 of docs/production-plan.md):** CORS locked to an explicit origin
  list for both FastAPI and Socket.IO, with `*` refused outright in production; rotating
  refresh tokens with reuse detection and hashed storage; `type` claim enforced so a
  refresh token can no longer be used as an access token; every timestamp column moved to
  `timestamptz` with an aware `utcnow()`; the dead duplicate `legal_transition` deleted;
  `as_uuid()` validation at every id boundary; the loose test scripts moved out of
  `backend/` root into `scripts/manual/` so they stop writing junk into the database.
- **Schema pass (§4):** `duels.mode` (casual/ranked) plus language, match clock and rating
  snapshots; `ranked_daily_usage` as an atomically-claimed counter table; `subscriptions`,
  `payments`, `rating_history`, `match_events`, `reports`, `rooms`; problem provenance
  (`source`, `license`) and per-problem limits; indexes behind the disconnect lookup.
  One migration: `c1a2d3e4f501_production_schema_pass.py`.
- **Day 10, finally:** presence tracking, disconnect → opponent notification → cancellable
  30s grace timer → forfeit, reconnect cancels the timer and resyncs, and
  `sweep_expired_duels()` as the server-restart backstop.
- **Days 11–13 (judge):** pinned non-root runner images, `sandbox.py` with the full flag
  set and a capped output reader, `judge_service.py` with verdict mapping and
  fail-fast test execution.
- **Day 14 (problems):** 5 original problems as YAML + reference solutions, a seeder, and
  `verify_problems.py` which runs each reference solution through the real sandbox.
- **Day 15 (winnable duels):** `duel:submit` → judge → submission row → atomic
  `finish_duel` → ELO → `duel:end`. A duel can now actually be won.
- **Days 16–17:** concurrency semaphore, submission/run rate limits, the attack suite.
- **Days 18–20 (frontend):** React + Vite + Monaco, auth, lobby with the ranked-cap wall,
  the duel screen with server-authoritative timers, opponent status panel, paste-disable
  and keystroke logging in ranked, and the post-match reveal.

**Confused me / worth remembering:**
- `refresh_tokens.token` held raw tokens. They cannot be hashed retroactively, so the
  migration deletes them — everyone gets logged out once, which is the cheap correct answer
  now and would not be later.
- Two refresh tokens minted for the same user in the same second were byte-identical,
  which collides with the new UNIQUE on `token_hash`. Fixed with a `jti` + nonce.
- Concurrent refresh calls from the browser look exactly like token theft. The client has
  to collapse them into one in-flight promise or it revokes its own session.

**Would do differently:** the schema pass should have happened around Day 8. Adding
`duels.mode` after the matchmaking and ready-up logic existed meant touching all of it.

**Open / not done:**
- The migration has **not been run** — the database was not reachable from this machine.
- The runner images have **not been built** — Docker Desktop started but its CLI stopped
  responding, so the attack suite is unverified.
- Both are the first two steps of the next session. See the end of docs/production-plan.md.
