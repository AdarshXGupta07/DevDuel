# CodeDuel — Day 11 Brief
**Docker fundamentals and the judge's threat model**

> Week 3 starts here. For ten days the enemy has been *the network* — things being slow,
> out of order, or gone. From today the enemy is **a person who is actively trying to
> hurt you**, and who you have voluntarily agreed to run arbitrary code for.
>
> Mentor mode stays on. No application code below. You write every line.

---

## 0. Before you start — the debt check (15 min, do it first)

This is a week boundary, and you said you wanted a real review at this point. Be honest
about what is actually in the repo versus what you think is:

| Thing | Actual state in `D:\DevDuel` right now |
|---|---|
| `docs/decisions.md` | **Does not exist.** Eleven days of ADRs (0001–0018) referenced but never filed. |
| `NOTES.md` | Filled in for **Day 1–3 only**. Days 4–10 entries missing. |
| Day 10 build | **Not in the code.** `app/sockets/server.py`'s `disconnect` only clears the matchmaking queue; there is no active-duel lookup, no grace timer, no forfeit, no room re-join on reconnect. |
| `app/services/matchmaking_service.py` | Has a **duplicate, dead `legal_transition`** at the bottom that shadows the real one in `duel_service.py`. Uncommitted. |
| Stray test rows | Test users/duels still in Supabase from `test_sockets.py`, `test_ready.py`, `test_ready2.py`, `test_matchmaking.py`. |
| Tests | `tests/test_auth.py` only. The socket tests are loose scripts at `backend/` root, not pytest. |

**Decide now, out loud, and write it in `NOTES.md`:** are you finishing Day 10's build
first, or declaring it deferred with a dated entry? Do not let it silently rot — an
unfinished disconnect handler means a duel that hangs forever, and Week 3 is about to
stack a *judge* on top of duels. Either choice is legitimate; pretending it's done is not.

Recommended: spend the first 60–90 minutes today closing Day 10 (§3.1–3.3 of that brief)
and creating `docs/decisions.md`, then do today's concept and threat-model work. Today's
build is genuinely small in code terms — it is a lot of reading and one Dockerfile.

---

## 1. Why today matters

Everything you have built so far is a system where the inputs are *shapes you chose*: an
email, a password, a `duel_id`, a "ready" click. Pydantic validates them; the worst a bad
one does is a 422.

Starting today, a user hands you **a program** and your server's entire job is to *run it*.
There is no schema that makes arbitrary code safe. The only thing standing between a
hostile submission and your database credentials, your host machine, your other players'
code, and your cloud bill is the **box you put it in** — and how carefully you built that
box.

This is also the first day where "it works" is completely worthless as a success criterion.
A judge that runs correct solutions correctly and *also* lets a submission read your `.env`
is a total failure that passes every happy-path test you would naturally write. Today you
learn to test like an attacker, because today the tests that matter are the ones that must
**fail**.

---

## 2. Concept study — 60 min

Longer than usual on purpose. This is the foundation for Days 12–15.

**Read/look up:**

1. **Image vs. container.** An image is a read-only, layered filesystem plus metadata; a
   container is a *running process* using that image as its root filesystem. Get this
   distinction clean — it is the most common confusion, and it explains why "the container
   died and my file is gone" is expected behaviour, not a bug.
2. **Layers and the build cache.** Every instruction in a `Dockerfile` makes a layer;
   layers are cached and reused by content. Understand *why* the order of your lines
   changes your rebuild time by orders of magnitude.
3. **A container is not a VM.** This is the load-bearing idea of the whole week. A VM has
   its own kernel; a container **shares the host's kernel** and is isolated by three Linux
   kernel features:
   - **namespaces** — what a process can *see* (its own pid tree, mounts, network stack, users)
   - **cgroups** — what a process can *use* (cpu, memory, pids)
   - **capabilities / seccomp** — what a process is *allowed to ask the kernel to do*

   Isolation is therefore a *configuration*, not an automatic property. A default
   `docker run` is far weaker than most people assume.
4. **Threat modeling.** The discipline of asking, before you build: who is the attacker,
   what do they want, what can they reach, and what happens if they get it. Look up
   **STRIDE** (spoofing, tampering, repudiation, information disclosure, denial of service,
   elevation of privilege) as a checklist — you do not need to be rigorous with it, you
   need to be *systematic* instead of imaginative.
5. **Blast radius** and **defense in depth** — two ideas you will design against all week:
   assume one control fails; what is the damage, and what is the *second* control behind it.
