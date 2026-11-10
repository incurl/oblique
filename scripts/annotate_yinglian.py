#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《楹联丛话全编》语义标注 Markdown 与索引 JSON。

用法：
    python3 scripts/annotate_yinglian.py
    python3 scripts/annotate_yinglian.py --out data/楹联丛话全编.tagged.md

输出：
    data/楹联丛话全编.tagged.md   带 Purple Numbers、实体标记、联语标记的正文
    data/entities.json           实体索引
    data/couplets.json           联语语料（上下联、类型、作者、地点、出处）
    data/structure.json          书 / 卷 / 门类 / 条目结构
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from yinglian_lib import (
    DATA_DIR,
    Document,
    Node,
    ROOT,
    SOURCE_PATH,
    annotate_text,
    parse_document,
)

TAGGED_PATH = DATA_DIR / "楹联丛话全编.tagged.md"
ENTITIES_PATH = DATA_DIR / "entities.json"
COUPLETS_PATH = DATA_DIR / "couplets.json"
STRUCTURE_PATH = DATA_DIR / "structure.json"

# 这些门类用 fenced div 包裹，便于渲染成不同样式
PREFACE_TITLES = {"序", "自序"}
BIO_TITLE = "作者简介"


def yaml_front_matter(doc: Document) -> str:
    meta = doc.metadata
    return (
        "---\n"
        f"title: {meta['title']}\n"
        f"author: {meta['author']}\n"
        f"dynasty: {meta['dynasty']}\n"
        f"source: {meta['source']}\n"
        f"source_lines: {meta['source_lines']}\n"
        f"schema: {meta['schema']}\n"
        "tags:\n"
        "  - 楹联\n"
        "  - 联话\n"
        "  - 巧对\n"
        "  - 清代\n"
        "---\n"
    )


def anchor(node_id: str) -> str:
    return f'<a id="pn-{node_id}"></a>'


def render_paragraph(
    node: Node,
    section: str,
    entities: list[dict],
    couplets: list[dict],
) -> str:
    """渲染一个段落（含续行），返回 Markdown 片段。"""
    result = annotate_text(node.text, node.id, section)
    entities.extend(result.entities)
    couplets.extend(result.couplets)

    lines = [f"[{node.id}] {result.text}"]
    for i, (_line_no, raw) in enumerate(node.cont, 1):
        cid = f"{node.id}.{i}"
        r = annotate_text(raw, cid, section)
        entities.extend(r.entities)
        couplets.extend(r.couplets)
        lines.append(f"[{cid}] {r.text}")

    body = "\n".join(lines)
    if result.block_couplet:
        return f"{anchor(node.id)}\n::: 联\n{body}\n:::"
    return f"{anchor(node.id)}\n{body}"


def render_note(node: Node, entities: list[dict], couplets: list[dict]) -> str:
    """渲染校注块。"""
    result = annotate_text(node.text, node.id, "校注")
    entities.extend(result.entities)
    lines = [f"[{node.id}] {result.text}"]
    for i, (_line_no, raw) in enumerate(node.cont, 1):
        cid = f"{node.id}.{i}"
        r = annotate_text(raw, cid, "校注")
        entities.extend(r.entities)
        couplets.extend(r.couplets)
        lines.append(f"[{cid}] {r.text}")
    body = "\n".join(lines)
    return f"{anchor(node.id)}\n::: 校注\n{body}\n:::"


def render_block(
    node: Node,
    level: int,
    section: str,
    entities: list[dict],
    couplets: list[dict],
) -> str:
    """递归渲染 book / volume / section / entry / paragraph。"""
    parts: list[str] = []

    if node.kind in {"book", "volume", "section", "entry"}:
        prefix = "#" * level
        parts.append(f"{anchor(node.id)}\n{prefix} [{node.id}] {node.text}")

        # 序、自序、作者简介用 fenced div 包住其段落
        wrap = None
        if node.kind == "section" and node.text in PREFACE_TITLES:
            wrap = "序"
        elif node.kind == "section" and node.text == BIO_TITLE:
            wrap = "小传"

        if wrap:
            parts.append(f"::: {wrap}")
            for child in node.children:
                if child.kind == "paragraph":
                    parts.append(render_paragraph(child, node.text, entities, couplets))
                else:
                    parts.append(render_block(child, level + 1, node.text, entities, couplets))
            parts.append(":::")
        else:
            for child in node.children:
                parts.append(render_block(child, level + 1, node.text, entities, couplets))

    elif node.kind == "paragraph":
        parts.append(render_paragraph(node, section, entities, couplets))

    elif node.kind == "note":
        parts.append(render_note(node, entities, couplets))

    return "\n\n".join(p for p in parts if p)


