"""Redis-backed mailbox — persistent, survives process restart.

Requires ``redis[hiredis]`` (``uv add redis[hiredis]``).

Usage::

    import redis.asyncio as redis
    from deerflow.actor import ActorSystem
    from deerflow.actor.mailbox_redis import RedisMailbox

    pool = redis.ConnectionPool.from_url("redis://localhost:6379")

    system = ActorSystem("app")
    ref = await system.spawn(
        MyActor, "worker",
        mailbox=RedisMailbox(pool, "actor:inbox:worker"),
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .mailbox import Empty, Mailbox
from .ref import _Envelope, _Stop

logger = logging.getLogger(__name__)


def _serialize(msg: _Envelope | _Stop) -> str:
    """Serialize an envelope to JSON for Redis storage.

    Raises ``TypeError`` if the payload is not JSON-serializable.
    """
    if isinstance(msg, _Stop):
        return json.dumps({"__type__": "stop"})
    try:
        return json.dumps({
            "__type__": "envelope",
            "payload": msg.payload,
            "correlation_id": msg.correlation_id,
            "reply_to": msg.reply_to,
        })
    except (TypeError, ValueError) as e:
        raise TypeError(f"Payload is not JSON-serializable: {e}. RedisMailbox requires JSON-compatible messages.") from e


def _deserialize(data: str | bytes) -> _Envelope | _Stop:
    """Deserialize a JSON string back to an envelope or stop sentinel."""
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    d = json.loads(data)
    if d.get("__type__") == "stop":
        return _Stop()
    return _Envelope(
        payload=d.get("payload"),
        sender=None,
        correlation_id=d.get("correlation_id"),
        reply_to=d.get("reply_to"),
    )


class RedisMailbox(Mailbox):
    """Mailbox backed by a Redis LIST.

    Each actor gets its own Redis key (the ``queue_name``).
    Messages are serialized as JSON, so payloads must be JSON-compatible.

    Args:
        pool: A ``redis.asyncio.ConnectionPool`` instance.
        queue_name: Redis key for this actor's inbox (e.g. ``"actor:inbox:worker"``).
        maxlen: Maximum queue length. 0 = unbounded. When exceeded, ``put_nowait`` returns False.
        brpop_timeout: Seconds to block on ``get()`` before retrying. Default 1s.
    """

    def __init__(
        self,
        pool: Any,
        queue_name: str,
        *,
        maxlen: int = 0,
        brpop_timeout: float = 1.0,
    ) -> None:
        self._queue_name = queue_name
        self._maxlen = maxlen
        self._brpop_timeout = brpop_timeout
        self._closed = False
        # Lazy import to avoid hard dependency on redis
        try:
            import redis.asyncio as aioredis
            self._redis: aioredis.Redis = aioredis.Redis(connection_pool=pool)
        except ImportError:
            raise ImportError("RedisMailbox requires 'redis' package. Install with: uv add redis[hiredis]")

    # Lua script for atomic bounded push: check length then push
    _LUA_BOUNDED_PUSH = """
    if tonumber(ARGV[2]) > 0 and redis.call('llen', KEYS[1]) >= tonumber(ARGV[2]) then
        return 0
    end
    redis.call('lpush', KEYS[1], ARGV[1])
    return 1
    """

    async def put(self, msg: Any) -> bool:
        if self._closed:
            return False
        data = _serialize(msg)
        if self._maxlen > 0:
            # Atomic check+push via Lua script to avoid TOCTOU race
            result = await self._redis.evalsha_or_eval(self._LUA_BOUNDED_PUSH, 1, self._queue_name, data, self._maxlen)
            return bool(result)
        await self._redis.lpush(self._queue_name, data)
        return True

    def put_nowait(self, msg: Any) -> bool:
        """Redis cannot do synchronous non-blocking enqueue reliably.

        Returns False so the caller uses dead-letter or task.cancel() fallback.
        Use ``put()`` (async) for reliable delivery.
        """
        return False

    async def get(self) -> Any:
        """Blocking dequeue via BRPOP. Retries until a message arrives."""
        while not self._closed:
            result = await self._redis.brpop(self._queue_name, timeout=self._brpop_timeout)
            if result is not None:
                _, data = result
                return _deserialize(data)
        raise Empty("mailbox closed")

    def get_nowait(self) -> Any:
        raise Empty("Redis mailbox does not support synchronous get_nowait")

    def empty(self) -> bool:
        # Cannot query Redis synchronously. Return True so drain loops
        # terminate immediately and rely on get_nowait raising Empty.
        return True

    @property
    def full(self) -> bool:
        # Cannot query Redis synchronously. Backpressure enforced
        # atomically inside put() via Lua script.
        return False

    async def close(self) -> None:
        self._closed = True
        await self._redis.aclose()