6. **Resource exhaustion as an attack.** Infinite loops, fork bombs, memory balloons, disk
   filling, and 10GB of stdout are not exotic — they are the *default* behaviour of a bored
   user with a text box. Denial of service is the attack you will actually receive.
7. **The principle of least privilege**, applied concretely: non-root user, no network,
   read-only filesystem, dropped capabilities, no environment inherited from the host.

**You must be able to answer, unaided:**

1. A container shares the host kernel. Given that, what *specifically* is a "container
   escape", and why is running a container as `root` (the Docker default) meaningfully more
   dangerous than running as an unprivileged user — even though it is "inside a container
   either way"?
2. List, without looking, at least **six distinct things** a malicious submission could
   attempt. For each, name the *single mechanism* that stops it. Make sure your list covers
   network, filesystem, memory, cpu, process count, and time.
3. Your `.env` holds a Supabase connection string with full write access to `users` and
   `duels`. Trace the exact path by which a submission could read it under a naive
   implementation (`docker run -v .:/app python:3.12 python solution.py`), and name every
   flag or decision that breaks that path.
4. What is the difference between a program that runs for 10 seconds and a program that
   never terminates — *from your judge's point of view*? Can you tell them apart? Should
   you try? What does this imply about where the timeout has to be enforced (inside the
   container, outside, or both)?
5. Why is `--network none` the correct default for a code judge, and what *legitimate*
   feature does it cost you?
6. If a submission writes 2GB to stdout, where does that data actually go, and what breaks
   first — the container, your Python process reading the pipe, or your server? This one is
   not solved by any Docker flag. It is yours to handle in code.
7. What is the *trust boundary* in CodeDuel? Draw it: on one side, code you wrote; on the
   other, code a stranger typed. Which of your existing components currently sit on the
   wrong side of it, or straddle it?

If you cannot do #2 with six items and six mechanisms, do not start §4 — the build is
mechanical once the threat model is real, and worthless if it is not.

---

## 3. Threat model and design doc — 45 min

Today's "design doc" is a **threat model**, written in a new `docs/threat-model.md`.

**3.1 — Write the table.** Minimum six rows, one per attack from concept question 2:

| # | Attack | What the attacker gains | Control (specific flag/mechanism) | Second line of defense |
|---|--------|------------------------|-----------------------------------|------------------------|
| 1 | e.g. `while True: pass` | ties up a judge slot forever | … | … |

Include at least: infinite loop, fork bomb, memory balloon, outbound network call, reading
host files and secrets, writing to disk, unbounded stdout, and **reading another player's
submission**.

**3.2 — The five questions**, applied to *running untrusted code*:

1. **What is the actual problem?** No technology names. Something like: "a stranger's
   program must produce an answer, within limits I set, without being able to affect
   anything outside the box I gave it — including other strangers' programs."
2. **Inputs, outputs, invariants.** Input: source text, a language, input data, limits.
   Output: stdout, stderr, exit code, wall time, and *why* it ended (finished / timed out /
   killed). Invariant: no submission can ever affect another submission, the host, or the
   database — and **every container that starts must eventually be gone**. No leaks, no
   orphans.
3. **Where does state live?** What lives in the image (built once, read-only), what lives
   per-run (the code file, the input, `/tmp`), and what is *deliberately absent* (env vars,
   credentials, network, the rest of your source tree).
4. **What breaks it?** Docker daemon not running. Image not built. A container that will
   not die. 50 submissions at once. A submission whose *output* is the attack. A user
   submitting to a duel they are not in.
5. **Simplest thing that satisfies 1–4?**

**3.3 — Write the ADRs:**

- **ADR-0019** — Sandbox technology: Docker containers, versus the alternatives you should
  at least name and reject in one line each (`subprocess` plus `resource` limits; gVisor;
  Firecracker microVMs; a third-party API such as Judge0 or Piston). Say *why* Docker, and
  say honestly what its weakness is (shared kernel).
- **ADR-0020** — Your concrete resource limits, with a number and a *reason* for each:
  wall-clock timeout, memory cap, cpu share, pid limit, output byte cap. "Because it felt
  right" is not a reason; "a correct Python solution to an easy problem runs in under 1s,
  so 5s is 5x headroom" is.
- **ADR-0021** *(optional)* — Language support for v1. One language (Python) or more?

---

## 4. Build — 2.5 hrs

**Nothing today touches your FastAPI app.** Today you build the box and drive it by hand
from a terminal. Day 12 wires it in.

### 4.1 Get Docker running (30 min, possibly more on Windows)

Install Docker Desktop, confirm `docker run --rm hello-world` works, and confirm you are on
the **Linux** container backend (WSL2), not Windows containers. Note in `NOTES.md` how long
this took and anything that bit you — Windows plus WSL2 plus line endings is a real source
of Day-12 confusion later.

