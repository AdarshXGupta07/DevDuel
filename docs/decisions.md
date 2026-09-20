# DevDuel — Architecture Decision Records

Each entry: the decision, why, and what it costs. An ADR is not a description of the
code — it is the reason the code looks like that, written down before the reason is
forgotten.

> **ADR-0001 through ADR-0018 were reconstructed on 2026-09-19 from the code as built.**
> They were real decisions made during Days 1–10 but never filed. Read them and correct
> anything that misremembers your actual reasoning — a wrong ADR is worse than a missing
> one. ADR-0019 onward were decided as part of the production pass.

---

## ADR-0001 — Python + FastAPI over Node
**Decision.** Backend in Python 3.12+ with FastAPI, not Node/Express.
**Why.** Async-native, first-class typing via Pydantic, and the language you are strongest
in — a month-long solo build is bounded by your velocity, not the framework's benchmarks.
**Cost.** The realtime ecosystem is smaller than Node's; `python-socketio` is less
travelled than `socket.io`. Accepted.

## ADR-0002 — Fail-fast configuration
**Decision.** All configuration through `pydantic-settings`; required values have no
defaults, so a missing env var crashes at import.
**Why.** A server that boots with a missing `JWT_SECRET` and defaults to `""` is worse
than one that refuses to start — the failure surfaces at 3am in production instead of
immediately in the terminal.
**Cost.** Every new required setting breaks local boots until `.env` is updated. That is
the feature working.
**Extended 2026-09-19.** `app/config.py` now also refuses to start when `APP_ENV` is
production and `CORS_ORIGINS` contains `*`.

## ADR-0003 — Postgres (Supabase) over MongoDB
**Decision.** Relational database, managed by Supabase.
**Why.** The data is inherently relational (duels reference two users and a problem;
submissions reference all three), and the invariants worth having — "a duel's players
must both exist", "players must be distinct" — are enforceable by the database itself
rather than hoped for in application code.
**Cost.** Migrations. Schema changes are a deliberate act, which is the point.

## ADR-0004 — SQLAlchemy 2.0 async + Alembic
**Decision.** Typed `Mapped[...]` models, `asyncpg` driver, Alembic for migrations.
**Why.** One model definition drives both the schema and the query layer; migrations are
reviewable files rather than remembered commands.
**Cost.** Alembic's autogenerate misses `server_default` changes and needs models
explicitly imported in `env.py`. Both have already cost real debugging time.

## ADR-0005 — Layered architecture: route → service → model
**Decision.** Routes handle HTTP only. Services hold business rules and know nothing
about HTTP. Models hold data.
**Why.** The socket layer added on Day 6 reuses the same services as the REST layer. That
reuse is only possible because the services never learned what a `Request` is.
**Cost.** More files, and more indirection for trivial endpoints.

## ADR-0006 — bcrypt directly, not passlib
**Decision.** Call `bcrypt` directly for hashing and verification.
**Why.** passlib 1.7.4 reads `bcrypt.__about__`, which bcrypt 5.0 removed — a hard break
with no maintained fix at the time.
**Cost.** You implement the small amount of glue passlib would have provided.

## ADR-0007 — Password hashing runs off the event loop
**Decision.** Every bcrypt call goes through `asyncio.to_thread`.
**Why.** bcrypt is deliberately slow (~100–300ms). On a single-threaded event loop that
is 300ms during which *every other connected player* is frozen.
**Cost.** A thread per hash. Negligible at this scale.

## ADR-0008 — UUID primary keys
**Decision.** UUIDv4 for every primary key, generated application-side.
**Why.** Ids can be created before the row exists — which matchmaking depends on, since
it generates a `duel_id`, puts both players in that room, and only then writes the row.
Sequential integers would also leak user and match counts to anyone reading a URL.
**Cost.** 16 bytes instead of 4, and worse index locality. Irrelevant at this scale.

