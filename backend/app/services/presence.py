"""Who is connected, and on which sockets.

In-memory, and therefore per-process. The moment you run two API instances (Week 5,
Day 25) this must move to Redis — a user connected to instance A is invisible to
instance B, which would make every cross-instance disconnect look like an abandonment.
Same limitation, same fix, as the matchmaking queue.
"""

from collections import defaultdict

# user_id -> set of socket ids. A user with two tabs open has two sids.
_sockets_by_user: dict[str, set[str]] = defaultdict(set)
_user_by_socket: dict[str, str] = {}


def register(user_id: str, sid: str) -> int:
    """Attach a socket to a user. Returns their new total socket count."""
    user_id = str(user_id)
    _sockets_by_user[user_id].add(sid)
    _user_by_socket[sid] = user_id
    return len(_sockets_by_user[user_id])


def unregister(sid: str) -> tuple[str | None, int]:
    """Detach a socket. Returns (user_id, remaining socket count for that user)."""
    user_id = _user_by_socket.pop(sid, None)
    if user_id is None:
        return None, 0
    sockets = _sockets_by_user.get(user_id)
    if sockets is None:
        return user_id, 0
    sockets.discard(sid)
    remaining = len(sockets)
    if remaining == 0:
        _sockets_by_user.pop(user_id, None)
    return user_id, remaining


def user_for(sid: str) -> str | None:
    return _user_by_socket.get(sid)


def sockets_for(user_id) -> set[str]:
    return set(_sockets_by_user.get(str(user_id), set()))


def is_online(user_id) -> bool:
    return bool(_sockets_by_user.get(str(user_id)))


def clear() -> None:
    _sockets_by_user.clear()
    _user_by_socket.clear()
