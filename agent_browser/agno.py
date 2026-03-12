from typing import Any, Callable, Dict, List, Optional
from .agent import AgentBrowser
import logging
logger = logging.getLogger(__name__)
try:
    from agno.tools import Toolkit 
except ImportError:
    class Toolkit:
        def __init__(self, *args, **kwargs):
            raise NotImplementedError("Toolkit is not implemented. Please install 'agno' to use this feature.")


class AgentBrowserToolkit(Toolkit):
    max_open_pages: int = 10
    on_page_close: Optional[Callable[[str], None]] = None

    def __init__(self, browser: AgentBrowser):
        self._browser = browser
        self._page_lru: List[str] = []
        super().__init__(
            name="agent_browser",
            tools=[],
            async_tools=[
                (self.open, "open"),
                (self.snapshot, "snapshot"),
                (self.snapshot_index, "snapshot_index"),
                (self.snapshot_search, "snapshot_search"),
                (self.get_url, "get_url"),
                (self.get_title, "get_title"),
                (self.click, "click"),
                (self.back, "back"),
                (self.fill, "fill"),
                (self.press, "press"),
                (self.select, "select"),
                (self.check, "check"),
                (self.uncheck, "uncheck"),
                (self.upload, "upload"),
            ],
            auto_register=True,
            instructions="""
[Web Page Operation Guidelines] First, use open() to obtain the page ID (the foundational parameter for all operations); prioritize calling snapshot_index() to get a page overview (low token consumption; returns headings, landmarks, and interactive elements with stable @eN refs); you can interact directly with these refs, or if you need to view full content of a specific area, call snapshot(selector="@eN") using the reference ID from the index; all interaction operations—such as fill, click, and select—must be executed using the @eN reference returned by the most recent snapshot operation. Note that each snapshot call regenerates references, invalidating previous ones. In dynamic pages, if click/press doesn't trigger a jump, observe changes via snapshot methods.
""",
            add_instructions=True,
        )

    async def start(self) -> None:
        """
        Start Playwright and launch the browser (idempotent).

        Args:
            None

        Returns:
            None
        """
        await self._browser.start()

    async def open(self, url: str) -> str:
        """
        Open a new page and navigate to the given URL.

        Args:
            url: Target URL to navigate to.

        Returns:
            A page_id string that identifies the opened page in this AgentBrowser instance.
        """
        try:
            page_id = await self._browser.open(url)
            self._touch_page(page_id)
            await self._evict_if_needed()
            return page_id
        except Exception as exc:
            logger.error(f"open error: {exc}", exc_info=True)
            return str(exc)

    def _touch_page(self, page_id: str) -> None:
        if page_id in self._page_lru:
            self._page_lru.remove(page_id)
        self._page_lru.append(page_id)

    async def _evict_if_needed(self) -> None:
        max_pages = self.max_open_pages
        if max_pages < 1:
            max_pages = 1
        while len(self._page_lru) > max_pages:
            evicted_page = self._page_lru.pop(0)
            try:
                await self._browser.close(evicted_page)
                callback = self.on_page_close
                if callback:
                    callback(evicted_page)
            except Exception as exc:
                logger.error(f"Failed to close page {evicted_page}: {exc}", exc_info=True)

    async def snapshot(
        self,
        page_id: str,
        interactive: bool = False,
        max_depth: Optional[int] = None,
        compact: bool = False,
        selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get an accessibility snapshot of the page and generate stable refs.

        Args:
            page_id: Target page id returned by open().
            interactive: If True, only include interactive elements in the snapshot.
            max_depth: Optional maximum tree depth to include.
            compact: If True, filter out purely structural unnamed nodes.
            selector: Optional CSS selector or @ref to scope the snapshot.

        Returns:
            Human-readable accessibility tree text.
        """
        try:
            s = await self._browser.snapshot(
                page_id,
                interactive=interactive,
                max_depth=max_depth,
                compact=compact,
                selector=selector,
            )
            return s
        except Exception as exc:
            logger.error(f"snapshot error: {exc}", exc_info=True)
            return str(exc)

    async def snapshot_index(
        self,
        page_id: str,
        text_limit: int = 180,
    ) -> str:
        """
        Build a compact hierarchical index of the page. to help you quickly understand the page content. You can conduct a deeper analysis based on the path or view the complete snapshot of the path via snapshot(selector="@ref").

        Args:
            page_id: Target page id returned by open().
            text_limit: Max length for node labels.
        """
        try:
            return await self._browser.snapshot_index(
                page_id,
                text_limit=text_limit,
            )
        except Exception as exc:
            logger.error(f"snapshot_index error: {exc}", exc_info=True)
            return str(exc)

    async def snapshot_search(
        self,
        page_id: str,
        query: str,
        mode: str = "fuzzy",
        limit: int = 50,
        text_limit: int = 80,
    ) -> str:
        """
        Search for nodes containing query text. Returns the node indices that match the query. You can gain deeper insight by using snapshot_index based on the path or parent path, or view the complete snapshot of the path via snapshot(selector="@ref").

        Args:
            page_id: Target page id returned by open().
            query: Search keyword or regex pattern.
            mode: "fuzzy" for substring match, "regex" for regular expression.
            limit: Maximum number of matches to return.
            text_limit: Max length for node labels.

        """
        try:
            return await self._browser.snapshot_search(
                page_id,
                query=query,
                mode=mode,
                limit=limit,
                text_limit=text_limit,
            )
        except Exception as exc:
            logger.error(f"snapshot_search error: {exc}", exc_info=True)
            return str(exc)

    async def get_url(self, page_id: str) -> str:
        """
        Get the current URL of the page.

        Args:
            page_id: Target page id returned by open().

        Returns:
            The current page URL.
        """
        try:
            return await self._browser.get_url(page_id)
        except Exception as exc:
            logger.error(f"get_url error: {exc}", exc_info=True)
            return str(exc)

    async def get_title(self, page_id: str) -> str:
        """
        Get the current document title of the page.

        Args:
            page_id: Target page id returned by open().

        Returns:
            The page title string.
        """
        try:
            return await self._browser.get_title(page_id)
        except Exception as exc:
            logger.error(f"get_title error: {exc}", exc_info=True)
            return str(exc)

    async def click(self, page_id: str, selector_or_ref: str) -> Dict[str, Any]:
        """
        Click an element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector (e.g. "#submit") or ref (e.g. "@e3") returned by snapshot() or snapshot_index().

        Returns:
            A dict describing what happened (url change, popup, download).
        """
        try:
            return await self._browser.click(page_id, selector_or_ref)
        except Exception as exc:
            logger.error(f"click error: {exc}", exc_info=True)
            return str(exc)

    async def back(self, page_id: str, steps: int = 1) -> Dict[str, Any]:
        """
        Navigate back in the page history.

        Args:
            page_id: Target page id returned by open().
            steps: Number of back navigations to attempt.

        Returns:
            A dict describing whether the page navigated back and the current URL.
        """
        try:
            return await self._browser.back(page_id, steps=steps)
        except Exception as exc:
            logger.error(f"back error: {exc}", exc_info=True)
            return str(exc)

    async def fill(self, page_id: str, selector_or_ref: str, text: str) -> None:
        """
        Clear and fill an input element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3") returned by snapshot() or snapshot_index().
            text: Text to fill into the element.

        Returns:
            A dict describing what happened, including the resulting value.
        """
        try:
            return await self._browser.fill(page_id, selector_or_ref, text)
        except Exception as exc:
            logger.error(f"fill error: {exc}", exc_info=True)
            return str(exc)

    async def press(self, page_id: str, selector_or_ref: str, key: str) -> Dict[str, Any]:
        """
        Press a key on an element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3") returned by snapshot() or snapshot_index().
            key: Playwright key name (e.g. "Enter").

        Returns:
            A dict describing what happened (e.g. url change).
        """
        try:
            return await self._browser.press(page_id, selector_or_ref, key)
        except Exception as exc:
            logger.error(f"press error: {exc}", exc_info=True)
            return str(exc)

    async def select(self, page_id: str, selector_or_ref: str, value: str) -> None:
        """
        Select an option in a <select> element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3") returned by snapshot() or snapshot_index().
            value: Option value to select.

        Returns:
            A dict describing what happened, including the resulting value.
        """
        try:
            return await self._browser.select(page_id, selector_or_ref, value)
        except Exception as exc:
            logger.error(f"select error: {exc}", exc_info=True)
            return str(exc)

    async def check(self, page_id: str, selector_or_ref: str) -> None:
        """
        Check a checkbox.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3") returned by snapshot() or snapshot_index().

        Returns:
            A dict describing what happened, including current checked state.
        """
        try:
            return await self._browser.check(page_id, selector_or_ref)
        except Exception as exc:
            logger.error(f"check error: {exc}", exc_info=True)
            return str(exc)

    async def uncheck(self, page_id: str, selector_or_ref: str) -> None:
        """
        Uncheck a checkbox.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3") returned by snapshot() or snapshot_index().

        Returns:
            A dict describing what happened, including current checked state.
        """
        try:
            return await self._browser.uncheck(page_id, selector_or_ref)
        except Exception as exc:
            logger.error(f"uncheck error: {exc}", exc_info=True)
            return str(exc)

    async def upload(self, page_id: str, selector_or_ref: str, files: List[str]) -> None:
        """
        Upload files via an <input type="file"> element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3") returned by snapshot() or snapshot_index().
            files: File paths to upload.

        Returns:
            A dict describing what happened.
        """
        try:
            return await self._browser.upload(page_id, selector_or_ref, files)
        except Exception as exc:
            logger.error(f"upload error: {exc}", exc_info=True)
            return str(exc)

    async def solve_cf(self, page_id: str) -> bool:
        """
        Solve Cloudflare Turnstile/Challenge captcha. Returns: True if the captcha was found and clicked, False otherwise.

        Args:
            page_id: Target page id returned by open().
        """
        try:
            return await self._browser.solve_cloudflare_captcha(page_id)
        except Exception as exc:
            logger.error(f"solve_cf error: {exc}", exc_info=True)
            return str(exc)


    async def inner_html(self, page_id: str, selector_or_ref: str) -> str:
        """
        Get the innerHTML of an element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3") returned by snapshot() or snapshot_index().

        Returns:
            The element's innerHTML.
        """
        try:
            return await self._browser.inner_html(page_id, selector_or_ref)
        except Exception as exc:
            logger.error(f"inner_html error: {exc}", exc_info=True)
            return str(exc)

    async def find(
        self,
        page_id: str,
        strategy: str,
        value: Optional[str] = None,
        name: Optional[str] = None,
        selector: Optional[str] = None,
        nth: Optional[int] = None,
        action: Optional[str] = None,
        action_value: Optional[str] = None,
        files: Optional[List[str]] = None,
    ) -> Any:
        """
        Locate an element using a strategy, then perform an action on it.

        Args:
            page_id: Target page id returned by open().
            strategy: One of:
                "role", "text", "label", "placeholder", "alt", "title", "testid",
                "first", "last", "nth", "css".
            action: One of:
                "click", "fill", "select", "press", "check", "uncheck", "upload",
                "inner_html", "text", "value", "hover", "count",
                "is_visible", "is_enabled", "is_checked".
            value: Strategy input value (e.g. role name / text / label / test id).
            name: Accessible name (only used when strategy="role").
            selector: CSS selector (used when strategy is "first"/"last"/"nth"/"css").
            nth: Index (used when strategy="nth").
            action_value: Action input value (required for action="fill" and action="select").
            files: Files to upload (required for action="upload").

        Returns:
            A dict describing the action result.
        """
        try:
            return await self._browser.find(
                page_id,
                strategy=strategy,
                value=value,
                name=name,
                selector=selector,
                nth=nth,
                action=action,
                action_value=action_value,
                files=files,
            )
        except Exception as exc:
            logger.error(f"find error: {exc}", exc_info=True)
            return str(exc)

