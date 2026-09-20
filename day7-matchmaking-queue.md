# CodeDuel — Day 7 Brief
**The matchmaking queue**

> Today is the first genuinely stateful, in-memory data structure in the project, and
> the first day you'll have to reason carefully about **race conditions** — two things
> trying to happen at the exact same instant. It's also the day that plants the seed
> for the biggest architectural limitation you'll knowingly accept this month.

---

## Why today matters

Everything through Day 6 either lived in the database (durable, survives a restart) or
was per-connection (one socket's own session). Today you build something new: a **shared**
piece of memory — the queue — that every connected user's socket reads from and writes to.

That's a different category of problem. Two users can try to queue at the *same millisecond*.
A user can disconnect while still technically "in" the queue. And — this is the one to sit
with — this queue only works because you're running **one** server process right now. The
moment you ever ran two, each would have its own separate queue, and users on different
instances could never be matched with each other. You're not fixing that today (that's
Redis, explicitly deferred to "after Day 20" in the plan) — but you need to be able to
name the problem precisely, because it's a very common interview question in disguise.

---

## 1. Concept study — 30 min

**Read/look up:**
1. Queues as a data structure — FIFO specifically, and why "first in, first out" is the
   natural default for "who's waited longest gets matched first."
2. Matchmaking algorithms at a conceptual level: strict FIFO pairing vs. **rating-banded**
   matching, where the acceptable rating gap widens the longer someone waits (so a 1200
   and a 1800 don't get matched instantly, but might after 60 seconds of nobody better
   available).
3. Race conditions, specifically in the context of "two events arriving at nearly the same
   time and both trying to modify the same shared data."
4. What "in-memory state" means for a running Python process, and why restarting the
   process wipes it — connect this back to Day 2's discussion of where different kinds of
   state should live.

**You must be able to answer, unaided:**

1. Two users queue within the same millisecond. Walk through, step by step, what your
   queue's code actually does with each one, in what order. Is the order guaranteed, or
   could it vary?
2. What does "shared mutable state" mean, and why is a plain Python list or dict, being
   read and written by multiple socket event handlers, an example of exactly that?
3. If you ran two copies of your backend server right now (two processes, both handling
   some of the traffic), and User A connects to instance 1 while User B connects to
   instance 2 — could they ever be matched into the same duel with today's design? Explain
   precisely why or why not, at the level of "where does the queue actually live in memory."
4. A user queues, then closes their laptop lid without clicking "cancel." What's supposed
   to happen to their queue entry, and what event tells your server this occurred? (Hint:
   you already built the mechanism for this on Day 6.)
5. State the core invariant you're protecting today, in one sentence: *a user is in at
   most one queue entry and at most one active duel, at any given moment.* What are the
   two or three specific ways a bug could violate this invariant if you're not careful?

If you can't answer #3 precisely, that's worth sitting with — it's the single most useful
thing to be able to explain clearly about this project in an interview.

---

## 2. Design doc — 20 min

Apply the five questions to **matchmaking**, in `NOTES.md`.

1. **What is the actual problem?** No technology names. Something like: "people who want
   to play need to be paired with someone else who also wants to play, without waiting
   forever and without being paired twice."
2. **Inputs, outputs, invariants.** What triggers someone entering the queue? What triggers
   removal? What must never happen — the same user matched into two duels at once, or a
   user vanishing from the queue without ever being told why?
3. **Where does state live, who owns it?** The queue itself — in memory, tied to the
   running server process. What does "owning" the queue actually mean here — which code
   is allowed to add/remove entries?
4. **What breaks it?** Two tabs, same account, both queuing. A queued user disconnecting.
   Two matches trying to claim the same waiting player in the same instant. A user queuing
   while already in an active duel.
5. **Simplest thing that satisfies 1–4?**

Write **ADR-0015** in `docs/decisions.md`: FIFO vs rating-banded matching — which are you
building today, and why? (My steer: start with plain FIFO. Rating-banding is a real
improvement but adds real complexity — expanding search windows, timers — and you can
add it in a focused pass later once basic matching works and is tested. Don't build both
at once.)

---

## 3. Build — 3 hrs

### 3.1 The queue itself — `app/services/matchmaking_service.py`

The simplest correct version: a plain Python data structure (a list, or a dict keyed by
user id — think about which one makes "is this user already queued?" a fast check) living
at **module level**, so it persists across different socket events (which are just function
calls — module-level state is what makes it "shared" across all of them).

Functions you'll need, roughly:
- add a user to the queue
- remove a user from the queue (used by both explicit cancel and disconnect)
- check if a user is already queued
- attempt to find a match (for today: just check if there are 2+ people waiting)

