# CodeDuel — Day 9 Brief
**Ready-up, countdown, and race conditions**

> This is the hardest day of the project so far. Not the most code — the least
> forgiving logic. Today's entire job is proving that one specific event can only
> ever fire exactly once, no matter how badly timed two players' clicks are.

---

## Why today matters

Every race condition you've handled so far (Day 7's matchmaking, Day 8's transitions)
had a fairly generous safety margin — you were mostly protected by "nothing in this
function awaits anything, so nothing can interleave." Today you build the first place
where that safety margin is genuinely thin: **two different players, on two different
connections, both saying "I'm ready" at nearly the same instant** — and your job is to
guarantee the duel starts exactly once, not zero times, not twice.

This is also the day server-authoritative timing stops being a slogan and becomes a real
design decision with a real, wrong-seeming-but-correct answer.

---

## 1. Concept study — 30 min

**Read/look up:**
1. Race conditions, specifically the **check-then-act** pattern: you check something is
   true, then — separately — you act on it being true. The bug lives in the gap between
   those two steps.
2. Locks — a mechanism for saying "only one piece of code may be in this section at a
   time." Understand the *idea*, even if you don't reach for Python's actual `asyncio.Lock`
   today.
3. Atomic database updates — an update that includes its own condition, so the database
   itself guarantees only one caller can "win," instead of your Python code checking first
   and updating second.
4. Optimistic concurrency / version columns — a different strategy: let multiple things
   attempt an update, but attach a version number so a stale attempt is rejected
   afterward, rather than blocked beforehand. You don't need to build this today, just
   understand it exists as an alternative to locking.

**You must be able to answer, unaided:**

1. Write out, in your own words, the exact sequence of steps your code would take if you
   implemented "ready up" as: *check if both players are ready → if yes, start the duel.*
   Now imagine both players' `duel:ready` events get processed by your server within a
   few microseconds of each other. Walk through both executions **interleaved**, step by
   step, and find the exact point where both could see "not both ready yet," both proceed,
   and both then trigger a start.
