# DevDuel — Production Plan

**Owner:** Adarsh Gupta · **Written:** 2026-09-19 · **Status of build:** Day 10 of ~50

This maps the product plan onto the code that actually exists in `D:\DevDuel` today, and
lays out the path from "two sockets can duel" to "strangers pay ₹50/month for this."

---

## 1. Honest state of the build

**What exists and works:** FastAPI + Socket.IO on one ASGI app, Postgres (Supabase) via
async SQLAlchemy + Alembic, register/login/refresh/logout with JWT, `/me` and profile
routes, socket auth at connect time, an in-memory matchmaking queue, a duel state machine
(`pending → ready → active → finished|abandoned`), race-safe ready-up via a single atomic
`UPDATE … WHERE`, and `GET /api/duels/{id}`.

**What does not exist yet:** any frontend, the code sandbox, problems with real test cases,
submissions actually being judged, ranked mode, ELO updates, the daily cap, billing,
anti-cheat, Redis, deployment, CI, and monitoring. Day 10's disconnect/grace-period work is
also still missing from `app/sockets/server.py`.

**The honest read:** you have roughly the auth + realtime skeleton of Phase 1, which is
maybe 20% of Phase 1 and ~8% of the product plan above. That is not a criticism — the
hard-to-retrofit parts (schema, state machine, concurrency correctness) are the ones you
did first, which is the right order. But the plan's Phase 1 milestone ("20–50 real users
dueling") is about 4 weeks of focused work away, not 4 days.

---

## 2. Gap analysis — product plan vs. code

| Product plan calls for | Today | Gap |
|---|---|---|
| Auth + subscription status flag | Auth ✅, subscription ❌ | `users.plan`, `subscriptions` table |
| Matchmaking, rating-based, enforces daily cap | Random pairing in a Python dict | Redis queue, rating buckets, cap check |
| Match engine: live sync, timer, winner | State machine ✅, timer ❌, winner ❌ | `duel:*` event set, server-side timer, win resolution |
| Sandbox | ❌ | Days 11–15 |
| Problem bank, per-language starter code | Tables exist, 1 placeholder row | Content work — see §7 |
| Rating engine (ELO, K=40 then 20) | `users.rating` column only | `rating_history`, ELO service |
| AI opponent | ❌ | Phase 3, scripted version |
| Anti-cheat (paste disable, keystroke log) | ❌ | Frontend + `match_events` ingestion |
| Billing | ❌ | Razorpay + webhooks |
| Leaderboard/profile/history | ❌ | Read APIs + indexes |
| Live opponent status, never opponent code | Rooms exist | Event contract + the rule enforced server-side |

**Design mismatch to fix early:** `duels` has no `mode` column. Casual vs ranked is not a
UI toggle — it changes matchmaking, ELO, anti-cheat strictness, and cap accounting. It must
be on the row from the start.

---

## 3. P0 — fix before building anything new (½ day)

These are real defects in code you already shipped, cheapest to fix now.

1. **`cors_allowed_origins='*'`** in [server.py:6](../backend/app/sockets/server.py:6) — with
   credentialed sockets this is an open door. Drive it from `settings` per environment.
   FastAPI has no CORS middleware at all yet either; the browser frontend will need it.
2. **No refresh-token rotation or reuse detection** —
   [auth_service.py:61](../backend/app/services/auth_service.py:61) issues a new access token
   and leaves the refresh token valid. A stolen refresh token works for 7 days. Rotate on
   every use; on reuse of a rotated token, revoke the whole family.
3. **`refresh_tokens` has no `expires_at`** and stores raw tokens. Store a hash, add an
   expiry column, and add a cleanup job.
4. **`datetime.utcnow()` everywhere** — naive datetimes against Postgres columns that should
   be `timestamptz`. Move to `datetime.now(timezone.utc)` and timezone-aware columns before
   you have data worth migrating. This *will* bite you on timers, the daily cap reset, and
   ELO history.
5. **Dead duplicate `legal_transition`** at the bottom of
   [matchmaking_service.py:36](../backend/app/services/matchmaking_service.py:36) — delete it.
