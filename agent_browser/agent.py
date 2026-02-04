from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

from playwright.async_api import Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, async_playwright

from .console import ConsoleRecorder, ConsoleStreamServer
from .errors import to_ai_friendly_error
from .snapshot import EnhancedSnapshot, SnapshotOptions, get_enhanced_snapshot
from .storage import cookies_clear, cookies_get, cookies_set, storage_clear, storage_get, storage_set
from .streaming import StreamServer


STEALTH_JS = """
// =================================================================================
// 0. Debug & Safety Wrapper
// =================================================================================
console.log("Stealth script starting...");
window.__stealth_debug = [];

function safeStealth(name, fn) {
    try {
        fn();
        window.__stealth_debug.push(name + ": success");
    } catch (e) {
        console.error("Stealth error in " + name, e);
        window.__stealth_debug.push(name + ": error - " + e.message);
    }
}

// =================================================================================
// 1. User Agent & App Version Override
// =================================================================================
safeStealth("webdriver_override", () => {
    // Remove webdriver property completely
    // Accessing the property directly on prototype might trigger Illegal invocation if it's a getter requiring an instance
    // So we use getOwnPropertyDescriptor to check existence safely
    const newProto = Navigator.prototype;
    if (newProto) {
        const desc = Object.getOwnPropertyDescriptor(newProto, 'webdriver');
        if (desc) {
            delete newProto.webdriver;
        }
    }
    if (Object.getOwnPropertyDescriptor(navigator, 'webdriver')) {
        delete navigator.webdriver;
    }
});

// =================================================================================
// 2. Chrome Object Mock
// =================================================================================
safeStealth("chrome_mock", () => {
    if (!window.chrome) {
        window.chrome = {
            app: {
                isInstalled: false,
                InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
            },
            runtime: {
                OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
                OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
                PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
                RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }
            },
            loadTimes: function() {
                return {
                    requestTime: new Date().getTime() / 1000,
                    startLoadTime: new Date().getTime() / 1000,
                    commitLoadTime: new Date().getTime() / 1000,
                    finishDocumentLoadTime: new Date().getTime() / 1000,
                    finishLoadTime: new Date().getTime() / 1000,
                    firstPaintTime: new Date().getTime() / 1000,
                    firstPaintAfterLoadTime: 0,
                    navigationType: 'Other',
                    wasFetchedViaSpdy: false,
                    wasNpnNegotiated: false,
                    npnNegotiatedProtocol: '',
                    wasAlternateProtocolAvailable: false,
                    connectionInfo: 'unknown'
                };
            },
            csi: function() {
                return { startE: new Date().getTime(), onloadT: new Date().getTime(), pageT: new Date().getTime(), tran: 15 };
            }
        };
    }
});

// =================================================================================
// 3. Permissions API
// =================================================================================
safeStealth("permissions_mock", () => {
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );
});

// =================================================================================
// 4. Plugins & MimeTypes (Advanced Mock)
// =================================================================================
safeStealth("plugins_mock", () => {
    // Always overwrite to ensure consistency
    const pluginsData = [
        {
            name: "Chrome PDF Plugin",
            filename: "internal-pdf-viewer",
            description: "Portable Document Format",
            mimeTypes: [{ type: "application/pdf", suffixes: "pdf", description: "Portable Document Format" }, { type: "text/pdf", suffixes: "pdf", description: "Portable Document Format" }]
        },
        {
            name: "Chrome PDF Viewer",
            filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
            description: "",
            mimeTypes: [{ type: "application/pdf", suffixes: "pdf", description: "Portable Document Format" }]
        },
        {
            name: "Native Client",
            filename: "internal-nacl-plugin",
            description: "",
            mimeTypes: [{ type: "application/x-nacl", suffixes: "", description: "Native Client Executable" }, { type: "application/x-pnacl", suffixes: "", description: "Portable Native Client Executable" }]
        }
    ];

    const plugins = [];
    const mimeTypes = [];
    
    pluginsData.forEach(data => {
        const plugin = Object.create(Plugin.prototype);
        Object.defineProperties(plugin, {
            name: { value: data.name, enumerable: true },
            filename: { value: data.filename, enumerable: true },
            description: { value: data.description, enumerable: true },
            length: { value: data.mimeTypes.length, enumerable: true },
        });
        data.mimeTypes.forEach((mimeData, index) => {
            const mimeType = Object.create(MimeType.prototype);
            Object.defineProperties(mimeType, {
                type: { value: mimeData.type, enumerable: true },
                suffixes: { value: mimeData.suffixes, enumerable: true },
                description: { value: mimeData.description, enumerable: true },
                enabledPlugin: { value: plugin, enumerable: true },
            });
            Object.defineProperty(plugin, index, { value: mimeType, enumerable: true });
            Object.defineProperty(plugin, mimeData.type, { value: mimeType, enumerable: false });
            mimeTypes.push(mimeType);
        });
        plugins.push(plugin);
    });
    
    const fakePluginArray = Object.create(PluginArray.prototype);
    Object.defineProperties(fakePluginArray, {
        length: { value: plugins.length, enumerable: true },
        item: { value: (index) => plugins[index], enumerable: false },
        namedItem: { value: (name) => plugins.find(p => p.name === name), enumerable: false },
        refresh: { value: () => {}, enumerable: false }
    });
    // Fix toString tag
    if (window.Symbol && Symbol.toStringTag) {
        Object.defineProperty(fakePluginArray, Symbol.toStringTag, { value: 'PluginArray' });
    }

    plugins.forEach((p, i) => {
        Object.defineProperty(fakePluginArray, i, { value: p, enumerable: true });
        Object.defineProperty(fakePluginArray, p.name, { value: p, enumerable: false });
    });
    
    const fakeMimeTypeArray = Object.create(MimeTypeArray.prototype);
    Object.defineProperties(fakeMimeTypeArray, {
        length: { value: mimeTypes.length, enumerable: true },
        item: { value: (index) => mimeTypes[index], enumerable: false },
        namedItem: { value: (name) => mimeTypes.find(m => m.type === name), enumerable: false }
    });
    // Fix toString tag
    if (window.Symbol && Symbol.toStringTag) {
        Object.defineProperty(fakeMimeTypeArray, Symbol.toStringTag, { value: 'MimeTypeArray' });
    }

    mimeTypes.forEach((m, i) => {
        Object.defineProperty(fakeMimeTypeArray, i, { value: m, enumerable: true });
        // Prevent collision if multiple plugins handle same mimetype
        if (!Object.getOwnPropertyDescriptor(fakeMimeTypeArray, m.type)) {
            Object.defineProperty(fakeMimeTypeArray, m.type, { value: m, enumerable: false });
        }
    });
    
    // Debug info
    window.__debug_plugins_len = fakePluginArray.length;
    
    // Use Navigator.prototype to avoid hasOwnProperty detection
    Object.defineProperty(Navigator.prototype, 'plugins', { 
        get: () => fakePluginArray, 
        enumerable: true, 
        configurable: true 
    });
    
    Object.defineProperty(Navigator.prototype, 'mimeTypes', { 
        get: () => fakeMimeTypeArray, 
        enumerable: true, 
        configurable: true 
    });
});

// =================================================================================
// 5. WebGL Fingerprint Override (WebGL 1 & 2)
// =================================================================================
safeStealth("webgl_mock", () => {
    const overrideWebGL = (contextType) => {
        if (!window[contextType]) return;
        const getParameter = window[contextType].prototype.getParameter;
        window[contextType].prototype.getParameter = function(parameter) {
            // 37445: UNMASKED_VENDOR_WEBGL
            // 37446: UNMASKED_RENDERER_WEBGL
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel(R) Iris(R) Xe Graphics';
            return getParameter.apply(this, arguments);
        };
    };
    overrideWebGL('WebGLRenderingContext');
    overrideWebGL('WebGL2RenderingContext');
});

// =================================================================================
// 6. Hardware Concurrency & Memory
// =================================================================================
safeStealth("hardware_mock", () => {
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
});

// =================================================================================
// 7. Canvas Noise (2D)
// =================================================================================
safeStealth("canvas_noise", () => {
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    
    // Generate stable noise for this session
    // We use a small shift to keep the image looking correct but having a different hash
    const shift = {
        r: Math.floor(Math.random() * 10) - 5,
        g: Math.floor(Math.random() * 10) - 5,
        b: Math.floor(Math.random() * 10) - 5,
        a: Math.floor(Math.random() * 10) - 5
    };
    // Ensure at least one component has some noise to guarantee unique hash
    if (shift.r === 0 && shift.g === 0 && shift.b === 0 && shift.a === 0) {
        shift.r = 1;
    }

    const applyNoise = (data) => {
        // Apply noise to pixel data
        for (let i = 0; i < data.length; i += 4) {
            // R
            data[i] = Math.min(255, Math.max(0, data[i] + shift.r));
            // G
            data[i+1] = Math.min(255, Math.max(0, data[i+1] + shift.g));
            // B
            data[i+2] = Math.min(255, Math.max(0, data[i+2] + shift.b));
            // A (Optional, usually we don't touch alpha to avoid transparency issues, but safe to shift slightly)
            // data[i+3] = Math.min(255, Math.max(0, data[i+3] + shift.a));
        }
    };

    CanvasRenderingContext2D.prototype.getImageData = function(x, y, w, h) {
        try {
            const imageData = originalGetImageData.apply(this, arguments);
            applyNoise(imageData.data);
            return imageData;
        } catch (e) {
            // CORS or other errors
            throw e;
        }
    };

    HTMLCanvasElement.prototype.toDataURL = function(type, encoderOptions) {
        try {
            // Only interfere if we can get a 2D context to read data
            // If it's a WebGL canvas, this returns null
            const context = this.getContext("2d");
            if (context) {
                const width = this.width;
                const height = this.height;
                const imageData = originalGetImageData.call(context, 0, 0, width, height);
                applyNoise(imageData.data);
                
                // Create a temporary canvas to export the noisy data
                const tempCanvas = document.createElement("canvas");
                tempCanvas.width = width;
                tempCanvas.height = height;
                const tempCtx = tempCanvas.getContext("2d");
                tempCtx.putImageData(imageData, 0, 0);
                
                return originalToDataURL.call(tempCanvas, type, encoderOptions);
            }
        } catch (e) {
            // Fallback to original if anything fails (e.g. CORS tainted)
        }
        return originalToDataURL.apply(this, arguments);
    };
});

console.log("Stealth script finished");
"""