def build_toc(doc: Document) -> str:
    """生成带锚点的目录。"""
    lines = ["## 目录", ""]

    def walk(node: Node, depth: int) -> None:
        if node.kind in {"book", "volume", "section", "entry"}:
            lines.append(
                f"{'  ' * depth}- [{node.id} {node.text}](#pn-{node.id})"
            )
        for child in node.children:
            if child.kind in {"volume", "section", "entry"}:
                walk(child, depth + 1)

    if doc.author_intro:
        lines.append(
            f"- [0 {doc.author_intro.text}](#pn-{doc.author_intro.id})"
        )
    for book in doc.books:
        walk(book, 0)
    return "\n".join(lines)


def build_legend() -> str:
    return """## 凡例

本书采用与 `shiji-kb` 一致的分层标注原则：**只加标记，不改原文**。

### 1. 结构层

- `# [0]` 全书；`## [1]` 书名；`### [1.3]` 卷/门类；`#### [3.2.1]` 条目标题。
- `[1.3.1]` 为段落级 Purple Number，`[1.3.1.1]` 为源文件断行产生的续行编号。
- 每个节点前有 `<a id="pn-...">` 锚点，可精确定位到段。

### 2. 名词实体层 `〖TYPE 内容〗`

| 符号 | 类型 | 示例 |
|---|---|---|
| `@` | 人名 | `〖@林则徐〗` |
| `=` | 地名 | `〖=扬州〗` |
| `;` | 官职 | `〖;太守〗` |
| `%` | 时间 | `〖%道光二十年〗` |
| `&` | 氏族 | `〖&林氏〗` |
| `◆` | 朝代/邦国 | `〖◆前明〗` |
| `^` | 名物/制度 | `〖^楹联〗` |
| `~` | 族群 | `〖~英夷〗` |
| `•` | 器物 | `〖•桃符〗` |
| `!` | 天文 | `〖!北斗〗` |
| `?` | 神祇/神话 | `〖?关帝〗` |
| `+` | 生物 | `〖+梅花〗` |
| `{` | 典籍 | `《〖{楹联丛话〗》` |
| `:` | 礼仪 | `〖:祭祀〗` |
| `[` | 刑法 | `〖[斩首〗` |
| `_` | 思想概念 | `〖_忠孝〗` |
| `#` | 身份 | `〖#进士〗` |
| `$` | 数量 | `〖$三千里〗` |

消歧语法：`〖@少穆|林则徐〗`，竖线前为原文显示名，竖线后为规范名。

### 3. 修辞层 `〘TYPE 内容〙`

- `〘※脍炙人口〙`：成语。

### 4. 联语标记 `〖聯〗`

联语本身保留原引号，`〖聯〗` 是前置提示符，不包裹正文，因此联内仍可标人名、地名等实体。
上下联以原文的 `；` 分隔，可用 `data/couplets.json` 直接取得切分结果。

### 5. 语义块 `::: 标签`

- `::: 序`、`::: 小传`、`::: 校注`、`::: 联`。

### 6. 文本完整性

`python3 scripts/lint_text_integrity.py` 会去除全部标记后与源文件逐段比对。
"""


def build_structure(doc: Document) -> dict:
    def serialize(node: Node) -> dict:
        item: dict = {
            "id": node.id,
            "kind": node.kind,
            "line_no": node.line_no,
        }
        if node.kind in {"paragraph", "note"}:
            text = node.text.strip()
            item["preview"] = text[:80] + ("…" if len(text) > 80 else "")
            item["chars"] = len(text)
        else:
            item["title"] = node.text.strip()
        item["children"] = [serialize(c) for c in node.children]
        return item

    return {
        "schema": doc.metadata["schema"],
        "title": doc.metadata["title"],
        "author": doc.metadata["author"],
        "dynasty": doc.metadata["dynasty"],
        "source": doc.metadata["source"],
        "author_intro": serialize(doc.author_intro) if doc.author_intro else None,
        "books": [serialize(b) for b in doc.books],
    }


def build_entities_index(entities: list[dict]) -> dict:
    counts: Counter[tuple[str, str]] = Counter()
    refs: dict[tuple[str, str], list[str]] = {}
    canonical: dict[tuple[str, str], str] = {}

    for e in entities:
        key = (str(e["type"]), str(e["canonical"] or e["display"]))
        counts[key] += 1
        refs.setdefault(key, []).append(str(e["ref"]))
        canonical[key] = str(e["canonical"] or e["display"])

    items = []
    for (type_, name), count in sorted(
        counts.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1])
    ):
        items.append(
            {
                "type": type_,
                "name": name,
                "canonical": canonical[(type_, name)],
                "count": count,
                "refs": refs[(type_, name)][:200],
            }
        )

    return {
        "schema": "yinglian-semantic-v1",
        "total": len(entities),
        "distinct": len(items),
        "counts_by_type": dict(Counter(str(e["type"]) for e in entities)),
        "entities": items,
    }


