"""ELO maths. Pure functions, no database, no network — fast enough to run constantly."""

import pytest

from app.services.rating_service import (
    K_PLACEMENT,
    K_STANDARD,
    PLACEMENT_MATCHES,
    expected_score,
    k_factor,
    new_rating,
)


def test_equal_ratings_expect_half():
    assert expected_score(1200, 1200) == pytest.approx(0.5)


def test_stronger_player_expected_to_win_more():
    assert expected_score(1600, 1200) > 0.9
    assert expected_score(1200, 1600) < 0.1


def test_expectations_sum_to_one():
    assert expected_score(1450, 1310) + expected_score(1310, 1450) == pytest.approx(1.0)


def test_k_factor_drops_after_placements():
    assert k_factor(0) == K_PLACEMENT
    assert k_factor(PLACEMENT_MATCHES - 1) == K_PLACEMENT
    assert k_factor(PLACEMENT_MATCHES) == K_STANDARD


def test_even_match_win_gains_half_k():
    assert new_rating(1200, 1200, 1.0, 20) == 1210
    assert new_rating(1200, 1200, 0.0, 20) == 1190


def test_draw_between_equals_changes_nothing():
    assert new_rating(1200, 1200, 0.5, 40) == 1200


def test_upset_moves_rating_more_than_expected_win():
    upset = new_rating(1200, 1600, 1.0, 20) - 1200
    expected_win = new_rating(1600, 1200, 1.0, 20) - 1600
    assert upset > expected_win


def test_zero_sum_for_equal_k():
    """What one player gains, the other loses — otherwise the ladder inflates."""
    r1, r2 = 1340, 1275
    a = new_rating(r1, r2, 1.0, 20) - r1
    b = new_rating(r2, r1, 0.0, 20) - r2
    assert a + b == pytest.approx(0, abs=1)
