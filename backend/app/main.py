import logging
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError

from app.config import settings
from app.routes.ai import router as ai_router
from app.routes.auth import router as auth_router
from app.routes.billing import router as billing_router
from app.routes.duels import router as duels_router
from app.routes.problems import router as problems_router
from app.sockets import duel  # noqa: F401 — import registers its @sio.on handlers
from app.sockets import lifecycle  # noqa: F401 — connect/disconnect handlers
from app.sockets import matchmaking  # noqa: F401 — import registers its @sio.on handlers
from app.sockets.server import sio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger("devduel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup recovery.

    Grace-period and match-clock timers live in process memory, so a restart loses every
    pending one — a duel whose deadline passed while the server was down would otherwise
    sit `active` forever. Sweeping at boot re-resolves those. It must never prevent
    startup: a database that is briefly unreachable is a reason to log and carry on, not
    to refuse to serve /health.
    """
    from app.services.duel_runtime import sweep_expired_duels

    try:
        resolved = await sweep_expired_duels()
        logger.info("startup sweep resolved %s expired duel(s)", resolved)
    except Exception:  # noqa: BLE001
        logger.exception("startup sweep failed; continuing without it")

    yield


fastapi_app = FastAPI(title="DevDuel API", version="0.1.0", lifespan=lifespan)


UNREACHABLE_MESSAGE = (
    "The database is currently unreachable. If this is a free Supabase project, "
    "it may be paused."
)


@fastapi_app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    """A database that cannot be reached is 503, not 500.

    503 says "temporarily unable to serve", which is true and actionable — a client can
    retry and a monitor can alert. A bare 500 with Starlette's plain-text body told the
    user nothing and broke their JSON parser.
    """
    logger.exception("database error on %s %s", request.method, request.url.path)
    unreachable = isinstance(exc, (OperationalError, InterfaceError))
    return JSONResponse(
        status_code=503 if unreachable else 500,
        content={"detail": UNREACHABLE_MESSAGE if unreachable else "A database error occurred."},
    )


@fastapi_app.exception_handler(OSError)
async def socket_error_handler(request: Request, exc: OSError):
    """DNS and TCP failures reaching the database arrive here, not as SQLAlchemy errors.

    A name that does not resolve (`socket.gaierror`, which is an OSError) propagates
    straight through SQLAlchemy's greenlet bridge unwrapped, so catching SQLAlchemyError
    alone misses the single most common outage: a paused database.
    """
    logger.exception("network error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=503, content={"detail": UNREACHABLE_MESSAGE})


@fastapi_app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """Every unhandled error leaves as JSON, and never carries a stack trace.

    The traceback goes to the log, where it is useful; the client gets a shape it can
    parse and nothing about our internals.
    """
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@fastapi_app.get("/health")
async def health_check():
    """Liveness only — cheap and dependency-free, safe for an uptime monitor to hammer."""
    return {"status": "ok", "env": settings.app_env}


@fastapi_app.get("/health/ready")
async def readiness_check():
    """Readiness — actually touches the things a request needs."""
    from sqlalchemy import text

    from app.db.session import async_session_factory
    from app.services.judge_service import judge_health

    checks: dict[str, str] = {}

    try:
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001 — a readiness probe reports, it does not raise
        checks["database"] = f"error: {type(e).__name__}"

    checks["judge"] = await judge_health()

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}


fastapi_app.include_router(auth_router)
fastapi_app.include_router(duels_router)
fastapi_app.include_router(problems_router)
fastapi_app.include_router(billing_router)
fastapi_app.include_router(ai_router)

app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
