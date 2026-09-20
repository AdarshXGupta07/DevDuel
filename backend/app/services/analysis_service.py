"""Post-duel analysis — shown to both players, win or lose.

The losing player is the one who most needs to know what went wrong, so gating analysis
behind winning (or behind "Keep solving") had it exactly backwards. Every finished duel
now produces this for both participants.

Three layers, in increasing cost:
  1. Always free: the verdict breakdown, timings, and the reference solution.
  2. Free heuristics: cheap static signals about the submitted code.
  3. Paid: the AI review (`ai_service`), which actually reads the code.
"""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Duel, Problem, Submission

VERDICT_EXPLANATIONS = {
    "accepted": "Passed every test.",
    "wrong_answer": "Ran to completion, but produced the wrong output for at least one case.",
    "tle": "Too slow — the time limit was reached before it finished.",
    "mle": "Used more memory than allowed.",
    "runtime_error": "Crashed while running.",
    "compile_error": "Did not compile.",
    "system_error": "The judge failed — this one is on us, not your code.",
}


def _complexity_hints(code: str, language: str) -> list[str]:
    """Cheap static signals. Deliberately conservative.

    These are heuristics on text, not analysis of a program — a hint that is wrong is
    worse than no hint, so anything ambiguous is left out. The AI review is where real
    reasoning about the code happens.
    """
    hints: list[str] = []
    lines = [line for line in code.split("\n") if line.strip()]

    if language == "python":
        # Nested loops at increasing indentation — the classic accidental O(n^2).
        loop_depth, max_depth = 0, 0
        indent_stack: list[int] = []
        for line in lines:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            while indent_stack and indent <= indent_stack[-1]:
                indent_stack.pop()
                loop_depth -= 1
            if re.match(r"(for|while)\b", stripped):
                indent_stack.append(indent)
                loop_depth += 1
                max_depth = max(max_depth, loop_depth)
        if max_depth >= 2:
            hints.append(
                f"{max_depth} nested loops — that is roughly O(n^{max_depth}). "
                "Check whether a hash map or a sorted pass removes the inner one."
            )

        if re.search(r"\bin\s+\w*(list|arr|nums|values|data)\w*\b", code):
            hints.append(
                "Membership test against a list is O(n) each time. A set makes it O(1)."
            )
        if re.search(r"\.sort\(|sorted\(", code) and max_depth >= 1:
            hints.append("Sorting inside a loop repeats O(n log n) work — sort once, outside.")
        if re.search(r"^\s*\w+\s*\+=\s*\[|\.insert\(0,", code, re.M):
            hints.append(
                "Inserting at the front of a list is O(n). `collections.deque` is O(1)."
            )
        if "input()" in code:
            hints.append(
                "`input()` is slow for large inputs — `sys.stdin.read()` reads it in one go."
            )

    return hints


async def build_analysis(db: AsyncSession, duel: Duel, user_id) -> dict:
    """Everything the result screen shows, for one player, after the duel is over."""
    problem = await db.get(Problem, duel.problem_id)

    result = await db.execute(
        select(Submission)
        .where(Submission.duel_id == duel.id, Submission.user_id == user_id)
        .order_by(Submission.submitted_at)
    )
    mine = list(result.scalars())
    best = max(mine, key=lambda s: (s.tests_passed, -s.submitted_at.timestamp()), default=None)

    attempts = [
        {
            "verdict": s.verdict,
            "explanation": VERDICT_EXPLANATIONS.get(s.verdict, ""),
            "tests_passed": s.tests_passed,
            "tests_total": s.tests_total,
            "runtime_ms": s.runtime_ms,
            "language": s.language,
            "at": s.submitted_at.isoformat(),
            "stderr": s.stderr_excerpt,
        }
        for s in mine
    ]

    return {
        "duel_id": str(duel.id),
        "outcome": (
            "draw"
            if duel.winner_id is None
            else "win"
            if str(duel.winner_id) == str(user_id)
            else "loss"
        ),
        "end_reason": duel.end_reason,
        "solved": bool(best and best.verdict == "accepted"),
        "attempts": attempts,
        "attempt_count": len(mine),
        "best": (
            {
                "tests_passed": best.tests_passed,
                "tests_total": best.tests_total,
                "runtime_ms": best.runtime_ms,
                "verdict": best.verdict,
            }
            if best
            else None
        ),
        "hints": _complexity_hints(best.code, best.language) if best else [],
        # The answer key. Only ever reached through a finished-duel check in the route.
        "reference": {
            "solution": (problem.reference_solution or {}) if problem else {},
            "editorial": problem.editorial if problem else None,
            "constraints": problem.constraints if problem else None,
        },
    }