2. What's the difference between checking "are both ready" in Python (`if p1_ready and
   p2_ready`) versus using a single atomic database `UPDATE ... WHERE ...` that only
   succeeds for one caller? Which one is actually safe against the scenario in question 1?
3. You're told: "this works fine because Python's asyncio is single-threaded, so nothing
   truly runs at the same time." Is that enough to make check-then-act safe here? What
   would have to be true about your code for that claim to actually hold? (Hint: think
   about what happens the moment an `await` appears between the check and the act.)
4. Why should the countdown be driven by a `starts_at` timestamp that the client counts
   down to locally, rather than the server sending a `tick` event every second? What
   breaks with the "server sends ticks" approach the moment there's any network delay?
5. A user refreshes their browser 4 seconds into a 10-second countdown. With the
   `starts_at`-timestamp approach, how does their client know to show "6 seconds left"
   instead of restarting at 10? What has to happen for this to work?

If you can't walk through #1 concretely — actual interleaved steps, not just "it could
be a problem" — stop and work through it on paper before writing code. This is the one
concept the whole day hinges on.

---

## 2. Design doc — 20 min

Apply the five questions to **ready-up and countdown**, in `NOTES.md`.

1. **What is the actual problem?** No technology names. Something like: "two people need
   to both signal they're prepared, and the moment both have, one single, unambiguous
   'start' needs to happen — never zero times, never twice."
2. **Inputs, outputs, invariants.** What triggers `duel:ready`? What must be true before a
   duel can transition to `active` (both ready, and — check your Day 8 state machine —
   which *current* status is required)? What must **never** happen — `duel:start` firing
   twice for the same duel, or firing before both players are actually ready?
3. **Where does state live?** "Is this specific player ready" — new column? A row in a
   separate table? In-memory? Think about which choice makes the atomic-update strategy
   from concept question 2 actually possible.
4. **What breaks it?** Simultaneous ready clicks (the core problem). One client sending
   `duel:ready` twice. A client refreshing mid-countdown. A client's clock being wrong.
5. **Simplest thing that satisfies 1–4?**

Write **ADR-0017**: how you're solving the race from concept question 1 — an atomic
database update, an in-process lock, or something else. State which, and why the
alternative you didn't pick would be worse (or wouldn't work at all with more than one
server instance — tie this back to Day 7's ADR about multi-instance limitations).

---

## 3. Build — 3 hrs

### 3.1 Where does "ready" live?

You need somewhere to track each player's ready state. Two reasonable options — pick one,
write it in the ADR:
- Two boolean columns on `duels` (`player1_ready`, `player2_ready`)
- A computed check against something simpler

Whichever you pick, this is a schema change → new migration, same process as every other
day this month.

### 3.2 `duel:ready` — the socket event, and the actual race fix

The handler needs to:
- Mark the calling player as ready (using their session's `user_id` to know which player
  they are — same pattern as every socket handler so far)
- Determine if **both** are now ready
- If so, transition the duel via `duel_service.py` (Day 8's "one door") to `active` —
  and this transition must be the thing that only succeeds once

**The actual fix for the race**, concretely: your `transition_duel` function from Day 8
already checks the current status before allowing a transition. Look closely at what
happens if two `duel:ready` events both reach the point of calling
`transition_duel(db, duel_id, "active")` for the same duel — walk through what your
Day 8 `legal_transition` function does the *second* time, given the *first* call already
changed the status. Is this already safe, or does it need something more? This is the
crux of today — work it out rather than assuming either answer.

### 3.3 `duel:start` — server-authoritative timing

Once (and only once) the duel transitions to `active`:
- Compute a `starts_at` timestamp — "now plus N seconds" (pick a countdown length, e.g. 5)
- Emit `duel:start` to the room, containing `starts_at` — **not** a countdown number, an
  actual timestamp
- The client is responsible for counting down locally based on that timestamp — you don't
  need to build a frontend today, but write down (in `NOTES.md`) what the client-side
  logic would look like, since Day 18 builds this for real

### 3.4 Handle the double-click case

A client sends `duel:ready` twice (double-click, or a retry). Decide what happens —
idempotent no-op, or does your race-condition fix from 3.2 already handle this for free?
Test it either way.

---

## 4. Test and verify — 45 min

- [ ] Two clients send `duel:ready` as close together as your test script can manage
      (no artificial delay between them) → confirm **exactly one** `duel:start` event
      reaches each client, with the **same** `starts_at` value.
- [ ] One client sends `duel:ready` twice in a row → confirm no double-start, and confirm
      the duel doesn't end up in a broken state.
- [ ] Only one player ready, the other never sends `duel:ready` → confirm no `duel:start`
      ever fires (obviously — but actually test it, don't assume).
- [ ] Directly query the `duels` table after a successful ready-up → confirm `status` is
      `active` and (if you added timing columns) `started_at` is set.
- [ ] Try calling `duel:ready` on a duel that's already `active` → confirm it's rejected
      or ignored cleanly, not crashing.

---

## 5. Definition of done

```
backend/
├── app/
│   ├── db/models.py           (+ ready columns, if you chose that approach)
│   ├── services/duel_service.py (+ ready-up logic, using Day 8's transition_duel)
│   └── sockets/duel.py         (duel:ready, duel:start)
├── alembic/versions/           (+ migration for ready columns)
docs/
└── decisions.md                 (+ ADR-0017)
```

---

## 6. Traps to expect

1. **Trusting "Python is single-threaded" as a blanket safety guarantee**, without
   checking whether an `await` sits between your check and your act. The moment it does,
   the single-threaded guarantee doesn't cover you anymore — another event can run during
   that `await`.
2. **Building the countdown as server-pushed ticks** instead of a `starts_at` timestamp.
   Works fine on your local machine with zero latency; falls apart the moment real network
   delay exists, which is every real deployment.
3. **Not actually testing the simultaneous-ready case** — it's the one thing that's easy
   to convince yourself "probably works" without proof, and it's the entire point of today.
4. **Forgetting the transition-legality check from Day 8 already does most of the work
   here** — today might be less new code than it feels like; the concept is the hard part,
   not the volume of code.
5. **A client sending `duel:ready` for a duel they're not part of.** Not the focus of
   today, but worth a passing thought — same authorization question as always.

---

## 7. Bring to review

1. Answers to the five concept questions — especially #1, walked through step by step.
2. `docs/decisions.md` — ADR-0017.
3. The simultaneous-ready test result — actual output showing exactly one `duel:start`
   per client, same `starts_at`.
4. `duel:ready`/`duel:start` handler code.

Opening question: **two `duel:ready` events for the same duel reach your server at
nearly the same instant. Walk me through, line by line, exactly which line of code is
the one that guarantees only one of them can succeed — and what would happen if that
line didn't exist.**

---

## 8. NOTES.md entry

```
## Day 9 — <date>
**Built:**
**Confused me:**
**Would do differently:**
**Open question for tomorrow:**
```

---

**Tomorrow (Day 10)** is disconnects, reconnects, and resync — what happens when a player
vanishes mid-duel, and how a client that reloads mid-countdown rebuilds its exact correct
state from the server rather than guessing. This closes Week 2's milestone: two humans
reaching a live, crash-tolerant duel.