def build_couplets_index(couplets: list[dict]) -> dict:
    items = []
    for i, c in enumerate(couplets, 1):
        upper = c.get("upper", "")
        lower = c.get("lower", "")
        source = c.get("lower_source", "")
        marks = c.get("editorial_markers", [])
        items.append(
            {
                "id": f"C{i:04d}",
                "book": c.get("book", ""),
                "volume": c.get("volume", ""),
                "section": c.get("section", ""),
                "entry": c.get("entry", ""),
                "ref": c.get("ref", ""),
                "type": c.get("type", "联语"),
                "upper": upper,
                "lower": lower,
                "lower_source": source,
                "editorial_markers": marks,
                "upper_len": len(upper),
                "lower_len": len(lower),
                "text": c.get("quote", ""),
                "author": c.get("author"),
                "author_near": c.get("author_near"),
                "place": c.get("place"),
                "context": c.get("context", ""),
            }
        )

    with_source = sum(1 for i in items if i["lower_source"])
    equal_len = sum(1 for i in items if i["upper_len"] == i["lower_len"])
    return {
        "schema": "yinglian-couplets-v1",
        "total": len(items),
        "counts_by_type": dict(Counter(i["type"] for i in items)),
        "with_lower_source": with_source,
        "equal_length": equal_len,
        "equal_length_ratio": round(equal_len / len(items), 4) if items else 0.0,
        "items": items,
    }


def annotate_book_context(
    node: Node,
    book: str = "",
    volume: str = "",
    section: str = "",
    entry: str = "",
) -> Iterable[tuple[Node, str, str, str, str]]:
    """遍历节点，返回 (node, book, volume, section, entry) 上下文。"""
    if node.kind == "book":
        book = node.text
        volume = section = entry = ""
    elif node.kind == "volume":
        volume = node.text
        section = entry = ""
    elif node.kind == "section":
        section = node.text
        entry = ""
    elif node.kind == "entry":
        entry = node.text

    yield node, book, volume, section, entry
    for child in node.children:
        yield from annotate_book_context(child, book, volume, section, entry)


def generate(out_path: Path = TAGGED_PATH) -> None:
    doc = parse_document()

    entities: list[dict] = []
    couplets: list[dict] = []
    body_parts: list[str] = [yaml_front_matter(doc)]
    body_parts.append(f"# [0] {doc.metadata['title']}")
    body_parts.append(
        f"> {doc.metadata['dynasty']}·{doc.metadata['author']}撰；"
        f"源文件 {doc.metadata['source_lines']} 行。"
    )
    body_parts.append(build_legend())
    body_parts.append(build_toc(doc))

    if doc.author_intro:
        body_parts.append(
            render_block(doc.author_intro, 2, BIO_TITLE, entities, couplets)
        )

    # 为联语补充书籍/卷/门类/条目上下文
    context_map: dict[str, tuple[str, str, str, str]] = {}
    for node, book, volume, section, entry in annotate_book_context(doc.author_intro) if doc.author_intro else []:
        context_map[node.id] = (book, volume, section, entry)
    for book in doc.books:
        for node, b, v, s, e in annotate_book_context(book):
            context_map[node.id] = (b, v, s, e)

    for book in doc.books:
        body_parts.append(render_block(book, 2, book.text, entities, couplets))

    for c in couplets:
        ref = str(c.get("ref", ""))
        b, v, s, e = context_map.get(ref, ("", "", "", ""))
        c["book"] = b
        c["volume"] = v
        c["section"] = s
        c["entry"] = e

    markdown = "\n\n".join(p for p in body_parts if p) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ENTITIES_PATH.write_text(
        json.dumps(build_entities_index(entities), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    COUPLETS_PATH.write_text(
        json.dumps(build_couplets_index(couplets), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    STRUCTURE_PATH.write_text(
        json.dumps(build_structure(doc), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"written {out_path} ({len(markdown):,} chars)")
    print(f"entities: {len(entities):,} tags / {len(build_entities_index(entities)['entities']):,} distinct")
    print(f"couplets: {len(couplets):,}")
    print(f"structure: {STRUCTURE_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=TAGGED_PATH,
        help="输出 Markdown 路径",
    )
    args = parser.parse_args()
    generate(args.out)


if __name__ == "__main__":
    main()
