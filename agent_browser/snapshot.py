from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import re

from playwright.async_api import Page


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


async def get_enhanced_snapshot(page: Page, options: SnapshotOptions) -> EnhancedSnapshot:
    """
    基于 ARIA 树生成可读快照，并为可交互元素生成可复用的 ref。
    """
    locator = page.locator(options.selector) if options.selector else page.locator(":root")
    aria_tree = await locator.aria_snapshot()

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
