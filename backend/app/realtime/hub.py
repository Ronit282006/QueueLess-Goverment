"""In-process WebSocket fan-out with a Redis pub/sub bridge.

Each API instance keeps its own set of connected sockets. Queue changes are
published to Redis; every instance (including the publisher) receives the
message and forwards it to its own clients — this is what lets multiple
horizontally-scaled FastAPI instances deliver the same live updates.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

from ..services.cache_service import get_redis, publish

logger = logging.getLogger("queueless.realtime")

CHANNEL_PREFIX = "ql:events"


class Hub:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, room: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms.setdefault(room, set()).add(websocket)

    async def disconnect(self, room: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._rooms.get(room, set()).discard(websocket)

    async def send_local(self, room: str, message: dict) -> None:
        for ws in list(self._rooms.get(room, set())):
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(room, ws)

    def publish(self, room: str, message: dict) -> None:
        """Publish to Redis so other instances relay it too."""
        publish(f"{CHANNEL_PREFIX}:{room}", json.dumps(message))

    async def broadcast(self, room: str, message: dict) -> None:
        """Deliver a message to all instances.

        With Redis available we publish and let every instance's listener
        (including this one) relay to its sockets. Without Redis we fall back
        to local-only delivery so single-process dev still works.
        """
        if get_redis() is not None:
            publish(f"{CHANNEL_PREFIX}:{room}", json.dumps(message))
        else:
            await self.send_local(room, message)

    @property
    def connection_count(self) -> int:
        return sum(len(v) for v in self._rooms.values())


hub = Hub()


async def redis_listener() -> None:
    """Background task: relay Redis messages to locally-connected clients."""
    client = get_redis()
    if client is None:
        return
    try:
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        pubsub.psubscribe(f"{CHANNEL_PREFIX}:*")
    except Exception:
        logger.warning("could not start Redis pub/sub listener")
        return
    while True:
        try:
            message = await asyncio.to_thread(pubsub.get_message, timeout=1.0)
            if not message:
                await asyncio.sleep(0.05)
                continue
            channel = message["channel"]
            room = channel.split(":", 2)[-1]
            payload = json.loads(message["data"])
            await hub.send_local(room, payload)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(0.2)