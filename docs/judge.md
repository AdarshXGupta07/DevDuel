# The judge — build, run, verify

## 1. Build the runner images

The runner images contain **no DevDuel code**. They are generic "run one file" boxes, and
they are pinned so a rebuild in six months produces the same judge.

```bash
docker build -f docker/runner/Dockerfile.python -t devduel-runner:py312 docker/runner
docker build -f docker/runner/Dockerfile.node   -t devduel-runner:node22 docker/runner
```

Verify they exist and run as the right user:

```bash
docker run --rm devduel-runner:py312 python -c "import os; print(os.getuid())"
```

Expected: `10001`. If it prints `0`, the image is running as root and the `USER` line did
not take — stop and fix that before anything else.

## 2. Verify the problem bank

Every problem ships with a reference solution. This runs each one through the real
sandbox against its own test cases, which is what stops an unwinnable problem reaching a
live ranked duel:

```bash
python -m scripts.verify_problems
```

Expected: `PASS` for every problem. A `FAIL` means the expected output in the YAML is
wrong, not that the solution is.

## 3. Run the attack suite

```bash
pytest tests/test_sandbox.py -v
```

Every test must pass, and every test represents something that must **fail** for the
submission. See `docs/threat-model.md` for what each one defends.

Afterwards, confirm nothing was left behind:

```bash
docker ps -a --filter name=devduel-
```

Expected: empty. A lingering container means a timeout path killed the client but not the
container, which is the bug that turns one hostile submission into a permanently pegged
CPU.

## 4. Seed the problems

```bash
python -m scripts.seed_problems --check   # validate the YAML, touch nothing
python -m scripts.seed_problems           # upsert by slug
```

## 5. Adding a problem

1. Write `backend/problems/<slug>.yaml` — at least 3 test cases, at least one `public: true`.
2. Write `backend/problems/solutions/<slug>.py` — a correct reference solution.
3. `python -m scripts.verify_problems <slug>` until it passes.
4. `python -m scripts.seed_problems`.

**Provenance is not optional.** Every problem carries `source` and `license`. Copying a
statement from LeetCode/HackerRank into a paid product is a copyright problem, not a style
one — write originals or use something explicitly licensed, and record which in the file.

## 6. Operational notes

- The judge is the only unbounded cost in the system. `JUDGE_MAX_CONCURRENT` is the
  ceiling; raise it only with a measured reason.
- Judging stops at the first failing test case, so a wrong submission costs one container,
  not twenty.
- `/health/ready` reports the judge as `unavailable` when the Docker daemon is not
  answering. That is the check an uptime monitor should watch, not `/health`.
- On Windows, Docker Desktop must be running **and** on the WSL2/Linux backend. A stalled
  Docker Desktop shows up as CLI commands hanging with no output rather than as an error.