6. **Day 10's disconnect handling** — a duel with a vanished player currently hangs forever.
7. **Missing indexes**: `duels(player1_id, status)`, `duels(player2_id, status)`,
   `submissions(duel_id)`, `refresh_tokens(user_id)`. Every one of these backs a query you
   are about to write constantly.
8. **`get_duel` takes a `str`** and compares against a UUID column — works by asyncpg
   coercion, fails confusingly on malformed input. Validate to `uuid.UUID` at the boundary.
9. **Loose test scripts at `backend/` root** (`test_sockets.py`, `test_ready*.py`,
   `test_matchmaking.py`) — move under `tests/` as real pytest, or delete. They currently
   write junk rows into your production Supabase.
10. **One database for dev and prod.** Split now (a second Supabase project, or local
    Postgres in Docker for dev) before real user data exists.

---

## 4. Schema additions (plan them as one design pass, ship as several migrations)

```
users              + plan ('free'|'paid'), plan_expires_at, ranked_matches_played,
                     is_banned, banned_reason, last_seen_at
subscriptions      NEW: user_id, provider, provider_sub_id, status, current_period_end,
                     amount_paise, created_at, raw_payload (jsonb)
payments           NEW: idempotent ledger of webhook events (provider_event_id UNIQUE)
duels              + mode ('casual'|'ranked'), time_limit_seconds, starts_at, ends_at,
                     end_reason ('solved'|'timeout'|'forfeit'|'disconnect'|'abandoned'),
                     p1_rating_before/after, p2_rating_before/after, language
problems           + slug (unique), tags (text[]), time_limit_ms, memory_limit_mb,
                     starter_code (jsonb: lang -> template), solution_reference,
                     is_active, source, license
test_cases         + ordinal, weight, is_sample  (+ index on problem_id)
submissions        + tests_passed, tests_total, runtime_ms, memory_kb, is_final,
                     stderr_excerpt  (+ index on duel_id, user_id)
ranked_daily_usage NEW: (user_id, usage_date) PK, matches_completed  ← the daily cap
rating_history     NEW: user_id, duel_id, rating_before, rating_after, delta, created_at
match_events       NEW: duel_id, user_id, seq, kind, payload(jsonb), client_ts, server_ts
                        ← keystroke/anti-cheat log; partition or archive from day one
reports            NEW: reporter_id, reported_id, duel_id, reason, status
rooms              NEW: code (unique), host_id, is_private, settings(jsonb)  ← Phase 3
```

**Two calls worth making consciously:**
- **Daily cap as a counter table, not a `COUNT(*)` over duels.** A row per user per day with
  an atomic `INSERT … ON CONFLICT DO UPDATE … WHERE matches_completed < 2 RETURNING` gives
  you the same race-safety you built on Day 9, for free, and survives the "does a forfeit
  count?" rule changing later.
- **`match_events` will be your largest table by 10x.** At ~5 events/sec/player a 15-minute
  ranked duel is ~9,000 rows. 100 duels/day = ~1M rows/day. Batch client-side (flush every
  2s), store compactly, and plan to archive to object storage after 30 days. Decide the
  retention window before you turn logging on, not after Supabase bills you.

---

## 5. The day-by-day plan (Days 11–50)

Same format as your existing briefs — one concept block, one build block, one
verification block per day. Phases map to the roadmap in the product plan.

### Week 3 — The judge (Days 11–17) → *unblocks everything*
- **Day 11** — Docker fundamentals + threat model. (Brief already written:
  [day11-docker-judge-threat-model.md](../day11-docker-judge-threat-model.md))
- **Day 12** — `judge_service.run_submission()`: structured result, verdict mapping
  (`accepted`/`wrong_answer`/`tle`/`mle`/`runtime_error`), exit-code semantics (137 = OOM-kill).
- **Day 13** — Test-case execution: run all cases, compare output (trailing-whitespace and
  float-tolerance rules decided *here*), partial scoring (`tests_passed/tests_total`).
- **Day 14** — Problem bank: schema additions, seed loader from a `problems/*.yaml` folder,
  5 hand-written problems end to end with starter code for Python + JS.
