#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验导出的 TiddlyWiki 是否自洽。

检查项：
    1. 无重复标题
    2. 所有内部链接（[[...]]）都能解析到存在的 tiddler
    3. 所有实体标签都有对应的实体 tiddler
    4. 条目 tiddler 覆盖全部源段落
    5. 联语 tiddler 覆盖全部联语
    6. 每个条目的实体 tag 与正文标注一致

用法：
    python3 scripts/verify_tiddlywiki.py
    python3 scripts/verify_tiddlywiki.py --wiki tiddlywiki/楹联丛话全编
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# TiddlyWiki 链接语法为 [[显示文本|目标]]，目标取竖线后的最后一段。
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
# <$link to="标题">…</$link> 形式的链接
WIDGET_LINK_RE = re.compile(r'<\$link\s+to="([^"]+)"')

# 原始段落文本，校验第 6 项时与正文比对
ORIGINAL_PARAGRAPHS: dict[str, str] = {}


def parse_tid(path: Path) -> tuple[str, str, list[str]]:
    """解析 .tid → (title, text, tags)。"""
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("\n\n", 1)
    header = parts[0]
    text = parts[1] if len(parts) > 1 else ""
    title = ""
    tags: list[str] = []
    for line in header.split("\n"):
        if line.startswith("title:"):
            title = line[6:].strip()
        elif line.startswith("tags:"):
            tags = parse_tags(line[5:].strip())
    return title, text, tags


