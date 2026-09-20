"""Problem selection and the client-safe view of a problem."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Duel, Problem, TestCase
from app.services.duel_service import as_uuid

DEFAULT_STARTER = {
    "python": (
        "import sys\n\n"
        "def solve(data: str) -> str:\n"
        "    # TODO: your solution here\n"
        "    return \"\"\n\n"
        "if __name__ == \"__main__\":\n"
        "    print(solve(sys.stdin.read()), end=\"\")\n"
    ),
    "javascript": (
        "function solve(data) {\n"
        "  // TODO: your solution here\n"
        "  return '';\n"
        "}\n\n"
        "const data = require('fs').readFileSync(0, 'utf8');\n"
        "process.stdout.write(solve(data));\n"
    ),
    "cpp": (
        "#include <bits/stdc++.h>\n"
        "using namespace std;\n\n"
        "int main() {\n"
        "    ios::sync_with_stdio(false);\n"
        "    cin.tie(nullptr);\n"
        "    // TODO: your solution here\n"
        "    return 0;\n"
        "}\n"
    ),
    # The class MUST be named Main — the judge compiles Main.java and runs Main.
    "java": (
        "import java.io.*;\n"
        "import java.util.*;\n\n"
        "public class Main {\n"
        "    public static void main(String[] args) throws IOException {\n"
        "        BufferedReader in = new BufferedReader(new InputStreamReader(System.in));\n"
        "        // TODO: your solution here\n"
        "    }\n"
        "}\n"
    ),
}


class NoProblemsAvailable(Exception):
    pass


async def seen_problem_ids(db: AsyncSession, user_ids: list) -> set:
    """Every problem these players have already been served in a duel.

    Counts any duel they took part in, including ones they abandoned — seeing the
    statement is what spoils it, not finishing the match.
    """
    ids = [as_uuid(u) for u in user_ids if u]
    if not ids:
        return set()

    result = await db.execute(
        select(Duel.problem_id).where(
            or_(Duel.player1_id.in_(ids), Duel.player2_id.in_(ids))
        )
    )
    return {row[0] for row in result.all()}


async def pick_random_problem(
    db: AsyncSession,
    difficulty: str | None = None,
    topics: list[str] | None = None,
    for_users: list | None = None,
) -> Problem:
    """Pick a problem, avoiding repeats and honouring topic preferences.

    Preferences are applied in order of how much they matter, each falling back rather
    than failing:

      1. **Unseen by every player in the duel**, plus the requested topics.
      2. Unseen by everyone, any topic.  ← repeats matter more than topics
      3. Requested topics, even if seen.
      4. Anything active.

    The ordering is deliberate. A player who asked for graphs and got an array problem
    is mildly disappointed; a player handed a problem they already solved last week has
    had the duel ruined, and their opponent has too. So repeat-avoidance outranks the
    topic request — and both outrank failing to start the match at all, which is the one
    outcome nobody recovers from.

    ORDER BY random() is fine at this table size; it becomes a problem around 100k rows,
    long after the bank would need restructuring anyway.
    """
    base = select(Problem).where(Problem.is_active.is_(True))
    if difficulty:
        base = base.where(Problem.difficulty == difficulty)

    # `overlap` is Postgres `&&`: true when the arrays share any element.
    topic_filter = Problem.tags.overlap(list(topics)) if topics else None
    seen = await seen_problem_ids(db, for_users or [])

    attempts = []
    if seen and topic_filter is not None:
        attempts.append(base.where(topic_filter, Problem.id.not_in(seen)))
    if seen:
        attempts.append(base.where(Problem.id.not_in(seen)))
    if topic_filter is not None:
        attempts.append(base.where(topic_filter))
    attempts.append(base)

    for query in attempts:
        result = await db.execute(query.order_by(func.random()).limit(1))
        problem = result.scalar_one_or_none()
        if problem is not None:
            return problem

    raise NoProblemsAvailable("No active problems are configured.")


async def unseen_count(db: AsyncSession, user_id) -> dict:
    """How much of the bank a player has left. Drives the 'seen everything' notice."""
    total = await db.execute(
        select(func.count()).select_from(Problem).where(Problem.is_active.is_(True))
    )
    total_count = int(total.scalar() or 0)
    seen = await seen_problem_ids(db, [user_id])
    return {
        "total": total_count,
        "seen": len(seen),
        "unseen": max(total_count - len(seen), 0),
    }


async def available_topics(db: AsyncSession) -> list[str]:
    """Every tag that has at least one active problem behind it.

    Driven by the bank rather than a hardcoded list, so the picker can never offer a
    topic that would always fall back to something else.
    """
    result = await db.execute(
        select(Problem.tags).where(Problem.is_active.is_(True), Problem.tags.isnot(None))
    )
    seen: set[str] = set()
    for (tags,) in result.all():
        seen.update(tags or [])
    return sorted(seen)


async def problem_for_client(db: AsyncSession, problem_id, language: str = "python") -> dict:
    """What a player is allowed to see: the statement and the *sample* cases only.

    Hidden test cases never cross this boundary. If they did, "solve the problem"
    becomes "print the expected outputs", which is not the same game.
    """
    problem = await db.get(Problem, problem_id)
    if problem is None:
        raise NoProblemsAvailable(f"Problem {problem_id} not found.")

    result = await db.execute(
        select(TestCase)
        .where(TestCase.problem_id == problem.id, TestCase.is_public.is_(True))
        .order_by(TestCase.ordinal)
    )
    samples = [
        {"input": c.input_data, "expected_output": c.expected_output} for c in result.scalars()
    ]

    starter = (problem.starter_code or {}).get(language) or DEFAULT_STARTER.get(language, "")

    return {
        "id": str(problem.id),
        "slug": problem.slug,
        "title": problem.title,
        "question": problem.question,
        "constraints": problem.constraints,
        "difficulty": problem.difficulty,
        "tags": problem.tags or [],
        "time_limit_ms": problem.time_limit_ms,
        "memory_limit_mb": problem.memory_limit_mb,
        "starter_code": starter,
        "samples": samples,
    }
