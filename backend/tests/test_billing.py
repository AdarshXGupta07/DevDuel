"""Webhook signature verification — the only thing standing between a stranger and a
free Pro plan, so it gets tested properly."""

import hashlib
import hmac

import pytest

from app.config import settings
from app.services.billing_service import _ts, verify_webhook_signature

SECRET = "whsec_test_devduel"
BODY = b'{"event":"subscription.activated","payload":{}}'


def sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def _webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_webhook_secret", SECRET)


def test_valid_signature_accepted():
    assert verify_webhook_signature(BODY, sign(BODY)) is True


def test_wrong_signature_rejected():
    assert verify_webhook_signature(BODY, sign(BODY, "not_the_secret")) is False


def test_tampered_body_rejected():
    """The signature covers the raw bytes, so changing one character invalidates it."""
    signature = sign(BODY)
    tampered = BODY.replace(b"activated", b"cancelled")
    assert verify_webhook_signature(tampered, signature) is False


def test_missing_signature_rejected():
    assert verify_webhook_signature(BODY, None) is False
    assert verify_webhook_signature(BODY, "") is False


def test_reserialised_body_rejected():
    """Re-encoding the JSON changes the bytes, which is why the raw body must be used."""
    reserialised = b'{"event": "subscription.activated", "payload": {}}'  # added spaces
    assert verify_webhook_signature(reserialised, sign(BODY)) is False


def test_no_secret_configured_rejects_everything(monkeypatch):
    """Fail closed. An unconfigured server must not accept unsigned plan upgrades."""
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "")
    assert verify_webhook_signature(BODY, sign(BODY)) is False


class TestTimestamps:
    def test_unix_seconds_become_aware_utc(self):
        dt = _ts(1760000000)
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.utcoffset().total_seconds() == 0

    def test_none_and_zero_are_none(self):
        assert _ts(None) is None
        assert _ts(0) is None


class TestConfigGuards:
    def test_billing_disabled_without_keys(self, monkeypatch):
        monkeypatch.setattr(settings, "razorpay_key_id", "")
        assert settings.billing_enabled is False

    def test_test_mode_detected_from_key_prefix(self, monkeypatch):
        monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_abc123")
        assert settings.billing_is_test_mode is True
        monkeypatch.setattr(settings, "razorpay_key_id", "rzp_live_abc123")
        assert settings.billing_is_test_mode is False
