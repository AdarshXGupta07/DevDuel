# Building the problem bank

**The short version:** you can use the *curriculum* (which topics, in which order, at
which difficulty) from any sheet you like. You cannot copy the *problem statements*.
Those are someone else's writing, and copying them into a product you charge ₹50/month
for is the kind of risk that ends a startup rather than slows it down.

---

## 1. What is and is not yours to use

| Thing | Safe? | Why |
|---|---|---|
| **A list of topics and canonical problem names** ("Two Sum", "Kadane's Algorithm", "Detect cycle in a linked list") | ✅ Yes | Facts and short titles aren't protectable expression. A curriculum ordering is a list of ideas. |
| **The underlying algorithm or task** ("find the maximum subarray sum") | ✅ Yes | Copyright protects expression, not ideas or algorithms. Everyone teaches Kadane's. |
| **Your own statement describing that task**, with your own examples and constraints | ✅ Yes | You wrote it. This is the whole game. |
| **LeetCode/GFG/InterviewBit statement text, examples, or constraints, copied or lightly reworded** | ❌ No | That's their prose. Light rewording is still a derivative work. |
| **Their test cases** | ❌ No | Also theirs, and usually behind a login you agreed terms to use. |
| **Scraping their site** | ❌ No | Breaches their terms of service independently of copyright. |

**So Striver's SDE Sheet is usable as a map, not as a source.** The sheet is a list —
"Day 3: Kadane's, merge intervals, duplicate in array…" — and following that curriculum
is entirely legitimate. The statements it links to are mostly LeetCode's and GFG's, and
those are not.

I will help you write originals at volume. I won't write a scraper.

---

## 2. What "writing your own" actually costs

Honestly: **1–2 hours per problem** done properly — statement, 5–10 test cases including
adversarial ones, a reference solution, and verification that the two agree.

That is the real bottleneck in this project. Not the judge, not the frontend.

**Do not aim for 200 problems.** Aim for **20 good ones** to launch, then add 5 a week.
A player who does two duels a day takes ten days to see 20 problems, and you will learn
more from those ten days than from three months of writing you did up front.

---

## 3. The realistic sources, ranked

**1. Write originals from a topic list (recommended).**
Take the Striver ordering, pick the *concept* (sliding window, two pointers, topological
sort), and write a fresh problem around it. Change the domain — a "warehouse hourly
request log" instead of "an array of integers" — and the statement is unambiguously
yours. Your five current problems were written this way.

**2. Openly-licensed collections.** These exist and are genuinely free to adapt, but
check each licence individually:
- Project Euler (attribution required, non-commercial ambiguity — read their terms before
  using in a paid product)
- Rosetta Code (GFDL / CC BY-SA — share-alike obligations you probably don't want)
- University course problem sets released under CC BY — plenty of these, and usually the
  cleanest option
- Public-domain classics: sorting, searching, string processing, graph traversal. Nobody
  owns "implement binary search".

**3. LLM-drafted, human-verified.** Fast for first drafts, but *you* own correctness. An
LLM will cheerfully produce a problem whose stated constraints make the intended solution
impossible, or test cases that disagree with the reference solution. Every generated
problem must pass `verify_problems.py` before it is real.

---

## 4. The pipeline that already exists

```bash
python -m scripts.new_problem two-sum-variant   # scaffold statement + solution + tests
python -m scripts.seed_problems --check         # validate the YAML
python -m scripts.verify_problems               # run every reference solution in the sandbox
python -m scripts.seed_problems                 # load into the database
```

`verify_problems.py` is the quality gate that matters: it runs each reference solution
against its own test cases **in the real judge**. A problem whose expected output is
wrong is invisible until two players both fail something nobody can pass — and in a
ranked duel that costs someone a match.

Every problem file records `source` and `license`. Fill them in honestly:

```yaml
source: original          # or: adapted-from-cc-by-<url>, public-domain
license: proprietary      # or: CC-BY-4.0, etc.
```

That field is not bureaucracy. It's the thing you'll be glad exists if anyone ever asks.

---

## 5. A workable plan for 20 problems

Use the Striver ordering for *coverage*, write the statements yourself:

| # | Concept | Difficulty |
|---|---|---|
| 1–3 | Array traversal, prefix sums, running aggregates | easy |
| 4–6 | Two pointers, sliding window | easy → medium |
| 7–8 | Hashing / frequency counting | easy |
| 9–10 | Sorting + custom comparators | medium |
| 11–12 | Stack (bracket matching, next greater element) | easy → medium |
| 13–14 | Binary search, including search-on-answer | medium |
| 15–16 | Linked list manipulation | medium |
| 17–18 | Tree traversal, BFS/DFS on a grid | medium |
| 19 | Topological sort | medium |
| 20 | One-dimensional DP | medium → hard |

You already have 5 covering rows 1, 4, 7, 11 and 19. **Fifteen to go.**

Give me a topic from that table and I'll draft the statement, test cases and reference
solution, then run it through `verify_problems.py` before it goes near the database. A
couple per session is a sustainable pace alongside the rest of the build.
