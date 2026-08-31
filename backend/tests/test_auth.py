import pytest
import uuid


@pytest.mark.asyncio
async def test_register_and_login(client):
    email = f"test_{uuid.uuid4()}@example.com"

    register_resp = await client.post("/auth/register", json={
        "name": "Test User",
        "email": email,
        "password": "testpass123",
    })
    assert register_resp.status_code == 201

    login_resp = await client.post("/auth/login", json={
        "email": email,
        "password": "testpass123",
    })
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


@pytest.mark.asyncio
async def test_me_requires_token(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_valid_token(client):
    email = f"test_{uuid.uuid4()}@example.com"
    await client.post("/auth/register", json={
        "name": "Test User", "email": email, "password": "testpass123",
    })
    login_resp = await client.post("/auth/login", json={
        "email": email, "password": "testpass123",
    })
    token = login_resp.json()["access_token"]

    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == email