## ADR-0009 — Duel status as a string column with a CHECK constraint
**Decision.** `duels.status` is text, constrained to five values by a database CHECK, with
the legal transitions encoded as a dict in `duel_service.TRANSITIONS`.
**Why.** A Postgres enum type is painful to extend (`ALTER TYPE` in a migration, and it is
not transactional in older versions). The CHECK gives the same guarantee and edits easily.
**Cost.** The transition rules live in two places — the constraint says which values are
legal, the dict says which moves are legal. They must be kept in sync by hand.

## ADR-0010 — Duplicate email returns 409
**Decision.** `POST /auth/register` with a taken email returns `409 Conflict`, and the
service raises a domain exception the route translates.
**Why.** 409 says "the request is fine, the state of the world conflicts with it" — which
is exactly true. 400 would blame the input; 500 would blame us.
**Cost.** Confirms an email is registered, which is an account-enumeration vector. Accepted
for now: the alternative (a generic response) makes signup materially worse, and the same
information leaks from the login form regardless.

## ADR-0011 — Access + refresh token split
**Decision.** 15-minute access tokens, 7-day refresh tokens, `type` claim on both.
**Why.** A stolen access token expires on its own in minutes. The long-lived credential is
used rarely and can be revoked server-side, which is the only revocation JWTs allow.
**Cost.** Two tokens for the client to manage, and a refresh endpoint to protect.
**Extended 2026-09-19.** `get_current_user` now rejects tokens whose `type` is not
`access` — previously a 7-day refresh token was silently accepted as an access token
everywhere, which collapsed the entire benefit of this split.

## ADR-0012 — Refresh tokens stored in the database
**Decision.** A `refresh_tokens` table, with a row per issued token.
**Why.** Without server-side state there is no logout, no revocation and no theft
response. The statelessness that makes access tokens cheap is exactly what makes refresh
tokens dangerous.
**Cost.** A database read on every refresh. Cheap and correct.

## ADR-0013 — Cascade delete of refresh tokens
**Decision.** `refresh_tokens.user_id` is `ON DELETE CASCADE`.
**Why.** Orphan credentials are the worst kind of leftover.
**Superseded in part by ADR-0027:** accounts are now anonymised rather than deleted, so
this cascade rarely fires. It stays as a correctness backstop.

## ADR-0014 — Socket authentication at connect time
**Decision.** The JWT is presented in the Socket.IO `auth` payload during `connect`;
rejection raises `ConnectionRefusedError`. The user id is then stored in the socket
session.
**Why.** Authenticating once per connection rather than once per event means an
unauthenticated socket never exists at all, and every later event has a trustworthy
identity without re-parsing a token.
**Cost.** Socket.IO reconnects the transport automatically but the server re-runs
`connect` with no memory — so the client must present a *valid* token on every reconnect.
A 15-minute access token can expire mid-duel, so the client refreshes before reconnecting
(`frontend/src/socket.js`).

## ADR-0015 — In-memory matchmaking queue
**Decision.** The queue is a per-process Python dict.
**Why.** The simplest thing that works for one instance, and the queue is genuinely
ephemeral — nothing of value is lost if it disappears.
**Cost, stated plainly.** It dies with the process, and two API instances have two queues
that cannot see each other. **This blocks horizontal scaling entirely** and is scheduled
to move to Redis on Day 25, along with socket presence and the rate limiter.

## ADR-0016 — Duels are written to the database at match time
**Decision.** A `duels` row is created the moment two players are paired, in `pending`,
then immediately transitioned to `ready`.
**Why.** The duel's durable truth lives in Postgres, so a reconnecting client can rebuild
its entire view from `GET /api/duels/{id}` with no in-memory state involved.
**Cost.** A row for every match that may never actually be played. Cleaned up by the
`abandoned` status rather than deletion, which preserves the record.

## ADR-0017 — Ready-up resolved by an atomic conditional UPDATE
**Decision.** Each player writes only their own `playerN_ready` column; the start is a
single `UPDATE … WHERE status='ready' AND player1_ready AND player2_ready`, and the
winner is whoever gets `rowcount == 1`.
**Why.** Check-then-act in Python has a gap: the moment there is an `await` between
reading "are both ready" and writing "start", two events can interleave and both start
the duel. Folding the check into the write removes the gap entirely — the database
decides, and it can only decide once.
**Cost.** The logic is less obvious to read than an `if`. Worth it.
**Generalised 2026-09-19.** The same pattern now also guards duel completion
(`finish_duel`) and the free-tier daily cap (`claim_ranked_slot`).

