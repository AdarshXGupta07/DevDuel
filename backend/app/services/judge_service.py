"""Run a submission against a problem's test cases and produce a verdict."""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Problem, Submission, TestCase
from app.services.sandbox import RunResult, UnsupportedLanguage, docker_available, run_in_sandbox

logger = logging.getLogger(__name__)

VERDICTS = (
    "accepted",
    "wrong_answer",
    "tle",
    "mle",
    "runtime_error",
    "compile_error",
    "system_error",
)

MAX_CODE_BYTES = 100_000


class CodeTooLarge(Exception):
    pass


def normalize_output(text: str) -> str:
    """Compare outputs the way a human would grade them.

    Trailing whitespace on each line and trailing blank lines are ignored; everything
    else is significant. Deliberately strict about internal spacing — "1 2 3" and
    "1  2  3" are different answers, and a problem that cares should say so.
    """
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _verdict_for(result: RunResult, matched: bool) -> str:
    if result.status == "compile_error":
        return "compile_error"
    if result.status == "timeout":
        return "tle"
    if result.status == "oom":
        return "mle"
    if result.status == "output_limit":
        return "wrong_answer"  # a 64KB+ answer is not a correct answer
    if result.status == "system_error":
        return "system_error"
    if result.exit_code != 0:
        return "runtime_error"
    return "accepted" if matched else "wrong_answer"


async def _load_problem(db: AsyncSession, problem_id) -> tuple[Problem, list[TestCase]]:
    problem = await db.get(Problem, problem_id)
    if problem is None:
        raise ValueError(f"Problem {problem_id} not found")
    result = await db.execute(
        select(TestCase).where(TestCase.problem_id == problem.id).order_by(TestCase.ordinal)
    )
    return problem, list(result.scalars())


async def run_submission(
    db: AsyncSession,
    problem_id,
    code: str,
    language: str = "python",
    public_only: bool = False,
) -> dict:
    """Execute `code` against a problem's test cases.

    `public_only=True` is the editor's "Run" button: sample cases only, no database
    write, no effect on the duel. Judging is sequential and stops at the first failure —
    a wrong answer on case 1 tells you everything, and running 20 more containers for a
    submission already known to be wrong is pure cost.
    """
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise CodeTooLarge("Submission exceeds the size limit.")

    problem, cases = await _load_problem(db, problem_id)
    if public_only:
        cases = [c for c in cases if c.is_public]
    if not cases:
        return {
            "verdict": "system_error",
            "tests_passed": 0,
            "tests_total": 0,
            "runtime_ms": 0,
            "stderr": "Problem has no test cases configured.",
            "results": [],
        }

    timeout = (problem.time_limit_ms or int(settings.judge_timeout_seconds * 1000)) / 1000
    passed = 0
    worst_verdict = "accepted"
    total_ms = 0
    stderr_excerpt = ""
    case_results: list[dict] = []

    for case in cases:
        try:
            result = await run_in_sandbox(
                code=code,
                language=language,
                stdin=case.input_data,
                timeout_seconds=timeout,
            )
        except UnsupportedLanguage as e:
            return {
                "verdict": "system_error",
                "tests_passed": 0,
                "tests_total": len(cases),
                "runtime_ms": 0,
                "stderr": str(e),
                "results": [],
            }

        total_ms += result.duration_ms
        matched = normalize_output(result.stdout) == normalize_output(case.expected_output)
        verdict = _verdict_for(result, matched)

        case_results.append(
            {
                "ordinal": case.ordinal,
                "is_public": case.is_public,
                "passed": verdict == "accepted",
                "verdict": verdict,
                "runtime_ms": result.duration_ms,
                # Never leak a hidden case's data back to the player.
                "input": case.input_data if case.is_public else None,
                "expected": case.expected_output if case.is_public else None,
                "got": result.stdout if case.is_public else None,
            }
        )

        if verdict == "accepted":
            passed += 1
            continue

        worst_verdict = verdict
        if not stderr_excerpt:
            stderr_excerpt = result.stderr[:2000]
        break  # fail fast: no point spending containers on a doomed submission

    return {
        "verdict": "accepted" if passed == len(cases) else worst_verdict,
        "tests_passed": passed,
        "tests_total": len(cases),
        "runtime_ms": total_ms,
        "stderr": stderr_excerpt,
        "results": case_results,
    }


async def judge_and_record(
    db: AsyncSession,
    duel_id,
    user_id,
    problem_id,
    code: str,
    language: str = "python",
) -> tuple[Submission, dict]:
    """Judge a real submission and persist it."""
    outcome = await run_submission(db, problem_id, code, language)

    submission = Submission(
        duel_id=duel_id,
        user_id=user_id,
        problem_id=problem_id,
        language=language,
        code=code,
        verdict=outcome["verdict"],
        tests_passed=outcome["tests_passed"],
        tests_total=outcome["tests_total"],
        runtime_ms=outcome["runtime_ms"],
        is_final=True,
        stderr_excerpt=outcome["stderr"] or None,
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return submission, outcome


async def judge_health() -> str:
    """Used by /health/ready. Cheap: asks the daemon its version, runs nothing."""
    try:
        return "ok" if await asyncio.wait_for(docker_available(), timeout=5) else "unavailable"
    except asyncio.TimeoutError:
        return "unavailable"