def parse_tags(value: str) -> list[str]:
    """解析 tags 字段：空格分隔，`[[...]]` 包裹含空格的标签。"""
    out: list[str] = []
    for m in re.finditer(r"\[\[([^\]]*)\]\]|(\S+)", value):
        out.append(m.group(1) if m.group(1) is not None else m.group(2))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", default=str(ROOT / "tiddlywiki" / "楹联丛话全编"))
    args = ap.parse_args()
    wiki_dir = Path(args.wiki).resolve()
    tiddlers_dir = wiki_dir / "tiddlers"

    if not tiddlers_dir.exists():
        print(f"找不到 tiddlers 目录：{tiddlers_dir}")
        return 1

    # ---- 载入全部 tiddler ----
    titles: dict[str, Path] = {}
    dupes: list[str] = []
    all_tags: dict[str, list[str]] = {}
    bodies: dict[str, str] = {}
    for p in sorted(tiddlers_dir.rglob("*.tid")):
        title, text, tags = parse_tid(p)
        if title in titles:
            dupes.append(title)
        titles[title] = p
        all_tags[title] = tags
        bodies[title] = text

    errors: list[str] = []

    print(f"wiki 目录：{wiki_dir}")
    print(f"tiddler 总数：{len(titles)}")
    print()

    # ---- 1. 重复标题 ----
    if dupes:
        errors.append(f"重复标题 {len(dupes)} 个：{dupes[:10]}")
    else:
        print("✓ 1. 无重复标题")

    # ---- 2. 链接完整性 ----
    broken: list[tuple[str, str]] = []
    link_count = 0
    for title, text in bodies.items():
        for m in LINK_RE.finditer(text):
            inner = m.group(1).strip()
            # [[显示|目标]] → 目标是竖线后的最后一段；无竖线时整段即目标
            target = inner.split("|")[-1].strip()
            link_count += 1
            if target not in titles:
                broken.append((title, target))
        for m in WIDGET_LINK_RE.finditer(text):
            target = m.group(1).strip()
            link_count += 1
            if target not in titles:
                broken.append((title, target))
    if broken:
        errors.append(f"断链 {len(broken)} 处，例：{broken[:5]}")
    else:
        print(f"✓ 2. 全部 {link_count} 处内部链接均可解析")

    # ---- 3. 实体标签 → 实体 tiddler ----
    entity_tags: set[str] = set()
    for tags in all_tags.values():
        for t in tags:
            if "/" in t and not t.startswith("$:/"):
                entity_tags.add(t)
    missing_entity: list[str] = []
    from export_tiddlywiki import TYPE_PREFIX as _TP  # noqa: E402

    entity_prefixes = set(_TP.values())
    for tag in sorted(entity_tags):
        prefix, _, name = tag.partition("/")
        # 只有实体类型前缀才要求存在实体 tiddler；
        # 「书/门类」是层级标签，不对应实体。
        if prefix not in entity_prefixes:
            continue
        if f"实体/{prefix}/{name}" not in titles:
            missing_entity.append(tag)
    if missing_entity:
        errors.append(f"无对应实体 tiddler 的标签 {len(missing_entity)} 个：{missing_entity[:10]}")
    else:
        print(f"✓ 3. {len(entity_tags)} 个实体标签均有对应 tiddler")

    # ---- 4. 条目覆盖 ----
    # 源段落 id：以 structure.json 的段落/注记节点为准（独立于导出器）。
    source_ids: set[str] = set()
    _structure = json.loads((DATA / "structure.json").read_text(encoding="utf-8"))

    def _collect(node: dict) -> None:
        if node["kind"] in ("paragraph", "note"):
            source_ids.add(node["id"])
        for child in node.get("children") or []:
            _collect(child)

    if _structure.get("author_intro"):
        _collect(_structure["author_intro"])
    for _book in _structure.get("books", []):
        _collect(_book)
    entry_ids = {t.split("/", 1)[1] for t in titles if t.startswith("条目/")}
    if entry_ids != source_ids:
        only_src = sorted(source_ids - entry_ids)[:10]
        only_tw = sorted(entry_ids - source_ids)[:10]
        errors.append(f"条目覆盖不一致：源 {len(source_ids)} / 导出 {len(entry_ids)}；"
                      f"仅源 {only_src}；仅导出 {only_tw}")
    else:
        print(f"✓ 4. 全部 {len(source_ids)} 个源段落均已导出")

    # ---- 5. 联语覆盖 ----
    couplets = json.loads((DATA / "couplets.json").read_text(encoding="utf-8"))["items"]
    tw_couplets = {t.split("/", 1)[1] for t in titles if t.startswith("联语/")}
    src_couplets = {c["id"] for c in couplets}
    if tw_couplets != src_couplets:
        errors.append(f"联语覆盖不一致：源 {len(src_couplets)} / 导出 {len(tw_couplets)}")
    else:
        print(f"✓ 5. 全部 {len(src_couplets)} 副联语均已导出")

    # ---- 6. 条目 tag 与正文实体一致 ----
    from export_tiddlywiki import ENTITY_RE, TYPE_PREFIX  # noqa: E402

    mismatch: list[str] = []
    checked = 0
    for title in titles:
        if not title.startswith("条目/"):
            continue
        checked += 1
        pid = title.split("/", 1)[1]
        orig = ORIGINAL_PARAGRAPHS.get(pid, "")
        want: set[str] = set()
        for m in ENTITY_RE.finditer(orig):
            type_ = m.group(1)
            canon = m.group(3) or m.group(2)
            prefix = TYPE_PREFIX.get(type_)
            if prefix:
                want.add(f"{prefix}/{canon}")
        got = {t for t in all_tags[title] if "/" in t}
        if want - got:
            mismatch.append(f"{title}: 缺少 {sorted(want - got)[:3]}")
    if mismatch:
        errors.append(f"条目 tag 与正文实体不一致 {len(mismatch)} 例：{mismatch[:3]}")
    else:
        print(f"✓ 6. {checked} 个条目的实体 tag 与正文标注一致")

    # ---- 统计 ----
    kinds = Counter(t.split("/", 1)[0] if "/" in t else "根" for t in titles)
    print()
    print("tiddler 分布：")
    for k, n in kinds.most_common():
        print(f"  {k:6} {n:6}")

    tag_counts: Counter[str] = Counter()
    for tags in all_tags.values():
        tag_counts.update(tags)
    print()
    print(f"不同标签总数：{len(tag_counts)}")
    print("最常用标签 Top 12：")
    for t, n in tag_counts.most_common(12):
        print(f"  {t:24} {n}")

    print()
    if errors:
        print("校验未通过：")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    print("全部校验通过 ✓")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import export_tiddlywiki as _ex

    _p = _ex.parse_marked_markdown(DATA / "楹联丛话全编.tagged.md")
    ORIGINAL_PARAGRAPHS.update(_p["paragraphs"])
    sys.exit(main())