## ADR-0018 — Disconnects get a grace period, then a forfeit
**Decision.** A player who drops mid-`active` duel has **30 seconds** to return. Their
opponent is told immediately. If they do not return, the duel is `finished` with the
opponent as winner and `end_reason = 'disconnect'`. Duels that had not yet started are
`abandoned` with no winner.
**Why.** The three options were instant loss, indefinite pause, and a timed grace period.
Instant loss punishes a 10-second tunnel or a phone locking, which is the common case and
not cheating. An indefinite pause is worse: it hands every losing player a free escape by
pulling their cable, and leaves the winner stuck in a match that never ends. A grace
period costs the honest player nothing and gives the cheat only a 30-second delay.
**Why 30 seconds.** Long enough for a wifi handover, a tab reload, or a phone unlocking.
Short enough that the waiting player does not give up on the match.
**Cost.** The timer is in process memory. A server restart mid-grace-period loses it —
`duel_runtime.sweep_expired_duels()` catches the resulting stuck duel at its deadline
instead, so a restart costs latency, not correctness.
**Open question for ranked.** A disconnect forfeit costs rating. That is the correct
deterrent, but it also punishes genuine bad connections. Revisit after seeing real data.

---

## ADR-0019 — Docker containers as the code sandbox
**Decision.** Each submission runs in a fresh Docker container, one per test case.
**Alternatives rejected:** `subprocess` + `resource` limits (no filesystem or network
isolation at all — unacceptable for arbitrary code); gVisor (stronger isolation, much more
operational complexity); Firecracker microVMs (strongest, needs bare metal and a scheduler
you do not have time to build); Judge0/Piston as a service (fastest to ship, but a hard
dependency on someone else's uptime and cost model for your core loop, and self-hosting it
is the same Docker problem plus their abstractions).
**Why Docker.** It is the only option with the right ratio of isolation to effort for a
solo build, and it is a skill worth having regardless.
**Cost, stated plainly.** Containers **share the host kernel**. A kernel exploit escapes
the box. The second line of defense is that the judge host holds no secrets, no database
credentials, and no production data — so an escape costs a rebuilt VPS, not user data.

## ADR-0020 — Judge resource limits
**Decision.** Per run: **5s** wall clock, **256MB** memory (with `--memory-swap` equal, or
the cap is fiction), **0.5** CPU, **64** pids, **64KB** captured output, and at most **4**
concurrent containers per instance.
**Why these numbers.** A correct Python solution to an easy problem runs in well under a
second, so 5s is roughly 5x headroom and still bounds the worst case. 256MB comfortably
holds a 200k-element list, which is the largest input any current problem specifies.
64 pids is far more than any legitimate single-threaded solution needs and far less than a
fork bomb wants. 64KB of output is ~1000 lines — more than any problem's answer.
**Cost.** A legitimately heavy solution in a slow language could be misjudged `tle`. Per
problem limits exist (`problems.time_limit_ms`) for exactly that case.

## ADR-0021 — Python and JavaScript only at launch
**Decision.** Two languages. Not three, not ten.
**Why.** Every language is a Docker image to maintain and pin, starter code for every
problem, a judge edge case (compile step, different exit codes), and a way for a problem's
test cases to be subtly unfair. Two covers the overwhelming majority of interview prep.
**Cost.** Turns away C++/Java competitive-programming users. That is not the launch
audience.

## ADR-0022 — CORS locked to an explicit origin list
**Decision.** `CORS_ORIGINS` is an explicit, comma-separated list for both FastAPI and
Socket.IO. `*` is refused outright when `APP_ENV` is production.
**Why.** `cors_allowed_origins='*'` on a credentialed socket server lets any page on the
internet open an authenticated connection on behalf of a logged-in user. It was a
development convenience that would have shipped.
**Cost.** One more thing to set per environment.

