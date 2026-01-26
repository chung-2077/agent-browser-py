from __future__ import annotations

import asyncio
import base64
from typing import Any, Awaitable, Callable, Dict, Optional
from playwright.async_api import Page



class StreamServer:
    """
    通过回调推送浏览器画面，并支持注入用户输入。
    """

    def __init__(
        self,
        page: Page,
        on_frame: Callable[[Dict[str, Any]], Awaitable[None] | None],
        on_status: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None,
        image_format: str = "jpeg",
        quality: int = 80,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        every_nth_frame: Optional[int] = None,
        fallback_interval: float = 0.2,
    ) -> None:
        self._page = page
        self._on_frame = on_frame
        self._on_status = on_status
        self._image_format = image_format
        self._quality = quality
        self._max_width = max_width
        self._max_height = max_height
        self._every_nth_frame = every_nth_frame
        self._fallback_interval = fallback_interval
        self._cdp_session = None
        self._screencast_task: Optional[asyncio.Task] = None
        self._running = False
        self._use_cdp = True

    async def start(self) -> None:
        self._running = True
        await self._emit_status()
        await self._start_screencast()

    async def stop(self) -> None:
        self._running = False
        await self._stop_screencast()

    async def _emit_status(self) -> None:
        if not self._on_status:
            return
        viewport = self._page.viewport_size or {}
        payload = {
            "type": "status",
            "connected": True,
            "screencasting": self._screencast_task is not None,
            "viewportWidth": viewport.get("width"),
            "viewportHeight": viewport.get("height"),
        }
        await self._emit(self._on_status, payload)

    async def _emit_frame(self, payload: Dict[str, Any]) -> None:
        await self._emit(self._on_frame, payload)

    async def _emit(
        self, callback: Callable[[Dict[str, Any]], Awaitable[None] | None], payload: Dict[str, Any]
    ) -> None:
        try:
            result = callback(payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

    async def _start_screencast(self) -> None:
        if self._screencast_task:
            return

        try:
            self._cdp_session = await self._page.context.new_cdp_session(self._page)
        except Exception:
            self._use_cdp = False

        if self._use_cdp and self._cdp_session:
            await self._start_cdp_screencast()
        else:
            self._screencast_task = asyncio.create_task(self._start_fallback_stream())

    async def _start_cdp_screencast(self) -> None:
        params: Dict[str, Any] = {
            "format": self._image_format,
            "quality": self._quality,
        }
        if self._max_width:
            params["maxWidth"] = self._max_width
        if self._max_height:
            params["maxHeight"] = self._max_height
        if self._every_nth_frame:
            params["everyNthFrame"] = self._every_nth_frame

        async def handle_frame(frame: Dict[str, Any]) -> None:
            await self._emit_frame(
                {
                    "type": "frame",
                    "data": frame.get("data"),
                    "metadata": frame.get("metadata", {}),
                }
            )
            await self._cdp_session.send(
                "Page.screencastFrameAck", {"sessionId": frame.get("sessionId")}
            )

        self._cdp_session.on("Page.screencastFrame", lambda frame: asyncio.create_task(handle_frame(frame)))
        await self._cdp_session.send("Page.startScreencast", params)
        self._screencast_task = asyncio.create_task(self._keepalive())

    async def _start_fallback_stream(self) -> None:
        while self._running:
            image_bytes = await self._page.screenshot(
                type="jpeg" if self._image_format == "jpeg" else "png",
                quality=self._quality if self._image_format == "jpeg" else None,
                full_page=False,
            )
            data = base64.b64encode(image_bytes).decode("utf-8")
            await self._emit_frame(
                {
                    "type": "frame",
                    "data": data,
                    "metadata": {
                        "timestamp": asyncio.get_running_loop().time(),
                    },
                }
            )
            await asyncio.sleep(self._fallback_interval)

    async def _keepalive(self) -> None:
        while self._running:
            await asyncio.sleep(1.0)

    async def _stop_screencast(self) -> None:
        if self._screencast_task:
            self._screencast_task.cancel()
            self._screencast_task = None
        if self._cdp_session:
            try:
                await self._cdp_session.send("Page.stopScreencast")
            except Exception:
                pass
            self._cdp_session = None

    async def inject_mouse(
        self,
        event_type: str,
        x: float,
        y: float,
        button: str = "none",
        click_count: int = 1,
        delta_x: float = 0,
        delta_y: float = 0,
        modifiers: int = 0,
    ) -> None:
        if not self._cdp_session:
            return
        await self._cdp_session.send(
            "Input.dispatchMouseEvent",
            {
                "type": event_type,
                "x": x,
                "y": y,
                "button": button,
                "clickCount": click_count,
                "deltaX": delta_x,
                "deltaY": delta_y,
                "modifiers": modifiers,
            },
        )

    async def inject_keyboard(
        self,
        event_type: str,
        key: Optional[str] = None,
        code: Optional[str] = None,
        text: Optional[str] = None,
        modifiers: int = 0,
    ) -> None:
        if not self._cdp_session:
            return
        await self._cdp_session.send(
            "Input.dispatchKeyEvent",
            {
                "type": event_type,
                "key": key,
                "code": code,
                "text": text,
                "modifiers": modifiers,
            },
        )

    async def inject_touch(
        self,
        event_type: str,
        touch_points: list[Dict[str, Any]],
        modifiers: int = 0,
    ) -> None:
        if not self._cdp_session:
            return
        await self._cdp_session.send(
            "Input.dispatchTouchEvent",
            {
                "type": event_type,
                "touchPoints": touch_points,
                "modifiers": modifiers,
            },
        )
