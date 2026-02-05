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
    results: list[str] = []
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
        text_hint = _truncate_text(text_value or suffix, text_limit)
        label = node["role"]
        if text_hint:
            label += f' "{text_hint}"'
        results.append(f"- {label} [path={node['path']}]")
        if len(results) >= limit:
            break
    header = f'search (query="{query}", mode={mode}, limit={limit})'
    return "\n".join([header, *results]) if results else f"{header}\n(empty)"


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
    if not name:
        nth_index = 0
        for candidate in nodes:
            if candidate["role"] == role:
                if candidate["id"] == node["id"]:
                    break
                nth_index += 1
        return page.get_by_role(role).nth(nth_index)
    nth_index = 0
    for candidate in nodes:
        if candidate["role"] == role and candidate["name"] == name:
            if candidate["id"] == node["id"]:
                break
            nth_index += 1
    return page.get_by_role(role, name=name, exact=True).nth(nth_index)


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


async def get_enhanced_snapshot(page: Page, options: SnapshotOptions) -> EnhancedSnapshot:
    """
    基于 ARIA 树生成可读快照，并为可交互元素生成可复用的 ref。
    """
    locator = page.locator(options.selector) if options.selector else page.locator(":root")
    aria_tree = await locator.aria_snapshot()
    return _build_snapshot_from_aria_tree(aria_tree, options)


async def get_enhanced_snapshot_locator(locator, options: SnapshotOptions) -> EnhancedSnapshot:
    aria_tree = await locator.aria_snapshot()
    return _build_snapshot_from_aria_tree(aria_tree, options)