## ADR-0023 — Rotating refresh tokens with reuse detection
**Decision.** Every refresh mints a new refresh token and revokes the presented one.
Tokens are stored as SHA-256 hashes, grouped by a `family_id`. Presenting an
already-rotated token revokes the **entire family**.
**Why.** Before this, a stolen refresh token worked for a full 7 days and nothing could
detect it. With rotation, a thief and the real user cannot both use the chain — the second
one to present a spent token triggers the alarm, and the only safe response is to end
every session in that chain.
**Cost.** A client that loses the response to a refresh call is logged out. Concurrent
refreshes must be collapsed client-side (`frontend/src/api.js` does) or they look like
theft. Both are correct behaviour, and both will generate occasional confused support
mail. Worth it.
**Why hashed storage.** A database dump must not contain working sessions. A fast hash is
right here — unlike passwords, these are long and high-entropy, so there is no guess space
to slow an attacker through.

## ADR-0024 — Fixed IST midnight reset for the free ranked cap
**Decision.** The free tier's 2 ranked matches per day reset at **midnight Asia/Kolkata**,
not on a rolling 24-hour window.
**Why.** It is trivially explainable in the UI ("resets at midnight"), needs no per-user
timer, and matches where your first users are. A rolling window means a player must
remember when each individual match was played to know when they get another.
**Cost.** A player in another timezone gets a reset at an odd local hour.
`daily_reset_timezone` is configurable if the audience changes.

## ADR-0025 — The cap is a counter table, claimed atomically
**Decision.** `ranked_daily_usage (user_id, usage_date)` with an
`INSERT … ON CONFLICT DO UPDATE … WHERE matches_started < :limit RETURNING`. A slot is
claimed when queueing and **refunded** if the match never happens.
**Why a counter and not `COUNT(*)` over duels.** Counting duels makes the rule
("does a forfeit count?") a query that must be rewritten every time the rule changes, and
it races: two tabs clicking Ranked simultaneously can both count 1 and both proceed. One
atomic statement cannot.
**Why claim-then-refund.** The product rule is that only a *completed* match should burn
an attempt, but a pure "count on completion" design lets a user queue unlimited times.
Claiming up front bounds abuse; refunding on abandonment honours the rule.
**Cost.** A refund path that must be called from every abandonment route. Missing one
silently costs a user a free match — worth a test.

## ADR-0026 — Timeout tiebreak: tests passed, then earliest
**Decision.** When the clock expires with nobody fully solving: most hidden tests passed
wins; tie broken by earliest submission time; still tied is a draw (no rating change).
**Why.** It rewards actual progress rather than luck, and "earlier is better" matches the
race framing of the product. A draw is a real outcome and should not be forced into a
coin flip.
**Cost.** Encourages submitting early partial work purely to bank a timestamp. Acceptable —
that is also just playing well.

## ADR-0027 — Account deletion anonymises, it does not DELETE
**Decision.** `DELETE /auth/profile` scrubs email, name and password, stamps `deleted_at`,
and revokes every token. Duels and submissions remain.
**Why.** A hard delete either fails (duels reference `users` with the default RESTRICT) or
cascades away matches that are *also the opponent's history* — one user erasing another
user's record. Anonymising removes every piece of personal data while leaving the ladder
intact.
**Cost.** A row remains. The privacy policy must say so plainly, and the account cannot be
"undeleted" through this path.

## ADR-0028 — Opponent code is never sent during a live duel
**Decision.** Socket status events carry only a state string and integer test counts.
`GET /api/duels/{id}/submissions` returns the opponent's submissions **only when the duel
is finished**; during play it silently narrows to the caller's own.
**Why.** This single rule is what makes the product work: live enough to feel head-to-head,
closed enough that it is not a copying tool. It is enforced server-side, because anything
enforced only in the UI is not enforced.
**Cost.** None worth mentioning.

## ADR-0029 — Anti-cheat: prevention is a speed bump, the log is the evidence
**Decision.** Ranked editors block paste (keyboard and context menu) and log a
`paste_attempt`; large single inserts are logged, never blocked; all behavioural events
batch every ~2s into `match_events`.
**Why.** Paste-disable stops the common case — alt-tab to an LLM, ctrl-V. Anyone with
devtools defeats it in seconds, so ranked integrity cannot rest on it. Typed code has a
keystroke rhythm that pasted-then-edited code does not, and that signal survives devtools.
Logging starts now even though nothing analyses it yet, because the history cannot be
collected retroactively.
**Cost.** `match_events` will be the largest table in the system — see ADR-0030. Blocking
paste also mildly annoys honest players who duplicate a function.