- **Day 15** — `duel:submit` over the socket → judge → `submissions` row → winner resolution
  → atomic `finished` transition. **This is the day a duel becomes winnable.**
- **Day 16** — Concurrency + queueing: a bounded worker pool, max N containers, queue depth
  limits, per-user submission rate limit, backpressure when the judge is saturated.
- **Day 17** — Week 3 review + hardening: run the §5 attack suite from Day 11's brief against
  the *wired-in* judge, not the script.

### Week 4 — Frontend + the playable loop (Days 18–24) → *Phase 1*
- **Day 18** — React + Vite + Monaco editor shell; auth pages against your real API.
- **Day 19** — Socket client: connect with the JWT, the matchmaking screen, queue/cancel.
- **Day 20** — The duel screen: problem pane, editor, run-samples, submit, timer driven by
  `ends_at` (server-authoritative, exactly like Day 9's `starts_at`).
- **Day 21** — Opponent status panel: `typing` / `ran tests: 2/5` / `submitted`. Define the
  event contract and **enforce server-side that opponent code never enters the payload.**
- **Day 22** — Result screen, both solutions revealed after the match, rematch.
- **Day 23** — Reconnect/resync in the browser (Day 10's backend work, finally visible),
  plus the full-duel timer expiry path and the tiebreak rule.
- **Day 24** — Polish + a real end-to-end run: two browsers, two accounts, a complete duel.

### Week 5 — Make it survivable (Days 25–31) → *alpha-ready*
- **Day 25** — Redis: matchmaking queue moves out of process memory; Socket.IO
  `AsyncRedisManager` so more than one server instance can exist at all.
- **Day 26** — Rate limiting + abuse basics; request/socket-event limits per user.
- **Day 27** — Structured logging, request IDs, Sentry, `/health` that actually checks DB +
  Redis + Docker.
- **Day 28** — Containerize the app, `docker-compose` for local (api + postgres + redis),
  environment config split (dev/prod), secrets handling.
- **Day 29** — Deploy: single VPS with Docker (Hetzner/DigitalOcean — you need a real Docker
  daemon for the judge, which rules out most managed PaaS). TLS, domain, nginx.
- **Day 30** — CI: GitHub Actions running pytest + migrations check on every push. Backups
  verified by actually restoring one.
- **Day 31** — Alpha launch to 20–50 users from the communities in the plan. Instrument
  funnel: signup → first duel → second duel (the only retention number that matters now).

### Week 6 — Ranked, ELO, cap, anti-cheat L1 (Days 32–38) → *Phase 2 part 1*
- **Day 32** — `duels.mode`, ranked matchmaking with a widening rating window.
- **Day 33** — ELO service + `rating_history`, K=40 for first 20 matches then 20.
- **Day 34** — Daily cap: `ranked_daily_usage`, atomic claim, UTC/IST reset decision,
  "1 ranked match left today" in the UI.
- **Day 35** — Paste-disable in the ranked editor + large-single-insert detection.
- **Day 36** — `match_events` ingestion: batched keystroke logging, retention policy.
- **Day 37** — Leaderboard + profile + match history (watch the N+1 — this is the Day 2 brief's
  "Day 19" warning coming true).
- **Day 38** — Ranked integrity pass: what happens on disconnect in *ranked* (forfeit +
  rating loss), and the abuse case that creates.

### Week 7 — Money (Days 39–45) → *Phase 2 launch*
- **Day 39** — Razorpay account, subscription plan setup, sandbox keys, UPI Autopay mandate flow.
- **Day 40** — Checkout flow + `subscriptions`/`payments` tables.
- **Day 41** — **Webhooks**: signature verification, idempotency by `provider_event_id`,
  the states you must handle (`authenticated`, `activated`, `charged`, `halted`, `cancelled`).
  Never trust the client's "I paid".
- **Day 42** — Feature gating: one `require_paid` dependency, enforced server-side on every
  paid path; free-tier UI states.
- **Day 43** — Billing edge cases: failed renewal, grace period, cancellation mid-period,
  refunds. Plus the legal pages Razorpay requires (§7).
- **Day 44** — Pricing page, upgrade prompts at the cap wall, payment failure emails.
- **Day 45** — Launch ₹50/month.

### Week 8+ — Phase 3 (Days 46–55)
AI opponent (scripted timing simulation first, per §8 of the product plan — it is a
*simulated event stream*, not an LLM, and should take ~3 days), post-duel analytics,
private rooms, then Phase 4 hardening.

---

## 6. Production-readiness checklist

Nothing here is optional before taking money.

**Security** — CORS locked to your domain · JWT secret from a secret store, rotated ·
refresh rotation + reuse detection · rate limits on auth, submit, and socket events ·
bcrypt cost verified under load · no stack traces to clients · SQL via ORM only (you're
clean) · **sandbox verified against the Day 11 attack suite after wiring, not before** ·
webhook signature verification · dependency scanning · a `SECURITY.md` and an email to
receive reports.

**Correctness** — every state transition covered by a test · the ready-up race and the
daily-cap race tested with concurrent clients · judge determinism (same submission, same
verdict, 100 runs) · timer expiry with both players idle · both players disconnecting.

**Ops** — health checks · structured logs with a duel_id you can grep · Sentry · uptime
monitor · metrics you actually watch (queue depth, judge latency p95, container leak count,
socket count) · automated DB backups **with a tested restore** · a runbook for "judge is
saturated" and "Docker daemon died".

**Data & privacy** — an actual privacy policy (you are logging keystrokes; say so) ·
retention windows · account deletion that really deletes (your `deleteuser` relies on FK
cascades that exist only for `refresh_tokens` — duels and submissions will block it) ·
DPDP Act basics if you have Indian users, which you will.

**Cost control** — the judge is your only unbounded cost. Cap concurrent containers, cap
per-user submissions/minute, and put a hard ceiling on total daily judge-seconds before
someone discovers they can burn your VPS for free.

---

## 7. What I need from you

### 7.1 Decisions (blocking, ~30 min of thinking)
1. **Daily reset:** fixed midnight **IST** or **UTC**? (Recommend IST — your users are there.)
2. **Does a forfeit/disconnect count against the cap?** (Recommend: only completed matches.)
3. **Tiebreak when nobody solves:** highest `tests_passed`, then earliest submission — confirm.
4. **Match duration:** fixed 15 min? Per-difficulty? (Recommend fixed 15 for v1.)
5. **Languages at launch:** Python + JavaScript only? (Strongly recommend exactly these two —
   every extra language is a Docker image, starter code, and a judge edge case.)
6. **Private-room invitees need paid accounts?** (Recommend no — it's your best growth loop.)
7. **Ranked disconnect = loss?** This is ADR-0018 from Day 10, now with money attached.
8. **Do you want a `devduel` rebrand?** The repo says DevDuel, the briefs say CodeDuel. Pick one
   before it's in a database, a domain, and a Razorpay account.

### 7.2 Accounts and access (you must create; I cannot and should not)
- **Razorpay** — needs business KYC (PAN, bank account, and for recurring UPI Autopay,
  usually a registered entity). **Start this on Day 32, not Day 39** — approval takes days to
  weeks and is the single most likely thing to delay your launch.
- **Domain** + DNS.
- **VPS** (Hetzner CX22 ~€4/mo or DigitalOcean $6 — needs to run Docker; that requirement
  rules out Vercel/Render free tiers for the judge).
- **Supabase**: a second project for dev, and a decision on when you need the $25 Pro tier
  (backups + no pausing — you need it before real users).
- **Sentry** (free tier is fine), **Resend/Postmark** for transactional email.
- Give me the **key names** you add to `.env`, never the values — I'll wire config and you
  fill them in.

### 7.3 Content — the thing that will surprise you
**50–100 problems with test cases is weeks of work, and it is a legal question, not just a
writing one.** LeetCode/HackerRank problem statements are copyrighted; scraping them into a
paid product is the kind of risk that ends startups. Your options:
- Write originals (slow, ~1–2 hrs each including test cases — realistically 20 good ones for
  launch, not 100)
- Use openly-licensed sources (Project Euler-style, CC-licensed sets, university course material used
  with permission) — check each license individually
- Generate drafts with an LLM and edit heavily — *you* still own verifying correctness, and
  every problem needs a reference solution plus adversarial test cases

**I can help write problems and test cases at volume once you decide the source policy.**
Give me: 5 problems you consider ideal in tone/difficulty, and your call on the above.

### 7.4 Things only you can answer
- Are you building this solo, and how many hours/day? The plan above assumes ~4 hrs/day and
  lands Phase 2 launch around **mid-November 2026**. Halve the hours, double the calendar.
- Do you have 20–50 people you can actually get into an alpha? If not, that's a Week 4 task
  to start *in parallel*, not a Week 5 afterthought.
- Budget ceiling per month before revenue? (Realistic floor: ~₹2,500/mo — VPS + Supabase Pro
  + domain.)

---

## 8. My honest assessment of the plan itself

**Strong:** the free/paid split is well-reasoned — one ladder with a cap really is a better
upsell than a fenced-off tier. Phase ordering is right. The anti-cheat layering (cheap
prevention first, detection later) is correct engineering judgment.

**Three things I'd push back on:**

1. **₹50/month against this cost structure is thin.** Your marginal cost per user is real
   (judge CPU), unlike most SaaS. 100 subscribers = ₹5,000/mo, which roughly covers a VPS
   and Supabase and nothing else — not your time. ₹50 is fine as a *validation* price; just
   go in knowing it validates willingness-to-pay, not unit economics, and that AI practice
   mode (option 2, LLM-driven) would be loss-making at ₹50 with any real usage.

2. **The AI opponent is listed as your differentiator but sits in Phase 3.** If it's truly
   the differentiator, a scripted version is ~3 days and would make your *alpha* better —
   it also solves the empty-queue problem, which is the thing most likely to kill your first
   50 users. **Consider pulling the scripted bot into Week 4.** A duel site with nobody to
   duel is the single biggest risk in Phase 1, and this is the cheapest fix for it.

3. **"Disable paste" is unenforceable on a web page.** It stops casual cheating, which is
   most of it — keep it. But anyone with devtools bypasses it in 30 seconds, so ranked
   integrity ultimately rests on the behavioral log, not the prevention. Price your
   expectations accordingly, and log from day one as the plan already says.

**The single highest-risk item in the whole plan** is not technical: it's problem content.
Everything else is work you can grind through. That one has a licensing trap in it and it
gates your entire launch.

---

## 9. What happens next

**Executed on 2026-09-19:** §3 (all ten P0 items), §4 (schema pass, one migration), Day 10
(disconnect/grace/forfeit/resync), Days 11–17 (judge, problem bank, winnable duels,
concurrency and rate limits, attack suite) and Days 18–20 (frontend through a complete
duel). See the Day 11 entry in `NOTES.md` for detail.

### Two things you must run yourself before any of it is live

Neither could be verified from the machine this was built on — the database host did not
resolve, and Docker Desktop's CLI stopped responding mid-build.

**1. Apply the migration.** Back up first; it rewrites timestamp columns and drops
`refresh_tokens.token` (everyone gets logged out once, by design):

```bash
cd backend && alembic upgrade head && python -m scripts.seed_problems
```

**2. Build the judge images and prove the box holds:**

```bash
cd backend && docker build -f docker/runner/Dockerfile.python -t devduel-runner:py312 docker/runner && docker build -f docker/runner/Dockerfile.node -t devduel-runner:node22 docker/runner && python -m scripts.verify_problems && pytest tests/test_sandbox.py -v
```

Until `tests/test_sandbox.py` is green, treat the judge as unproven — a sandbox that has
never been attacked is a sandbox whose flags have never been checked.

### Then, in order

1. Day 21–24 polish: two browsers, two accounts, a complete duel end to end.
2. Answer §7.1 — especially the name (DevDuel vs CodeDuel) and the problem-source policy,
   which gate the domain and the content work respectively.
3. Start Razorpay KYC. It is pure waiting, so it should be waiting in the background.
4. Week 5 (Days 25–31): Redis, deploy, alpha.
