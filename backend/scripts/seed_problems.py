"""Load problems from backend/problems/*.yaml into the database.

Idempotent: matches on `slug`, updates in place, and replaces that problem's test cases
wholesale. Safe to re-run after every edit to a problem file.

    python -m scripts.seed_problems              # seed everything
    python -m scripts.seed_problems --check      # validate the files, touch nothing
"""

import asyncio
import sys
from pathlib import Path

import yaml
from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Problem, TestCase  # noqa: E402
from app.db.session import async_session_factory  # noqa: E402

PROBLEM_DIR = Path(__file__).resolve().parents[1] / "problems"
REQUIRED = ("slug", "title", "difficulty", "question", "test_cases")


def load_files() -> list[dict]:
    problems = []
    for path in sorted(PROBLEM_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        missing = [field for field in REQUIRED if not data.get(field)]
        if missing:
            raise ValueError(f"{path.name}: missing required field(s): {', '.join(missing)}")
        if data["difficulty"] not in ("easy", "medium", "hard"):
            raise ValueError(f"{path.name}: difficulty must be easy|medium|hard")
        if not any(c.get("public") for c in data["test_cases"]):
            raise ValueError(f"{path.name}: needs at least one public (sample) test case")
        if len(data["test_cases"]) < 3:
            raise ValueError(f"{path.name}: needs at least 3 test cases to be a real judge")
        data["_file"] = path.name
        problems.append(data)
    return problems


async def seed() -> None:
    problems = load_files()
    async with async_session_factory() as db:
        for data in problems:
            result = await db.execute(select(Problem).where(Problem.slug == data["slug"]))
            problem = result.scalar_one_or_none()

            # The reference solution doubles as the post-duel answer key, so it is
            # loaded from the same file `verify_problems.py` runs. That guarantees the
            # code shown to players is the code that provably passes every test.
            reference = {}
            solution_path = PROBLEM_DIR / "solutions" / f"{data['slug']}.py"
            if solution_path.exists():
                reference["python"] = solution_path.read_text(encoding="utf-8")
            for lang in ("cpp", "java", "javascript"):
                extra = PROBLEM_DIR / "solutions" / f"{data['slug']}.{lang}"
                if extra.exists():
                    reference[lang] = extra.read_text(encoding="utf-8")

            fields = dict(
                slug=data["slug"],
                reference_solution=reference or None,
                editorial=(data.get("editorial") or "").strip() or None,
                title=data["title"],
                question=data["question"].strip(),
                constraints=(data.get("constraints") or "").strip() or None,
                difficulty=data["difficulty"],
                tags=data.get("tags") or [],
                time_limit_ms=data.get("time_limit_ms", 5000),
                memory_limit_mb=data.get("memory_limit_mb", 256),
                starter_code=data.get("starter_code"),
                is_active=data.get("is_active", True),
                source=data.get("source", "original"),
                license=data.get("license", "proprietary"),
            )

            if problem is None:
                problem = Problem(**fields)
                db.add(problem)
                await db.flush()
                action = "created"
            else:
                for key, value in fields.items():
                    setattr(problem, key, value)
                await db.execute(delete(TestCase).where(TestCase.problem_id == problem.id))
                action = "updated"

            for ordinal, case in enumerate(data["test_cases"]):
                db.add(
                    TestCase(
                        problem_id=problem.id,
                        ordinal=ordinal,
                        input_data=str(case.get("input", "")),
                        expected_output=str(case.get("output", "")),
                        weight=case.get("weight", 1),
                        is_public=bool(case.get("public", False)),
                    )
                )

            await db.commit()
            print(f"{action}: {data['slug']} ({len(data['test_cases'])} cases)")

    print(f"\n{len(problems)} problem(s) seeded.")


if __name__ == "__main__":
    if "--check" in sys.argv:
        loaded = load_files()
        for data in loaded:
            public = sum(1 for c in data["test_cases"] if c.get("public"))
            print(
                f"ok: {data['_file']:<32} {data['difficulty']:<7} "
                f"{len(data['test_cases'])} cases ({public} public)"
            )
        print(f"\n{len(loaded)} problem file(s) valid.")
    else:
        asyncio.run(seed())
