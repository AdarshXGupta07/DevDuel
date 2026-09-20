# CodeDuel — Day 10 Brief
**Disconnects, reconnects, and resync**

> This closes Week 2's milestone: two humans can get matched and reach a live,
> crash-tolerant duel. Today is about the unglamorous but essential question every
> realtime system has to answer — what happens when the network just... stops.

---

## Why today matters

Every day this week has assumed a connection stays open and everything goes smoothly.
Real networks don't cooperate: phones lock, wifi drops, laptops sleep, tabs get backgrounded.
A duel that can't survive a 10-second network blip isn't a duel system — it's a demo that
only works when you don't actually test it. Today is the day you stop assuming the happy
path and start designing for the network failing, because it will.

---

## 1. Concept study — 30 min

**Read/look up:**
1. Fault tolerance in stateful systems — what it means for a system to keep working
   correctly (or degrade gracefully) when a piece of it fails or disappears.
2. Delivery semantics: **at-most-once**, **at-least-once**, **exactly-once**. Understand
   why "exactly-once" is, in practice, extremely hard to actually guarantee across a
   network — and why most real systems settle for "at-least-once, plus a way to safely
   handle receiving the same thing twice" instead.
3. The distinction between two very different recovery strategies: **replaying missed
   events** (send everything that happened while you were gone, in order) versus **full
   state resync** (throw away what the client thinks it knows, send the complete current
   truth). You're building the second, not the first.
