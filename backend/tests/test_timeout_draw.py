"""The timeout rule (ADR-0044) and the free analysis heuristics."""

import pytest

from app.services.analysis_service import VERDICT_EXPLANATIONS, _complexity_hints
from app.services.rating_service import expected_score, new_rating


class TestDrawLeavesRatingsAlone:
    """A problem that beat both players says nothing about which is stronger.

    Standard ELO disagrees — it shifts ratings on any draw between unequal players —
    which is why `apply_duel_result` special-cases `end_reason == 'draw'` instead of
    feeding 0.5 through the formula. These tests pin down *why* that branch exists.
    """

    def test_plain_elo_would_move_unequal_ratings_on_a_draw(self):
        higher, lower = 1600, 1200
        assert new_rating(higher, lower, 0.5, 20) < higher
        assert new_rating(lower, higher, 0.5, 20) > lower

    def test_plain_elo_leaves_equal_ratings_alone_on_a_draw(self):
        assert new_rating(1400, 1400, 0.5, 20) == 1400

    def test_the_gap_being_punished_grows_with_rating_difference(self):
        small = 1500 - new_rating(1500, 1400, 0.5, 20)
        large = 1900 - new_rating(1900, 1400, 0.5, 20)
        assert large > small > 0
        # ~9 points for a 500-point gap: small, but it accumulates and it is unearned.
        assert large >= 8


class TestVerdictExplanations:
    @pytest.mark.parametrize(
        "verdict",
        ["accepted", "wrong_answer", "tle", "mle", "runtime_error", "compile_error",
         "system_error"],
    )
    def test_every_verdict_has_a_plain_english_explanation(self, verdict):
        assert VERDICT_EXPLANATIONS[verdict]

    def test_system_error_does_not_blame_the_player(self):
        assert "on us" in VERDICT_EXPLANATIONS["system_error"]


class TestComplexityHints:
    def test_nested_loops_are_flagged(self):
        code = "for i in range(n):\n    for j in range(n):\n        total += a[i] * a[j]\n"
        hints = _complexity_hints(code, "python")
        assert any("nested loops" in h for h in hints)

    def test_a_single_loop_is_not_flagged(self):
        """A false hint is worse than no hint — O(n) must stay quiet."""
        code = "for i in range(n):\n    total += a[i]\n"
        assert _complexity_hints(code, "python") == []

    def test_dedented_loops_are_not_counted_as_nested(self):
        """Two sequential loops are O(n), not O(n^2)."""
        code = "for i in range(n):\n    x += 1\nfor j in range(n):\n    y += 1\n"
        assert not any("nested" in h for h in _complexity_hints(code, "python"))

    def test_list_membership_is_flagged(self):
        code = "for x in nums:\n    if x in nums_list:\n        pass\n"
        assert any("set" in h.lower() for h in _complexity_hints(code, "python"))

    def test_slow_input_is_flagged(self):
        assert any("stdin" in h for h in _complexity_hints("n = int(input())", "python"))

    def test_front_insertion_is_flagged(self):
        assert any("deque" in h for h in _complexity_hints("q.insert(0, x)", "python"))

    def test_other_languages_get_no_python_hints(self):
        code = "for (int i=0;i<n;i++){ for(int j=0;j<n;j++){} }"
        assert _complexity_hints(code, "cpp") == []
