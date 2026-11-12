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
    7. 紫色编号目录（章节/条目 的 caption 与父节点标签）完整
    8. 目录排序（零填充「序」字段）与紫色编号一致
    9. 正文里的筛选器参数（`filter:"…"`）括号配平
    10. 每个标签都有同名 tiddler（否则标签胶囊显示 "Missing tiddler"）

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


def tid_header_defects(path: Path) -> list[str]:
    """检查 .tid 的头是否合法，返回问题描述列表。

    TiddlyWiki 的 deserializer（boot.js 的 tiddlerdeserializer/tid）用
    `text.split(/\\r?\\n\\r?\\n/mg)` 切分头部与正文：
      - 头部每行必须是 `name: value` 字段（`#` 开头为注释）
      - 若正文第一行不含冒号，它会连同正文一起被当成字段吞掉

    所以必须存在真正的空行，且头部不能混入正文的行。
    """
    raw = path.read_text(encoding="utf-8")
    problems: list[str] = []
    if "\n\n" not in raw:
        return ["头与正文之间缺少空行（正文会被当成字段解析）"]
    header = raw.split("\n\n", 1)[0]
    for line in header.split("\n"):
        if not line.strip() or line.startswith("#"):
            continue
        if ":" not in line:
            problems.append(f"头部含非字段行：{line[:40]}")
    return problems


