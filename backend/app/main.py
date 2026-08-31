import socketio
from app.config import settings
from fastapi import FastAPI
from app.routes.auth import router as auth_router
from app.sockets.server import sio

fastapi_app = FastAPI()


@fastapi_app.get("/health")
def health_check():
    return {
        "status": "ok"
    }


fastapi_app.include_router(auth_router)

app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
