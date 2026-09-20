"""Scaffold a new problem: YAML skeleton + reference solution stub.

    python -m scripts.new_problem sliding-window-max --difficulty medium --tags window,arrays

Writes two files and refuses to overwrite either. Fill them in, then:

    python -m scripts.verify_problems <slug>
    python -m scripts.seed_problems

The template carries the rules that are easy to forget at 1am: at least three test
cases, at least one public sample, and a `source`/`license` you must fill in honestly.
See docs/problems.md for what is and is not yours to use.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBLEM_DIR = ROOT / "problems"
SOLUTION_DIR = PROBLEM_DIR / "solutions"

TEMPLATE = """slug: {slug}
title: {title}
difficulty: {difficulty}
tags: [{tags}]
# Provenance is not optional. 'original' means you wrote this statement yourself.
# If you adapted something, say what and under which licence. See docs/problems.md.
source: original
license: proprietary
time_limit_ms: 5000
memory_limit_mb: 256

question: |
  TODO: describe the task in your own words. Set it in a concrete situation rather than
  "given an array" — a domain makes the statement yours and makes it easier to read.

  **Input**
  The first line contains ...
  The second line contains ...

  **Output**
  A single line containing ...

constraints: |
  1 <= n <= 100000
  TODO: state the bounds that make the intended solution necessary. If an O(n^2)
  solution passes, the constraints are wrong.

starter_code:
  python: |
    import sys

    def main():
        data = sys.stdin.read().split()
        # TODO
        print()

    main()

test_cases:
  # At least one public case — these are shown to the player and used by "Run samples".
  - public: true
    input: |
      TODO
    output: |
      TODO
  - public: true
    input: |
      TODO
    output: |
      TODO
  # Hidden cases. Include the nasty ones: smallest input, largest input, all-equal
  # values, negatives, and whatever breaks a naive solution.
  - input: |
      TODO
    output: |
      TODO
"""

SOLUTION = '''"""Reference solution for {slug}.

Must be correct AND fast enough for the stated constraints — verify_problems.py runs it
in the real sandbox against every test case, under the real time limit.
"""

import sys


def main():
    data = sys.stdin.read().split()
    # TODO: solve it
    print()


main()
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new DevDuel problem.")
    parser.add_argument("slug", help="kebab-case identifier, e.g. sliding-window-max")
    parser.add_argument("--title", help="human title (default: derived from the slug)")
    parser.add_argument(
        "--difficulty", default="easy", choices=("easy", "medium", "hard")
    )
    parser.add_argument("--tags", default="", help="comma-separated, e.g. arrays,hashing")
    args = parser.parse_args()

    slug = args.slug.strip().lower()
    if not slug.replace("-", "").isalnum():
        print(f"error: {slug!r} should be kebab-case letters, digits and hyphens")
        return 1

    problem_path = PROBLEM_DIR / f"{slug}.yaml"
    solution_path = SOLUTION_DIR / f"{slug}.py"

    for path in (problem_path, solution_path):
        if path.exists():
            print(f"error: {path.relative_to(ROOT)} already exists — pick another slug")
            return 1

    title = args.title or slug.replace("-", " ").title()
    tags = ", ".join(t.strip() for t in args.tags.split(",") if t.strip())

    PROBLEM_DIR.mkdir(parents=True, exist_ok=True)
    SOLUTION_DIR.mkdir(parents=True, exist_ok=True)
    problem_path.write_text(
        TEMPLATE.format(slug=slug, title=title, difficulty=args.difficulty, tags=tags),
        encoding="utf-8",
    )
    solution_path.write_text(SOLUTION.format(slug=slug), encoding="utf-8")

    print(f"created {problem_path.relative_to(ROOT)}")
    print(f"created {solution_path.relative_to(ROOT)}")
    print(f"\nNext:\n  1. fill both in\n  2. python -m scripts.verify_problems {slug}"
          f"\n  3. python -m scripts.seed_problems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