def parse_fields(path: Path) -> dict[str, str]:
    """解析 .tid 头部，返回全部 name: value 字段。"""
    raw = path.read_text(encoding="utf-8")
    header = raw.split("\n\n", 1)[0]
    fields: dict[str, str] = {}
    for line in header.split("\n"):
        if not line.strip() or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()
    return fields


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
    all_fields: dict[str, dict[str, str]] = {}
    bodies: dict[str, str] = {}
    malformed: list[tuple[str, str]] = []
    for p in sorted(tiddlers_dir.rglob("*.tid")):
        defects = tid_header_defects(p)
        if defects:
            malformed.append((str(p.relative_to(tiddlers_dir)), defects[0]))
        title, text, tags = parse_tid(p)
        if title in titles:
            dupes.append(title)
        titles[title] = p
        all_tags[title] = tags
        all_fields[title] = parse_fields(p)
        bodies[title] = text

    errors: list[str] = []

    print(f"wiki 目录：{wiki_dir}")
    print(f"tiddler 总数：{len(titles)}")
    print()

    # ---- 0. .tid 文件结构 ----
    if malformed:
        errors.append(f".tid 结构不合法 {len(malformed)} 个，例：{malformed[:3]}")
    else:
        print("✓ 0. 全部 .tid 的头/正文分隔正确（正文不会被当成字段吞掉）")

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

    # ---- 7. 紫色编号目录（TiddlyWiki 标准 TOC 机制）----
    toc_problems: list[str] = []

    if "TableOfContents" not in titles:
        toc_problems.append("缺少 TableOfContents 目录根 tiddler")
    else:
        toc_tags = all_tags.get("TableOfContents", [])
        if "$:/tags/SideBar" not in toc_tags:
            toc_problems.append("TableOfContents 未打 $:/tags/SideBar 标签（不会出现在侧栏）")
        if "toc-selective-expandable" not in bodies.get("TableOfContents", ""):
            toc_problems.append("TableOfContents 正文未调用标准 toc 宏")

    # 目录节点：用 caption 字段承载紫色编号
    toc_nodes = 0
    for title in titles:
        if not (title.startswith("章节/") or title.startswith("条目/")):
            continue
        fields = all_fields.get(title, {})
        caption = fields.get("caption", "")
        if not caption:
            toc_problems.append(f"{title} 缺 caption 字段（目录中不显示紫色编号）")
            continue
        if '<span class="pn">' not in caption:
            toc_problems.append(f"{title} 的 caption 未含紫色编号标记")
        toc_nodes += 1

    # 父子关系：子 tiddler 必须被打上父 tiddler 的标题标签。
    # 父节点的 tiddler 标题由其紫色编号决定：段落 → 条目/<id>，其余 → 章节/<id>。
    entry_ids = {t.split("/", 1)[1] for t in titles if t.startswith("条目/")}
    orphan = 0
    for title in titles:
        if not (title.startswith("章节/") or title.startswith("条目/")):
            continue
        nid = title.split("/", 1)[1]
        parent_id = nid.rsplit(".", 1)[0] if "." in nid else ""
        if not parent_id:
            # 顶层（书 / 作者简介）：应打 TableOfContents 标签
            if "TableOfContents" not in all_tags.get(title, []):
                orphan += 1
            continue
        parent_title = ("条目/" if parent_id in entry_ids else "章节/") + parent_id
        if parent_title not in titles:
            toc_problems.append(f"{title} 的父节点 {parent_title} 不存在")
        elif parent_title not in all_tags.get(title, []):
            orphan += 1

    if orphan:
        toc_problems.append(f"{orphan} 个目录节点未挂上父节点标签（TOC 层级会断）")
    if toc_problems:
        errors.append("目录有问题：" + "；".join(toc_problems[:5]))
    else:
        print(f"✓ 7. 紫色编号目录完整（{toc_nodes} 个节点，父子标签关系全部正确）")

    # 排序：TOC 宏用 `sortan[序]` 排序，"序" 是零填充的紫色编号，
    # 字典序即数值序。此处独立复算一遍，防止将来改动破坏顺序。
    def _sortkey(value: str) -> tuple[int, ...]:
        try:
            return tuple(int(seg) for seg in value.split("."))
        except ValueError:
            return (0,)

    sort_bad: list[str] = []
    by_parent: dict[str, list[tuple[str, str]]] = {}
    for title in titles:
        if not (title.startswith("章节/") or title.startswith("条目/")):
            continue
        nid = title.split("/", 1)[1]
        parent = nid.rsplit(".", 1)[0] if "." in nid else ""
        key = all_fields.get(title, {}).get("序", "")
        if not key:
            sort_bad.append(f"{title} 缺「序」字段")
            continue
        by_parent.setdefault(parent, []).append((key, nid))
    for parent, kids in by_parent.items():
        # 同一父节点下，按「序」排序后应与按紫色编号排序一致
        by_seq = [nid for _, nid in sorted(kids)]
        by_num = [nid for _, nid in sorted(kids, key=lambda kv: _sortkey(kv[1]))]
        if by_seq != by_num:
            sort_bad.append(f"父 {parent or '(顶层)'}：按序={by_seq[:3]} 按号={by_num[:3]}")
    if sort_bad:
        errors.append(f"目录排序错误 {len(sort_bad)} 处：{sort_bad[:3]}")
    else:
        print(f"✓ 8. 目录排序正确（{len(by_parent)} 个父节点下，同级「序」与紫色编号一致）")

    # 筛选器静态检查：TiddlyWiki 的 `parseFilter` 遇到不闭合的括号会抛
    # "Missing [ in filter expression"，但 `compileFilter` 把它吞成一个
    # 报错的桩函数——页面只多出一行红字，构建/导出本身全都"成功"。
    # 所以必须在导出侧做一次括号配平，否则这类错误会静默随包发布。
    FILTER_ARG_RE = re.compile(r'filter(?::|=)"([^"]*)"')
    filter_bad: list[str] = []
    filter_count = 0
    for title, text in bodies.items():
        for m in FILTER_ARG_RE.finditer(text):
            filter_count += 1
            depth = 0
            for ch in m.group(1):
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth < 0:
                        break
            if depth != 0:
                filter_bad.append(f"{title}：filter:\"{m.group(1)}\"")
    if filter_bad:
        errors.append(f"筛选器括号不配平 {len(filter_bad)} 处：{filter_bad[:3]}")
    elif filter_count == 0:
        errors.append("正文里找不到任何 filter 参数（导出可能不完整）")
    else:
        print(f"✓ 9. 筛选器参数括号全部配平（{filter_count} 处）")

    # ---- 10. 标签同名 tiddler（"Missing tiddler" 的根因）----
    # TiddlyWiki 的标签胶囊用**标签名本身**查同名 tiddler 来判断存在 / 缺失
    # （core/wiki/macros/tag.tid 的 `[<__tag__>is[missing]...]`，
    #  is[missing] 只认真 tiddler，不认 shadow，见
    #  core/modules/filters/is/missing.js）。
    # 查不到同名 tiddler，标签就渲染成 missing，点进去只见一句
    # "Missing tiddler …"（$:/language/MissingTiddler/Hint）。
    #
    # 这一项要求：**每个被使用的标签都必须有同名 tiddler**
    # （锚点 tiddler 或本来就有）。
    used_tags: set[str] = set()
    for tags in all_tags.values():
        used_tags.update(tags)
    # 系统标签由 TiddlyWiki 核心/主题提供，不在本项目责任范围内
    checkable = {t for t in used_tags if not t.startswith("$:/")}
    without_page = sorted(t for t in checkable if t not in titles)
    if without_page:
        errors.append(f"有标签但无同名 tiddler {len(without_page)} 个"
                      f"（标签会显示 Missing tiddler）：{without_page[:10]}")
    else:
        print(f"✓ 10. 全部 {len(checkable)} 个标签均有同名 tiddler"
              f"（标签不会显示 Missing tiddler）")

    # 锚点 tiddler 必须指向存在的 tiddler，且不得给自己打同名标签
    anchor_bad: list[str] = []
    anchor_selfref: list[str] = []
    anchor_count = 0
    for title, tags in all_tags.items():
        if all_fields.get(title, {}).get("锚点") != "true":
            continue
        anchor_count += 1
        target = all_fields.get(title, {}).get("指向", "")
        if target not in titles:
            anchor_bad.append(f"{title} → {target}")
        if title in tags:
            anchor_selfref.append(title)
    if anchor_bad:
        errors.append(f"锚点指向不存在的 tiddler {len(anchor_bad)} 个：{anchor_bad[:5]}")
    if anchor_selfref:
        errors.append(f"锚点给自己打了同名标签 {len(anchor_selfref)} 个"
                      f"（会污染筛选结果）：{anchor_selfref[:5]}")
    if not anchor_bad and not anchor_selfref:
        print(f"✓ 10b. {anchor_count} 个锚点 tiddler 指向有效，且无自引用标签")

    # 锚点正文不应再出现 "Missing tiddler" 字样（否则页面自身又会误导读者）
    anchor_leak = [t for t, body in bodies.items()
                   if all_fields.get(t, {}).get("锚点") == "true"
                   and "Missing tiddler" in body]
    if anchor_leak:
        errors.append(f"锚点正文含 “Missing tiddler” 字样 {len(anchor_leak)} 个："
                      f"{anchor_leak[:5]}")
    else:
        print("✓ 10c. 锚点正文无 “Missing tiddler” 残留")

    # 锚点正文用筛选器动态列举相关 tiddler。这些筛选器必须真的能选出
    # 存在的 tiddler——否则页面打开是一堆空标题。
    # 这里用 Python 独立复算一遍（不调用 TiddlyWiki）。
    ANCHOR_FILTER_RE = re.compile(r'<\$list filter="([^"]*)"')
    anchor_filter_bad: list[str] = []
    anchor_filter_count = 0
    for title, body in bodies.items():
        if all_fields.get(title, {}).get("锚点") != "true":
            continue
        for flt in ANCHOR_FILTER_RE.findall(body):
            anchor_filter_count += 1
            # 只处理本项目生成的固定形状：
            #   [tag[X]prefix[P/]sort[F]]   —— 限定前缀的分类列表
            #   [tag[X]sort[F]]             —— 不限前缀的列表
            m = re.fullmatch(
                r"\[tag\[(.+?)\](?:prefix\[(.+?)/\])?(?:sort\[(.+?)\])?\]", flt)
            if not m:
                anchor_filter_bad.append(f"{title}: 无法解析的筛选器 {flt}")
                continue
            tag, prefix, sort_field = m.group(1), m.group(2), m.group(3)
            if prefix:
                matched = [t for t, tgs in all_tags.items()
                           if tag in tgs and t.startswith(prefix + "/")]
            else:
                matched = [t for t, tgs in all_tags.items() if tag in tgs]
            if not matched:
                anchor_filter_bad.append(f"{title}: {flt} 选出 0 个 tiddler")
                continue
            # 排序字段必须真的存在于这些 tiddler 上，否则排序结果无意义
            if sort_field and sort_field != "title":
                missing_field = [t for t in matched
                                 if sort_field not in all_fields.get(t, {})]
                if missing_field:
                    anchor_filter_bad.append(
                        f"{title}: {flt} 排序字段「{sort_field}」在 "
                        f"{len(missing_field)} 个 tiddler 上不存在")
    if anchor_filter_bad:
        errors.append(f"锚点筛选器有问题 {len(anchor_filter_bad)} 处："
                      f"{anchor_filter_bad[:5]}")
    else:
        print(f"✓ 10d. {anchor_filter_count} 个锚点筛选器都能选出存在的 tiddler"
              f"（且排序字段有效）")

    # 锚点的「相关清单」必须**一项一行**：每个条目都要套在 <li> 里，
    # 否则一长串链接会挤在同一行，读起来是一团。
    # 这里检查每个锚点的每个 <$list> 是否紧跟着 <$genesis $type="li">。
    anchor_rowspan_bad: list[str] = []
    anchor_rowspan_ok = 0
    for title, body in bodies.items():
        if all_fields.get(title, {}).get("锚点") != "true":
            continue
        # 逐个 <$list ...>…</$list> 片段
        for m in re.finditer(r"<\$list filter=\"[^\"]*\">(.*?)</\$list>", body, re.S):
            seg = m.group(1)
            if '<$genesis $type="li"' not in seg:
                anchor_rowspan_bad.append(f"{title}: <$list> 内没有 <li> 包裹")
            else:
                anchor_rowspan_ok += 1
    if anchor_rowspan_bad:
        errors.append(f"锚点清单未做到一项一行 {len(anchor_rowspan_bad)} 处："
                      f"{anchor_rowspan_bad[:5]}")
    else:
        print(f"✓ 10e. {anchor_rowspan_ok} 个锚点清单均一项一行（<li> 包裹）")

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