## ADR-0030 — match_events retention: 30 days hot
**Decision.** Behavioural events stay queryable for 30 days, then archive to cold storage
and drop from Postgres. Never queried on a request path.
**Why.** At ~5 events/sec/player, a 15-minute duel is ~9,000 rows; 100 duels/day is ~1M
rows/day. That is the fastest-growing thing you own, and it is attached to a Supabase bill.
30 days covers any realistic dispute window.
**Cost.** A cheat reported on day 45 cannot be reviewed from hot data. Decide the archive
destination before switching logging on at volume.

## ADR-0031 — Judge concurrency is bounded and submissions are rate-limited
**Decision.** A semaphore caps concurrent containers per instance; players get 6
submissions and 20 sample runs per minute.
**Why.** The judge is the only part of the system with unbounded marginal cost. Without a
cap, 50 simultaneous submissions is a self-inflicted outage; without a rate limit, the
judge is a free compute farm and hidden test cases can be brute-forced by resubmission.
**Cost.** Under load, submissions queue and feel slow. That is the correct failure mode —
slow beats down.

## ADR-0032 — Razorpay Subscriptions, called over REST rather than the SDK
**Decision.** Recurring ₹50/month through Razorpay Subscriptions, driven by direct
`httpx` calls to their REST API instead of the official `razorpay` Python package.
**Why Razorpay.** UPI Autopay is the only recurring-payment method most Indian users will
actually complete at this price point; Stripe's India support does not compare.
**Why not the SDK.** It is synchronous. Every call would block the event loop — the same
mistake as bcrypt on Day 3, and the API surface we need is four endpoints.
**Cost.** We hand-roll signature verification and error mapping. Both are small and both
are now tested.

## ADR-0033 — The client never grants itself a plan
**Decision.** `users.plan` is written in exactly one function, `_apply_entity()`, reached
only from a **signed webhook** or a **server-to-server fetch** of the subscription. The
browser's success callback is treated as a pointer to re-check, never as evidence.
**Why.** The Checkout handler runs in the user's browser, where anyone can call it with
any argument. If the client could assert payment, the paid tier would be a devtools
console away.
**Why both paths.** The webhook is authoritative but can take seconds; users who just
paid expect access immediately. The `/sync` call closes that gap without trusting anyone.
**Cost.** Two code paths reaching the same function, and both must be idempotent.

## ADR-0034 — Access outlives the billing period by a grace window
**Decision.** A paid plan expires at `current_end + BILLING_GRACE_DAYS` (3). A `halted`
subscription keeps access for the same window. Cancellation keeps access to the end of
the period already paid for.
**Why.** A failed renewal is usually a bank blip, not a decision to leave. Cutting
someone off mid-duel over a retryable charge is a worse outcome than three free days.
**Cost.** Up to three days of unpaid access per lapsed user. At ₹50/month that is ₹5 —
far less than the support cost of one wrongly locked-out player.

## ADR-0035 — Webhooks return 200 once the signature verifies
**Decision.** After signature verification, the webhook route returns 200 even if
processing throws. Failures are logged with the event id.
**Why.** A non-2xx makes Razorpay retry, and retrying does not fix a bug in our handler —
it just multiplies the same failure and eventually disables the webhook. A logged event
id can be replayed deliberately from the dashboard.
**Cost.** A silent failure needs monitoring to be noticed. Worth an alert once Sentry is
in (Day 27).

