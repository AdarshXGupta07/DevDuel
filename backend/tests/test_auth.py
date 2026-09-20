import uuid

import pytest

from tests.conftest import requires_db

pytestmark = pytest.mark.db


def _credentials():
    return {
        "name": "Test User",
        "email": f"test_{uuid.uuid4()}@example.com",
        "password": "testpass123",
    }


@requires_db
async def test_register_and_login(client):
    creds = _credentials()

    register_resp = await client.post("/auth/register", json=creds)
    assert register_resp.status_code == 201
    assert "password" not in register_resp.json()

    login_resp = await client.post(
        "/auth/login", json={"email": creds["email"], "password": creds["password"]}
    )
    assert login_resp.status_code == 200
    body = login_resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


@requires_db
async def test_duplicate_email_is_409(client):
    creds = _credentials()
    assert (await client.post("/auth/register", json=creds)).status_code == 201
    assert (await client.post("/auth/register", json=creds)).status_code == 409


async def test_me_requires_token(client):
    """No database needed: this must be rejected before any query runs."""
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@requires_db
async def test_me_with_valid_token(client):
    creds = _credentials()
    await client.post("/auth/register", json=creds)
    login_resp = await client.post(
        "/auth/login", json={"email": creds["email"], "password": creds["password"]}
    )
    token = login_resp.json()["access_token"]

    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == creds["email"]


@requires_db
async def test_refresh_rotates_the_token(client):
    """ADR-0023: refresh returns a NEW refresh token and spends the old one."""
    creds = _credentials()
    await client.post("/auth/register", json=creds)
    login = (
        await client.post(
            "/auth/login", json={"email": creds["email"], "password": creds["password"]}
        )
    ).json()

    first = await client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert first.status_code == 200
    rotated = first.json()["refresh_token"]
    assert rotated != login["refresh_token"]

    # Reusing the spent token is theft-shaped: it must be refused...
    replay = await client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert replay.status_code == 401

    # ...and it must take the whole family down with it, including the rotated token.
    after_breach = await client.post("/auth/refresh", json={"refresh_token": rotated})
    assert after_breach.status_code == 401


@requires_db
async def test_refresh_token_is_not_an_access_token(client):
    """ADR-0011: the 7-day token must not open doors the 15-minute one opens."""
    creds = _credentials()
    await client.post("/auth/register", json=creds)
    login = (
        await client.post(
            "/auth/login", json={"email": creds["email"], "password": creds["password"]}
        )
    ).json()

    resp = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {login['refresh_token']}"}
    )
    assert resp.status_code == 401


@requires_db
async def test_logout_revokes_the_session(client):
    creds = _credentials()
    await client.post("/auth/register", json=creds)
    login = (
        await client.post(
            "/auth/login", json={"email": creds["email"], "password": creds["password"]}
        )
    ).json()

    assert (
        await client.post("/auth/logout", json={"refresh_token": login["refresh_token"]})
    ).status_code == 204
    assert (
        await client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    ).status_code == 401


async def test_short_password_is_rejected(client):
    """No database needed: Pydantic rejects it before the service is reached."""
    resp = await client.post(
        "/auth/register", json={"name": "x", "email": "a@b.com", "password": "short"}
    )
    assert resp.status_code == 422
