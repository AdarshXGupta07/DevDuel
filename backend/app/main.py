import socketio
from app.config import settings
from fastapi import FastAPI
from app.routes.auth import router as auth_router
from app.routes.duels import router as duels_router
from app.sockets.server import sio
from app.sockets import matchmaking  # noqa: F401 — import registers its @sio.on handlers
from app.sockets import duel  # noqa: F401 — import registers its @sio.on handlers

fastapi_app = FastAPI()


@fastapi_app.get("/health")
def health_check():
    return {
        "status": "ok"
    }


fastapi_app.include_router(auth_router)
fastapi_app.include_router(duels_router)

app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