COOKIE_BANNER_JS = """
(() => {
    const selectors = [
        "#onetrust-accept-btn-handler",
        "#onetrust-reject-all-handler",
        "button[aria-label*='accept']",
        "button[aria-label*='agree']",
        "button[aria-label*='consent']",
        "button[aria-label*='同意']",
        "button[aria-label*='接受']",
        "[data-testid*='accept']",
        "[data-testid*='agree']",
        "[data-testid*='consent']",
        ".cookie-accept",
        ".cookie-consent-accept",
        ".cc-allow",
        ".cc-accept",
        ".cc-btn",
        ".cookie-banner button",
        ".cookie-consent button"
    ];
    const textMatchers = [
        /accept/i,
        /agree/i,
        /allow all/i,
        /ok/i,
        /got it/i,
        /consent/i,
        /同意/,
        /接受/,
        /允许/,
        /好的/,
        /知道了/,
        /继续/
    ];
    const isVisible = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (!style) return false;
        if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
            return false;
        }
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };
    const clickIfMatch = (el) => {
        if (!el || !(el instanceof Element)) return false;
        if (el.disabled) return false;
        if (!isVisible(el)) return false;
        const text = (el.innerText || el.textContent || "").trim();
        if (!text) return false;
        if (textMatchers.some((matcher) => matcher.test(text))) {
            el.click();
            return true;
        }
        return false;
    };
    const findAndClick = () => {
        let clicked = false;
        for (const sel of selectors) {
            const nodes = document.querySelectorAll(sel);
            for (const node of nodes) {
                if (clickIfMatch(node)) {
                    clicked = true;
                    break;
                }
            }
            if (clicked) return true;
        }
        const candidates = document.querySelectorAll(
            "button, [role='button'], input[type='button'], input[type='submit'], a"
        );
        for (const node of candidates) {
            if (clickIfMatch(node)) {
                clicked = true;
                break;
            }
        }
        return clicked;
    };
    const run = () => {
        let attempts = 0;
        const maxAttempts = 20;
        const intervalMs = 400;
        const timer = window.setInterval(() => {
            attempts += 1;
            const clicked = findAndClick();
            if (clicked || attempts >= maxAttempts) {
                window.clearInterval(timer);
            }
        }, intervalMs);
    };
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", run, { once: true });
    } else {
        run();
    }
    const observer = new MutationObserver(() => {
        findAndClick();
    });
    observer.observe(document.documentElement || document.body, {
        childList: true,
        subtree: true,
        attributes: true
    });
})();
"""


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
        timeout_ms: int = 60000,
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
        self._stream_all_config: Optional[Dict[str, Any]] = None
        self._stream_all_page_ids: set[str] = set()

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

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-zygote",
        ]
        if self._headless:
            args.extend(["--ignore-gpu-blocklist"])

        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=args,
            ignore_default_args=["--enable-automation"],
        )
        
        # 如果未指定 user_agent，则使用去除 Headless 标记的默认 UA
        if not self._user_agent:
            # 简单策略：先获取当前的默认 UA，然后替换
            # 但这里我们无法直接获取（需要 page），所以我们硬编码一个现代 Chrome Mac UA
            # 或者，我们可以启动一个临时页面获取它，但那样太慢。
            # 最佳实践：硬编码一个较新的稳定版 UA。
            self._user_agent = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )

        self._context = await self._browser.new_context(
            viewport={"width": self._viewport[0], "height": self._viewport[1]},
            user_agent=self._user_agent,
            locale=self._locale,
            timezone_id=self._timezone,
        )

        await self._context.add_init_script(STEALTH_JS)

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
        await page.evaluate(COOKIE_BANNER_JS)
        page_id = await self._register_page(page)
        return f"page_id: {page_id}"

    async def _register_page(self, page: Page) -> str:
        self._page_counter += 1
        page_id = f"p{self._page_counter}"
        page.set_default_timeout(self._timeout_ms)
        state = PageState(page=page)
        state.console.attach(page)
        self._pages[page_id] = state
        if self._stream_all_config:
            await self._start_stream_for_page(page_id, self._stream_all_config)
            self._stream_all_page_ids.add(page_id)
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
            self._stream_all_page_ids.discard(page_id)
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

    async def _start_stream_for_page(
        self,
        page_id: str,
        config: Dict[str, Any],
    ) -> StreamServer:
        state = self._get_state(page_id)
        if state.stream_server:
            return state.stream_server
        state.stream_server = StreamServer(
            state.page,
            page_id=page_id,
            on_frame=config["on_frame"],
            on_status=config.get("on_status"),
            image_format=config["image_format"],
            quality=config["quality"],
            max_width=config.get("max_width"),
            max_height=config.get("max_height"),
            every_nth_frame=config.get("every_nth_frame"),
        )
        await state.stream_server.start()
        return state.stream_server

    async def snapshot(
        self,
        page_id: str,
        interactive: bool = False,
        max_depth: Optional[int] = None,
        compact: bool = False,
        selector: Optional[str] = None,
    ) -> str:
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
        return snapshot.tree

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
            A dict describing what happened (url change, popup, download).
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        return await self._click_locator(state, locator, selector=selector_or_ref)

    async def _click_locator(self, state: PageState, locator, selector: str) -> dict:
        url_before = state.page.url
        popup_timeout_ms = min(1500, self._timeout_ms)
        download_timeout_ms = min(1500, self._timeout_ms)
        new_page: Optional[Page] = None
        download = None
        page_task = None
        download_task = None

        try:
            if self._context:
                page_task = asyncio.create_task(
                    self._context.wait_for_event("page", timeout=popup_timeout_ms)
                )
            download_task = asyncio.create_task(
                state.page.wait_for_event("download", timeout=download_timeout_ms)
            )
            await locator.click()
            try:
                await state.page.wait_for_load_state("domcontentloaded", timeout=popup_timeout_ms)
            except PlaywrightTimeoutError:
                pass
        except Exception as error:
            for task in (page_task, download_task):
                if task and not task.done():
                    task.cancel()
            raise to_ai_friendly_error(error, selector) from error

        if page_task:
            try:
                new_page = await page_task
            except PlaywrightTimeoutError:
                new_page = None

        if download_task:
            try:
                download = await download_task
            except PlaywrightTimeoutError:
                download = None

        new_pages: list[dict] = []
        if new_page:
            new_page_id = await self._register_page(new_page)
            new_pages.append({"page_id": new_page_id, "url": new_page.url})

        download_info = None
        if download:
            download_info = {
                "url": download.url,
                "suggested_filename": download.suggested_filename,
            }

        return {
            "clicked": True,
            "url_before": url_before,
            "url_after": state.page.url,
            "opened_new_page": len(new_pages) > 0,
            "new_page_ids": [p["page_id"] for p in new_pages],
            "new_pages": new_pages,
            "downloaded": download_info is not None,
            "download": download_info,
        }

    async def fill(self, page_id: str, selector_or_ref: str, text: str) -> dict:
        """
        Clear and fill an input element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").
            text: Text to fill into the element.

        Returns:
            A dict describing what happened, including the resulting value.
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        try:
            await locator.fill(text)
            value = await locator.input_value()
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error
        return {"filled": True, "value": value, "url": state.page.url}

    async def select(self, page_id: str, selector_or_ref: str, value: str) -> dict:
        """
        Select an option in a <select> element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").
            value: Option value to select.

        Returns:
            A dict describing what happened, including the resulting value.
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        try:
            await locator.select_option(value=value)
            selected = await locator.input_value()
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error
        return {"selected": True, "value": selected, "url": state.page.url}

    async def press(self, page_id: str, selector_or_ref: str, key: str) -> dict:
        """
        Press a key on an element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").
            key: Playwright key name (e.g. "Enter").

        Returns:
            A dict describing what happened (e.g. url change).
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        url_before = state.page.url
        try:
            await locator.press(key)
            try:
                await state.page.wait_for_load_state("domcontentloaded", timeout=min(1500, self._timeout_ms))
            except PlaywrightTimeoutError:
                pass
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error
        return {"pressed": True, "url_before": url_before, "url_after": state.page.url}

    async def check(self, page_id: str, selector_or_ref: str) -> dict:
        """
        Check a checkbox.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").

        Returns:
            A dict describing what happened, including current checked state.
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        try:
            await locator.check()
            checked = await locator.is_checked()
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error
        return {"checked": True, "is_checked": checked, "url": state.page.url}

    async def uncheck(self, page_id: str, selector_or_ref: str) -> dict:
        """
        Uncheck a checkbox.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").

        Returns:
            A dict describing what happened, including current checked state.
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        try:
            await locator.uncheck()
            checked = await locator.is_checked()
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error
        return {"unchecked": True, "is_checked": checked, "url": state.page.url}

    async def upload(self, page_id: str, selector_or_ref: str, files: Iterable[str]) -> dict:
        """
        Upload files via an <input type="file"> element.

        Args:
            page_id: Target page id returned by open().
            selector_or_ref: CSS selector or ref (e.g. "@e3").
            files: File paths to upload.

        Returns:
            A dict describing what happened.
        """
        state = self._get_state(page_id)
        locator = self._get_locator(state, selector_or_ref)
        try:
            await locator.set_input_files(list(files))
        except Exception as error:
            raise to_ai_friendly_error(error, selector_or_ref) from error
        return {"uploaded": True, "url": state.page.url}

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

    async def screenshot(self, page_id: str, path: str, full_page: bool = True) -> None:
        """
        Take a screenshot of the page.

        Args:
            page_id: Target page id returned by open().
            path: File path to save the screenshot.
            full_page: Whether to take a screenshot of the full scrollable page.
        """
        state = self._get_state(page_id)
        await state.page.screenshot(path=path, full_page=full_page)

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
            state,
            locator,
            action,
            value=action_value,
            files=files,
            selector=selector_label,
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
                return {"filled": True, "value": await locator.input_value(), "url": state.page.url}
            if action == "select":
                if value is None:
                    raise ValueError("action=select 需要 action_value 参数")
                await locator.select_option(value=value)
                return {"selected": True, "value": await locator.input_value(), "url": state.page.url}
            if action == "press":
                if value is None:
                    raise ValueError("action=press 需要 action_value 参数")
                url_before = state.page.url
                await locator.press(value)
                try:
                    await state.page.wait_for_load_state("domcontentloaded", timeout=min(1500, self._timeout_ms))
                except PlaywrightTimeoutError:
                    pass
                return {"pressed": True, "url_before": url_before, "url_after": state.page.url}
            if action == "check":
                await locator.check()
                return {"checked": True, "is_checked": await locator.is_checked(), "url": state.page.url}
            if action == "uncheck":
                await locator.uncheck()
                return {"unchecked": True, "is_checked": await locator.is_checked(), "url": state.page.url}
            if action == "upload":
                if files is None:
                    raise ValueError("action=upload 需要 files 参数")
                await locator.set_input_files(list(files))
                return {"uploaded": True, "url": state.page.url}
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
    ) -> StreamServer | Dict[str, StreamServer]:
        """
        Start streaming the page viewport via callbacks.

        Args:
            page_id: Target page id returned by open(), or "*" for all pages.
            on_frame: Callback invoked for each frame payload.
            on_status: Optional callback invoked for status payload updates.
            image_format: "jpeg" or "png" for emitted frame data.
            quality: JPEG quality (only used when image_format="jpeg").
            max_width: Optional max width for CDP screencast.
            max_height: Optional max height for CDP screencast.
            every_nth_frame: Optional frame sampling for CDP screencast.

        Returns:
            StreamServer for a single page, or a mapping for all pages when page_id="*".
        """
        config = {
            "on_frame": on_frame,
            "on_status": on_status,
            "image_format": image_format,
            "quality": quality,
            "max_width": max_width,
            "max_height": max_height,
            "every_nth_frame": every_nth_frame,
        }

        if page_id == "*":
            self._stream_all_config = config
            servers: Dict[str, StreamServer] = {}
            for pid, state in self._pages.items():
                was_running = state.stream_server is not None
                server = await self._start_stream_for_page(pid, config)
                servers[pid] = server
                if not was_running:
                    self._stream_all_page_ids.add(pid)
            return servers

        return await self._start_stream_for_page(page_id, config)

    async def stream_stop(self, page_id: str) -> None:
        """
        Stop streaming for the given page.

        Args:
            page_id: Target page id returned by open(), or "*" for all pages.

        Returns:
            None
        """
        if page_id == "*":
            page_ids = list(self._stream_all_page_ids)
            for pid in page_ids:
                state = self._get_state(pid)
                if state.stream_server:
                    await state.stream_server.stop()
                    state.stream_server = None
            self._stream_all_page_ids.clear()
            self._stream_all_config = None
            return

        state = self._get_state(page_id)
        if state.stream_server:
            await state.stream_server.stop()
            state.stream_server = None
        self._stream_all_page_ids.discard(page_id)

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
