from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

from playwright.async_api import Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, async_playwright

from .console import ConsoleRecorder, ConsoleStreamServer
from .errors import to_ai_friendly_error
from .snapshot import EnhancedSnapshot, SnapshotOptions, get_enhanced_snapshot
from .storage import cookies_clear, cookies_get, cookies_set, storage_clear, storage_get, storage_set
from .streaming import StreamServer


@dataclass
class PageState:
    page: Page
    refs: Dict[str, Any] = field(default_factory=dict)
    console: ConsoleRecorder = field(default_factory=ConsoleRecorder)
    stream_server: Optional[StreamServer] = None
    console_server: Optional[ConsoleStreamServer] = None


class AgentBrowser:
    """
    A minimal Playwright wrapper designed for AI agents and humans.

    It manages the browser lifecycle, provides an accessibility snapshot with stable refs,
    and exposes a small set of high-level actions to reduce caller complexity.
    """

    def __init__(
        self,
        headless: bool = True,
        viewport: tuple[int, int] = (1280, 720),
        user_agent: Optional[str] = None,
        timeout_ms: int = 30000,
        locale: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> None:
        """
        Create an AgentBrowser instance.

        Args:
            headless: Whether to run the browser in headless mode.
            viewport: Default viewport size as (width, height).
            user_agent: Custom user agent string for the browser context.
            timeout_ms: Default timeout (ms) for Playwright operations.
            locale: Browser context locale.
            timezone: Browser context timezone id.

        Returns:
            None
        """
        self._headless = headless
        self._viewport = viewport
        self._user_agent = user_agent
        self._timeout_ms = timeout_ms
        self._locale = locale
        self._timezone = timezone
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._pages: Dict[str, PageState] = {}
        self._page_counter = 0

    async def start(self) -> None:
        """
        Start Playwright and launch the browser (idempotent).

        Args:
            None

        Returns:
            None
        """
        if self._browser:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context(
            viewport={"width": self._viewport[0], "height": self._viewport[1]},
            user_agent=self._user_agent,
            locale=self._locale,
            timezone_id=self._timezone,
        )

    async def open(self, url: str) -> str:
        """
        Open a new page and navigate to the given URL.

        Args:
            url: Target URL to navigate to.

        Returns:
            A page_id string that identifies the opened page in this AgentBrowser instance.
        """
        await self.start()
        if not self._context:
            raise RuntimeError("浏览器上下文未初始化")
        page = await self._context.new_page()
        page.set_default_timeout(self._timeout_ms)
        await page.goto(url, wait_until="domcontentloaded")
        return self._register_page(page)

    def _register_page(self, page: Page) -> str:
        self._page_counter += 1
        page_id = f"p{self._page_counter}"
        page.set_default_timeout(self._timeout_ms)
        state = PageState(page=page)
        state.console.attach(page)
        self._pages[page_id] = state
        return page_id

    async def close(self, page_id: Optional[str] = None) -> None:
        """
        Close a page or the entire browser session.

        Args:
            page_id: If provided, closes only the given page. If None, closes all pages and
                shuts down the browser and Playwright.

        Returns:
            None
        """
        if page_id:
            state = self._pages.pop(page_id, None)
            if state:
                if state.stream_server:
                    await state.stream_server.stop()
                if state.console_server:
                    await state.console_server.stop()
                await state.page.close()
            return

        for pid in list(self._pages.keys()):
            await self.close(pid)

        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def _get_state(self, page_id: str) -> PageState:
        if page_id not in self._pages:
            raise KeyError(f"未知的 page_id: {page_id}")
        return self._pages[page_id]

    async def snapshot(
        self,
        page_id: str,
        interactive: bool = False,
        max_depth: Optional[int] = None,
        compact: bool = False,
        selector: Optional[str] = None,
    ) -> EnhancedSnapshot:
        """
        Get an accessibility snapshot of the page and generate stable refs.

        Args:
            page_id: Target page id returned by open().
            interactive: If True, only include interactive elements in the snapshot.
            max_depth: Optional maximum tree depth to include.
            compact: If True, filter out purely structural unnamed nodes.
            selector: Optional CSS selector to scope the snapshot.

        Returns:
            An EnhancedSnapshot object with:
            - tree: Human-readable accessibility tree text.
            - refs: A mapping from ref id (e.g. "e3", used as "@e3" in actions) to a locator description.
        """
        state = self._get_state(page_id)
        options = SnapshotOptions(
            interactive=interactive,
            max_depth=max_depth,
            compact=compact,
            selector=selector,
        )
        snapshot = await get_enhanced_snapshot(state.page, options)
        state.refs = snapshot.refs
        return snapshot

    def _resolve_ref_locator(self, state: PageState, ref_id: str):
        if ref_id not in state.refs:
            raise KeyError(f"未知的 ref: {ref_id}")
        target = state.refs[ref_id]
        if target.name:
            locator = state.page.get_by_role(target.role, name=target.name, exact=True)
        else:
            locator = state.page.get_by_role(target.role)
        if target.nth is not None:
            locator = locator.nth(target.nth)
        return locator

    def _get_locator(self, state: PageState, selector_or_ref: str):
        if selector_or_ref.startswith("@"):
            return self._resolve_ref_locator(state, selector_or_ref[1:])
        return state.page.locator(selector_or_ref)

    async def click(self, page_id: str, selector_or_ref: str) -> dict:
        """
        Click an element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector (e.g. "#submit") or ref (e.g. "@e3").

        Returns:
            A dict describing what happened, including whether a new page was opened.
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        return await self._click_locator(state, locator, selector=selector_or_ref)

    async def _click_locator(self, state: PageState, locator, selector: str) -> dict:
        url_before = state.page.url
        popup_timeout_ms = min(1500, self._timeout_ms)
        new_page: Optional[Page] = None

        try:
            if self._context:
                try:
                    async with self._context.expect_page(timeout=popup_timeout_ms) as page_info:
                        await locator.click()
                    new_page = await page_info.value
                except PlaywrightTimeoutError:
                    new_page = None
            else:
                await locator.click()
        except Exception as error:
            raise to_ai_friendly_error(error, selector) from error

        new_pages: list[dict] = []
        if new_page:
            new_page_id = self._register_page(new_page)
            new_pages.append({"page_id": new_page_id, "url": new_page.url})

        return {
            "clicked": True,
            "url_before": url_before,
            "url_after": state.page.url,
            "opened_new_page": len(new_pages) > 0,
            "new_page_ids": [p["page_id"] for p in new_pages],
            "new_pages": new_pages,
        }

    async def fill(self, page_id: str, selector_or_ref: str, text: str) -> None:
        """
        Clear and fill an input element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").
            text: Text to fill into the element.

        Returns:
            None
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        try:
            await locator.fill(text)
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error

    async def select(self, page_id: str, selector_or_ref: str, value: str) -> None:
        """
        Select an option in a <select> element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").
            value: Option value to select.

        Returns:
            None
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        try:
            await locator.select_option(value=value)
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error

    async def check(self, page_id: str, selector_or_ref: str) -> None:
        """
        Check a checkbox.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").

        Returns:
            None
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        try:
            await locator.check()
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error

    async def uncheck(self, page_id: str, selector_or_ref: str) -> None:
        """
        Uncheck a checkbox.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").

        Returns:
            None
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        try:
            await locator.uncheck()
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error

    async def upload(self, page_id: str, selector_or_ref: str, files: Iterable[str]) -> None:
        """
        Upload files via an <input type="file"> element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").
            files: File paths to upload.

        Returns:
            None
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        try:
            await locator.set_input_files(list(files))
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error

    async def inner_html(self, page_id: str, selector_or_ref: str) -> str:
        """
        Get the innerHTML of an element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").

        Returns:
            The element's innerHTML.
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        try:
            return await locator.inner_html()
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error

    async def find(
        self,
        page_id: str,
        strategy: str,
        action: str,
        value: Optional[str] = None,
        name: Optional[str] = None,
        selector: Optional[str] = None,
        nth: Optional[int] = None,
        action_value: Optional[str] = None,
        files: Optional[Iterable[str]] = None,
    ) -> Any:
        """
        Locate an element using a strategy, then perform an action on it.

        Args:
            page_id: Target page id returned by open().
            strategy: One of:
                "role", "text", "label", "placeholder", "alt", "title", "testid",
                "first", "last", "nth", "css".
            action: One of:
                "click", "fill", "select", "check", "uncheck", "upload",
                "inner_html", "text", "value", "hover", "count",
                "is_visible", "is_enabled", "is_checked".
            value: Strategy input value (e.g. role name / text / label / test id).
            name: Accessible name (only used when strategy="role").
            selector: CSS selector (used when strategy is "first"/"last"/"nth"/"css").
            nth: Index (used when strategy="nth").
            action_value: Action input value (required for action="fill" and action="select").
            files: Files to upload (required for action="upload").

        Returns:
            A dict-like result for query actions (e.g. {"text": "..."}), or an ack dict for
            operation actions (e.g. click returns a dict including opened_new_page/new_page_ids).
        """
        state = self._get_state(page_id)
        page = state.page
        locator = None

        if strategy == "role":
            if not value:
                raise ValueError("strategy=role 需要 value 作为 role 名称")
            locator = page.get_by_role(value, name=name, exact=True)
        elif strategy == "text":
            if not value:
                raise ValueError("strategy=text 需要 value 作为文本内容")
            locator = page.get_by_text(value)
        elif strategy == "label":
            if not value:
                raise ValueError("strategy=label 需要 value 作为 label 文本")
            locator = page.get_by_label(value)
        elif strategy == "placeholder":
            if not value:
                raise ValueError("strategy=placeholder 需要 value 作为 placeholder 文本")
            locator = page.get_by_placeholder(value)
        elif strategy == "alt":
            if not value:
                raise ValueError("strategy=alt 需要 value 作为 alt 文本")
            locator = page.get_by_alt_text(value)
        elif strategy == "title":
            if not value:
                raise ValueError("strategy=title 需要 value 作为 title 文本")
            locator = page.get_by_title(value)
        elif strategy == "testid":
            if not value:
                raise ValueError("strategy=testid 需要 value 作为 test id")
            locator = page.get_by_test_id(value)
        elif strategy == "first":
            if not selector:
                raise ValueError("strategy=first 需要 selector")
            locator = page.locator(selector).first
        elif strategy == "last":
            if not selector:
                raise ValueError("strategy=last 需要 selector")
            locator = page.locator(selector).last
        elif strategy == "nth":
            if not selector or nth is None:
                raise ValueError("strategy=nth 需要 selector 与 nth")
            locator = page.locator(selector).nth(nth)
        elif strategy == "css":
            if not selector:
                raise ValueError("strategy=css 需要 selector")
            locator = page.locator(selector)
        else:
            raise ValueError(f"未知的 strategy: {strategy}")

        selector_label = f"{strategy}:{value or selector or name or ''}".strip(":")
        return await self._perform_action(
            state, locator, action, value=action_value, files=files, selector=selector_label
        )

    async def _perform_action(
        self,
        state: PageState,
        locator,
        action: str,
        value: Optional[str],
        files: Optional[Iterable[str]],
        selector: str,
    ) -> Any:
        try:
            if action == "click":
                return await self._click_locator(state, locator, selector=selector)
            if action == "fill":
                if value is None:
                    raise ValueError("action=fill 需要 action_value 参数")
                await locator.fill(value)
                return {"filled": True}
            if action == "select":
                if value is None:
                    raise ValueError("action=select 需要 action_value 参数")
                await locator.select_option(value=value)
                return {"selected": True}
            if action == "check":
                await locator.check()
                return {"checked": True}
            if action == "uncheck":
                await locator.uncheck()
                return {"unchecked": True}
            if action == "upload":
                if files is None:
                    raise ValueError("action=upload 需要 files 参数")
                await locator.set_input_files(list(files))
                return {"uploaded": True}
            if action == "inner_html":
                return {"inner_html": await locator.inner_html()}
            if action == "text":
                return {"text": await locator.inner_text()}
            if action == "value":
                return {"value": await locator.input_value()}
            if action == "hover":
                await locator.hover()
                return {"hovered": True}
            if action == "count":
                return {"count": await locator.count()}
            if action == "is_visible":
                return {"visible": await locator.is_visible()}
            if action == "is_enabled":
                return {"enabled": await locator.is_enabled()}
            if action == "is_checked":
                return {"checked": await locator.is_checked()}
        except Exception as error:
            raise to_ai_friendly_error(error, selector) from error

        raise ValueError(f"未知的 action: {action}")

    async def back(self, page_id: str, steps: int = 1) -> dict:
        """
        Navigate back in the page history.

        Args:
            page_id: Target page id returned by open().
            steps: Number of back navigations to attempt.

        Returns:
            A dict describing whether the page navigated back and the current URL.
        """
        state = self._get_state(page_id)
        went_back = False
        last_status: Optional[int] = None

        for _ in range(max(1, steps)):
            try:
                response = await state.page.go_back(wait_until="domcontentloaded")
            except Exception as error:
                raise to_ai_friendly_error(error, "back") from error
            if response is None:
                break
            went_back = True
            last_status = response.status

        result: dict[str, Any] = {"went_back": went_back, "url": state.page.url}
        if last_status is not None:
            result["status"] = last_status
        return result

    async def cookies_get(self, page_id: str) -> list[dict]:
        """
        Get all cookies from the current browser context.

        Args:
            page_id: Target page id returned by open().

        Returns:
            A list of cookie dicts compatible with Playwright.
        """
        state = self._get_state(page_id)
        return await cookies_get(state.page)

    async def cookies_set(self, page_id: str, cookies: list[dict]) -> None:
        """
        Set cookies on the current browser context.

        Args:
            page_id: Target page id returned by open().
            cookies: A list of cookie dicts compatible with Playwright.

        Returns:
            None
        """
        state = self._get_state(page_id)
        await cookies_set(state.page, cookies)

    async def cookies_clear(self, page_id: str) -> None:
        """
        Clear all cookies in the current browser context.

        Args:
            page_id: Target page id returned by open().

        Returns:
            None
        """
        state = self._get_state(page_id)
        await cookies_clear(state.page)

    async def storage_get(
        self, page_id: str, storage: str = "local", keys: Optional[Iterable[str]] = None
    ) -> Dict[str, Any]:
        """
        Read localStorage or sessionStorage values.

        Args:
            page_id: Target page id returned by open().
            storage: "local" or "session".
            keys: Optional keys to read. If omitted, reads all entries.

        Returns:
            A dict mapping keys to values.
        """
        state = self._get_state(page_id)
        return await storage_get(state.page, storage, keys)

    async def storage_set(self, page_id: str, items: Dict[str, Any], storage: str = "local") -> None:
        """
        Write values to localStorage or sessionStorage.

        Args:
            page_id: Target page id returned by open().
            items: Key-value pairs to write.
            storage: "local" or "session".

        Returns:
            None
        """
        state = self._get_state(page_id)
        await storage_set(state.page, storage, items)

    async def storage_clear(self, page_id: str, storage: str = "local") -> None:
        """
        Clear localStorage or sessionStorage.

        Args:
            page_id: Target page id returned by open().
            storage: "local" or "session".

        Returns:
            None
        """
        state = self._get_state(page_id)
        await storage_clear(state.page, storage)

    async def console_get(
        self, page_id: str, since: Optional[float] = None, limit: int = 200
    ) -> list[dict]:
        """
        Get collected console messages from the page.

        Args:
            page_id: Target page id returned by open().
            since: Unix timestamp (seconds). If provided, only returns entries after it.
            limit: Max number of entries to return.

        Returns:
            A list of console entry dicts: timestamp/type/text/location/args.
        """
        state = self._get_state(page_id)
        entries = state.console.get_entries(since=since, limit=limit)
        return [
            {
                "timestamp": entry.timestamp,
                "type": entry.type,
                "text": entry.text,
                "location": entry.location,
                "args": entry.args,
            }
            for entry in entries
        ]

    async def console_stream_start(self, page_id: str, host: str = "127.0.0.1", port: int = 9224) -> int:
        """
        Start a WebSocket console stream server for the page.

        Args:
            page_id: Target page id returned by open().
            host: Bind host.
            port: Bind port.

        Returns:
            The port number used by the server.
        """
        state = self._get_state(page_id)
        if state.console_server:
            return port
        state.console_server = ConsoleStreamServer(state.console, host=host, port=port)
        await state.console_server.start()
        return port

    async def console_stream_stop(self, page_id: str) -> None:
        """
        Stop the WebSocket console stream server for the page.

        Args:
            page_id: Target page id returned by open().

        Returns:
            None
        """
        state = self._get_state(page_id)
        if state.console_server:
            await state.console_server.stop()
            state.console_server = None

    async def stream_start(
        self,
        page_id: str,
        on_frame,
        on_status=None,
        image_format: str = "jpeg",
        quality: int = 80,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        every_nth_frame: Optional[int] = None,
    ) -> StreamServer:
        """
        Start streaming the page viewport via callbacks.

        Args:
            page_id: Target page id returned by open().
            on_frame: Callback invoked for each frame payload.
            on_status: Optional callback invoked for status payload updates.
            image_format: "jpeg" or "png" for emitted frame data.
            quality: JPEG quality (only used when image_format="jpeg").
            max_width: Optional max width for CDP screencast.
            max_height: Optional max height for CDP screencast.
            every_nth_frame: Optional frame sampling for CDP screencast.

        Returns:
            The StreamServer instance bound to this page.
        """
        state = self._get_state(page_id)
        if state.stream_server:
            return state.stream_server
        state.stream_server = StreamServer(
            state.page,
            on_frame=on_frame,
            on_status=on_status,
            image_format=image_format,
            quality=quality,
            max_width=max_width,
            max_height=max_height,
            every_nth_frame=every_nth_frame,
        )
        await state.stream_server.start()
        return state.stream_server

    async def stream_stop(self, page_id: str) -> None:
        """
        Stop streaming for the given page.

        Args:
            page_id: Target page id returned by open().

        Returns:
            None
        """
        state = self._get_state(page_id)
        if state.stream_server:
            await state.stream_server.stop()
            state.stream_server = None

    async def stream_inject_mouse(
        self,
        page_id: str,
        event_type: str,
        x: float,
        y: float,
        button: str = "none",
        click_count: int = 1,
        delta_x: float = 0,
        delta_y: float = 0,
        modifiers: int = 0,
    ) -> None:
        """
        Inject a mouse event into the page (requires an active stream/CDP session).

        Args:
            page_id: Target page id returned by open().
            event_type: CDP mouse event type (e.g. "mouseMoved", "mousePressed").
            x: X coordinate in page viewport space.
            y: Y coordinate in page viewport space.
            button: "left", "right", "middle", or "none".
            click_count: Click count.
            delta_x: Horizontal wheel delta.
            delta_y: Vertical wheel delta.
            modifiers: Modifier bitmask (CDP).

        Returns:
            None
        """
        state = self._get_state(page_id)
        if state.stream_server:
            await state.stream_server.inject_mouse(
                event_type=event_type,
                x=x,
                y=y,
                button=button,
                click_count=click_count,
                delta_x=delta_x,
                delta_y=delta_y,
                modifiers=modifiers,
            )

    async def stream_inject_keyboard(
        self,
        page_id: str,
        event_type: str,
        key: Optional[str] = None,
        code: Optional[str] = None,
        text: Optional[str] = None,
        modifiers: int = 0,
    ) -> None:
        """
        Inject a keyboard event into the page (requires an active stream/CDP session).

        Args:
            page_id: Target page id returned by open().
            event_type: CDP key event type (e.g. "keyDown", "keyUp", "char").
            key: Key value (e.g. "A", "Enter").
            code: Physical key code (e.g. "KeyA").
            text: Text to input (for "char" events).
            modifiers: Modifier bitmask (CDP).

        Returns:
            None
        """
        state = self._get_state(page_id)
        if state.stream_server:
            await state.stream_server.inject_keyboard(
                event_type=event_type,
                key=key,
                code=code,
                text=text,
                modifiers=modifiers,
            )

    async def stream_inject_touch(
        self,
        page_id: str,
        event_type: str,
        touch_points: list[Dict[str, Any]],
        modifiers: int = 0,
    ) -> None:
        """
        Inject a touch event into the page (requires an active stream/CDP session).

        Args:
            page_id: Target page id returned by open().
            event_type: CDP touch event type (e.g. "touchStart", "touchMove").
            touch_points: CDP touchPoints array.
            modifiers: Modifier bitmask (CDP).

        Returns:
            None
        """
        state = self._get_state(page_id)
        if state.stream_server:
            await state.stream_server.inject_touch(
                event_type=event_type, touch_points=touch_points, modifiers=modifiers
            )

    async def get_url(self, page_id: str) -> str:
        """
        Get the current URL of the page.

        Args:
            page_id: Target page id returned by open().

        Returns:
            The current page URL.
        """
        state = self._get_state(page_id)
        return state.page.url

    async def get_title(self, page_id: str) -> str:
        """
        Get the current document title of the page.

        Args:
            page_id: Target page id returned by open().

        Returns:
            The page title string.
        """
        state = self._get_state(page_id)
        return await state.page.title()
