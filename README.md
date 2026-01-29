# Agent Browser (Python)

A minimal Playwright wrapper designed for AI agents (and humans).

- Manages the browser lifecycle and pages
- Generates an accessibility snapshot with stable `@eN` refs for interaction
- Exposes a small set of high-level actions with compact, AI-friendly results

## Install

```bash
pip install -e .
python -m playwright install
```

## Quick Start

```python
import asyncio
from agent_browser import AgentBrowser


async def main():
    browser = AgentBrowser(headless=True)
    page_id = await browser.open("https://example.com")

    snapshot = await browser.snapshot(page_id, interactive=True)
    print(snapshot.tree)

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
```

## Snapshot Output Example

Example `snapshot.tree` (truncated):

```text
- document:
  - heading "Example Domain" [ref=@e1]
  - link "More information..." [ref=@e2]
```

The `@eN` values are stable refs within the snapshot. Pass them to action APIs as `"@eN"`.

## Core API (English)

### Pages & Snapshot
- `open(url) -> page_id`
- `close(page_id=None)`
- `snapshot(page_id, interactive=False, max_depth=None, compact=False, selector=None) -> EnhancedSnapshot`

### Basic Actions
All action APIs accept a CSS selector (e.g. `"#submit"`) or a ref (e.g. `"@e3"`).

- `click(page_id, selector_or_ref) -> dict`
  - Includes `url_before/url_after`, `opened_new_page`, `new_page_ids`, and optional download info
- `fill(page_id, selector_or_ref, text) -> dict`
  - Includes the resulting `value`
- `press(page_id, selector_or_ref, key) -> dict`
  - Useful for `"Enter"` after filling a search box
- `select(page_id, selector_or_ref, value) -> dict`
  - Includes the resulting `value`
- `check(page_id, selector_or_ref) -> dict`
- `uncheck(page_id, selector_or_ref) -> dict`
- `upload(page_id, selector_or_ref, files) -> dict`
- `inner_html(page_id, selector_or_ref) -> str`
- `back(page_id, steps=1) -> dict`

Note: `@eN` refs come from `snapshot()` and are accepted by action APIs.

### Unified `find` Interface

```python
result = await browser.find(
    page_id,
    strategy="role",      # role/text/label/placeholder/alt/title/testid/first/last/nth/css
    value="button",       # value for role/text/label/placeholder/alt/title/testid
    name="Submit",        # only used by strategy="role"
    selector="a.item",    # used by first/last/nth/css
    nth=2,                # used by nth
    action="click",       # click/fill/select/press/check/uncheck/upload/inner_html/text/value/hover/count/is_visible/is_enabled/is_checked
    action_value="Enter", # used by fill/select/press
    files=["/tmp/a.png"], # used by upload
)
```

### Cookies & Storage
- `cookies_get(page_id) -> list[dict]`
- `cookies_set(page_id, cookies) -> None`
- `cookies_clear(page_id) -> None`
- `storage_get(page_id, storage="local", keys=None) -> dict`
- `storage_set(page_id, items, storage="local") -> None`
- `storage_clear(page_id, storage="local") -> None`

### Console
- `console_get(page_id, since=None, limit=200) -> list[dict]`
- `console_stream_start(page_id, host="127.0.0.1", port=9224) -> None`
- `console_stream_stop(page_id) -> None`

### Streaming Preview (callbacks)

```python
async def on_frame(payload: dict):
    ...

async def on_status(payload: dict):
    ...

stream = await browser.stream_start(
    page_id,
    on_frame=on_frame,
    on_status=on_status,
    image_format="jpeg",
    quality=80,
)

await browser.stream_inject_mouse(page_id, event_type="mouseMoved", x=100, y=200)
await browser.stream_inject_keyboard(page_id, event_type="keyDown", key="A", text="A")
await browser.stream_inject_touch(
    page_id,
    event_type="touchStart",
    touch_points=[{"x": 100, "y": 200, "id": 1}],
)

await browser.stream_stop(page_id)
```

## 中文介绍

Agent Browser 是一个面向 AI Agent 的 Playwright 轻量封装：

- 管理浏览器生命周期与多页面
- 用 `snapshot()` 生成可读的无障碍树，并为元素生成稳定的 `@eN` 引用
- 提供少量高层动作接口，返回精简结果，降低工具调用与 token 成本

### 典型用法

先 `snapshot()` 拿到 `@eN`，然后用动作接口操作：

```python
snapshot = await browser.snapshot(page_id, interactive=True)
print(snapshot.tree)

await browser.fill(page_id, "@e1", "关键词")
await browser.press(page_id, "@e1", "Enter")
```
