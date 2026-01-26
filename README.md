# Agent Browser Python 使用文档

## 安装

```bash
pip install -e .
python -m playwright install
```

## 快速开始

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

## 核心 API

### 页面与快照
- open(url) -> page_id
- close(page_id=None)
- snapshot(page_id, interactive=False, max_depth=None, compact=False, selector=None)

### 基础交互
- click(page_id, selector_or_ref) -> dict (包含是否打开新页面与新 page_id)
- back(page_id, steps=1) -> dict
- fill(page_id, selector_or_ref, text)
- select(page_id, selector_or_ref, value)
- check(page_id, selector_or_ref)
- uncheck(page_id, selector_or_ref)
- upload(page_id, selector_or_ref, files)
- inner_html(page_id, selector_or_ref)

说明：snapshot 输出的 ref 使用格式 @eN（例如 @e3），交互 API 也只支持 @eN 形式的 ref。


### 统一 find 接口

```python
await browser.find(
    page_id,
    strategy="role",      # role/text/label/placeholder/alt/title/testid/first/last/nth/css
    value="button",       # role/text/label/placeholder/alt/title/testid 的 value
    name="提交",          # role 的 name
    selector="a.item",    # first/last/nth/css 的 selector
    nth=2,                # nth 的序号
    action="click",       # click/fill/select/check/uncheck/upload/inner_html/text/value/hover/count/is_visible/is_enabled/is_checked
    action_value="test@example.com",  # fill/select 使用
    files=["/tmp/a.png"],             # upload 使用
)
```

### Cookie 与 Storage
- cookies_get(page_id)
- cookies_set(page_id, cookies)
- cookies_clear(page_id)
- storage_get(page_id, storage="local", keys=None)
- storage_set(page_id, items, storage="local")
- storage_clear(page_id, storage="local")

### Console
- console_get(page_id, since=None, limit=200)
- console_stream_start(page_id, host="127.0.0.1", port=9224)
- console_stream_stop(page_id)

### 流式预览（回调式）

```python
async def on_frame(payload: dict):
    # payload: {type: "frame", data: base64, metadata: {...}}
    ...

async def on_status(payload: dict):
    # payload: {type: "status", connected: True, screencasting: bool, ...}
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