### 4.2 The runner image

Create `backend/docker/runner/Dockerfile`. It should be **small and boring**:

- a slim Python base, pinned to a specific version (not `latest` — you want reproducibility)
- a **non-root** user created explicitly, and `USER` switched to it
- a working directory that the non-root user owns
- **no** `COPY` of your application code. The runner image must contain *nothing* of
  CodeDuel. It is a generic "run a Python file" box.
- no meaningful `CMD` — you pass the command at `docker run` time

Build it with an explicit tag, e.g. `codeduel-runner:py312`. Write the build command down;
you will run it again.

### 4.3 Drive it by hand — the flag safari (the real work)

In a scratch directory **outside your repo**, write `solution.py` (prints something correct)
and one deliberately hostile file per attack in your table.

Run each by hand and **record the actual observed behaviour** — exit code, stderr, elapsed
time. Work up from naive to hardened so you *see* each flag do its job:

```bash
docker run --rm -v "$PWD:/box" codeduel-runner:py312 python /box/solution.py
```

Then add, one at a time, understanding each before adding the next: `--network none`,
`--memory` (plus `--memory-swap` — find out why the second one matters, or your memory cap
is a lie), `--cpus`, `--pids-limit`, `--read-only` (plus a `--tmpfs` for scratch space),
`--cap-drop ALL`, `--security-opt no-new-privileges`, a read-only bind mount (`:ro`), and
`--rm`.

The deliverable of this section is a **table in `NOTES.md`: attack → flag → what you
actually saw happen**. Not a paragraph saying you did it.

### 4.4 A throwaway driver script

`backend/scripts/run_in_container.py` — a standalone script (not imported by the app) that
shells out to `docker run` with your full flag set and returns stdout, stderr, exit code,
and elapsed wall time.

Things to get right here, because they *are* the lesson:

- use `asyncio.create_subprocess_exec` with an argument **list**, never a shell string —
  the same non-blocking discipline as Day 3's bcrypt and Day 10's grace timer
- enforce the timeout **outside** the container too (`asyncio.wait_for`), and on timeout
  make sure the container is actually killed, not merely detached from
- cap how many bytes you read from stdout and stderr (concept question 6)
- make "timed out" a distinct, first-class result — not an exception you swallow

Run your whole hostile file set through it and confirm you get a clean structured result for
every single one, including the ones designed to hang.

---

## 5. Test and verify — 45 min

Every one of these must **fail from the submission's point of view** and **succeed from
yours** (a clean, structured, non-hanging result):

- [ ] `while True: pass` → killed at your timeout, reported as a timeout, container gone
      (`docker ps -a` shows nothing lingering)
- [ ] a fork bomb → blocked by `--pids-limit`, host stays responsive
- [ ] `x = "a" * 10**10` → killed by the memory cap, not by your host swapping to death
- [ ] `urllib.request.urlopen("http://example.com")` → fails, no network
- [ ] `open("/etc/passwd").read()`, and an attempt to walk up to your source tree or `.env`
      → cannot reach anything of yours
- [ ] `open("/box/evil.txt", "w")` → read-only filesystem refuses it
- [ ] `print("x" * 10**9)` → your driver returns a truncated result and does not blow up
      your Python process's memory
- [ ] a *correct* solution still runs correctly and fast under the **full** hardened flag
      set — verify this last, so you know the hardening did not break the happy path

Record real output. "I think it worked" is the one thing today cannot accept.

---

## 6. Definition of done

```
backend/
├── docker/
│   └── runner/
│       └── Dockerfile              (new — slim, pinned, non-root, contains no app code)
└── scripts/
    └── run_in_container.py         (new — standalone driver, not wired into the app)
docs/
├── decisions.md                    (created; ADR-0001..0018 backfilled, + ADR-0019/0020[/0021])
└── threat-model.md                 (new — the attack table from §3.1)
NOTES.md                            (Day 4–10 backfilled + Day 11 entry + the flag-safari table)
```

**Deliberately unchanged today:** `app/main.py`, `app/sockets/*`, `app/services/*`,
`app/routes/*`. If you find yourself editing those, you have started Day 12 early.

