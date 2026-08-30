# CodeDuel — Day 2 Brief
**Relational modeling and migrations**

> Mentor mode is on. No code below. `models.py`, the migration, `docs/decisions.md` —
> you write every line. This file tells you what to think about and in what order,
> not what to type.

---

## Why today matters more than most

Get `duels.status` or the players-in-a-duel design wrong today, and you don't find out
today. You find out:
- **Day 8**, when the state machine doesn't fit the column you chose
- **Day 15**, when "exactly one winner" needs an atomic update your schema fights
- **Day 19**, when the history query is an N+1 you can't index your way out of

Schema mistakes are the most expensive mistakes in this whole course, because every table
that references a bad table inherits the bad decision. Slow down today on purpose.

---

## 1. Concept study — 30 min

Coming from Mongo, this is the single biggest mental shift of the month. In Mongo you'd
nest a duel's players inside the duel document. In SQL **you don't nest** — you put things
in separate tables and connect them with keys. That's the whole idea; everything else today
is applying it.

**Read/look up:**
1. Primary key vs foreign key — what each *is*, and what a foreign key actually **enforces**
   at the database level (not just "it's a reference").
2. One-to-many vs many-to-many — and why many-to-many always needs a third table in between.
3. `NULL` — it means "unknown / not yet", and choosing to allow it on a column is a design
   decision, not a formality.
4. Indexes — what they speed up, what they cost (disk, slower writes), and why you don't
   index everything "just in case."

**You must be able to answer, unaided:**
1. If `duels.player1_id` points at `users.id`, and someone tries to insert a duel with a
   `player1_id` that doesn't exist in `users` — what happens, and *where* does it get stopped?
   (Application code, or the database itself?)
2. Why can't you just put "player1" and "player2" as two columns holding full user objects,
   the way you would in Mongo? What's actually being stored in a foreign key column?
3. Give one real example (not from this project) of one-to-many, and one of many-to-many.
   For the many-to-many one, name the junction table.
4. A column is nullable. What does a `NULL` value in it *mean* — unknown? not applicable?
   not yet happened? Why does that distinction matter for code that later reads the column?
5. You put an index on `users.email`. What just got faster, and what (if anything) just got
   slower or more expensive?

If you can't answer #1, don't move to the design step — that's the difference between a
suggestion and a guarantee, and it's the whole reason you're using Postgres instead of Mongo.

---

## 2. Design the schema — ON PAPER — 45 min

**Pen and paper. Not the keyboard, not an ORM, not yet.** Four tables:

`users` · `problems` · `duels` · `submissions`

For each table write down:
- every column, with its type
- which column is the primary key
- which columns are foreign keys, and exactly what table and column they point to
- which columns are required and which allow a missing value

Then draw lines between the tables for the relationships. This is your ER diagram, hand-drawn.

### The six decisions your schema actually has to answer

Don't just list columns — these are the load-bearing calls. Write your answer and your
reasoning for each into `docs/decisions.md` as you go (these become ADR-0004 onward).

**D-1. How do you store the two players in a duel?**
Two columns (`player1_id`, `player2_id`) on `duels`, or a separate `duel_participants` table
with one row per player per duel?
- Two columns: simpler queries, "who's in this duel" is one row read.
- Junction table: extends to 3+ players / tournaments later without a schema change, but
  every query now needs a join, and "exactly 2 players" isn't enforced by the shape alone.

Pick one. Argue both sides in writing before you pick.

**D-2. What are the legal values of `duels.status`?**
Day 8 builds a state machine directly on this column: pending, then ready, then active,
then finished, plus a separate abandoned state. List every state now. Then ask: what stops
someone (a bug, a bad migration, a rushed query) from writing a value that isn't one of
these five? Look at what your database offers for "this column may only be one of a fixed
set of values."

**D-3. Which columns start empty, and how?**
A duel has no winner until it ends, no start time until it starts. For each such column: is
it left unset until it's set, or does it get a default value on creation? What does an
unset/missing value mean *specifically* in that column? Be precise; this is Day 1's
required-config discussion, applied to duels instead of env vars.

**D-4. Where does a user's rating live?**
One column on `users` holding the current number? Or do you also keep a history of every
change? What question can you answer with a history table that you can't answer with just
the current value — and do you need that answer for anything in this course? (Day 15 is
zero-sum rating updates; Day 19 is a leaderboard and history page.)

