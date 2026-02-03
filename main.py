import sys
import asyncio
import shlex
import base64
import time
from pathlib import Path

from agent_browser import AgentBrowser


def _parse_options(tokens: list[str]) -> dict:
    options: dict[str, object] = {}
    files: list[str] = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token.startswith("--"):
            key = token[2:]
            if key == "file":
                if idx + 1 >= len(tokens):
                    raise ValueError("缺少 --file 参数值")
                files.append(tokens[idx + 1])
                idx += 2
                continue
            if idx + 1 >= len(tokens):
                raise ValueError(f"缺少 --{key} 参数值")
            options[key] = tokens[idx + 1]
            idx += 2
        else:
            idx += 1
    if files:
        options["files"] = files
    return options


async def cli() -> None:
    # 简单的参数解析
    headless = "--headless" in sys.argv
    
    print(f"正在启动浏览器 (Headless: {headless})...")
    # 注意：Playwright 默认使用的就是其绑定的 Chromium，而非系统 Chrome。
    # 除非显式指定 channel="chrome"，否则都是 Chromium。
    browser = AgentBrowser(headless=headless)
    current_page: str | None = None
    known_pages: set[str] = set()
    stream_running = False
    frame_counters: dict[str, int] = {}

    print("Agent Browser CLI 已启动，输入 help 查看命令。")

    async def require_page() -> str:
        if not current_page:
            raise RuntimeError("当前未选择页面，请先执行 open 或 use")
        return current_page

    try:
        while True:
            try:
                line = await asyncio.to_thread(input, "agent> ")
            except EOFError:
                break
            line = line.strip()
            if not line:
                continue
            parts = shlex.split(line)
            command = parts[0].lower()
            args = parts[1:]

            if command in {"exit", "quit"}:
                break
            if command == "help":
                print(
                    "\n".join(
                        [
                            "open <url>",
                            "use <page_id>",
                            "url",
                            "title",
                            "snapshot",
                            "click <selector_or_ref>",
                            "back [steps]",
                            "fill <selector_or_ref> <text>",
                            "select <selector_or_ref> <value>",
                            "check <selector_or_ref>",
                            "uncheck <selector_or_ref>",
                            "upload <selector_or_ref> <file1> [file2...]",
                            "inner_html <selector_or_ref>",
                            "find <strategy> <action> [--value v] [--name n] [--selector s] [--nth n] [--action-value v] [--file f]",
                            "stream_start [--dir output] [--format jpeg|png] [--quality q] [--every_nth n]",
                            "stream_stop",
                            "close [page_id]",
                            "test_stealth",
                            "exit|quit",
                        ]
                    )
                )
                continue

            try:
                if command == "test_stealth":
                    print(f"开始隐身性测试 (当前模式: {'Headless/无头' if headless else 'Headed/有头'})...")
                    if not headless:
                        print("提示: 想要测试最严格的“防爬检测”，建议使用 `python main.py --headless` 启动。")
                        
                    tasks = [
                        ("https://bot.sannysoft.com/", "stealth_sannysoft.png"),
                        ("https://arh.antoinevastel.com/bots/", "stealth_antoinevastel.png")
                    ]
                    for url, filename in tasks:
                        print(f"正在访问 {url} ...")
                        page_id = await browser.open(url)
                        current_page = page_id
                        known_pages.add(page_id)
                        # 等待页面可能的检测脚本执行
                        await asyncio.sleep(5)
                        
                        # 尝试提取关键检测结果并打印
                        try:
                            if "sannysoft" in url:
                                print("--- Sannysoft 检测结果摘要 ---")
                                # 提取 WebDriver 状态
                                result = await browser.find(page_id, strategy="first", action="inner_html", selector="td:has-text('WebDriver') + td")
                                print(f"WebDriver: {result.get('inner_html', 'Unknown')}")
                                # 提取 WebGL Renderer
                                result = await browser.find(page_id, strategy="first", action="inner_html", selector="td:has-text('WebGL Renderer') + td")
                                print(f"WebGL Renderer: {result.get('inner_html', 'Unknown')}")
                                # 提取 Plugins 长度
                                result = await browser.find(page_id, strategy="first", action="inner_html", selector="td:has-text('Plugins Length') + td")
                                print(f"Plugins Length: {result.get('inner_html', 'Unknown')}")
                                # 提取失败项 (红色)
                                failed_result = await browser.find(page_id, strategy="css", action="count", selector=".failed")
                                failed_count = failed_result.get("count", 0)
                                if failed_count > 0:
                                    print(f"检测到的失败项数量: {failed_count}")
                                else:
                                    print("未检测到明显的失败项 (.failed 类)")
                            
                            elif "antoinevastel" in url:
                                print("--- Antoine Vastel 检测结果摘要 ---")
                                # 这个页面结构比较复杂，通常显示 "You are a bot" 或 "You are not a bot"
                                # 尝试抓取标题或主要结论
                                body_text = await browser.inner_html(page_id, "body")
                                if "You are a bot" in body_text:
                                    print("结论: You are a bot (被检测到了)")
                                elif "You are not a bot" in body_text:
                                    print("结论: You are not a bot (通过检测)")
                                else:
                                    print("结论: 未知状态")
                        except Exception as e:
                            print(f"提取检测结果失败: {e}")

                        print(f"正在截图保存到 {filename} ...")
                        await browser.screenshot(page_id, path=filename)
                        print(f"已保存 {filename}")
                    print("测试完成。")
                elif command == "open":
                    if not args:
                        raise ValueError("缺少 url")
                    page_id = await browser.open(args[0])
                    current_page = page_id
                    known_pages.add(page_id)
                    print(f"page_id: {page_id}")
                elif command == "use":
                    if not args:
                        raise ValueError("缺少 page_id")
                    if args[0] not in known_pages:
                        raise ValueError("未知 page_id")
                    current_page = args[0]
                    print(f"当前页面: {current_page}")
                elif command == "url":
                    page_id = await require_page()
                    print(await browser.get_url(page_id))
                elif command == "title":
                    page_id = await require_page()
                    print(await browser.get_title(page_id))
                elif command == "snapshot":
                    page_id = await require_page()
                    snapshot_tree = await browser.snapshot(page_id, interactive=False)
                    print(snapshot_tree)
                elif command == "click":
                    page_id = await require_page()
                    result = await browser.click(page_id, args[0])
                    if result.get("opened_new_page"):
                        for pid in result.get("new_page_ids", []):
                            known_pages.add(pid)
                    print(result)
                elif command == "back":
                    page_id = await require_page()
                    steps = int(args[0]) if args else 1
                    print(await browser.back(page_id, steps=steps))
                elif command == "fill":
                    page_id = await require_page()
                    await browser.fill(page_id, args[0], args[1])
                elif command == "select":
                    page_id = await require_page()
                    await browser.select(page_id, args[0], args[1])
                elif command == "check":
                    page_id = await require_page()
                    await browser.check(page_id, args[0])
                elif command == "uncheck":
                    page_id = await require_page()
                    await browser.uncheck(page_id, args[0])
                elif command == "upload":
                    page_id = await require_page()
                    await browser.upload(page_id, args[0], args[1:])
                elif command == "inner_html":
                    page_id = await require_page()
                    print(await browser.inner_html(page_id, args[0]))
                elif command == "find":
                    page_id = await require_page()
                    if len(args) < 2:
                        raise ValueError("find 需要 strategy 与 action")
                    strategy = args[0]
                    action = args[1]
                    options = _parse_options(args[2:])
                    result = await browser.find(
                        page_id,
                        strategy=strategy,
                        action=action,
                        value=options.get("value"),
                        name=options.get("name"),
                        selector=options.get("selector"),
                        nth=int(options["nth"]) if "nth" in options else None,
                        action_value=options.get("action-value"),
                        files=options.get("files"),
                    )
                    if result is not None:
                        print(result)
                elif command == "stream_start":
                    options = _parse_options(args)
                    output_dir = Path(options.get("dir", "frames"))
                    image_format = options.get("format", "jpeg")
                    if image_format not in {"jpeg", "png"}:
                        raise ValueError("image_format 必须是 jpeg 或 png")
                    quality = int(options["quality"]) if "quality" in options else 80
                    every_nth_frame = int(options["every_nth"]) if "every_nth" in options else None
                    output_dir.mkdir(parents=True, exist_ok=True)
                    frame_counters.clear()

                    async def on_frame(payload: dict) -> None:
                        if payload.get("type") != "frame":
                            return
                        data = payload.get("data")
                        if not data:
                            return
                        page_id = payload.get("page_id", "unknown")
                        counter = frame_counters.get(page_id, 0) + 1
                        frame_counters[page_id] = counter
                        ext = "jpg" if image_format == "jpeg" else "png"
                        filename = f"{page_id}_{int(time.time() * 1000)}_{counter}.{ext}"
                        image_bytes = base64.b64decode(data)
                        await asyncio.to_thread((output_dir / filename).write_bytes, image_bytes)

                    await browser.stream_start(
                        "*",
                        on_frame=on_frame,
                        image_format=image_format,
                        quality=quality,
                        every_nth_frame=every_nth_frame,
                    )
                    stream_running = True
                    print(f"帧监听已启动，输出目录: {output_dir}")
                elif command == "stream_stop":
                    if stream_running:
                        await browser.stream_stop("*")
                        stream_running = False
                        print("帧监听已停止")
                    else:
                        print("帧监听未启动")
                elif command == "close":
                    if args:
                        await browser.close(args[0])
                        known_pages.discard(args[0])
                        if current_page == args[0]:
                            current_page = None
                    else:
                        await browser.close()
                        known_pages.clear()
                        current_page = None
                else:
                    print("未知命令，输入 help 查看可用命令")
            except Exception as error:
                print(f"错误: {error}")
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(cli())
