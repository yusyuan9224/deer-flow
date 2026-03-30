"""Async Actor framework — lightweight, asyncio-native, supervision-ready.

Usage::

    from deerflow.actor import Actor, ActorSystem

    class Greeter(Actor):
        async def on_receive(self, message):
            return f"Hello, {message}!"

    async def main():
        system = ActorSystem("app")
        ref = await system.spawn(Greeter, "greeter")
        reply = await ref.ask("World", timeout=5.0)
        print(reply)  # Hello, World!
        await system.shutdown()
"""

from .actor import Actor, ActorContext
from .mailbox import Mailbox, MemoryMailbox
from .middleware import Middleware
from .ref import ActorRef, ReplyChannel
from .supervision import AllForOneStrategy, Directive, OneForOneStrategy, SupervisorStrategy
from .system import ActorSystem, DeadLetter

__all__ = [
    "Actor",
    "ActorContext",
    "ActorRef",
    "ActorSystem",
    "AllForOneStrategy",
    "DeadLetter",
    "Directive",
    "Mailbox",
    "MemoryMailbox",
    "Middleware",
    "OneForOneStrategy",
    "ReplyChannel",
    "SupervisorStrategy",
]