## ADR-0036 — Four languages, and an executable /tmp for the compiled two
**Decision.** Python, JavaScript, C++17 and Java 21. The compiled pair build and run
inside a single container, which requires mounting `/tmp` with `exec` instead of
`noexec`, and per-language memory/pid limits (Java gets 512MB and 256 pids; a JVM will
not start inside the interpreter defaults).
**Why more than two.** ADR-0021 chose Python and JavaScript only, on the argument that
each extra language is an image, starter code and judge edge cases. That argument still
holds — but C++ and Java are what most interview candidates actually write, and turning
them away is turning away the launch audience. The cost was paid once.
**The security cost, stated plainly.** An executable `/tmp` means a submission can write
a binary and run it. That is strictly weaker than the interpreted languages, where it
cannot. Everything else still holds — no network, read-only `/box`, no inherited
environment, dropped capabilities, non-root, and the memory/pid/time caps — and
`tests/test_sandbox.py` re-tests network and filesystem isolation *specifically for C++*
rather than inferring it from the Python results.
**Cost noticed in testing.** Docker keeps `noexec` on a tmpfs unless `exec` is passed
explicitly; omitting `noexec` is not enough. Compiled runs are also 5–7x slower than
interpreted ones (~3s vs ~0.5s) because compilation happens per test case.
**Not done yet:** compiling once and reusing the binary across a problem's test cases.
Worth doing when judge latency starts mattering — it would cut a 20-case C++ submission
from ~60s to ~5s.

## ADR-0037 — Compile failure is its own verdict
**Decision.** The compile step exits with sentinel code 92, which maps to
`compile_error` rather than `runtime_error`.
**Why.** "Your code does not build" and "your program crashed while running" are
different mistakes and need different messages. Collapsing them tells a player with a
missing semicolon to go debug their algorithm.
**Cost.** A magic number shared between the shell command and the Python that reads it.
Named as `COMPILE_ERROR_EXIT` on the Python side so it is greppable.

## ADR-0038 — AI features are key-gated and degrade to "off", never to "broken"
**Decision.** Code review and the AI opponent call Claude (`claude-opus-5`) through the
official `anthropic` SDK. With no `ANTHROPIC_API_KEY`, `/api/ai/status` reports
`enabled: false`, the endpoints return 503, and the UI shows a labelled sample instead.
**Why gated this way.** A missing key is the normal state in development and the normal
state for anyone cloning the repo. Failing at call time — mid-duel, after a player has
clicked — would be the worst place to discover it.
**Why the sample is labelled.** A canned review presented as if it had read your code is
worse than no review: it teaches the wrong lesson with full confidence.
**Cost.** Two rendering paths for one panel, normalised in `ReviewBody`.

## ADR-0039 — Reviews are stored on the submission
**Decision.** `submissions.ai_review` holds the generated review as JSONB; a second
request returns the stored one.
**Why.** A player reopens a result screen repeatedly. Paying for the same review twice is
waste with no upside, and the review does not change — the code it reviewed cannot.
**Cost.** A stale review if the prompt or model improves later. Acceptable; clearing the
column regenerates.

## ADR-0040 — The AI opponent is scripted, and never sees the player's code
**Decision.** The opponent is a *timeline* generated once at duel start — when it types,
runs tests, submits wrong, and finishes — calibrated to the player's rating. It does not
execute code and receives no part of the opponent's submission.
**Why.** The product plan's option 1. One LLM call per practice duel instead of one per
event: bounded cost, no mid-duel latency, and a network blip cannot stall the opponent.
It is also the only version that cannot leak a player's code into a prompt.
**Cost.** The opponent cannot react to how the player is doing. Nobody has asked for that
yet, and the honest framing — "simulated pacing, the AI does not read your code" — is in
the UI.

## ADR-0041 — Judge and API share a host, for now
**Decision.** The API container mounts the host's Docker socket to start judge
containers, rather than running Docker-in-Docker or a separate judge service.
**Why.** DinD is slow and its own security problem; a separate judge service is a second
deployment for a product with no users yet.
**Cost, stated plainly.** The Docker socket is root-equivalent on the host. A container
escape reaches the API process and its environment, including database credentials. This
is the top item in `docs/deploy.md` § Hardening and an accepted gap in the threat model —
not a solved problem. Splitting the judge onto its own host is the first thing to buy
when there is revenue.

