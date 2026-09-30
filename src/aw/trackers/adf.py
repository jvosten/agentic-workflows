"""Atlassian Document Format (Jira Cloud rich text) to and from Markdown.

Covers what issues and plans use: headings, paragraphs, bold/italic/code/strike,
links, nested lists, code blocks, quotes, rules, and tables. Unknown nodes keep
their text content.
"""

from __future__ import annotations

import re
from typing import Any

# --- ADF -> Markdown ---------------------------------------------------------

_MARKS = {"strong": "**", "em": "_", "strike": "~~", "code": "`"}


def _text(node: dict) -> str:
    text = node.get("text", "")
    href = None
    for mark in node.get("marks", []):
        kind = mark.get("type")
        if kind == "link":
            href = mark.get("attrs", {}).get("href")
        elif kind in _MARKS:
            text = f"{_MARKS[kind]}{text}{_MARKS[kind]}"
    return f"[{text}]({href})" if href else text


def _inline(nodes: list) -> str:
    return "".join(_node(n, 0) for n in nodes)


def _list(node: dict, depth: int) -> str:
    out = []
    for i, item in enumerate(node.get("content", []), 1):
        bullet = f"{i}." if node["type"] == "orderedList" else "-"
        parts = []
        for child in item.get("content", []):
            if child.get("type") in ("bulletList", "orderedList"):
                parts.append(_list(child, depth + 1).rstrip("\n"))
            else:
                parts.append(_node(child, depth).strip())
        first, *rest = parts or [""]
        out.append(f"{'  ' * depth}{bullet} {first}")
        out += rest
    return "\n".join(out) + "\n"


def _table(node: dict) -> str:
    rows = []
    for row in node.get("content", []):
        cells = [_inline_block(c).replace("|", "\\|") for c in row.get("content", [])]
        rows.append("| " + " | ".join(cells) + " |")
        if len(rows) == 1:
            rows.append("|" + "---|" * len(cells))
    return "\n".join(rows) + "\n"


def _inline_block(node: dict) -> str:
    return " ".join(_node(c, 0).strip() for c in node.get("content", []))


def _node(node: Any, depth: int) -> str:
    if not isinstance(node, dict):
        return ""
    kind = node.get("type")
    content = node.get("content", [])
    attrs = node.get("attrs", {})
    if kind == "text":
        return _text(node)
    if kind == "hardBreak":
        return "\n"
    if kind == "paragraph":
        return _inline(content) + "\n"
    if kind == "heading":
        return f"{'#' * int(attrs.get('level', 1))} {_inline(content)}\n"
    if kind in ("bulletList", "orderedList"):
        return _list(node, depth)
    if kind == "codeBlock":
        return f"```{attrs.get('language', '')}\n{_inline(content)}\n```\n"
    if kind == "blockquote":
        inner = to_markdown({"type": "doc", "content": content}).strip()
        return "\n".join(f"> {line}".rstrip() for line in inner.splitlines()) + "\n"
    if kind == "rule":
        return "---\n"
    if kind == "table":
        return _table(node)
    if kind in ("inlineCard", "blockCard"):
        return attrs.get("url", "")
    if kind == "mention":
        return attrs.get("text", "@user")
    if kind == "emoji":
        return attrs.get("text") or attrs.get("shortName", "")
    if kind == "status":
        return f"[{attrs.get('text', '')}]"
    if kind in ("mediaSingle", "mediaGroup", "media"):
        return "[attachment]\n" if kind != "media" else ""
    return "".join(_node(c, depth) for c in content)


def to_markdown(doc: Any) -> str:
    if doc is None:
        return ""
    if isinstance(doc, str):
        return doc
    blocks = [_node(n, 0).rstrip("\n") for n in doc.get("content", [])]
    return "\n\n".join(b for b in blocks if b.strip()) + ("\n" if blocks else "")


# --- Markdown -> ADF ---------------------------------------------------------