4. Reconnection at the Socket.IO level — you've had automatic reconnection this whole
   time (it's a built-in Socket.IO feature you never had to build), but reconnecting the
   *transport* is different from the *application* knowing what to do once reconnected.

**You must be able to answer, unaided:**

1. Why is "replay every event the client missed" harder to build correctly than "just
   send the complete current state"? Think about what you'd need to track to make replay
   work (ordering, a durable log of every event, handling gaps) versus what you already
   have for resync (Day 8's `GET /api/duels/{id}` already *is* most of the answer).
2. A player's opponent disconnects mid-duel. Is that immediately a loss for the
   disconnecting player, a pause, or something else? Argue at least two of these
   positions, then pick one. What's the obvious way a player could **abuse** whichever
   rule you pick? (e.g., if disconnecting mid-duel is a free pause with no penalty, what
   stops someone from unplugging their router the moment they're about to lose?)
3. What is a **grace period**, and why does one make sense here at all — what real-world
   situation is it specifically protecting against that an instant forfeit wouldn't?
4. A client reconnects mid-countdown (from Day 9). What's the *minimum* information the
   server needs to send back for that client to correctly resume showing the right
   remaining time — and why is `starts_at` (a timestamp) rather than "5 seconds left" (a
   countdown number) exactly the right shape of data for this to work at all?
5. Socket.IO automatically reconnects the underlying transport for you. Does your server
   automatically know this is the "same" user coming back, or does something need to
   happen at `connect` again? (Look back at Day 6 — what does `connect` require every
   single time, even for a returning user?)

If you can't answer #1 concretely, it's worth sitting with — it's the reason today's
build is much smaller than it might sound, because Day 8 already did most of the work.

---

## 2. Design doc — 20 min

Apply the five questions to **disconnect handling**, in `NOTES.md`.

1. **What is the actual problem?** No technology names. Something like: "one player's
   connection can vanish at any moment, and the system needs to behave sensibly — for
   both the disconnecting player and their opponent — without hanging forever."
2. **Inputs, outputs, invariants.** What triggers the grace period? What ends it (early
   reconnect, or timeout)? What must never happen — a duel stuck forever with no
   resolution because one player vanished and never came back?
3. **Where does state live?** The duel's *durable* truth is in Postgres (Day 8). What, if
   anything, needs to live only in memory for this feature — specifically, the running
   grace-period timer itself. What happens to that timer if the server restarts?
   (You don't need to solve server-restart-mid-grace-period today — just be able to name
   that it's a real gap, same spirit as Day 7's multi-instance limitation.)
4. **What breaks it?** A disconnect that's actually just a page refresh (reconnects in
   under a second). A genuine abandonment. Both players disconnecting at once. A
   reconnect arriving *just* as the grace period timer is about to fire — a race, same
   family as Day 9's.
5. **Simplest thing that satisfies 1–4?**

Write **ADR-0018**: your decision on concept question 2 (what disconnect means — loss,
pause, or something else) and the grace period length you're using, with reasoning for
both.

---

## 3. Build — 3 hrs

### 3.1 Detect the disconnect and notify the opponent

Extend your Day 6 `disconnect` handler (it already exists and already cleans up the
matchmaking queue). Now it needs to also check: was this user in an **active duel**? If
so, notify the *other* player in that duel's room.

```python
@sio.on("duel:opponent_disconnect")  # emitted BY your server TO the remaining player
```

You'll need a way to look up "which active duel is this user currently in" — think about
where that lookup comes from (a query against `duels` filtering by player id and status,
most likely).

### 3.2 The grace period

Start a timer when a player disconnects mid-duel. Look up `asyncio.sleep` combined with
`asyncio.create_task` (or `sio.start_background_task`, Socket.IO's own helper for this) —
you need something that waits N seconds *without blocking* everything else on your server
while it waits.

If the timer completes **without** the player reconnecting: resolve the duel per your
ADR-0018 decision (forfeit → transition to `finished` via Day 8's `transition_duel`,
with the remaining player as `winner_id`, or whatever you decided).

If the player **reconnects** before the timer fires: cancel the timer, notify the
opponent the player is back.

### 3.3 Resync on reconnect

This is the part that's smaller than it sounds, per concept question 1. You already have
`GET /api/duels/{id}` from Day 8 — that endpoint, called by a client immediately after
`connect`, already gives it everything it needs to rebuild its view: current status,
both player ids, `winner_id` if finished, timestamps.

The one thing worth adding: when a socket connects (or reconnects), have the client
immediately ask "am I currently in an active duel?" — you could add a small socket event
for this, or lean on the client simply calling the REST endpoint proactively if it knows
a `duel_id` from wherever it stored it (localStorage, in the real frontend later). For
backend purposes today: make sure `GET /api/duels/{id}` returns everything necessary,
and write down (in `NOTES.md`) what the frontend's reconnect flow will look like when you
build it in Week 4.

---

## 4. Test and verify — 45 min

- [ ] Two clients in an active duel. Disconnect one (in your test script, just call
      `.disconnect()`) → confirm the *other* client receives some kind of
      "opponent disconnected" notification.
- [ ] Reconnect the disconnected client **within** the grace period → confirm the duel is
      untouched (still `active`, not resolved), and the opponent gets notified they're
      back.
- [ ] Disconnect a client and **do not** reconnect within the grace period → confirm the
      duel resolves per your ADR-0018 decision — check the database directly for the
      final `status` and `winner_id`.
- [ ] Query `GET /api/duels/{id}` as if freshly reconnecting mid-duel → confirm the
      response alone contains everything a client would need to redraw the correct
      screen (whose turn, what status, timestamps) without any other information.

---

## 5. Definition of done

```
backend/
├── app/
│   ├── services/duel_service.py   (+ forfeit/resolve-on-timeout logic)
│   └── sockets/
│       ├── server.py               (disconnect extended: check for active duel)
│       └── duel.py                 (+ grace period timer, reconnect handling)
docs/
└── decisions.md                     (+ ADR-0018)
```

---

## 6. Traps to expect

1. **Blocking the whole server while "waiting" for the grace period.** A plain
   `time.sleep()` would freeze everything — same async/blocking lesson as Day 3's bcrypt.
   You need something that waits *without* blocking other connections.
2. **Forgetting the grace-period timer needs to be cancellable.** If a player reconnects
   at second 8 of a 10-second grace period, something has to actually stop the pending
   forfeit from firing at second 10 — an uncancelled timer is a ticking bug.
3. **Treating "replay missed events" as the goal**, per concept question 1, when full
   resync is both simpler and more robust. Don't build an event log/replay system today —
   that's real added complexity for a benefit you don't need yet.
4. **Not testing the "reconnect just barely in time" race** — same family of race as
   Day 9, worth at least thinking through even if you don't build an elaborate test for
   the exact millisecond boundary.
5. **A disconnect during matchmaking (Day 7) getting confused with a disconnect during an
   active duel (today).** They need different handling — make sure your `disconnect`
   handler checks which situation it actually is.

---

## 7. Bring to review

1. Answers to the five concept questions, especially #1 and #2.
2. `docs/decisions.md` — ADR-0018.
3. The four test results from §4 — actual output.
4. Your grace-period timer code, and how it gets cancelled on reconnect.

Opening question: **a player's connection drops for exactly 3 seconds during a 10-second
grace period, then reconnects. Walk me through, step by step, every piece of state that
has to be correctly restored on both that player's screen and their opponent's — and
where each piece of information actually comes from.**

---

## 8. NOTES.md entry

```
## Day 10 — <date>
**Built:**
**Confused me:**
**Would do differently:**
**Open question for tomorrow:**
```

---

## Week 2 milestone

If today closes clean: two humans can get matched, ready up, reach a live duel, and
survive a real network interruption without the system breaking. That's the plan's
explicit Week 2 milestone — and the point where you said you wanted a full review and
evaluation session covering everything from Day 1 through today, before moving into
Week 3's judge and sandboxing work.

**Before that review**, the accumulated debt is worth actually clearing, not carrying
into Week 3:
- `docs/decisions.md` — ten days of ADRs, several referenced in reviews but never filed
- `NOTES.md` — check which daily entries are actually filled in vs. skipped
- The stray test data scattered across your Supabase `users`/`duels` tables from a
  week and a half of test scripts

**Day 11** starts Week 3 — Docker fundamentals and the judge's threat model. Different
kind of problem entirely: not concurrency anymore, but security, for the first time.