## ADR-0042 — Quitting is allowed, confirmed, and counted
**Decision.** Leaving a live duel always works, but it requires confirming a dialog that
states the exact cost, and it is recorded. Two abandons in one day pause matchmaking for
15 minutes; each further one doubles the pause, capped at 8x.
**Why allow it at all.** Trapping someone in a match they want to leave is worse product
design than letting them go — they will close the tab instead, which produces the same
outcome with a worse experience and a 30-second wait for their opponent.
**Why it must not be free.** An unpunished quit turns every losing position into "just
leave", which ruins the match for the player who was *winning*. They queued, waited, and
played well; a free quit takes that from them.
**Why a dialog that names the consequence.** "Are you sure?" gets clicked through without
reading. "This is your second walkout today — matchmaking will be paused for 15 minutes"
does not. The dialog reads the player's real count, so it is specific rather than generic.
**Why per-day, and why escalating.** The first walkout is usually a bad connection or a
misclick. The fourth in one afternoon is a habit. Counting per day means a bad afternoon
does not follow someone around forever; escalation means the deterrent tracks intent.
**Why the disconnect path counts too.** Otherwise pulling the cable is cheaper than
pressing the button, and the deterrent teaches the worse behaviour.
**Cost.** A player with genuinely unstable internet is penalised for something outside
their control. Mitigated by the 30-second grace period (ADR-0018) absorbing short drops,
and by the daily reset. Worth revisiting if real data shows honest players hitting it.
**Deliberate UI choice.** "Keep playing" is the filled primary button; "Quit and forfeit"
is the outlined destructive one. The safe action should be the easy click.

## ADR-0043 — Ranked duels are proctored: fullscreen, no copy, no leaving
**Decision.** Ranked duels run fullscreen behind a click-through gate. Copy, cut and
paste are blocked in the editor; text selection is disabled on the problem statement.
Leaving the window — tab switch, focus loss, or exiting fullscreen — shows a countdown;
failing to return forfeits the match, as does exceeding `proctor_max_violations` (3)
round trips. Casual duels are not proctored.
**Why copy matters more than paste.** The obvious cheat is pasting a solution in. The
*fast* cheat is copying the problem statement out into an LLM, which paste-blocking does
nothing about. Selection is disabled on the statement pane for that reason.
**What this actually is.** A deterrent and a behavioural record, not a control. The
browser cannot force fullscreen (entering needs a user gesture, exiting cannot be
blocked) and the client decides whether to report a violation at all — a determined
cheat patches the listeners out in a minute, exactly as with paste-disable. It makes
alt-tabbing a deliberate, recorded act rather than a reflex, which covers most people.
**Why the forfeit decision is server-side.** The client reports events; the server
decides consequences and writes the result. A client that could forfeit its opponent
would be a much worse bug than the cheating this prevents.
**Why a grace period rather than an instant kick — a deliberate softening of the
request.** An OS notification, an incoming call, or a screen reader can steal focus
through no fault of the player, and losing a ranked match to a calendar popup is
indefensible. 15 seconds to return, configurable to 0 via `PROCTOR_GRACE_SECONDS` if the
data says otherwise. Three round trips still forfeits, so the grace cannot be farmed.
**Why ranked only.** Casual is where people try the product. Kicking a first-time user
for alt-tabbing is a good way never to see them again.
**Cost.** Mobile browsers handle fullscreen inconsistently (iOS Safari on iPhone has no
element fullscreen at all) — tab-switch detection still works there, but the gate is
weaker. Accessibility tooling that takes focus may trip the warning. Both are worth
watching once there are real users.

## ADR-0044 — Timeout with neither player solving is a draw, and ratings do not move
**Supersedes ADR-0026.**
**Decision.** When the clock expires, a player only wins by having actually solved the
problem. If neither did, it is a draw with `end_reason='draw'` and **no rating change for
either player** — not an ELO draw, no change at all.
**Why the old tiebreak was wrong.** ADR-0026 awarded the win to whoever passed more
hidden tests. Passing 4 of 7 can mean a genuinely better attempt, or a wrong solution
that happens to survive the easy cases — those are indistinguishable from the outside.
Ranking two failures against each other reads signal into noise, and it rewards writing
something that games the sample cases over writing something that nearly works.
**Why no rating change rather than a 0.5/0.5 ELO draw.** Standard ELO moves ratings on
any draw between unequal players: the higher-rated one "underperformed". That is exactly
the wrong lesson from a problem that beat both of them. The match is still recorded and
`ranked_matches_played` still increments (it counts toward calibration); only the numbers
stay put. `tests/test_timeout_draw.py` pins down what plain ELO *would* have done, so
the special case cannot be silently removed.
**Cost.** The ladder is no longer strictly zero-sum across every match. Accepted: a draw
neither player earned should not redistribute rating between them. Partial progress is
still shown on the result screen — it just does not decide the match.

