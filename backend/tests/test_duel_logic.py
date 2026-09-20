"""State machine, output comparison and verdict mapping — the rules, without a database."""

import pytest

from app.services.duel_service import IllegalTransition, legal_transition
from app.services.judge_service import _verdict_for, normalize_output
from app.services.sandbox import RunResult


class TestTransitions:
    @pytest.mark.parametrize(
        "current,new",
        [
            ("pending", "ready"),
            ("ready", "active"),
            ("active", "finished"),
            ("pending", "abandoned"),
            ("ready", "abandoned"),
            ("active", "abandoned"),
        ],
    )
    def test_legal(self, current, new):
        legal_transition(current, new)  # must not raise

    @pytest.mark.parametrize(
        "current,new",
        [
            ("pending", "active"),      # cannot skip ready
            ("pending", "finished"),
            ("finished", "active"),     # terminal
            ("abandoned", "ready"),
            ("active", "ready"),        # no going back
            ("ready", "ready"),
        ],
    )
    def test_illegal(self, current, new):
        with pytest.raises(IllegalTransition):
            legal_transition(current, new)


class TestNormalizeOutput:
    def test_trailing_newline_ignored(self):
        assert normalize_output("42\n") == normalize_output("42")

    def test_trailing_spaces_ignored(self):
        assert normalize_output("1 2 3   \n") == normalize_output("1 2 3")

    def test_windows_line_endings_ignored(self):
        assert normalize_output("a\r\nb\r\n") == normalize_output("a\nb")

    def test_multiple_trailing_blank_lines_ignored(self):
        assert normalize_output("x\n\n\n") == normalize_output("x")

    def test_internal_spacing_is_significant(self):
        assert normalize_output("1 2") != normalize_output("1  2")

    def test_internal_blank_line_is_significant(self):
        assert normalize_output("a\n\nb") != normalize_output("a\nb")


class TestVerdictMapping:
    def _result(self, status="ok", exit_code=0):
        return RunResult(status=status, exit_code=exit_code, stdout="", stderr="", duration_ms=1)

    def test_accepted(self):
        assert _verdict_for(self._result(), matched=True) == "accepted"

    def test_wrong_answer(self):
        assert _verdict_for(self._result(), matched=False) == "wrong_answer"

    def test_timeout_is_tle(self):
        assert _verdict_for(self._result(status="timeout", exit_code=None), True) == "tle"

    def test_oom_is_mle(self):
        assert _verdict_for(self._result(status="oom", exit_code=137), True) == "mle"

    def test_nonzero_exit_is_runtime_error(self):
        assert _verdict_for(self._result(exit_code=1), matched=True) == "runtime_error"

    def test_output_flood_is_not_accepted(self):
        """A submission that floods stdout must never pass, even if a prefix matched."""
        assert _verdict_for(self._result(status="output_limit"), matched=True) == "wrong_answer"

    def test_system_error_is_not_the_players_fault(self):
        assert _verdict_for(self._result(status="system_error", exit_code=None), False) == (
            "system_error"
        )
