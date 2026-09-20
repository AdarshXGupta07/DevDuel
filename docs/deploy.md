# Deploying DevDuel

**Target:** one VPS running Docker, Postgres managed by Supabase, nginx terminating TLS.

**Why a VPS and not Vercel/Render/Railway:** the judge needs a real Docker daemon it can
start containers on. Managed PaaS platforms don't give you one. This requirement drives
the whole hosting decision.

---

## 1. What to provision

| Thing | Spec | ~Cost |
|---|---|---|
| VPS | Hetzner CX22 (2 vCPU, 4GB) or DigitalOcean 2GB | €4 / $12 per month |
| Database | Supabase Pro | $25/mo — **needed before real users**: the free tier pauses after a week idle and has no usable backups |
| Domain + DNS | any registrar | ~₹800/yr |
| Sentry | free tier | ₹0 |

4GB RAM is the floor: the API, four runner images, and concurrent judge containers
(256MB each, 512MB for Java) add up faster than you would guess.

## 2. First-time server setup

```bash
# On the VPS, as root
apt update && apt install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx git
adduser --disabled-password --gecos "" devduel
usermod -aG docker devduel
```

Then as `devduel`:

```bash
git clone <your repo> ~/devduel && cd ~/devduel
cp backend/.env.example backend/.env    # fill it in — see §3
```

Build the runner images once (they are not part of the API image):

```bash
cd backend
docker build -f docker/runner/Dockerfile.python -t devduel-runner:py312 docker/runner
docker build -f docker/runner/Dockerfile.node   -t devduel-runner:node22 docker/runner
docker build -f docker/runner/Dockerfile.cpp    -t devduel-runner:cpp13 docker/runner
docker build -f docker/runner/Dockerfile.java   -t devduel-runner:java21 docker/runner
```

## 3. Production environment

Everything in `backend/.env.example`, with these **not** left at their defaults:

```
APP_ENV=production
JWT_SECRET=<openssl rand -hex 32>          # never the dev value
SUPABASE_URL=<Supabase pooler URI, +asyncpg>
CORS_ORIGINS=https://devduel.app           # your domain only; '*' refuses to boot
ANTHROPIC_API_KEY=<real key>
RAZORPAY_KEY_ID=rzp_live_...               # test keys refuse to boot in production
RAZORPAY_WEBHOOK_SECRET=<strong random>
```

Three of these are enforced at startup rather than trusted (ADR-0002): `*` in
`CORS_ORIGINS`, `rzp_test_` keys, and billing enabled without a webhook secret each
refuse to boot when `APP_ENV=production`.

**Use the Supabase connection pooler**, not `db.<ref>.supabase.co`. The direct host is
IPv6-only and resolves inconsistently on hosts without IPv6 — which cost hours of
debugging during development. The pooler URI is under Project Settings → Database.

## 4. Deploy

```bash
cd ~/devduel && git pull
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d
docker compose logs -f api
```

Migrations run as a separate step on purpose. Running them at container start means N
instances race each other, and a failed migration takes the app down with it instead of
just failing loudly.

Serve the frontend as static files:

```bash
cd frontend && npm ci && npm run build   # then point nginx at frontend/dist
```

## 5. nginx

```nginx
server {
    server_name devduel.app;

    root /home/devduel/devduel/frontend/dist;
    index index.html;

    # SPA routing: /profile, /duel/<id> etc. are client-side routes.
    location / { try_files $uri $uri/ /index.html; }

    location ~ ^/(api|auth|health) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # The judge can take ~60s on a slow C++ submission with many test cases.
        proxy_read_timeout 120s;
    }

    # WebSockets need the upgrade headers, and a long read timeout — a duel holds an
    # idle-ish socket open for 15 minutes.
    location /socket.io/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }
}
```

Then `certbot --nginx -d devduel.app` for TLS.

## 6. Before you take real money

- [ ] `pytest` green, including `tests/test_sandbox.py` with `DEVDUEL_REQUIRE_DOCKER=1`
- [ ] `python -m scripts.verify_problems` — every problem solvable
- [ ] `/health/ready` reports `database: ok` and `judge: ok`
- [ ] A **restore** tested from a Supabase backup, not just a backup taken
- [ ] Sentry receiving errors (deliberately raise one and check it arrives)
- [ ] Uptime monitor on `/health/ready`, not `/health`
- [ ] Razorpay webhook pointed at `https://<domain>/api/billing/webhook`, and a test
      event delivered **and** replayed (the replay must be a no-op)
- [ ] Terms, Privacy Policy and Refund Policy published — Razorpay requires them, and the
      privacy policy must disclose keystroke logging
- [ ] `docker ps -a --filter name=devduel-` is empty after a load test

## 7. Hardening, in priority order

1. **Split the judge onto its own host.** Today the API container mounts the host Docker
   socket, which is root-equivalent on that host. A container escape therefore reaches
   the API process and its environment. This is the single highest-value hardening step
   and the reason `docs/threat-model.md` lists it as an accepted gap rather than a solved
   problem.
2. **A firewall** (`ufw allow 22,80,443`) — Postgres and Redis must not be exposed.
3. **Cap total judge spend**: `JUDGE_MAX_CONCURRENT` bounds parallelism, but nothing yet
   bounds judge-seconds per day. That is the one unbounded cost in the system.
4. **Redis** (Day 25) before a second instance. Two instances today would be *incorrect*,
   not merely uncoordinated: two matchmaking queues, split presence, and grace timers
   that only exist on one of them.
5. **Log rotation** — `match_events` and container logs both grow without bound.

## 8. Rollback

```bash
git checkout <previous-sha>
docker compose build api && docker compose up -d
```

Migrations are **not** auto-reverted. Every migration in this project has a `downgrade()`,
but run one deliberately (`alembic downgrade -1`) only after checking what it drops —
`c1a2d3e4f501` deletes refresh tokens, and `downgrade` will not bring them back.