## ADR-0045 — Post-duel analysis is shown after every outcome, including a loss
**Decision.** Every finished duel produces analysis for both players: per-attempt verdict
breakdown with plain-English explanations, free static hints about the submitted code,
the **reference solution**, and the AI review (paid). Previously this appeared only
behind a "Keep solving" click, which in practice meant after a loss and only if you went
looking.
**Why.** The player who just lost is the one who most needs to know why. Gating the
explanation behind winning — or behind a button most people never press — had it exactly
backwards.
**Why the reference solution is stored in the database.** It is loaded by the seeder from
`problems/solutions/<slug>.py` — the same file `verify_problems.py` executes. The code
shown to players is therefore provably the code that passes every test, rather than a
second copy that can drift.
**The load-bearing check.** `GET /api/duels/{id}/analysis` returns 409 unless the duel is
`finished` and the caller is a participant. That response contains the answer key;
serving it mid-duel would end the product.
**Why free heuristics as well as the AI review.** The static hints (nested loops, list
membership, `input()`, front insertion) cost nothing and cover the most common mistakes,
so a free player still learns something. They are deliberately conservative — a wrong
hint is worse than no hint — and the UI says plainly that they are pattern checks rather
than a reading of the logic.

## ADR-0046 — No player is served a problem they have already seen
**Decision.** Problem selection excludes anything either player has been served before,
in any duel — including duels they abandoned. Preferences are applied in a fixed order,
each falling back rather than failing: unseen + requested topic → unseen, any topic →
requested topic, even if seen → anything active.
**Why repeats outrank topics.** A player who asked for graphs and got an array problem is
mildly disappointed. A player handed a problem they solved last week has had the duel
ruined — and so has their opponent, who is now racing someone with a head start. The
second failure is much worse, so it is prevented first.
**Why both players' histories are excluded, not just one.** A problem one of them has
seen is unfair to the *other*, not merely stale for them.
**Why abandoned duels still count.** Seeing the statement is what spoils it. Whether the
match finished is irrelevant.
**Why it degrades instead of erroring.** When the bank is exhausted, selection falls
through to serving a repeat rather than refusing to start the duel. Failing to match is
the one outcome nobody recovers from. `unseen_count()` exists so the UI can warn a player
before they get there.
**Cost.** One `SELECT problem_id FROM duels WHERE player IN (...)` per match, and the
bank effectively caps how many duels a regular player gets before repeats begin — 26
problems is under a month for someone playing twice a day. That is a content problem, not
a code one, and it is the argument for continuing to add problems after launch.

## ADR-0047 — AI practice judges real code, and works without an API key
**Decision.** The AI practice screen calls `POST /api/ai/opponent/plan` for a
model-generated opponent timeline, and `POST /api/ai/practice/run` to judge submissions
in the real sandbox. With no `ANTHROPIC_API_KEY`, the endpoint still returns a problem
and a fixed-curve opponent marked `scripted: true`.
**Why the fallback matters.** Practice mode that breaks without an API key is a broken
feature; practice mode with a less-varied opponent is a degraded one. The UI says which
it is rather than quietly pretending.
**Why the plan is generated once, up front.** One model call per practice duel instead of
one per event: bounded cost, no mid-duel latency, and a network blip cannot stall the
opponent mid-timeline.
**Why practice has its own rate limit.** A duel has an opponent waiting, which naturally
paces submissions. Practice has nobody — without a separate limit it would be the
cheapest way to occupy every judge slot on the box.
