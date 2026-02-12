from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import re

from patchright.async_api import Page


@dataclass
class RefTarget:
    selector: str
    role: str
    name: Optional[str]
    nth: Optional[int]


@dataclass
class EnhancedSnapshot:
    tree: str
    refs: Dict[str, RefTarget]


@dataclass
class SnapshotOptions:
    interactive: bool = False
    max_depth: Optional[int] = None
    compact: bool = False
    selector: Optional[str] = None


INTERACTIVE_ROLES = {
    "button",
    "link",
    "textbox",
    "checkbox",
    "radio",
    "combobox",
    "listbox",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "searchbox",
    "slider",
    "spinbutton",
    "switch",
    "tab",
    "treeitem",
}

CONTENT_ROLES = {
    "heading",
    "cell",
    "gridcell",
    "columnheader",
    "rowheader",
    "listitem",
    "article",
    "region",
    "main",
    "navigation",
}

STRUCTURAL_ROLES = {
    "generic",
    "group",
    "list",
    "table",
    "row",
    "rowgroup",
    "grid",
    "treegrid",
    "menu",
    "menubar",
    "toolbar",
    "tablist",
    "tree",
    "directory",
    "document",
    "application",
    "presentation",
    "none",
}


def _get_indent_level(line: str) -> int:
    match = re.match(r"^(\s*)", line)
    return len(match.group(1)) // 2 if match else 0


def _build_selector(role: str, name: Optional[str]) -> str:
    if name:
        escaped = name.replace('"', '\\"')
        return f'getByRole("{role}", {{ name: "{escaped}", exact: true }})'
    return f'getByRole("{role}")'


def _clean_suffix(suffix: str) -> str:
    if not suffix:
        return ""
    cleaned = re.sub(r"\[ref=@e\d+\]", "", suffix)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned.startswith(":"):
        cleaned = cleaned[1:].strip()
    return cleaned


