from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from playwright.async_api import Page


async def cookies_get(page: Page) -> list[dict]:
    """
    获取当前上下文的全部 cookies。
    """
    return await page.context.cookies()


async def cookies_set(page: Page, cookies: list[dict]) -> None:
    """
    设置 cookies，cookies 的结构与 Playwright 保持一致。
    """
    await page.context.add_cookies(cookies)


async def cookies_clear(page: Page) -> None:
    """
    清空当前上下文的 cookies。
    """
    await page.context.clear_cookies()


async def storage_get(page: Page, storage: str, keys: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """
    获取 localStorage 或 sessionStorage。
    """
    storage_key = "localStorage" if storage == "local" else "sessionStorage"
    if keys:
        script = """
        (storageName, keys) => {
            const storage = window[storageName];
            const result = {};
            for (const key of keys) {
                result[key] = storage.getItem(key);
            }
            return result;
        }
        """
        return await page.evaluate(script, storage_key, list(keys))

    script = """
    (storageName) => {
        const storage = window[storageName];
        const result = {};
        for (let i = 0; i < storage.length; i++) {
            const key = storage.key(i);
            result[key] = storage.getItem(key);
        }
        return result;
    }
    """
    return await page.evaluate(script, storage_key)


async def storage_set(page: Page, storage: str, items: Dict[str, Any]) -> None:
    """
    写入 localStorage 或 sessionStorage。
    """
    storage_key = "localStorage" if storage == "local" else "sessionStorage"
    script = """
    (storageName, items) => {
        const storage = window[storageName];
        for (const [key, value] of Object.entries(items)) {
            storage.setItem(key, value === null || value === undefined ? "" : String(value));
        }
    }
    """
    await page.evaluate(script, storage_key, items)


async def storage_clear(page: Page, storage: str) -> None:
    """
    清空 localStorage 或 sessionStorage。
    """
    storage_key = "localStorage" if storage == "local" else "sessionStorage"
    script = """
    (storageName) => {
        window[storageName].clear();
    }
    """
    await page.evaluate(script, storage_key)
