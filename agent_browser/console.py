from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

import websockets
from playwright.async_api import ConsoleMessage, Page


@dataclass
class ConsoleEntry:
    timestamp: float
    type: str
    text: str
    location: Dict[str, Any]
    args: List[Any]


class ConsoleRecorder:
    """
    记录页面 console 事件，并提供查询与订阅能力。
    """

    def __init__(self, max_entries: int = 1000) -> None:
        self._max_entries = max_entries
        self._entries: List[ConsoleEntry] = []
        self._subscribers: Set[Callable[[ConsoleEntry], None]] = set()

    def attach(self, page: Page) -> None:
        page.on("console", self._handle_console)

    def _handle_console(self, message: ConsoleMessage) -> None:
        asyncio.create_task(self._record_entry(message))

    async def _record_entry(self, message: ConsoleMessage) -> None:
        args = []
        for arg in message.args:
            try:
                args.append(await arg.json_value())
            except Exception:
                try:
                    to_string = getattr(arg, "to_string", None)
                    if callable(to_string):
                        args.append(to_string())
                    else:
                        args.append(str(arg))
                except Exception:
                    args.append(None)
        entry = ConsoleEntry(
            timestamp=time.time(),
            type=message.type,
            text=message.text,
            location=message.location,
            args=args,
        )
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

        for subscriber in list(self._subscribers):
            subscriber(entry)

    def get_entries(self, since: Optional[float] = None, limit: int = 200) -> List[ConsoleEntry]:
        if since is None:
            return self._entries[-limit:]
        return [entry for entry in self._entries if entry.timestamp >= since][-limit:]

    def subscribe(self, callback: Callable[[ConsoleEntry], None]) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: Callable[[ConsoleEntry], None]) -> None:
        self._subscribers.discard(callback)


class ConsoleStreamServer:
    """
    通过 WebSocket 推送 console 事件流，方便外部实时观察。
    """

    def __init__(self, recorder: ConsoleRecorder, host: str = "127.0.0.1", port: int = 9224) -> None:
        self._recorder = recorder
        self._host = host
        self._port = port
        self._clients: Set[websockets.WebSocketServerProtocol] = set()
        self._server: Optional[Any] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle_client, self._host, self._port)
        self._recorder.subscribe(self._broadcast_entry)

    async def stop(self) -> None:
        self._recorder.unsubscribe(self._broadcast_entry)
        async with self._lock:
            for client in list(self._clients):
                await client.close()
            self._clients.clear()

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(self, websocket: websockets.WebSocketServerProtocol) -> None:
        async with self._lock:
            self._clients.add(websocket)

        try:
            await websocket.send(json.dumps({"type": "status", "connected": True}))
            async for _ in websocket:
                pass
        finally:
            async with self._lock:
                self._clients.discard(websocket)

    def _broadcast_entry(self, entry: ConsoleEntry) -> None:
        payload = json.dumps(
            {
                "type": "console",
                "data": {
                    "timestamp": entry.timestamp,
                    "type": entry.type,
                    "text": entry.text,
                    "location": entry.location,
                    "args": entry.args,
                },
            }
        )

        async def _send() -> None:
            async with self._lock:
                clients = list(self._clients)
            for client in clients:
                if client.closed:
                    continue
                try:
                    await client.send(payload)
                except Exception:
                    pass

        asyncio.create_task(_send())