### 3.2 Socket events — `app/sockets/matchmaking.py`

Four events, matching the plan's names:
- `matchmaking:find` — client asks to join the queue
- `matchmaking:cancel` — client asks to leave the queue
- `matchmaking:queued` — **server-to-client**, confirms "you're in the queue now"
- `matchmaking:found` — **server-to-client**, sent to *both* matched players, containing
  a shared duel id

Reuse the session you built on Day 6 (`sio.get_session(sid)`) to know *which user* is
calling `matchmaking:find` — you already have their identity attached to the connection,
no need to ask again.

### 3.3 Socket.IO rooms — grouping the two matched players

Once two users are matched, put both of their connections into a shared **room** — a
Socket.IO concept from the Day 6 brief's concept study, now used for real. Look up
`sio.enter_room(sid, room_name)`. A sensible room name: something derived from the duel id
you generate for the match. This is what lets you later send one event that reaches *both*
players in a duel at once, instead of tracking two `sid`s by hand everywhere.

### 3.4 Handle disconnect removing a queued user

Your Day 6 `disconnect` handler currently just prints. Extend it: if the disconnecting
user was in the queue, remove them. This is where the invariant from concept question 5
actually gets enforced against the "closed the lid" scenario from concept question 4.

---

## 4. Test and verify — 45 min

Same tool as Day 6 — a Python test client script, not curl. Extend yesterday's script or
write a new one.

- [ ] Two different clients call `matchmaking:find` → both eventually receive
      `matchmaking:found` with the **same** duel id.
- [ ] One client queues, then calls `matchmaking:cancel` → never receives `matchmaking:found`,
      even if another client queues afterward.
- [ ] One client queues, then the connection is closed without cancelling (just disconnect
      the test client) → confirm, by some means (a debug print, or a check event), that
      they're no longer in the queue afterward.
- [ ] The same account tries to queue twice (two connections, same user, same token) →
      your invariant should hold. Decide what "holding" means here — second attempt
      rejected? Silently ignored? Replaces the first? Pick one, document it, test it.
- [ ] Three clients queue in quick succession → confirm exactly two get matched together,
      and the third stays waiting (not three-way matched, not two separate incomplete
      matches).

---

## 5. Definition of done

```
backend/
├── app/
│   ├── services/matchmaking_service.py
│   ├── sockets/
│   │   ├── server.py       (disconnect extended to clean up the queue)
│   │   └── matchmaking.py
docs/
└── decisions.md             (+ ADR-0015)
```

---

## 6. Traps to expect

1. **Using a plain list and doing "is user already in it" with a linear search.** Works
   for testing with 3 users; the *shape* of the bug (not the performance) is what matters —
   a dict keyed by user id makes "already queued" a single lookup and naturally prevents
   duplicate entries, which is worth more than the speed today.
2. **Forgetting disconnect cleanup entirely** — a user who closes their tab stays "in" the
   queue forever, silently, until the server restarts.
3. **The race in concept question 1** — if your "check if 2+ people are waiting, then match
   them" logic isn't atomic (all of it happening as one uninterrupted step), two matching
   attempts triggered close together could both grab the same waiting player. Python's
   single-threaded async model actually protects you here *if* you don't `await` anything
   in the middle of the check-and-match logic — but you need to understand *why* that's
   true, not just trust it.
4. **Not testing the two-tabs-same-account case.** It's tempting to skip because it feels
   like an edge case; it's exactly the kind of thing concept question 5 warns about.
5. **Forgetting rooms entirely** and trying to track "who's in this duel" some other way.
   You'll need this exact grouping again on Day 8 for the duel state itself — build the
   habit now.

---

## 7. Bring to review

1. Answers to the five concept questions, especially #3 (multi-instance problem) stated
   precisely.
2. `docs/decisions.md` — ADR-0015.
3. Test results for all five checks in §4 — actual output, not descriptions.
4. `matchmaking_service.py` and `matchmaking.py`.

Opening question: **your queue is a Python dict living in your server process's memory.
I stop your server and start it again. What happened to everyone who was queued, and is
that the behavior you want?**

---

## 8. NOTES.md entry

```
## Day 7 — <date>
**Built:**
**Confused me:**
**Would do differently:**
**Open question for tomorrow:**
```

---

**Tomorrow (Day 8)** is the duel lifecycle as a persisted state machine — the matched
`duel_id` from today gets a real row in the `duels` table, with legal state transitions
enforced. Today's Socket.IO room is what tomorrow's real-time duel events broadcast into.
