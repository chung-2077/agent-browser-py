import asyncio
import shlex

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
    browser = AgentBrowser(headless=False)
    current_page: str | None = None
    known_pages: set[str] = set()

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
                            "close [page_id]",
                            "exit|quit",
                        ]
                    )
                )
                continue

            try:
                if command == "open":
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
                    snapshot = await browser.snapshot(page_id, interactive=False)
                    print(snapshot.tree)
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
