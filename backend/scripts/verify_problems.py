"""Run each problem's reference solution against its own test cases, in the real sandbox.

This is the quality gate that stops an unwinnable problem reaching a live duel. A wrong
expected output is invisible until two players both fail a problem nobody can pass, and
by then it has cost someone a ranked match.

    python -m scripts.verify_problems             # all problems
    python -m scripts.verify_problems busiest-window

Requires Docker and the runner images (see docs/judge.md).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.judge_service import normalize_output  # noqa: E402
from app.services.sandbox import run_in_sandbox  # noqa: E402
from scripts.seed_problems import load_files  # noqa: E402

SOLUTION_DIR = Path(__file__).resolve().parents[1] / "problems" / "solutions"


async def verify_problem(data: dict) -> tuple[bool, list[str]]:
    slug = data["slug"]
    solution_path = SOLUTION_DIR / f"{slug}.py"
    if not solution_path.exists():
        return False, [f"no reference solution at problems/solutions/{slug}.py"]

    code = solution_path.read_text(encoding="utf-8")
    failures: list[str] = []

    for ordinal, case in enumerate(data["test_cases"]):
        result = await run_in_sandbox(
            code=code,
            language="python",
            stdin=str(case.get("input", "")),
            timeout_seconds=data.get("time_limit_ms", 5000) / 1000,
        )
        if result.status != "ok" or result.exit_code != 0:
            failures.append(
                f"case {ordinal}: {result.status} (exit {result.exit_code}) "
                f"{result.stderr.strip()[:200]}"
            )
            continue

        got = normalize_output(result.stdout)
        want = normalize_output(str(case.get("output", "")))
        if got != want:
            failures.append(f"case {ordinal}: expected {want!r}, got {got!r}")

    return not failures, failures


async def main() -> int:
    wanted = [a for a in sys.argv[1:] if not a.startswith("-")]
    problems = [p for p in load_files() if not wanted or p["slug"] in wanted]
    if not problems:
        print("no matching problems")
        return 1

    failed = 0
    for data in problems:
        ok, failures = await verify_problem(data)
        if ok:
            print(f"PASS  {data['slug']:<20} {len(data['test_cases'])} cases")
        else:
            failed += 1
            print(f"FAIL  {data['slug']}")
            for failure in failures:
                print(f"        {failure}")

    print(f"\n{len(problems) - failed}/{len(problems)} problems verified.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