_INLINE = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\[(?P<ltext>[^\]]+)\]\((?P<href>[^)\s]+)\)"
    r"|\*\*(?P<strong>.+?)\*\*|__(?P<strong2>.+?)__"
    r"|~~(?P<strike>.+?)~~"
    r"|(?<![\w*])\*(?!\s)(?P<em>.+?)(?<!\s)\*(?![\w*])"
    r"|(?<![\w_])_(?!\s)(?P<em2>.+?)(?<!\s)_(?![\w_])"
)
_LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_FENCE = re.compile(r"^\s*```\s*(\S*)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


def _t(text: str, marks: list[dict]) -> dict:
    node: dict = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def inline(text: str, marks: list[dict] | None = None) -> list[dict]:
    marks = marks or []
    out: list[dict] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append(_t(text[pos:m.start()], marks))
        g = m.groupdict()
        if g["code"] is not None:
            out.append(_t(g["code"], [*[k for k in marks if k["type"] == "link"], {"type": "code"}]))
        elif g["ltext"] is not None:
            out += inline(g["ltext"], [*marks, {"type": "link", "attrs": {"href": g["href"]}}])
        elif (s := g["strong"] or g["strong2"]) is not None:
            out += inline(s, [*marks, {"type": "strong"}])
        elif g["strike"] is not None:
            out += inline(g["strike"], [*marks, {"type": "strike"}])
        else:
            out += inline(g["em"] or g["em2"], [*marks, {"type": "em"}])
        pos = m.end()
    if pos < len(text):
        out.append(_t(text[pos:], marks))
    return [n for n in out if n.get("text")]


def _para(text: str) -> dict:
    return {"type": "paragraph", "content": inline(text) or [_t(" ", [])]}


def _parse_list(lines: list[str]) -> dict:
    base = len(_LIST_ITEM.match(lines[0]).group(1))
    ordered = _LIST_ITEM.match(lines[0]).group(2)[0].isdigit()
    items: list[list[str]] = []
    for line in lines:
        m = _LIST_ITEM.match(line)
        if m and len(m.group(1)) == base:
            items.append([m.group(3)])
        else:
            items[-1].append(line[base:] if line[:base].isspace() else line.lstrip())
    content = []
    for first, *rest in items:
        sub = _blocks("\n".join(line.removeprefix("  ") for line in rest)) if rest else []
        content.append({"type": "listItem", "content": [_para(first), *sub]})
    return {"type": "orderedList" if ordered else "bulletList", "content": content}


def _table_node(lines: list[str]) -> dict:
    rows = []
    for i, line in enumerate(lines):
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if i == 1 and all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        kind = "tableHeader" if i == 0 else "tableCell"
        rows.append({"type": "tableRow", "content": [
            {"type": kind, "content": [_para(c.replace("\\|", "|"))]} for c in cells]})
    return {"type": "table", "content": rows}


def _blocks(text: str) -> list[dict]:
    lines = text.splitlines()
    out: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if m := _FENCE.match(line):
            j = i + 1
            while j < len(lines) and not _FENCE.match(lines[j]):
                j += 1
            node: dict = {"type": "codeBlock", "content": [_t(t, [])] if (t := "\n".join(lines[i + 1:j])) else []}
            if m.group(1):
                node["attrs"] = {"language": m.group(1)}
            out.append(node)
            i = j + 1
        elif m := _HEADING.match(line):
            out.append({"type": "heading", "attrs": {"level": len(m.group(1))}, "content": inline(m.group(2))})
            i += 1
        elif _RULE.match(line):
            out.append({"type": "rule"})
            i += 1
        elif line.lstrip().startswith(">"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith(">"):
                j += 1
            inner = "\n".join(re.sub(r"^\s*>\s?", "", x) for x in lines[i:j])
            out.append({"type": "blockquote", "content": _blocks(inner)})
            i = j
        elif line.lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            out.append(_table_node(lines[i:j]))
            i = j
        elif _LIST_ITEM.match(line):
            j = i + 1
            while j < len(lines) and lines[j].strip() and (_LIST_ITEM.match(lines[j]) or lines[j][:1].isspace()):
                j += 1
            out.append(_parse_list(lines[i:j]))
            i = j
        else:
            j = i
            while j < len(lines) and lines[j].strip() and not (
                _FENCE.match(lines[j]) or _HEADING.match(lines[j]) or _LIST_ITEM.match(lines[j])
                or lines[j].lstrip().startswith((">", "|"))
            ):
                j += 1
            out.append(_para(" ".join(x.strip() for x in lines[i:j])))
            i = j
    return out


def from_markdown(text: str) -> dict:
    return {"type": "doc", "version": 1, "content": _blocks(text) or [_para(text.strip() or " ")]}
