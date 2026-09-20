import socket
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import fastapi_app


def _database_reachable() -> bool:
    """Tests that need the database skip cleanly when it is not reachable.

    Without this, a laptop offline (or a CI job with no database) reports failures that
    say nothing about the code.
    """
    try:
        parsed = urlparse(settings.supabase_url.replace("+asyncpg", ""))
        if not parsed.hostname:
            return False
        socket.getaddrinfo(parsed.hostname, parsed.port or 5432)
        return True
    except Exception:  # noqa: BLE001
        return False


DATABASE_AVAILABLE = _database_reachable()

requires_db = pytest.mark.skipif(
    not DATABASE_AVAILABLE, reason="database not reachable from this machine"
)


@pytest_asyncio.fixture
async def client():
    # Mount the FastAPI app directly, not the Socket.IO wrapper — httpx speaks HTTP.
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