**D-5. How do you store a problem's test cases?**
A separate `test_cases` table (one row per case), or a JSON column on `problems`? Some test
cases are hidden from players and must never appear in an API response (Day 14's rule).
Which storage shape makes that easy to enforce, and which makes it easy to leak by accident?

**D-6. What does a `submission` row need to point at?**
Which duel, which user, which problem — does it need all three as explicit foreign keys, or
can one be derived through another? What column holds the verdict, and what's the full list
of values it can take? (Look ahead at Day 14's verdict taxonomy: Accepted, Wrong Answer,
Time Limit Exceeded, Memory Limit Exceeded, Runtime Error, Compile Error, System Error —
that list lives here.)

---

## 3. Build — after the paper design is reviewed

Do not start this until you've shown the paper sketch for review. Order:

1. **`app/db/base.py`** — the SQLAlchemy declarative base. One small file, look up the
   SQLAlchemy 2.0 "declarative base" pattern (it changed from 1.x — make sure what you copy
   the *shape* of is 2.0 syntax, not an older tutorial).
2. **`app/db/models.py`** — your four tables as SQLAlchemy model classes, matching the paper
   design exactly. If reality forces a change from the paper, that's fine — but go back and
   update the paper/decisions doc too, don't let them drift apart.
3. **`app/db/session.py`** — the async engine and session factory, pointed at your Supabase
   URL via `settings`. This is the first file that actually uses `config.py` for something
   real.
4. **Alembic init** — run alembic's init command inside `backend/`, then configure `env.py`
   to import your models' metadata and read the DB URL from `settings` (not from
   `alembic.ini` directly — same "one door" rule as Day 1's config).
5. **First migration** — autogenerate it from your models, **read the generated SQL before
   running it**, then apply it to Supabase.

### Which Supabase connection string, again

You already have one in `.env` for the app itself. Alembic migrations are typically better
run over the **direct connection**, not a pooler — poolers can behave oddly with the DDL
statements a migration issues. If you used a pooled connection string on Day 1, this is
worth re-checking now and noting in decisions.md, not silently discovering as an error.

---

## 4. Test and verify — 45 min

- [ ] Migration applies with no errors.
- [ ] Migration reverses cleanly, then re-applies — it's reversible, not just forward-only.
- [ ] Open the Supabase table editor — all four tables exist with the columns you designed.
- [ ] By hand, in the Supabase SQL editor, try to insert a submission row with a duel id
      that doesn't exist. **Confirm it's rejected.** This is D-1's foreign-key guarantee,
      proven, not assumed.
- [ ] Try to insert a duels row with a status value not in your allowed list, if you
      implemented a constraint for D-2. Confirm it's rejected.
- [ ] Insert one valid row per table by hand, referencing each other correctly. Confirm it
      all links up the way your diagram said it would.

---

## 5. Definition of done

```
backend/
├── app/
│   └── db/
│       ├── base.py
│       ├── models.py
│       └── session.py
├── alembic/
│   ├── env.py
│   └── versions/
│       └── (one migration file)
└── alembic.ini
docs/
└── decisions.md      (+ ADR-0004 through ADR-0009, the six D- questions above)
```

Plus: a photographed or described paper ER diagram, migration applies and reverses cleanly,
foreign key and status constraints proven by hand in the SQL editor.

---

## 6. Traps to expect

1. **Alembic can't find your models.** `env.py` needs to import your metadata for
   autogenerate to see anything — a blank migration is the symptom.
2. **Async engine and Alembic friction.** Alembic's autogenerate historically expects a sync
   connection. Look up how SQLAlchemy 2.0 async projects typically structure this — there's
   a standard pattern for it, worth finding rather than guessing at.
3. **Forgetting the difference between a database-side default and a Python-side default.**
   A Python-side default only applies when SQLAlchemy itself inserts the row — it does
   nothing if you insert via raw SQL or another tool. Know which one you're choosing and why.
4. **Enum drift.** If you implement `duels.status` as a database enum type, adding a new
   status later is a migration of its own, and some databases make that awkward. Worth
   knowing now, not discovering on Day 8.
5. **Pooler vs direct connection** for Alembic — see §3 above. Wrong pick shows up as a
   confusing connection error, not an obviously labeled one.
6. **Committing a migration you didn't read.** Autogenerate is a *suggestion*, not a
   guarantee. Read the generated SQL every time before running it — this matters far more
   once migrations start altering tables that already have data, which yours will soon.

---

## 7. Bring to review

1. Photo or description of the paper ER diagram.
2. `docs/decisions.md` — ADR-0004 through ADR-0009 (the six D- questions), with reasoning.
3. Migration up, then down, then up again — paste the output.
4. The by-hand SQL editor test where a bad foreign key or bad status got rejected — paste
   the error Postgres gave you.
5. `models.py` as it stands.

Opening question: **you chose two columns or a junction table for duel players — walk me
through the query you'd write for "show me this user's duel history" under your choice, and
tell me what it costs.**

---

## 8. NOTES.md entry

```
## Day 2 — <date>
**Built:**
**Confused me:**
**Would do differently:**
**Open question for tomorrow:**
```

---

**Tomorrow (Day 3)** is layered architecture and the register endpoint — router, then
service, then ORM, and why you never return a SQLAlchemy model straight out of an API
response. If you finish early today, read (don't write) how a Pydantic schema differs from
a SQLAlchemy model, so Day 3 starts with the concept already loaded.
