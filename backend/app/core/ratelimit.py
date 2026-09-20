"""A small in-memory rate limiter.

Per-process, like the queue and presence — which means it is per-instance and resets on
restart. Good enough to stop a player brute-forcing hidden test cases or using the judge
as a free compute farm; not a defence against a distributed attacker. Moves to Redis
with the rest of the shared state (ADR-0015).
"""

import time
from collections import defaultdict, deque

_hits: dict[str, deque] = defaultdict(deque)


def rate_limited(key: str, limit: int, window_seconds: float) -> bool:
    """Record an attempt. Returns True when the caller is over the limit.

    Sliding window rather than fixed buckets: a fixed window lets someone spend their
    whole allowance at 11:59:59 and again at 12:00:00.
    """
    now = time.monotonic()
    hits = _hits[key]
    while hits and now - hits[0] > window_seconds:
        hits.popleft()
    if len(hits) >= limit:
        return True
    hits.append(now)
    return False


def reset(key: str | None = None) -> None:
    """Testing helper."""
    if key is None:
        _hits.clear()
    else:
        _hits.pop(key, None)
