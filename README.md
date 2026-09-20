# DevDuel

Competitive 1v1 coding duels. Two developers get the same problem at the same time and
race to solve it. Live match state is shared — "opponent ran tests: 3/5 passing" — the
code itself never is, until the duel ends.

**Status:** pre-alpha. The core loop (match → ready → duel → judge → winner → rating)
is built. Not yet built: billing, AI opponent, private rooms, deployment.

---

## Quick start

### Requirements
Python 3.12+, Node 20+, Docker (running, Linux/WSL2 backend), a Postgres database.

### Backend

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r requirements.txt
cp .env.example .env                                 # then fill it in
alembic upgrade head
python -m scripts.seed_problems
uvicorn app.main:app --reload
```

### Judge images (required before any duel can be won)

```bash
docker build -f docker/runner/Dockerfile.python -t devduel-runner:py312 docker/runner
docker build -f docker/runner/Dockerfile.node   -t devduel-runner:node22 docker/runner
```

See [docs/judge.md](docs/judge.md) for verification steps.

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api and /socket.io to :8000
```

---

## Layout

```
backend/
  app/
    core/         security (hashing, JWT), DI dependencies
    db/           SQLAlchemy models, session factory
    routes/       HTTP layer — thin, translates exceptions to status codes
    schemas/      Pydantic request/response shapes
    services/     business rules; knows nothing about HTTP or sockets
    sockets/      Socket.IO handlers (lifecycle, matchmaking, duel)
  docker/runner/  judge images — contain no application code
  problems/       problem bank as YAML + reference solutions
  scripts/        seeding, verification, manual test scripts
  tests/
frontend/         React + Vite + Monaco
docs/             decisions, threat model, judge, production plan
```

Read [docs/decisions.md](docs/decisions.md) before changing anything structural — it
records why things are the way they are, including the parts that look odd.

## Testing

```bash
cd backend
pytest                         # unit tests, no Docker or DB needed
pytest tests/test_sandbox.py   # the attack suite — needs Docker + runner images
```

## Key design points

- **Server-authoritative time.** The server sends `starts_at` / `ends_at` timestamps and
  clients count locally. No tick streams — they are wrong for every client by its own
  network delay and unrecoverable after a refresh.
- **Races are resolved by the database.** Ready-up, duel completion and the free-tier cap
  are all single atomic `UPDATE … WHERE` statements, so exactly one caller can win.
- **Recovery is full resync, not event replay.** `GET /api/duels/{id}` returns everything
  needed to redraw the screen.
- **Untrusted code runs in a container with no network, no writable disk, no inherited
  environment and a hard memory/CPU/pid cap.** See [docs/threat-model.md](docs/threat-model.md).
- **Opponent code is never transmitted during a live duel.** Enforced server-side.
