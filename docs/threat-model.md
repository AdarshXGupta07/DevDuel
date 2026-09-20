# DevDuel — Threat Model

**Scope:** running untrusted code submitted by strangers, plus the account and ranked
systems that code is attached to.
**Last reviewed:** 2026-09-19

The attacker is not hypothetical. It is a user with a text box that you have agreed to
execute, and a ranked ladder they would like to be at the top of.

---

## 1. Trust boundary

```
       TRUSTED                                    UNTRUSTED
  ┌──────────────────────┐                 ┌──────────────────────┐
  │ FastAPI + Socket.IO  │                 │ submission source    │
  │ services, DB session │ ─── writes ───► │ text (arbitrary)     │
  │ .env, Supabase creds │                 │                      │
  └───────────┬──────────┘                 └──────────┬───────────┘
              │                                       │
              │  docker run (no net, no env, ro fs)   │
              └──────────────► ┌─────────────────────▼─────────┐
                               │ container: /box/main.py only  │
                               │ uid 10001, caps dropped       │
                               └───────────────────────────────┘
```

Everything the player sends — code, event payloads, status strings, `duel_id`s — is data,
never instructions. The boundary that matters most is the one in the diagram: the process
holding your database credentials must never be the process running their code.

---

## 2. Attack table

| # | Attack | Gains the attacker | Control | Second line of defense |
|---|---|---|---|---|
| 1 | `while True: pass` | Holds a judge slot forever, denies service | `asyncio.wait_for` + explicit `docker kill` by container name | Concurrency semaphore bounds total damage to N slots |
| 2 | Fork bomb (`os.fork()` loop) | Exhausts host pids, freezes the server | `--pids-limit 64` | `--memory` cap; container is killed with the process tree |
| 3 | Memory balloon (`'a' * 10**10`) | OOM-kills the host, takes down live duels | `--memory 256m` **with `--memory-swap` equal** | Host-level OOM score; judge runs nowhere near the DB |
| 4 | Outbound network (exfiltrate, fetch solution, attack third parties from your IP) | Data exfiltration; your IP in someone's abuse report | `--network none` | Egress firewall on the judge host |
| 5 | Read host files / `.env` / source | Supabase credentials → every user's data | No bind mount of the repo; only a temp dir mounted `:ro`; `--env` allowlist so nothing is inherited | Judge host holds no production secrets |
| 6 | Write to disk (persist a payload, fill the volume) | Persistence between runs; disk exhaustion | `--read-only` + `--tmpfs /tmp:noexec,nosuid,size=16m` | Container is destroyed (`--rm`); temp dir removed in `finally` |
| 7 | Output flood (`print('x' * 10**9)`) | Kills *our* process, not theirs — no Docker flag stops this | Capped read (`judge_max_output_bytes`), then kill the container | Verdict maps to `wrong_answer`, never `accepted` |
| 8 | Privilege escalation inside the container | Root in container → better odds of a kernel escape | `--user 10001:10001`, `--cap-drop ALL`, `--security-opt no-new-privileges`, non-root `USER` in the image | Host is single-purpose and rebuildable |
| 9 | Read another player's submission | Steal the answer mid-duel | Opponent code never leaves the server while `status != 'finished'` (ADR-0028); enforced server-side in `duels.py` and `duel.py` | Submissions are per-duel rows; no cross-duel read path exists |
| 10 | Brute-force hidden test cases by resubmitting | Reverse-engineer the expected outputs | 6 submissions/minute rate limit; hidden case data stripped from every response | `match_events` records the pattern for review |
| 11 | Paste an LLM solution into a ranked duel | Fraudulent rank | Paste blocked (keyboard + context menu) in ranked | Keystroke rhythm log (`match_events`); large-insert flags |
| 12 | Disconnect when losing | Avoid a rating loss | 30s grace then forfeit to the opponent (ADR-0018) | `end_reason='disconnect'` is recorded and reviewable |
| 13 | Two tabs to double-spend the free ranked cap | Unlimited free ranked play | Atomic `ON CONFLICT … WHERE matches_started < limit` claim (ADR-0025) | Cap is in Postgres, so it survives restarts and multiple instances |
| 14 | Stolen refresh token | 7 days of account access | Rotation + reuse detection revokes the family (ADR-0023) | Tokens stored hashed; password change revokes all |
| 15 | Cross-origin socket hijack from a malicious page | Authenticated actions as a logged-in user | Explicit CORS origin list; `*` refused in production (ADR-0022) | Access token is memory-only, never in localStorage |

---

## 3. Known gaps, accepted for now

1. **Kernel escape.** Containers share the host kernel; a kernel exploit defeats every row
   above. Mitigation is blast radius, not prevention: the judge host holds no secrets.
   Revisit gVisor if the product ever justifies it.
2. **Paste-disable is bypassable** with devtools in under a minute. Ranked integrity rests
   on the behavioural log, not on prevention. Do not market it as more than it is.
3. **No automated cheat detection yet** — events are logged, nothing analyses them.
   Deliberate: manual review of reports first, automation once that stops scaling.
4. **Single-instance state.** Queue, presence, rate limits and grace timers are per
   process. Two instances would behave incorrectly, not just inefficiently. Blocks
   horizontal scaling until Day 25.
5. **Judge and API share a host** in the current deployment plan. A container escape would
   therefore reach the API process. Splitting the judge onto its own host is the single
   highest-value hardening step once revenue justifies a second VPS.
6. **Account enumeration** via registration's 409 (ADR-0010).

---

## 4. The attack suite

`backend/tests/test_sandbox.py` encodes rows 1–8 as executable tests. Every one must fail
from the submission's point of view and return a clean structured result from ours. Run it
after any change to `sandbox.py`, the Dockerfiles, or the judge limits:

```bash
pytest tests/test_sandbox.py -v
```

A green happy-path test alone proves nothing here — the tests that matter are the ones
that must fail.
