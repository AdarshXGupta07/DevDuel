import socketio
from app.core.security import decode_token
from jose import JWTError
from socketio.exceptions import ConnectionRefusedError
sio=socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')


@sio.event
async def connect(sid, environ,auth):
    if auth is None or 'token' not in auth:
        raise ConnectionRefusedError("Authentication token is required.")
    token=auth.get('token')
    try:
        payload=decode_token(token)
    except JWTError:
        raise ConnectionRefusedError("Invalid token.")
    user_id=payload.get("sub")
    if user_id is None:
        raise ConnectionRefusedError("Invalid token.")
    await sio.save_session(sid, {'user_id': user_id})
    
@sio.event
async def whoami(sid):
    # 1. Get back the session dict you saved during connect()
    #    Look up: sio.get_session(sid) — it's async, so you'll need `await`
    session = await sio.get_session(sid)

    # 2. Send something back to just this one connection, confirming what it knows
    #    Look up: sio.emit(event_name, data, to=sid)
    #    - event_name: pick any string, e.g. "whoami_response"
    #    - data: a dict containing the user_id from the session
    #    - to=sid: makes sure only THIS connection receives it, not everyone connected
    await sio.emit('whoami_response', {'user_id': session['user_id']}, to=sid)
    
@sio.event
async def disconnect(sid):
    # Clean up any resources or state associated with this connection
    print(f"Client {sid} disconnected.")