(If you take the recommendation in §0, `app/sockets/server.py`, `app/sockets/duel.py` and
`app/services/duel_service.py` also change — but as *Day 10's* work, committed separately.)

---

## 7. Traps to expect

1. **Believing a default `docker run` is a sandbox.** It runs as root, with full network, a
   writable filesystem, and no resource limits. Out of the box it is a *convenience*
   feature, not a security one. Every bit of safety today is a flag you typed.
2. **`--memory` without `--memory-swap`.** Find out what happens when swap is left
   unlimited; your memory cap quietly stops being a cap.
3. **Bind-mounting your repo.** `-v "$PWD:/box"` from inside `D:\DevDuel\backend` hands the
   container your source *and your `.env`*. Mount a scratch dir, mount it read-only, and
   mount only the one file it needs.
4. **Timing out the `docker run` process without killing the container.** Killing your local
   `docker run` client can leave the container happily burning cpu. Verify with `docker ps`
   after every timeout test.
5. **Leaked containers.** No `--rm`, and you will have hundreds. Check `docker ps -a`.
6. **Reading a pipe with no bound.** `await proc.communicate()` on 2GB of stdout puts 2GB in
   *your server's* memory. The container behaved; you did not.
7. **Windows line endings.** A `\r` in a file the container executes produces errors that
   look nothing like their cause. Worth knowing before it costs you an hour on Day 12.
8. **Shell string instead of an argument list** in `create_subprocess_exec`. You are about
   to interpolate user-influenced values into a command line for the next two weeks — start
   with the safe habit on day one of it.

---

## 8. Bring to review

1. Answers to concept questions **1, 2, 3 and 6** — 2 and 6 in particular.
2. `docs/threat-model.md` — the table.
3. `docs/decisions.md` — ADR-0019 and ADR-0020, plus the backfilled 0001–0018.
4. Your `Dockerfile`, and a one-line justification for **every** line in it.
5. The §5 results, as actual terminal output.
6. Your `run_in_container.py`, specifically the timeout and output-capping paths.

**Opening question:** *I hand you a one-line Python submission. Walk me through every
boundary it crosses, from the socket event that carries it to the process that executes it,
and tell me at each boundary what is checking it and what would happen if that check were
not there. Then tell me which boundary you trust least.*

---

## 9. NOTES.md entry

```
## Day 11 — <date>
**Built:**
**Confused me:**
**Would do differently:**
**Open question for tomorrow:**
```

---

## 10. System design concepts — the running list (Days 1–11)

Keep this as your review spine. You should be able to give a two-minute answer to each,
using CodeDuel as the worked example.

**Foundations (Days 1–5)**
- Fail-fast configuration, and why a missing env var should crash at boot, not at 3am
- Relational modeling: PK/FK, one-to-many vs many-to-many, what a FK actually *enforces*
- Nullability as a design decision; indexes as a read/write tradeoff
- Layered architecture: route (HTTP) → service (business rules) → model/data, and why the
  service layer must not know what HTTP is
- Stateless authentication: JWT, access vs refresh token split, and revocation being hard
  precisely *because* JWTs are stateless
- Hashing vs encryption; why bcrypt is deliberately slow, and why slow work must leave the
  event loop
- Dependency injection: seams for testing, request-scoped lifetimes

**Realtime and concurrency (Days 6–10)**
- Request/response vs persistent bidirectional connections; when polling is actually fine
- Authentication at *connection* time vs per-message; identity bound to a connection
- Rooms/topics as a fan-out primitive
- In-memory state and the multi-instance problem (your queue dies with the process, and two
  instances have two queues) — the general shape of "you need shared state, i.e. Redis"
- Explicit state machines: legal transitions as data, illegal ones as errors
- Race conditions: check-then-act, the gap created by `await`, and why single-threaded is
  not the same as safe
- Atomic conditional updates (`UPDATE … WHERE`) as a concurrency primitive you already own;
  optimistic concurrency and version columns as the alternative
- Server-authoritative time: send a `starts_at` timestamp, never a countdown number
- Idempotency, and exactly-once being a lie; at-least-once plus safe re-handling as the real
  answer
- Fault tolerance: grace periods, cancellable timers, forfeit rules and their abuse cases
- Recovery: full state resync vs event replay, and why resync is nearly always the right
  first answer

**Security and isolation (Day 11 onward)**
- Trust boundaries, and untrusted input as a first-class design category
- Isolation mechanisms: namespaces, cgroups, capabilities; container is not a VM
- Least privilege, defense in depth, blast radius
- Resource exhaustion and denial of service as the default attack
- Threat modeling as a systematic practice (STRIDE as a checklist)
- Reproducibility: pinned base images, immutable image layers

---

## 11. Review question bank — Days 1 through 11

Answer out loud, no notes, no IDE. Anything you stumble on is your revision list before
Week 3 gets deep.

**Day 1 — Setup, config, fail-fast**
1. Why should the app refuse to boot on a missing env var instead of defaulting?
2. What does ASGI give you that WSGI does not, and why does CodeDuel need it?
3. Why is `app.main:app` run from `backend/` and not the repo root?

**Day 2 — Relational modeling**
4. A `duel` references a `user` that does not exist. Where is that stopped — app or database?
5. Why can you not nest the player objects inside the duel row, Mongo-style? What is actually
   stored in the FK column?
6. `duels.winner_id` is nullable. What does `NULL` mean there, and how must reading code
   treat it?
7. You index `users.email`. What got faster, what got slower?
8. Why is `player1_id != player2_id` a CHECK constraint rather than an `if` in Python?

**Day 3 — Layered architecture**
9. Draw the three layers and say what each may and may not know about.
10. Why does duplicate-email return 409 and not 500 — and *which layer* decides that?
11. bcrypt takes 200ms. Why is that a problem for every *other* connected user, and what
    fixes it?
12. What is `asyncio.to_thread` actually doing?

**Day 4 — JWT and login**
13. What is inside a JWT, and what stops a user editing the payload?
14. Why split access and refresh tokens? What does each one's lifetime buy you?
15. You want to log someone out immediately. Why is that hard with JWTs, and what is your
    answer?
16. What is refresh-token *reuse detection* and what attack does it catch?

**Day 5 — Dependency injection**
17. What does `Depends(get_db)` actually do per request, and when is the session closed?
18. How does DI make `get_current_user` testable without a running server?
19. `get_current_user` raises 401 in three distinct cases. Name them.

**Day 6 — WebSockets and socket auth**
20. When is a persistent connection genuinely necessary, and when is polling fine?
21. Why authenticate in `connect` rather than on every event? What does `save_session` buy
    you?
22. What happens to a client that connects with no token, and where is that decided?
23. What is a room, and why is it the right fan-out primitive for a two-player duel?

**Day 7 — Matchmaking queue**
24. Your queue is a Python dict. Name three distinct things that breaks.
25. Two users hit "find" at the same instant. Walk the interleaving. Where is the risk?
26. What happens to the queue when a user disconnects — and what happens if you forget?
27. What would the Redis version look like, and which specific problem does it solve?

**Day 8 — Duel state machine**
28. Why encode transitions as a dict instead of scattered `if`s?
29. What is the difference between `abandoned` and `finished`, and who sets each?
30. What does the DB-level status CHECK constraint protect that the Python code does not?

**Day 9 — Ready-up and races**
31. Walk the check-then-act failure for two simultaneous `duel:ready` events, step by step.
32. Why is `UPDATE … WHERE status='ready' AND both_ready` safe where `if` plus `update` is
    not?
33. What does `rowcount == 1` actually mean here, and why is it the whole answer?
34. Why `starts_at` and not per-second server ticks? What breaks with ticks?
35. A user refreshes 4 seconds into a 10-second countdown. How does their client show 6?

**Day 10 — Disconnects and resync**
36. Why is full resync simpler *and* more robust than replaying missed events?
37. Opponent disconnects mid-duel: loss, pause, or something else? Defend a choice, then name
    how a player abuses it.
38. What is a grace period protecting against specifically?
39. What must be cancellable, and what happens if you forget to cancel it?
40. Socket.IO reconnects the transport. What does your *server* still need to happen again,
    and why? (Day 6's answer.)
41. The server restarts mid-grace-period. What happens? Is that acceptable today?

**Day 11 — Docker and the threat model**
42. Image vs container, in one sentence each.
43. Container vs VM: what is shared, and what does that imply for your risk?
44. Namespaces vs cgroups vs capabilities — one line each, with an attack each stops.
45. Six attacks, six mechanisms. Go.
46. Trace how a naive `docker run` could leak your Supabase credentials.
47. Where must the timeout be enforced, and why possibly in more than one place?
48. A submission prints 2GB. Which flag saves you? (Trick question — answer it properly.)
49. Why non-root inside the container when it is "already isolated"?
50. Where is CodeDuel's trust boundary today, and which component do you trust least?

---

## 12. What Day 12 looks like (so today's choices are informed)

Day 12 turns §4.4's throwaway script into a real `app/services/judge_service.py`: a
`run_submission(code, language, test_cases)` the app can call, returning a verdict from
Day 2's `submissions.verdict` set (`accepted` / `wrong_answer` / `tle` / `mle` /
`runtime_error` / `compile_error` / `system_error`). Design today's return shape so that
mapping is obvious — if your driver returns "exit code 137, 5.0s elapsed" and you cannot
tell `tle` from `mle` from it, you will feel that tomorrow.
