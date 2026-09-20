"""AI features: post-duel code review, and the AI opponent's pacing.

Uses the official Anthropic SDK with `claude-opus-5`. Everything here is gated on
`settings.anthropic_api_key` — with no key the service reports itself disabled and the
API says so, rather than failing at call time inside a duel.

Two cost decisions worth knowing about:

1. **Reviews are stored on the submission** (`submissions.ai_review`). A review is
   deterministic-enough and a player will reopen a result screen repeatedly; paying for
   the same review twice is pure waste.
2. **The instructions are prompt-cached.** The system prompt and rubric are identical on
   every call, so marking them `ephemeral` means we pay ~0.1x for that prefix after the
   first request in a window.
"""

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Problem, Submission

logger = logging.getLogger(__name__)

_client = None


class AIDisabled(Exception):
    pass


class AIError(Exception):
    pass


def ai_enabled() -> bool:
    return settings.ai_enabled


def _get_client():
    """Lazily build the async client so importing this module never needs a key."""
    global _client
    if not settings.ai_enabled:
        raise AIDisabled("AI features are not configured on this server.")
    if _client is None:
        from anthropic import AsyncAnthropic

        _client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.ai_timeout_seconds,
            max_retries=2,
        )
    return _client


# --------------------------------------------------------------------- schemas


class ReviewIssue(BaseModel):
    title: str = Field(description="Short label for the problem, under 8 words.")
    detail: str = Field(description="What is wrong and why it matters, 1-3 sentences.")


class CodeReview(BaseModel):
    """The shape the result screen renders. Structured output means the frontend never
    has to parse prose, and a malformed response fails loudly instead of rendering junk."""

    verdict: str = Field(description="One-line summary judgement of the solution.")
    time_complexity: str = Field(description="Big-O of the submitted solution, e.g. O(n log n).")
    optimal_complexity: str = Field(description="Big-O of the best practical approach.")
    strengths: list[str] = Field(description="1-3 specific things done well.")
    issues: list[ReviewIssue] = Field(description="0-3 concrete improvements, most important first.")
    alternative: str = Field(description="A better or alternative approach as a short code snippet.")
    alternative_note: str = Field(description="One sentence on why the alternative is better.")


class OpponentStep(BaseModel):
    at_seconds: int = Field(description="Seconds from duel start when this happens.")
    state: Literal["typing", "running", "submitting", "ran_tests", "solved"]
    passed: int | None = Field(default=None, description="Tests passing, when state is ran_tests.")
    total: int | None = Field(default=None, description="Total tests, when state is ran_tests.")


class OpponentPlan(BaseModel):
    solve_seconds: int = Field(description="When the opponent finally solves it, or 0 if never.")
    steps: list[OpponentStep] = Field(description="Ordered timeline, 5-12 steps.")


# ----------------------------------------------------------------- code review

REVIEW_SYSTEM = """You review competitive-programming solutions for DevDuel, a 1v1 \
coding-duel site. Your reader just finished a timed duel and wants to get better.

How to review:
- Be specific to THIS code. Never give generic advice that would fit any submission.
- Lead with what is actually wrong, ranked by how much it matters. Correctness first, \
then complexity, then readability.
- If the solution is already optimal, say so plainly and do not invent issues.
- Judge complexity against the stated constraints, not in the abstract.
- Keep the alternative snippet short — the idea, not a full program.
- Write plainly. No praise padding, no "great job!", no exclamation marks."""


async def review_submission(db: AsyncSession, submission: Submission) -> dict:
    """Generate (or return the stored) AI review for one submission."""
    if submission.ai_review:
        return submission.ai_review

    client = _get_client()
    problem = await db.get(Problem, submission.problem_id)
    if problem is None:
        raise AIError("Problem not found for this submission.")

    outcome = (
        f"verdict={submission.verdict}, "
        f"tests={submission.tests_passed}/{submission.tests_total}, "
        f"runtime={submission.runtime_ms}ms"
    )

    try:
        response = await client.messages.parse(
            model=settings.ai_model,
            max_tokens=settings.ai_max_tokens,
            output_config={"effort": settings.ai_effort},
            system=[
                {
                    "type": "text",
                    "text": REVIEW_SYSTEM,
                    # Identical on every call — cache it and pay ~0.1x after the first.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"# Problem: {problem.title} ({problem.difficulty})\n\n"
                        f"{problem.question}\n\n"
                        f"## Constraints\n{problem.constraints or 'None stated.'}\n\n"
                        f"## Judge outcome\n{outcome}\n\n"
                        f"## Submission ({submission.language})\n"
                        f"```\n{submission.code[:20000]}\n```\n\n"
                        "Review this solution."
                    ),
                }
            ],
            output_format=CodeReview,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("AI review failed for submission %s", submission.id)
        raise AIError(f"Review could not be generated: {type(e).__name__}") from e

    review = response.parsed_output.model_dump()
    review["generated_by"] = settings.ai_model

    submission.ai_review = review
    await db.commit()
    return review


# --------------------------------------------------------------- ai opponent

OPPONENT_SYSTEM = """You script a believable opponent for a coding-duel practice mode.

You are NOT solving the problem. You are producing a timeline of what a human \
programmer at a given skill rating would plausibly *look like* solving it — when they \
type, when they run tests, how often they submit something wrong first, and when (or \
whether) they finish.

Calibration:
- rating 1000-1199: often fails to solve a medium problem in time; 2-3 wrong submissions.
- rating 1200-1499: solves easy comfortably, medium sometimes; 1-2 wrong submissions.
- rating 1500-1799: solves medium reliably in half the time; usually 1 wrong submission.
- rating 1800+: solves fast and usually first-try.

Make the pacing uneven — real people pause, re-read, and backtrack. Never produce a \
perfectly regular timeline."""


async def opponent_plan(problem: Problem, rating: int, time_limit_seconds: int) -> dict:
    """Ask the model for a realistic opponent timeline at a given rating.

    The AI opponent never runs code and never sees the player's code. It performs a
    plausible timeline — which is the scripted approach from the product plan, made a
    bit less repetitive by generating it per problem instead of replaying one curve.
    """
    client = _get_client()

    try:
        response = await client.messages.parse(
            model=settings.ai_model,
            max_tokens=2000,
            output_config={"effort": "low"},  # scheduling, not reasoning
            system=[
                {
                    "type": "text",
                    "text": OPPONENT_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Problem: {problem.title} ({problem.difficulty})\n"
                        f"Opponent rating: {rating}\n"
                        f"Duel length: {time_limit_seconds} seconds\n\n"
                        "Produce the opponent's timeline. Every at_seconds must be "
                        f"between 0 and {time_limit_seconds}."
                    ),
                }
            ],
            output_format=OpponentPlan,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("AI opponent planning failed")
        raise AIError(f"Opponent could not be planned: {type(e).__name__}") from e

    plan = response.parsed_output.model_dump()
    # Never trust a generated timeline to respect its own bounds.
    plan["steps"] = [
        s for s in sorted(plan["steps"], key=lambda s: s["at_seconds"])
        if 0 <= s["at_seconds"] <= time_limit_seconds
    ]
    return plan


async def ai_status() -> dict:
    return {
        "enabled": ai_enabled(),
        "model": settings.ai_model if ai_enabled() else None,
        "features": {
            "code_review": ai_enabled(),
            "ai_opponent": ai_enabled(),
        },
    }
