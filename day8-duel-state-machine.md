# CodeDuel — Day 8 Brief
**Duel lifecycle as a state machine, persisted**

> Today, the `duel_id` your matchmaking queue generates yesterday becomes a real row
> in the `duels` table — the one you designed all the way back on Day 2. This is the
> day those two pieces of work actually meet, and the day you start reasoning about
> what happens when your server crashes at the worst possible moment.

---

## Why today matters

Right now, a match produces a `duel_id` that exists only in memory, inside a dict, for
the length of one function call. Nothing durable happened. If your server restarted the
instant after two people matched, that match would simply vanish — neither player would
have any record it ever happened.

Today fixes that, and introduces a concept that will recur for the rest of the project:
a **finite state machine (FSM)**. A duel isn't just "a row in a table" — it's a row that
can only move through a specific, limited set of states, in a specific, limited set of
legal orders. Getting this modeled correctly on paper first is what makes Day 9 and
Day 15's harder concurrency problems tractable instead of chaotic.

---

## 1. Concept study — 30 min

**Read/look up:**
1. Finite state machines for domain modeling — states, and the specific *transitions*
   allowed between them. The core idea: not every state can go to every other state.
2. Source of truth: memory vs. database. You already have a working queue that lives only
   in memory (Day 7) — today's job is deciding what about a duel is durable (survives a
   restart) versus what can stay ephemeral.
3. Idempotency — what it means for the *same* event, arriving twice, to not corrupt state.
   Think of a concrete example: what if your "duel finished" logic ran twice for the same
   duel because of a network retry?
4. Database transactions and atomicity — a group of writes that either **all** happen or
   **none** happen. You've used this term loosely all month ("transactional DDL" in
   Alembic); today you use it deliberately, in your own service code.

**You must be able to answer, unaided:**

