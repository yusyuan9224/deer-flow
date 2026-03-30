"""Pluggable mailbox abstraction — Akka-inspired enqueue/dequeue interface.

Built-in implementations:
- ``MemoryMailbox``: asyncio.Queue backed (default)
- Extend ``Mailbox`` for Redis, RabbitMQ, Kafka, etc.
"""

from __future__ import annotations

import abc
import asyncio
from typing import Any


class Mailbox(abc.ABC):
    """Abstract mailbox — the message queue for an actor.

    Implementations must be async-safe for single-consumer usage.
    Multiple producers may call ``put`` concurrently.
    """

    @abc.abstractmethod
    async def put(self, msg: Any) -> bool:
        """Enqueue a message. Returns True if accepted, False if dropped."""

    @abc.abstractmethod
    def put_nowait(self, msg: Any) -> bool:
        """Non-blocking enqueue. Returns True if accepted, False if dropped."""

    @abc.abstractmethod
    async def get(self) -> Any:
        """Dequeue the next message. Blocks until available."""

    @abc.abstractmethod
    def get_nowait(self) -> Any:
        """Non-blocking dequeue. Raises ``Empty`` if no message."""

    @abc.abstractmethod
    def empty(self) -> bool:
        """Return True if no messages are queued."""

    @property
    @abc.abstractmethod
    def full(self) -> bool:
        """Return True if mailbox is at capacity."""

    async def close(self) -> None:
        """Release resources. Default is no-op."""


class Empty(Exception):
    """Raised by ``get_nowait`` when mailbox is empty."""


class MemoryMailbox(Mailbox):
    """In-process mailbox backed by ``asyncio.Queue``."""

    def __init__(self, maxsize: int = 256) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=maxsize)
        self._maxsize = maxsize

    async def put(self, msg: Any) -> bool:
        try:
            await self._queue.put(msg)
            return True
        except asyncio.QueueFull:
            return False

    def put_nowait(self, msg: Any) -> bool:
        try:
            self._queue.put_nowait(msg)
            return True
        except asyncio.QueueFull:
            return False

    async def get(self) -> Any:
        return await self._queue.get()

    def get_nowait(self) -> Any:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            raise Empty("mailbox empty")

    def empty(self) -> bool:
        return self._queue.empty()

    @property
    def full(self) -> bool:
        return self._queue.full()


# Type alias for mailbox factory
MailboxFactory = type[Mailbox] | Any  # Callable[[], Mailbox]