def _truncate_text(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…"


def _match_snippet(text: str, query: str, mode: str, limit: int) -> str:
    if not text:
        return ""
    if mode == "regex":
        try:
            pattern = re.compile(query, re.I)
        except re.error:
            return _truncate_text(text, limit)
        match = pattern.search(text)
        if not match:
            return _truncate_text(text, limit)
        start, end = match.span()
    else:
        lower = text.lower()
        needle = query.lower()
        start = lower.find(needle)
        if start < 0:
            return _truncate_text(text, limit)
        end = start + len(needle)
    context = max(8, limit // 3)
    left = max(0, start - context)
    right = min(len(text), end + context)
    snippet = text[left:right]
    if left > 0:
        snippet = f"…{snippet}"
    if right < len(text):
        snippet = f"{snippet}…"
    return _truncate_text(snippet, limit)


async def get_multiview_index_data(
    page: Page,
    text_limit: int,
    max_nodes: int,
    depth: int,
) -> dict:
    payload = {
        "textLimit": text_limit,
        "maxNodes": max_nodes,
        "depth": depth,
    }
    return await page.evaluate(
        """(params) => {
        const textLimit = params.textLimit || 80;
        const maxNodes = params.maxNodes || 200;
        const depth = params.depth || 1;
        const escapeCss = (value) => value.replace(/([ !"#$%&'()*+,.\\/\\\\:;<=>?@\\[\\]^`{|}~])/g, "\\\\$1");
        const textOf = (el) => {
            if (!el) return "";
            const text = el.innerText || el.textContent || "";
            return text.replace(/\\s+/g, " ").trim();
        };
        const clip = (text) => {
            if (!text) return "";
            return text.length > textLimit ? text.slice(0, textLimit) + "…" : text;
        };
        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            if (!style || style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        };
        const cssPath = (el) => {
            if (!el || el.nodeType !== 1) return "";
            if (el.id) return "#" + escapeCss(el.id);
            const parts = [];
            let current = el;
            while (current && current.nodeType === 1 && current !== document.documentElement) {
                const tag = current.tagName.toLowerCase();
                const parent = current.parentElement;
                if (!parent) break;
                const siblings = Array.from(parent.children).filter((child) => child.tagName === current.tagName);
                const index = siblings.indexOf(current) + 1;
                parts.unshift(`${tag}:nth-of-type(${index})`);
                current = parent;
            }
            parts.unshift("html");
            return parts.join(" > ");
        };
        const summaryFromHeading = (heading) => {
            const baseLevel = parseInt(heading.tagName.slice(1), 10);
            let node = heading.nextElementSibling;
            while (node) {
                if (/^H[1-6]$/.test(node.tagName)) {
                    const level = parseInt(node.tagName.slice(1), 10);
                    if (level <= baseLevel) break;
                }
                const text = textOf(node);
                if (text) return text;
                node = node.nextElementSibling;
            }
            return "";
        };
        const candidates = [
            document.querySelector("main, article, [role='main'], [role='article']"),
            document.querySelector("#content, #main, #page, #app, #root"),
            document.body,
            document.documentElement
        ].filter(Boolean);
        const pickRoot = () => {
            for (const el of candidates) {
                const text = textOf(el);
                if (text.length > 200) return el;
            }
            return candidates[0] || document.body || document.documentElement;
        };
        const root = pickRoot();
        const headingMax = Math.min(6, Math.max(1, depth + 1));
        let headings = Array.from(root.querySelectorAll("h1,h2,h3,h4,h5,h6"))
            .filter((el) => isVisible(el))
            .map((el) => {
                const level = parseInt(el.tagName.slice(1), 10);
                return {
                    title: clip(textOf(el)),
                    level,
                    summary: clip(summaryFromHeading(el)),
                    selector: cssPath(el),
                    anchor: el.id ? "#" + el.id : ""
                };
            })
            .filter((item) => item.title && item.level <= headingMax)
            .slice(0, maxNodes);
        if (headings.length === 0) {
            headings = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6"))
                .filter((el) => isVisible(el))
                .map((el) => {
                    const level = parseInt(el.tagName.slice(1), 10);
                    return {
                        title: clip(textOf(el)),
                        level,
                        summary: clip(summaryFromHeading(el)),
                        selector: cssPath(el),
                        anchor: el.id ? "#" + el.id : ""
                    };
                })
                .filter((item) => item.title && item.level <= headingMax)
                .slice(0, maxNodes);
        }
        if (headings.length === 0 && document.title) {
            const rootSelector = cssPath(root);
            headings = [
                {
                    title: clip(document.title),
                    level: 1,
                    summary: "",
                    selector: rootSelector,
                    anchor: ""
                }
            ];
        }
        const overlayCandidates = Array.from(document.querySelectorAll("[role='dialog'],[role='alertdialog'],[aria-modal='true']"))
            .filter((el) => isVisible(el))
            .map((el) => ({
                label: clip(el.getAttribute("aria-label") || textOf(el)),
                selector: cssPath(el)
            }))
            .slice(0, Math.max(5, Math.floor(maxNodes / 4)));
        const controlCandidates = Array.from(document.querySelectorAll("input, textarea, select, button, a"))
            .filter((el) => isVisible(el))
            .map((el) => {
                const tag = el.tagName.toLowerCase();
                const type = tag === "input" ? (el.getAttribute("type") || "text") : tag;
                const label = clip(el.getAttribute("aria-label") || el.getAttribute("placeholder") || textOf(el) || el.getAttribute("name") || "");
                return {
                    kind: type,
                    label,
                    selector: cssPath(el)
                };
            })
            .filter((item) => item.label)
            .slice(0, Math.max(10, Math.floor(maxNodes / 2)));
        const collectBlocks = (scope, minLen, minScore) => Array.from(scope.querySelectorAll("p, li, section, article, div"))
            .filter((el) => isVisible(el))
            .map((el) => {
                const text = textOf(el);
                const textLen = text.length;
                if (textLen < minLen) return null;
                const linkText = Array.from(el.querySelectorAll("a")).map((a) => textOf(a)).join(" ");
                const linkLen = linkText.length;
                const score = textLen - linkLen * 1.5;
                return {
                    text: clip(text),
                    score,
                    selector: cssPath(el)
                };
            })
            .filter((item) => item && item.score > minScore);
        let blockCandidates = collectBlocks(root, 80, 60)
            .sort((a, b) => b.score - a.score)
            .slice(0, maxNodes);
        if (blockCandidates.length === 0) {
            blockCandidates = collectBlocks(document.body || document.documentElement, 40, 20)
                .sort((a, b) => b.score - a.score)
                .slice(0, maxNodes);
        }
        return {
            title: document.title || "",
            lang: document.documentElement ? (document.documentElement.lang || "") : "",
            sections: headings,
            blocks: blockCandidates,
            interactions: controlCandidates,
            overlays: overlayCandidates
        };
        }""",
        payload,
    )


def _collect_multiview_items(
    data: dict,
    depth: int,
    text_limit: int,
    max_nodes: int,
    path: Optional[str] = None,
) -> tuple[list[dict], dict[str, str]]:
    items: list[dict] = []
    view_paths: dict[str, str] = {}
    sections = data.get("sections") or []
    blocks = data.get("blocks") or []
    interactions = data.get("interactions") or []
    overlays = data.get("overlays") or []
    max_level = min(6, max(1, depth + 1))
    section_indices = list(range(len(sections)))
    block_indices = list(range(len(blocks)))
    interaction_indices = list(range(len(interactions)))
    overlay_indices = list(range(len(overlays)))
    if path and path.startswith("v:structure/"):
        match = re.fullmatch(r"v:structure/s(\d+)", path)
        if match:
            start = int(match.group(1))
            if 0 <= start < len(sections):
                base_level = sections[start].get("level", 1)
                indices = [start]
                for idx in range(start + 1, len(sections)):
                    level = sections[idx].get("level", 1)
                    if level <= base_level:
                        break
                    indices.append(idx)
                section_indices = indices
    if path and path.startswith("v:content/"):
        match = re.fullmatch(r"v:content/b(\d+)", path)
        if match:
            start = int(match.group(1))
            block_indices = [start] if 0 <= start < len(blocks) else []
    if path and path.startswith("v:interact/"):
        match = re.fullmatch(r"v:interact/i(\d+)", path)
        if match:
            start = int(match.group(1))
            interaction_indices = [start] if 0 <= start < len(interactions) else []
    if path and path.startswith("v:overlay/"):
        match = re.fullmatch(r"v:overlay/o(\d+)", path)
        if match:
            start = int(match.group(1))
            overlay_indices = [start] if 0 <= start < len(overlays) else []
    for idx in section_indices:
        if idx >= len(sections):
            continue
        section = sections[idx]
        level = int(section.get("level") or 1)
        if level > max_level:
            continue
        title = _truncate_text(section.get("title") or "", text_limit)
        if not title:
            continue
        summary = _truncate_text(section.get("summary") or "", text_limit)
        anchor = section.get("anchor") or ""
        selector = section.get("selector") or ""
        path_id = f"v:structure/s{idx}"
        if selector:
            view_paths[path_id] = selector
        haystack = " ".join(part for part in [title, summary, anchor] if part)
        items.append(
            {
                "view": "structure",
                "path": path_id,
                "label": f'heading "{title}"',
                "summary": summary,
                "level": level,
                "haystack": haystack,
            }
        )
    for idx in block_indices[:max_nodes]:
        if idx >= len(blocks):
            continue
        block = blocks[idx]
        text_value = _truncate_text(block.get("text") or "", text_limit)
        if not text_value:
            continue
        selector = block.get("selector") or ""
        path_id = f"v:content/b{idx}"
        if selector:
            view_paths[path_id] = selector
        items.append(
            {
                "view": "content",
                "path": path_id,
                "label": f'block "{text_value}"',
                "summary": "",
                "level": 0,
                "haystack": text_value,
            }
        )
    for idx in interaction_indices[:max_nodes]:
        if idx >= len(interactions):
            continue
        control = interactions[idx]
        label = _truncate_text(control.get("label") or "", text_limit)
        if not label:
            continue
        selector = control.get("selector") or ""
        kind = control.get("kind") or "control"
        path_id = f"v:interact/i{idx}"
        if selector:
            view_paths[path_id] = selector
        items.append(
            {
                "view": "interact",
                "path": path_id,
                "label": f'{kind} "{label}"',
                "summary": "",
                "level": 0,
                "haystack": " ".join([kind, label]),
            }
        )
    for idx in overlay_indices[:max_nodes]:
        if idx >= len(overlays):
            continue
        overlay = overlays[idx]
        label = _truncate_text(overlay.get("label") or "", text_limit)
        if not label:
            continue
        selector = overlay.get("selector") or ""
        path_id = f"v:overlay/o{idx}"
        if selector:
            view_paths[path_id] = selector
        items.append(
            {
                "view": "overlay",
                "path": path_id,
                "label": f'dialog "{label}"',
                "summary": "",
                "level": 0,
                "haystack": label,
            }
        )
    return items, view_paths


def build_multiview_index_text(
    data: dict,
    path: Optional[str],
    depth: int,
    max_nodes: int,
    text_limit: int,
) -> tuple[str, dict[str, str]]:
    items, view_paths = _collect_multiview_items(
        data,
        depth=depth,
        text_limit=text_limit,
        max_nodes=max_nodes,
        path=path,
    )
    if not items:
        return "(empty)", view_paths
    lines: list[str] = []
    views = ["structure", "content", "interact", "overlay"]
    for view in views:
        view_items = [item for item in items if item["view"] == view]
        if not view_items:
            continue
        lines.append(f"index (view={view}, path={path or 'root'}, depth={depth}, max_nodes={max_nodes})")
        if view == "structure":
            min_level = min(item["level"] for item in view_items if item["level"] > 0) if view_items else 1
            for item in view_items:
                indent = "  " * max(0, item["level"] - min_level)
                line = f'{indent}- {item["label"]} [path={item["path"]}]'
                if item["summary"]:
                    line += f' :: {item["summary"]}'
                lines.append(line)
        else:
            for item in view_items:
                lines.append(f'- {item["label"]} [path={item["path"]}]')
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines), view_paths


def search_multiview_index_text(
    data: dict,
    query: str,
    mode: str,
    limit: int,
    text_limit: int,
) -> str:
    if not data or not query:
        return "(empty)"
    items, _ = _collect_multiview_items(
        data,
        depth=6,
        text_limit=text_limit,
        max_nodes=max(200, limit * 10),
        path=None,
    )
    results: list[dict] = []
    if mode == "regex":
        try:
            pattern = re.compile(query, re.I)
        except re.error as error:
            raise ValueError(f"无效正则: {error}") from error
        def is_match(text: str) -> bool:
            return bool(pattern.search(text))
    else:
        needle = query.lower()
        def is_match(text: str) -> bool:
            return needle in text.lower()
    for item in items:
        haystack = item.get("haystack") or ""
        if not haystack:
            continue
        if not is_match(haystack):
            continue
        snippet = _match_snippet(haystack, query, mode, text_limit)
        label = item["label"]
        if snippet and snippet not in label:
            label = f'{label} :: {snippet}'
        results.append(
            {
                "path": item["path"],
                "line": f'- {label} [path={item["path"]}]',
            }
        )
        if len(results) >= limit * 4:
            break
    results.sort(key=lambda item: item["path"])
    pruned: list[str] = []
    seen: set[str] = set()
    for item in results:
        path = item["path"]
        if path in seen:
            continue
        seen.add(path)
        pruned.append(item["line"])
        if len(pruned) >= limit:
            break
    header = f'search (query="{query}", mode={mode}, limit={limit})'
    return "\n".join([header, *pruned]) if pruned else f"{header}\n(empty)"


def _parse_aria_snapshot(aria_tree: str) -> tuple[list[dict], list[int], dict[str, int]]:
    lines = aria_tree.splitlines()
    element_pattern = re.compile(r'^(\s*-\s*)(\w+)(?:\s+"([^"]*)")?(.*)$')
    nodes: list[dict] = []
    root_ids: list[int] = []
    stack: list[int] = []

    for line in lines:
        match = element_pattern.match(line)
        if not match:
            continue
        prefix, role, name, suffix = match.groups()
        if role.startswith("/"):
            continue
        depth = _get_indent_level(line)
        node_id = len(nodes)
        node = {
            "id": node_id,
            "role": role.lower(),
            "name": name,
            "suffix": suffix or "",
            "depth": depth,
            "children": [],
            "parent_id": None,
            "path": "",
        }
        while len(stack) > depth:
            stack.pop()
        if stack:
            parent_id = stack[-1]
            node["parent_id"] = parent_id
            nodes[parent_id]["children"].append(node_id)
        else:
            root_ids.append(node_id)
        nodes.append(node)
        stack.append(node_id)

    path_to_id: dict[str, int] = {}

    def assign_paths(node_id: int, path: str) -> None:
        nodes[node_id]["path"] = path
        path_to_id[path] = node_id
        for idx, child_id in enumerate(nodes[node_id]["children"]):
            child_path = f"{path}/{idx}" if path else str(idx)
            assign_paths(child_id, child_path)

    for idx, root_id in enumerate(root_ids):
        assign_paths(root_id, str(idx))

    return nodes, root_ids, path_to_id


def _node_text_value(node: dict) -> str:
    if node["name"]:
        return node["name"]
    return _clean_suffix(node["suffix"])


def _format_node_label(node: dict, text_limit: int) -> str:
    text_value = _node_text_value(node)
    text_hint = _truncate_text(text_value, text_limit)
    label = node["role"]
    if text_hint:
        label += f' "{text_hint}"'
    return label


def _collect_summary(nodes: list[dict], node_id: int, max_items: int, text_limit: int) -> str:
    priority_roles = {
        "heading",
        "button",
        "link",
        "textbox",
        "combobox",
        "listbox",
        "checkbox",
        "radio",
        "menuitem",
        "tab",
        "option",
        "searchbox",
        "switch",
    }
    seen: set[str] = set()
    summary: list[str] = []

    def add_text(text: str) -> None:
        if not text:
            return
        text_hint = _truncate_text(text, text_limit)
        if not text_hint:
            return
        key = text_hint.lower()
        if key in seen:
            return
        seen.add(key)
        summary.append(text_hint)

    queue = [node_id]
    while queue and len(summary) < max_items:
        current_id = queue.pop(0)
        node = nodes[current_id]
        text_value = _node_text_value(node)
        if node["role"] in priority_roles:
            add_text(text_value)
        for child_id in node["children"]:
            queue.append(child_id)

    return " | ".join(summary)


def _format_preview_item(nodes: list[dict], node: dict, text_limit: int, summary_items: int) -> str:
    label = _format_node_label(node, text_limit)
    summary = _collect_summary(nodes, node["id"], summary_items, text_limit)
    suffix = f" :: {summary}" if summary else ""
    return f"{label} [path={node['path']}]".strip() + suffix


def build_snapshot_index_text(
    aria_tree: str,
    path: Optional[str],
    depth: int,
    max_nodes: int,
    text_limit: int,
) -> str:
    """
    Build a compact index from an ARIA snapshot.

    Args:
        aria_tree: Raw ARIA snapshot text.
        path: Optional index path to expand from.
        depth: Depth to expand from the start node.
        max_nodes: Maximum number of nodes to return.
        text_limit: Max length for node labels and summaries.

    Returns:
        A human-readable index string.
    """
    if not aria_tree:
        return "(empty)"
    nodes, root_ids, path_to_id = _parse_aria_snapshot(aria_tree)
    if path is not None:
        if path not in path_to_id:
            raise KeyError(f"未知的 path: {path}")
        start_ids = [path_to_id[path]]
    else:
        start_ids = root_ids

    counter = 0
    lines: list[str] = []
    summary_items = 6
    grandchild_preview = 3
    path_mode = path is not None

    def render_node(node_id: int, current_depth: int, indent: str) -> None:
        nonlocal counter
        if counter >= max_nodes:
            return
        node = nodes[node_id]
        counter += 1
        label = _format_node_label(node, text_limit)
        child_ids = node["children"]
        summary = ""
        line = f"{indent}- {label} [path={node['path']}]"
        if summary:
            line += f" :: {summary}"
        expand_children = current_depth < depth and (path_mode or current_depth == 0)
        if child_ids and not expand_children:
            previews = []
            for child_id in child_ids[:grandchild_preview]:
                child = nodes[child_id]
                previews.append(_format_preview_item(nodes, child, text_limit, summary_items))
            extra = len(child_ids) - min(grandchild_preview, len(child_ids))
            preview_text = "; ".join(previews)
            if extra > 0:
                preview_text = f"{preview_text}; +{extra} more" if preview_text else f"+{extra} more"
            if preview_text:
                line += f" (grandchildren: {preview_text})"
        lines.append(line)
        if not expand_children:
            return
        if not child_ids:
            return
        for child_id in child_ids:
            render_node(child_id, current_depth + 1, indent + "  ")

    lines.append(f"index (path={path or 'root'}, depth={depth}, max_nodes={max_nodes})")
    for node_id in start_ids:
        render_node(node_id, 0, "")
    if counter >= max_nodes and counter < len(nodes):
        lines.append(f"... (truncated: returned {counter} of {len(nodes)})")
    return "\n".join(lines)


def search_snapshot_index_text(
    aria_tree: str,
    query: str,
    mode: str,
    limit: int,
    text_limit: int,
) -> str:
    """
    Search index nodes by fuzzy text or regex.

    Args:
        aria_tree: Raw ARIA snapshot text.
        query: Search keyword or regex pattern.
        mode: "fuzzy" for substring match, "regex" for regular expression.
        limit: Maximum number of matches to return.
        text_limit: Max length for node labels.

    Returns:
        A human-readable list of matching nodes with their paths.
    """
    if not aria_tree or not query:
        return "(empty)"
    nodes, _, _ = _parse_aria_snapshot(aria_tree)
    results: list[dict] = []
    if mode == "regex":
        try:
            pattern = re.compile(query, re.I)
        except re.error as error:
            raise ValueError(f"无效正则: {error}") from error
        def is_match(text: str) -> bool:
            return bool(pattern.search(text))
    else:
        needle = query.lower()
        def is_match(text: str) -> bool:
            return needle in text.lower()

    for node in nodes:
        text_value = _node_text_value(node)
        suffix = _clean_suffix(node["suffix"])
        haystack = " ".join(part for part in [node["role"], text_value, suffix] if part)
        if not haystack:
            continue
        if not is_match(haystack):
            continue
        snippet_source = text_value or suffix or haystack
        text_hint = _match_snippet(snippet_source, query, mode, text_limit)
        label = node["role"]
        if text_hint:
            label += f' "{text_hint}"'
        results.append(
            {
                "path": node["path"],
                "line": f"- {label} [path={node['path']}]",
            }
        )
        if len(results) >= limit * 4:
            break
    results.sort(key=lambda item: (item["path"].count("/"), item["path"]))
    pruned: list[str] = []
    kept_paths: list[str] = []
    for item in results:
        path = item["path"]
        if any(path == kept or path.startswith(f"{kept}/") for kept in kept_paths):
            continue
        kept_paths.append(path)
        pruned.append(item["line"])
        if len(pruned) >= limit:
            break
    header = f'search (query="{query}", mode={mode}, limit={limit})'
    return "\n".join([header, *pruned]) if pruned else f"{header}\n(empty)"


def resolve_path_locator(page: Page, aria_tree: str, path: str):
    """
    Resolve an index path to a stable locator on the page.

    Args:
        page: Target Playwright page.
        aria_tree: Raw ARIA snapshot text.
        path: Index path to resolve.

    Returns:
        A locator pointing to the exact node, including nth disambiguation.
    """
    if not aria_tree:
        raise KeyError("空页面快照")
    nodes, _, path_to_id = _parse_aria_snapshot(aria_tree)
    if path not in path_to_id:
        raise KeyError(f"未知的 path: {path}")
    node = nodes[path_to_id[path]]
    role = node["role"]
    name = node["name"]
    text_value = _node_text_value(node)
    if role == "text":
        if text_value:
            nth_index = 0
            for candidate in nodes:
                if candidate["role"] == "text" and _node_text_value(candidate) == text_value:
                    if candidate["id"] == node["id"]:
                        break
                    nth_index += 1
            return page.get_by_text(text_value, exact=True).nth(nth_index)
        parent_id = node["parent_id"]
        while parent_id is not None:
            parent = nodes[parent_id]
            if parent["name"] or parent["role"] != "text":
                node = parent
                role = node["role"]
                name = node["name"]
                break
            parent_id = parent["parent_id"]
        if role == "text" and not name:
            raise KeyError(f"path 指向 text 节点且无可定位名称: {path}")
    if name:
        nth_index = 0
        for candidate in nodes:
            if candidate["role"] == role and candidate["name"] == name:
                if candidate["id"] == node["id"]:
                    break
                nth_index += 1
        if role == "text":
            return page.get_by_text(name, exact=True).nth(nth_index)
        return page.get_by_role(role, name=name, exact=True).nth(nth_index)
    nth_index = 0
    for candidate in nodes:
        if candidate["role"] == role:
            if candidate["id"] == node["id"]:
                break
            nth_index += 1
    return page.get_by_role(role).nth(nth_index)


def _build_snapshot_from_aria_tree(aria_tree: str, options: SnapshotOptions) -> EnhancedSnapshot:
    if not aria_tree:
        return EnhancedSnapshot(tree="(empty)", refs={})

    lines = aria_tree.splitlines()
    element_pattern = re.compile(r'^(\s*-\s*)(\w+)(?:\s+"([^"]*)")?(.*)$')

    counts: Dict[str, int] = {}
    parsed_lines = []

    for line in lines:
        match = element_pattern.match(line)
        if not match:
            parsed_lines.append((line, None))
            continue

        prefix, role, name, suffix = match.groups()
        role_lower = role.lower()

        if role.startswith("/"):
            parsed_lines.append((line, None))
            continue

        depth = _get_indent_level(line)
        if options.max_depth is not None and depth > options.max_depth:
            parsed_lines.append((None, None))
            continue

        is_interactive = role_lower in INTERACTIVE_ROLES
        is_content = role_lower in CONTENT_ROLES
        is_structural = role_lower in STRUCTURAL_ROLES

        if options.interactive and not is_interactive:
            parsed_lines.append((None, None))
            continue

        if options.compact and is_structural and not name:
            parsed_lines.append((None, None))
            continue

        key = f"{role_lower}:{name or ''}"
        counts[key] = counts.get(key, 0) + 1
        parsed_lines.append(((prefix, role, name, suffix, key), "element"))

    refs: Dict[str, RefTarget] = {}
    result_lines = []
    ref_index = 0
    key_counters: Dict[str, int] = {}

    for entry, kind in parsed_lines:
        if entry is None and kind is None:
            continue

        if kind is None:
            result_lines.append(entry)
            continue

        prefix, role, name, suffix, key = entry
        role_lower = role.lower()
        is_interactive = role_lower in INTERACTIVE_ROLES
        is_content = role_lower in CONTENT_ROLES
        should_have_ref = is_interactive or (is_content and name)

        line = f'{prefix}{role}'
        if name:
            line += f' "{name}"'

        if should_have_ref:
            ref_index += 1
            ref_id = f"e{ref_index}"
            total = counts.get(key, 0)
            nth_index = None
            if total > 1:
                nth_index = key_counters.get(key, 0)
                key_counters[key] = nth_index + 1

            refs[ref_id] = RefTarget(
                selector=_build_selector(role_lower, name),
                role=role_lower,
                name=name,
                nth=nth_index,
            )
            line += f" [ref=@{ref_id}]"

        line += suffix
        result_lines.append(line)

    return EnhancedSnapshot(tree="\n".join(result_lines), refs=refs)


async def get_enhanced_snapshot(
    page: Page,
    options: SnapshotOptions,
    timeout_ms: Optional[int] = None,
) -> EnhancedSnapshot:
    """
    基于 ARIA 树生成可读快照，并为可交互元素生成可复用的 ref。
    """
    locator = page.locator(options.selector) if options.selector else page.locator(":root")
    if timeout_ms is None:
        aria_tree = await locator.aria_snapshot()
    else:
        aria_tree = await locator.aria_snapshot(timeout=timeout_ms)
    return _build_snapshot_from_aria_tree(aria_tree, options)


async def get_enhanced_snapshot_locator(
    locator,
    options: SnapshotOptions,
    timeout_ms: Optional[int] = None,
) -> EnhancedSnapshot:
    if timeout_ms is None:
        aria_tree = await locator.aria_snapshot()
    else:
        aria_tree = await locator.aria_snapshot(timeout=timeout_ms)
    return _build_snapshot_from_aria_tree(aria_tree, options)
