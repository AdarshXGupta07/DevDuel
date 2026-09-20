"""The rage-quit deterrent: escalation curve and block state."""

from datetime import timedelta

import pytest

from app.config import settings
from app.db.models import User, utcnow
from app.services.conduct_service import _cooldown_for, block_status
from app.services.matchmaking_service import local_usage_date


def minutes(delta: timedelta | None) -> int | None:
    return None if delta is None else int(delta.total_seconds() // 60)


class TestEscalation:
    def test_below_threshold_is_free(self):
        """One walkout is a bad connection or a misclick, not a habit."""
        assert _cooldown_for(0) is None
        assert _cooldown_for(1) is None

    def test_threshold_triggers_base_cooldown(self):
        assert minutes(_cooldown_for(2)) == settings.abandon_cooldown_minutes

    def test_cooldown_doubles_each_further_abandon(self):
        base = settings.abandon_cooldown_minutes
        assert minutes(_cooldown_for(3)) == base * 2
        assert minutes(_cooldown_for(4)) == base * 4
        assert minutes(_cooldown_for(5)) == base * 8

    def test_doubling_is_capped(self):
        """An all-day tantrum should not produce a multi-day ban."""
        base = settings.abandon_cooldown_minutes
        assert minutes(_cooldown_for(20)) == base * 8
        assert minutes(_cooldown_for(200)) == base * 8


class TestBlockStatus:
    def _user(self, **kwargs) -> User:
        user = User(name="t", email="t@example.com", password_hash="x")
        user.abandons_today = kwargs.get("abandons_today", 0)
        user.abandons_date = kwargs.get("abandons_date", local_usage_date())
        user.matchmaking_blocked_until = kwargs.get("blocked_until")
        return user

    def test_clean_user_is_not_blocked(self):
        status = block_status(self._user())
        assert status["blocked"] is False
        assert status["remaining_before_block"] == settings.abandon_threshold

    def test_one_abandon_warns_but_does_not_block(self):
        status = block_status(self._user(abandons_today=1))
        assert status["blocked"] is False
        assert status["remaining_before_block"] == 1

    def test_active_block_reports_seconds_remaining(self):
        status = block_status(
            self._user(abandons_today=2, blocked_until=utcnow() + timedelta(minutes=10))
        )
        assert status["blocked"] is True
        assert 500 < status["seconds_remaining"] <= 600

    def test_expired_block_is_not_a_block(self):
        status = block_status(
            self._user(abandons_today=2, blocked_until=utcnow() - timedelta(minutes=1))
        )
        assert status["blocked"] is False

    def test_yesterdays_abandons_do_not_count(self):
        """Counted per day — a bad afternoon should not follow someone forever."""
        status = block_status(
            self._user(
                abandons_today=5,
                abandons_date=local_usage_date() - timedelta(days=1),
            )
        )
        assert status["abandons_today"] == 0
        assert status["remaining_before_block"] == settings.abandon_threshold