1. Draw the full state diagram for a duel — every state, and every arrow between states
   that's actually legal. (You don't need FSM notation — boxes and arrows on paper is
   fine.) What are ALL the states? (Hint: check your Day 2 schema — you already decided
   this once; does it hold up now that you're implementing it for real?)
2. What's the difference between checking "is this transition legal" in your Python
   service code versus enforcing it at the database level? Can you have both? Should you?
3. Your server crashes at the exact instant between "two players matched in memory" and
   "the duel row got written to Postgres." What does each player's client see? Is that
   acceptable, or does it need fixing — and if it needs fixing, roughly what would the fix
   look like (you don't have to build it today)?
4. What does "idempotent" mean for a transition like `pending → active`? If the same
   "start the duel" instruction somehow got processed twice, what should happen the second
   time — and what would happen with a naive, non-idempotent implementation?
5. Why does every transition need to go through **one** service function, rather than
   letting different parts of your code update `duels.status` directly wherever convenient?

If you can't draw #1 confidently, stop and draw it before writing any code — literally
every other question and the entire build today depends on having this right first.

---

## 2. Design doc — 20 min

Apply the five questions to **duel state**, in `NOTES.md`.

1. **What is the actual problem?** No technology names. Something like: "a match between
   two people needs to progress through a fixed sequence of stages, and it must be
   impossible for it to skip stages or go backwards."
2. **Inputs, outputs, invariants.** What triggers each transition? What must be true before
   a transition is allowed (e.g., can't go `pending → active` without both players present)?
   What must **never** happen — `finished → active`, a duel with no `problem_id` becoming
   `active`, two different transitions racing to change the same duel at once?
3. **Where does state live, who owns it?** The duel's *status* — fully in the database now,
   or does anything about it still need to live in memory (e.g., the Socket.IO room from
   Day 7)? Which one is the *source of truth* if they ever disagree?
4. **What breaks it?** Server crash mid-transition. The same transition instruction arriving
   twice. Two different transitions for the same duel arriving at nearly the same time.
5. **Simplest thing that satisfies 1–4?**

Write **ADR-0016**: your final state list and the legal transitions between them — this
should mostly just be your Day 8 diagram from concept question 1, written down properly
alongside the two ADRs (duel players, rating storage) you already owe from Day 2.

---

## 3. Build — 3 hrs

### 3.1 Confirm your states match reality

Your Day 2 schema already has `duels.status` with a comment listing:
`pending | ready | active | finished | abandoned`

Check this against your Day 8 diagram. If they disagree, the diagram wins — update the
column comment (and, if the *set* of values changed, that's a migration).

### 3.2 `app/services/duel_service.py` — the one gate all transitions pass through

This is today's core file. Every legal transition gets its own function, but they should
share a common shape:
- Look up the duel row
- Check the **current** status is one that's allowed to move to the **requested** status
  (this is where your diagram from concept question 1 becomes actual `if` logic)
- If illegal: raise a clear exception (same pattern as every service function all month)
- If legal: update the status, write it, commit — inside one transaction

Look up SQLAlchemy's session `commit`/`rollback` behavior if you're fuzzy on what
"transaction" means concretely in your async session — you've been calling `db.commit()`
all month without necessarily having named what it's doing.

### 3.3 Connect matchmaking to persistence

Right now, `try_match()` (Day 7) only builds a dict in memory. Extend the matchmaking
socket handler: once a match is found, **before** emitting `matchmaking:found`, create the
actual `duels` row (via your new service, or directly — your call, but be deliberate) with
status `pending`, both player ids, and a `problem_id`. You don't have real problem selection
logic yet (that's Day 14) — for today, hardcode or randomly pick from whatever's in your
`problems` table, even if it's empty and you have to seed one row by hand first.

The `duel_id` you emit to both clients should now be the **real** primary key of a real row,
not just a random UUID that happens to also be used as a room name.

### 3.4 A route to check current state

`GET /api/duels/{id}` — returns the current state of a duel. Useful for testing today, and
it's also explicitly needed later (Day 10's reconnect/resync). Protect it with
`get_current_user`, same as every other route this month — though today you don't need to
enforce that only the two participants can view it; that's worth thinking about but not
blocking today's build.

---

## 4. Test and verify — 45 min

- [ ] Match two users (reuse/extend Day 7's test client) → query the `duels` table directly
      (same technique as every SQL verification this month) → confirm a real row exists,
      with the correct two player ids and status `pending`.
- [ ] Attempt an illegal transition directly, by calling your service function with a duel
      that's already `finished`, asking to move it to `active` → confirm it's rejected, and
      confirm *why* it was rejected is clear from the error.
- [ ] Restart your server process entirely, mid-way through — after a duel row exists but
      before any further transitions happen. Query the database again. Confirm the row and
      its status survived the restart untouched. (This is intentionally the easiest possible
      version of concept question 3 — full crash-recovery logic isn't today's job, just
      proving the *data itself* is durable.)
- [ ] Call the same legal transition twice in a row (e.g., `pending → ready` twice) →
      decide what should happen (second call rejected because it's no longer `pending`? or
      silently a no-op?) and confirm your code actually does what you decided.

---

## 5. Definition of done

```
backend/
├── app/
│   ├── services/duel_service.py
│   ├── sockets/matchmaking.py     (writes a real duel row on match)
│   └── routers/duels.py           (GET /api/duels/{id})
docs/
└── decisions.md                    (+ ADR-0016, plus the still-owed Day 2 ADRs)
```

---

## 6. Traps to expect

1. **Updating `duels.status` from more than one place.** The instant a second code path
   writes to this column directly, you've lost your single point of validation — the whole
   reason `duel_service.py` exists is that it's the *only* door.
2. **Trusting the in-memory match result as if it were already durable.** Yesterday's
   `try_match()` returning a dict is not the same as a duel existing — until the database
   write succeeds, as far as your system's source of truth is concerned, nothing happened.
3. **Not deciding what happens on a repeated/duplicate transition request** (concept
   question 4) until a bug forces the question. Decide now, deliberately.
4. **Forgetting `problem_id` needs *something* real.** You don't have Day 14's problem
   selection yet — but a duel row with a `problem_id` pointing at nothing, or left null when
   your schema says it's required, will bite you immediately.
5. **Skipping the crash-restart test** because it feels like overkill for one day. It's the
   cheapest possible version of a question that gets much harder on Day 10 — worth building
   the habit now.

---

## 7. Bring to review

1. Your state diagram, photographed or described.
2. `docs/decisions.md` — ADR-0016, and the Day 2 ADRs if you've written them by now.
3. The illegal-transition rejection — actual error output, not a description.
4. The restart-survival test — what you did, what you saw in the database before and after.

Opening question: **walk me through exactly what would need to be true for `duels.status`
to ever incorrectly show `finished → active` — and what specifically in your code today
prevents that from being possible.**

---

## 8. NOTES.md entry

```
## Day 8 — <date>
**Built:**
**Confused me:**
**Would do differently:**
**Open question for tomorrow:**
```

---

**Tomorrow (Day 9)** is ready-up and the server-driven countdown — the hardest concurrency
problem so far: both players clicking "ready" in the same millisecond, and proving your
`duel:start` event can only ever fire once. Today's state machine is exactly what makes
that provable tomorrow, instead of just "probably fine."
