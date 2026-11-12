#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把《楹联丛话全编》标注结果导出为单个 TiddlyWiki。

原文条目是 tiddler，实体是 tag，因此可以直接用 TiddlyWiki 的筛选器
做交叉检索（`[tag[人名/林则徐]tag[楹联丛话]]`）。

用法：
    python3 scripts/export_tiddlywiki.py
    python3 scripts/export_tiddlywiki.py --out ../tiddlywiki/楹联丛话

产物（写入 <out>/）：
    tiddlywiki.info            编辑器 / 服务端配置
    tiddlers/                  全部 tiddler（.tid）
        条目/<编号>.tid        每个原文段落一个 tiddler
        联语/<Cxxxx>.tid       每副联语一个 tiddler
        实体/<类型>/<名>.tid   每个规范名一个 tiddler
        章节/<编号>.tid        书 / 卷 / 门类 / 条目 导航
        <标签>.tid             锚点 tiddler：与标签同名，见下
        <索引>.tid             首页、书目、实体索引、联语索引、体例说明

映射约定：
    条目 → tiddler（含正文与所属联语链接）
    实体 → tag（`人名/林则徐`、`地点/扬州`、`典籍/蜀梼杌`…）
    归属 → tag（`楹联丛话`、`楹联丛话/故事`）

锚点 tiddler：
    TiddlyWiki 的标签胶囊用**标签名本身**查同名 tiddler 来判断「存在 / 缺失」
    （core/wiki/macros/tag.tid 的 `[<__tag__>is[missing]]`）。查不到就把标签
    渲染成 missing，点进去只会看到一句 "Missing tiddler …"。
    本项目的实体标签是 `典籍/古格言`，真正的实体页却叫 `实体/典籍/古格言`，
    名字对不上 → 标签全部显示为缺失。
    修法是给每个标签补一个**与标签同名**的轻量锚点 tiddler，正文用**筛选器**
    动态列出该标签关联的全部内容（相关条目 / 相关联语 / 相关章节 / 相关实体）。
    锚点不打自己的标签名，也不打「实体」，因此 `[tag[…]]` 的筛选语义不变。

校验：见 scripts/verify_tiddlywiki.py（用独立数据源交叉核对）。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TID_RE = re.compile(r"[\\/:*?\"<>|\r\n\t]")

# 目录根 tiddler：TiddlyWiki 标准 TOC 机制以它为标签根
TOC_ROOT = "TableOfContents"

# ---------------------------------------------------------------------------
# 锚点 tiddler
# ---------------------------------------------------------------------------

# 锚点自用的标记标签。用独立标记而不是复用「实体」，
# 否则 `[tag[实体]]` 的计数会被锚点污染（C2）。
ANCHOR_TAG = "锚点"

# 锚点 tiddler 的存放目录（**仅**是文件路径，标题仍是标签名本身）。
ANCHOR_DIR = "锚点"


def safe_filename(title: str) -> str:
    """把 tiddler 标题转成安全的文件名。"""
    name = TID_RE.sub("_", title).strip()
    return name[:180] or "untitled"


def escape_field(value: str) -> str:
    """字段值里的换行会破坏 .tid 头，需压平。"""
    return value.replace("\r", " ").replace("\n", " ").strip()


def write_tid(path: Path, title: str, text: str, fields: dict[str, str]) -> None:
    """按 .tid 规范写一个 tiddler 文件。

    格式（见 TiddlyWiki5 boot/boot.js 的 tiddlerdeserializer/tid）：
      - 第一段是 `name: value` 字段，每行一个，`#` 开头为注释
      - **空行之后**才是正文

    注意：头与正文之间必须有一个真正的空行（两个换行符）。
    deserializer 用 `text.split(/\\r?\\n\\r?\\n/mg)` 切分，
    若少了这个空行，正文第一行会被当成字段解析而丢失。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"title: {escape_field(title)}"]
    for k, v in fields.items():
        if v is None or v == "":
            continue
        lines.append(f"{k}: {escape_field(str(v))}")
    body = text if text.endswith("\n") else text + "\n"
    # 头与正文之间：两个换行符 = 一个空行
    path.write_text("\n".join(lines) + "\n\n" + body, encoding="utf-8")


def build_tags(tag: str) -> str:
    """tags 字段：空格分隔；含空格的用 [[...]] 包裹。"""
    if not tag:
        return ""
    if re.search(r"\s", tag):
        return f"[[{tag}]]"
    return tag


# ---------------------------------------------------------------------------
# 标签体系
# ---------------------------------------------------------------------------

# 实体类型 → tag 前缀
TYPE_PREFIX = {
    "@": "人名",
    "=": "地点",
    ";": "官职",
    "%": "时间",
    "&": "氏族",
    "◆": "朝代",
    "^": "名物",
    "~": "族群",
    "•": "器物",
    "!": "天文",
    "?": "神祇",
    "+": "生物",
    "{": "典籍",
    ":": "礼仪",
    "[": "刑法",
    "_": "思想",
    "#": "身份",
    "$": "数量",
}

TYPE_DESC = {
    "@": "人名", "=": "地点", ";": "官职", "%": "时间", "&": "氏族",
    "◆": "朝代/邦国", "^": "名物/制度", "~": "族群", "•": "器物",
    "!": "天文", "?": "神祇/神话", "+": "生物", "{": "典籍",
    ":": "礼仪", "[": "刑法", "_": "思想概念", "#": "身份", "$": "数量",
}

# 实体类型的**类型名**（即上表取值的集合，18 个 + 「出处」）。
# 实体 tiddler 打 `tags: 实体 <类型名>`，所以这些类型名本身也是标签；
# 它们同样需要同名锚点，否则类型分类标签仍显示为 missing。
ENTITY_TYPE_NAMES = frozenset(TYPE_PREFIX.values()) | {"出处"}


# ---------------------------------------------------------------------------
# 各类 tiddler 的构建
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 标注正文解析
# ---------------------------------------------------------------------------

PURPLE_RE = re.compile(r"^\[([0-9.]+)\][ \t]?(.*)$")
ANCHOR_RE = re.compile(r'^<a id="pn-([0-9.]+)"></a>$')
HEADING_RE = re.compile(r"^(#{2,4}) \[([0-9.]+)\] ?(.*)$")
ENTITY_RE = re.compile(r"〖([@=;%&◆^~•!?+{:[_#$])([^〗|]*)(?:\|([^〗]*))?〗")
RHETORIC_RE = re.compile(r"〘([^〙]*)〙")


def parse_marked_markdown(path: Path) -> dict:
    """解析标注 Markdown，返回段落、标题与语义块。

    返回 {"paragraphs": {pid: text}, "headings": {id: (level, title)},
          "blocks": {pid: label}}
    """
    lines = path.read_text(encoding="utf-8").split("\n")
    paragraphs: dict[str, str] = {}
    headings: dict[str, tuple[int, str]] = {}
    blocks: dict[str, str] = {}
    current_block = ""

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = ANCHOR_RE.match(line)
        if m:
            pid = m.group(1)
            # 段落正文：紧随锚点之后，以空行或下一锚点/标题为界
            body: list[str] = []
            j = i + 1
            block_label = current_block
            while j < n:
                nxt = lines[j]
                if not nxt.strip():
                    break
                if ANCHOR_RE.match(nxt) or HEADING_RE.match(nxt):
                    break
                if nxt.startswith("::: "):
                    # 语义块起始：正文尚未开始时跳过并记下标签
                    if not body:
                        block_label = nxt[4:].strip()
                        j += 1
                        continue
                    break
                if nxt.strip() == ":::":
                    # 语义块结束
                    break
                body.append(nxt)
                j += 1
            if body:
                text = "\n".join(body)
                pm = PURPLE_RE.match(body[0])
                if pm:
                    text = pm.group(2)
                    # 续行（[1.2.3.1] 之类）保留其余行
                    for extra in body[1:]:
                        em = PURPLE_RE.match(extra)
                        text += ("\n" if em else "") + (em.group(2) if em else extra)
                paragraphs[pid] = text
                blocks[pid] = block_label
            i = j
            continue

        hm = HEADING_RE.match(line)
        if hm:
            headings[hm.group(2)] = (len(hm.group(1)), hm.group(3))
            i += 1
            continue

        if line.startswith("::: "):
            current_block = line[4:].strip()
            i += 1
            continue
        if line.strip() == ":::":
            current_block = ""
            i += 1
            continue

        i += 1

    return {"paragraphs": paragraphs, "headings": headings, "blocks": blocks}


# ---------------------------------------------------------------------------
# 标记渲染
# ---------------------------------------------------------------------------


def render_marked(text: str, alias_to_canonical: dict[tuple[str, str], str]) -> str:
    """把标注正文渲染为 TiddlyWiki wikitext。

    - 〖@纪文达|纪昀〗 → [[纪文达|实体/人名/纪昀]]（链接到规范名实体）
    - 〖@林则徐〗     → [[实体/人名/林则徐]]
    - 〘※脍炙人口〙   → ''脍炙人口''（修辞标记）
    - 〖聯〗           → 联语标记，转为斜体
    """
    # 修辞标记先处理，避免其内部字符被实体规则误伤
    def rhetoric(m: re.Match[str]) -> str:
        inner = m.group(1)
        if inner.startswith("※"):
            return "''" + inner[1:].strip() + "''"
        return inner

    text = RHETORIC_RE.sub(rhetoric, text)

    def entity(m: re.Match[str]) -> str:
        type_ = m.group(1)
        display = m.group(2)
        canonical = m.group(3) or display
        prefix = TYPE_PREFIX.get(type_, "")
        # 链接指向实体 tiddler（实体/人名/纪昀）
        target = f"实体/{prefix}/{canonical}" if prefix else canonical
        # 有别名：显示别名，链接规范名
        if m.group(3):
            return f"[[{display}|{target}]]"
        # 无别名：若该词在语料中只是别名，链接到其规范名
        alias_canon = alias_to_canonical.get((type_, display))
        if alias_canon and alias_canon != display:
            aprefix = prefix or "人名"
            return f"[[{display}|实体/{aprefix}/{alias_canon}]]"
        # 无别名：显示规范名本身，链接到实体 tiddler
        return f"[[{canonical}|{target}]]"

    text = ENTITY_RE.sub(entity, text)

    # 〖聯〗 联语标记
    text = text.replace("〖聯〗", "//")
    return text


def strip_markers(text: str) -> str:
    """去掉全部标注标记，得到纯文本（用于摘要/索引）。"""
    text = RHETORIC_RE.sub(lambda m: m.group(1).lstrip("※"), text)
    text = ENTITY_RE.sub(lambda m: m.group(3) or m.group(2), text)
    text = text.replace("〖聯〗", "")
    return text


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


class TiddlyWikiBuilder:
    """收集 tiddler 并写出 .tid 文件。"""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.tiddlers_dir = out_dir / "tiddlers"
        self.tiddlers: dict[str, dict] = {}
        self.duplicate_titles: list[str] = []

    def add(self, title: str, text: str, tags: list[str], fields: dict | None = None,
            anchor: bool = False) -> None:
        if title in self.tiddlers:
            self.duplicate_titles.append(title)
            return
        # 去重且保序
        seen: set[str] = set()
        unique_tags: list[str] = []
        for t in tags:
            if t and t not in seen:
                seen.add(t)
                unique_tags.append(t)
        rec = {"title": title, "text": text, "tags": unique_tags, "fields": fields or {},
               "anchor": anchor}
        self.tiddlers[title] = rec

    def write(self) -> dict:
        """写出全部 .tid，返回统计。"""
        if self.tiddlers_dir.exists():
            for p in sorted(self.tiddlers_dir.rglob("*.tid")):
                p.unlink()
        by_kind: Counter[str] = Counter()
        for title, rec in self.tiddlers.items():
            parts = title.split("/")
            filename = safe_filename(parts[-1]) + ".tid"
            if rec.get("anchor"):
                # 锚点 tiddler 的**标题**必须与标签名一致，文件另存到
                # tiddlers/锚点/ 下，以免与实体目录混在一起。
                kind = ANCHOR_DIR
                sub = self.tiddlers_dir.joinpath(ANCHOR_DIR, *parts[:-1])
            else:
                kind = parts[0] if len(parts) > 1 else "根"
                sub = self.tiddlers_dir.joinpath(*parts[:-1]) if len(parts) > 1 \
                    else self.tiddlers_dir
            path = sub / filename
            fields = dict(rec["fields"])
            if rec["tags"]:
                fields["tags"] = " ".join(build_tags(t) for t in rec["tags"])
            write_tid(path, title, rec["text"], fields)
            by_kind[kind] += 1
        return dict(by_kind)


def build_alias_map(marked_text: str) -> dict[tuple[str, str], str]:
    """(类型符号, 别名) → 规范名。语料中 `〖@别名|规范名〗` 的形式。

    按类型分开，避免同名异类（如人名与地名重名）串味。
    """
    alias: dict[tuple[str, str], str] = {}
    for m in ENTITY_RE.finditer(marked_text):
        if m.group(3):
            alias.setdefault((m.group(1), m.group(2)), m.group(3))
    return alias


def sort_key(node_id: str) -> str:
    """把紫色编号转成可正确排序的键。

    ``sort[编号]`` 是字典序，"1.3.10" 会排在 "1.3.2" 前面；
    标准 TOC 宏用 ``sortan[编号]`` 做自然排序，但正文里其它
    列表仍走 ``sort[编号]``，故统一改用零填充键。
    """
    return ".".join(f"{int(seg):04d}" for seg in node_id.split("."))


def toc_caption(node: dict | None, preview: str = "") -> str:
    """目录条目的显示文本：紫色编号 + 标题。

    ``caption`` 字段优先于 ``title``（见 core 的 toc-caption 宏），
    因此这里可以放 HTML，用 ``.pn`` 类给紫色编号上色。

    段落级节点没有标题，用正文开头作为摘要（过长则截断）。
    """
    if not node:
        return ""
    nid = node["编号"]
    title = node["标题"]
    if not title:
        title = preview.strip() or nid
        if len(title) > 40:
            title = title[:40] + "…"
    return f'<span class="pn">{nid}</span> {title}'


def build_toc_tree(structure: dict, headings: dict) -> dict[str, dict]:
    """构造紫色编号目录树。

    TiddlyWiki 标准目录宏（``toc-selective-expandable`` 等）用**标签**表达
    父子关系：子 tiddler 被打上父 tiddler **标题**的标签。
    因此这里返回 id → {编号, 标题, 父标题, 层级} 的映射：

        id         紫色编号（structure.json 的节点 id）
        标题       节点标题
        父标题     父节点对应的 tiddler 标题（顶层为 TableOfContents）
        层级       1=书 2=卷/门类 3=条目

    节点标题的 tiddler 标题约定：
        书 / 卷 / 门类 / 条目级 → ``章节/<id>``
        段落 / 注记               → ``条目/<id>``
    """
    tree: dict[str, dict] = {}

    def title_for(node: dict) -> str:
        kind = node["kind"]
        prefix = "条目" if kind in ("paragraph", "note") else "章节"
        return f"{prefix}/{node['id']}"

    def walk(node: dict, parent_title: str, depth: int) -> None:
        nid = node["id"]
        kind = node["kind"]
        title = headings.get(nid, (0, ""))[1] or node.get("title", "")
        tree[nid] = {
            "编号": nid,
            "标题": title,
            "父标题": parent_title,
            "层级": depth,
            "种类": kind,
            "tiddler": title_for(node),
        }
        for child in node.get("children") or []:
            walk(child, title_for(node), depth + 1)

    ai = structure.get("author_intro")
    if ai:
        walk(ai, TOC_ROOT, 1)
    for book in structure.get("books", []):
        walk(book, TOC_ROOT, 1)
    return tree


def build_paragraph_meta(structure: dict, headings: dict) -> dict:
    """节点 id → (书, 卷, 门类, 条目, 路径, 层级)。

    依据 structure.json 的层级判定；标题优先取 Markdown 里的（更完整）。
    同时收录段落与各级标题节点，便于生成导航。
    """
    meta: dict[str, tuple[str, str, str, str, str, str]] = {}

    def walk(node: dict, book: str, volume: str, section: str, entry: str, path: str) -> None:
        kind = node["kind"]
        nid = node["id"]
        title = headings.get(nid, (0, ""))[1] or node.get("title", "")
        nbook, nvolume, nsection, nentry = book, volume, section, entry
        npath = path
        if kind == "book":
            nbook = title or book
            npath = nbook
        elif kind == "volume":
            nvolume = title or volume
            npath = f"{nbook}/{nvolume}" if nbook else nvolume
        elif kind == "section":
            nsection = title or section
            npath = f"{nbook}/{nsection}" if nbook else nsection
        elif kind == "entry":
            nentry = title or entry
            npath = f"{nbook}/{nentry}" if nbook else nentry
        meta[nid] = (nbook, nvolume, nsection, nentry, npath, kind)
        for child in node.get("children") or []:
            walk(child, nbook, nvolume, nsection, nentry, npath)

    ai = structure.get("author_intro")
    if ai:
        walk(ai, "楹联丛话全编", "", "", "", "楹联丛话全编")
    for book in structure.get("books", []):
        walk(book, "", "", "", "", "")

    return meta


def build_toc_tiddler(builder: TiddlyWikiBuilder, toc_tree: dict[str, dict]) -> None:
    """写出目录根 tiddler 与配套样式。

    完全采用 TiddlyWiki 的标准目录机制（``toc`` 系列宏）：

    - 根 tiddler 名为 ``TableOfContents``，标签 ``$:/tags/SideBar``，
      置于侧栏首位（``list-before`` 指向 Open 标签页）；
    - 正文用 ``<<toc-selective-expandable 'TableOfContents' "sortan[序]">>``；
    - 子节点靠**标签**建立父子关系：子 tiddler 被打上父 tiddler 的标题，
      这一步已在各处 ``builder.add`` 时完成。

    ``sortan[序]`` 用自然排序，保证 "1.3.2" 排在 "1.3.10" 之前。
    """
    body = (
        '<div class="tc-table-of-contents">\n\n'
        '<<toc-selective-expandable \'TableOfContents\' "sortan[序]">>\n\n'
        '</div>\n'
    )
    builder.add(TOC_ROOT, body, ["$:/tags/SideBar"],
                fields={"caption": "目录",
                        "list-before": "$:/core/ui/SideBar/Open",
                        "序": "0000"})

    # 紫色编号的配色沿用 docs/index.html 的 .pn 样式
    css = (
        ".tc-sidebar-lists .pn,\n"
        ".tc-table-of-contents .pn {\n"
        "  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;\n"
        "  font-size: .78em;\n"
        "  color: #9b7bb5;\n"
        "  letter-spacing: .02em;\n"
        "  margin-right: .25em;\n"
        "}\n"
        ".tc-table-of-contents .toc-item-selected > a > .tc-toc-caption .pn { color: #7a4b8a; }\n"
        ".tc-table-of-contents .tc-toc-caption { letter-spacing: .02em; }\n"
    )
    builder.add("样式/紫色编号", css, ["$:/tags/Stylesheet"])


# ---------------------------------------------------------------------------
# 锚点 tiddler：让标签胶囊不再显示 "Missing tiddler"
# ---------------------------------------------------------------------------

# 锚点正文里列举相关 tiddler 时用的「相关列表」构件。
#
# 为什么不用核心的 <<list-links>> 宏：它内部是
#   <$genesis $type=<<__type__>> class=<<__class__>>
# 而 `class=<<__class__>>` 在 __class__ 为空串时，属性右值 `>>` 的后一个 `>`
# 会被解析器并进属性值，导致整个标签泄漏成纯文本、列表渲染为空。
# （实测 TiddlyWiki 5.5.0-prerelease：`<<list-links filter:"[…]">>` 输出为空。）
# 所以这里直接用原生构件 <$list> + <$link>，不依赖那个宏。
def related_list(flt: str, field: str = "caption") -> str:
    """生成一段「相关 tiddler」列表。

    flt 是筛选器表达式。显示文字优先取 ``field`` 指定的字段
    （条目 / 章节用 caption，实体用 规范名），字段不存在时退回 title。

    两个必须注意的写法细节（实测 TiddlyWiki 5.5.0-prerelease）：

    - **不要给 ``<$list>`` 起 ``variable``**。一旦改名，列表项的
      ``currentTiddler`` 上下文就丢了，``{{!!title}}`` 与
      ``<<currentTiddler>>`` 全部变空，链接渲染成 missing。
    - 链接目标用 ``<<currentTiddler>>``，不要用 ``{{!!title}}``——
      后者在列表上下文里取到的是**当前**（锚点）tiddler 的 title。
    """
    return (
        "<$list filter=\"" + flt + "\">"
        "<$link to=<<currentTiddler>>>"
        "<$let tv-wikilinks=\"no\">"
        "<$transclude field=\"" + field + "\">"
        "<$view field=\"title\"/>"
        "</$transclude>"
        "</$let>"
        "</$link>"
        "</$list>"
    )


def build_anchor_tiddlers(builder: TiddlyWikiBuilder,
                          all_tags: set[str],
                          entity_tags: list[str],
                          entity_type: dict[str, str]) -> int:
    """为每个「有标签但无同名 tiddler」的标签补一个同名锚点 tiddler。

    背景：TiddlyWiki 的标签胶囊用**标签名本身**查同名 tiddler 来判断
    「存在 / 缺失」——``core/wiki/macros/tag.tid`` 里写的是
    ``[<__tag__>is[missing]then[tc-tag-missing]else[tc-tag-exists]]``，
    而 ``is[missing]`` 走的是 ``core/modules/filters/is/missing.js`` 的
    ``options.wiki.tiddlerExists(title)``，**只认真 tiddler，不认 shadow**。
    标签名查不到同名 tiddler，胶囊就渲染成 missing，点进去只会看到
    ``$:/language/MissingTiddler/Hint``（"Missing tiddler …"）。

    本项目实体标签叫 ``典籍/古格言``，真正的实体页却叫
    ``实体/典籍/古格言``——名字对不上，于是三千多个标签全显示为缺失。

    修法：给每个标签补一个**与标签同名**的轻量锚点 tiddler。
    锚点正文用**筛选器**动态列出与该标签相关的全部 tiddler
    （相关条目 / 相关联语 / 相关章节 / 相关实体），
    而不是一个指向规范页的静态链接。

    约束（见交接文档 §10）：

    - 绝不覆盖已有 tiddler（``if title not in builder.tiddlers``）；
    - 锚点**不给自己打标签**（自引用会污染 ``[tag[...]]`` 的筛选结果）；
    - 锚点只打 ``ANCHOR_TAG`` 一个标记，便于识别与统计。
    """
    # 实体标签 → 规范页标题
    entity_pages = {
        tag: f"实体/{entity_type[tag]}/{tag.split('/', 1)[1]}"
        for tag in entity_tags
    }

    # 类型名标签（实体 tiddler 打 `tags: 实体 <类型名>`）→ 该类型的全部实体
    type_tags = {name: name for name in ENTITY_TYPE_NAMES}

    # 候选标签 = 已用标签 + ANCHOR_TAG 本身。
    # ANCHOR_TAG 是锚点自用的标记标签，锚点建好之后它也会变成「已用标签」，
    # 所以必须一并纳入候选，否则它自己会显示成 missing。
    candidates = set(all_tags) | {ANCHOR_TAG}

    # 「锚点」这个标记标签的锚点页要列出「全部锚点」，
    # 而锚点数只有等其它锚点都建好之后才知道，
    # 故把它排到最后处理。
    candidates.discard(ANCHOR_TAG)
    ordered = sorted(candidates) + [ANCHOR_TAG]

    created = 0
    for tag in ordered:
        # 已有同名 tiddler 的标签本来就正常，不需要锚点
        if tag in builder.tiddlers:
            continue
        # 系统标签（$:/…）是 TiddlyWiki 的机制标签，不能占用
        if tag.startswith("$:/"):
            continue

        body_parts: list[str] = [f"!{tag}\n"]

        # 统计该标签挂在哪些类别的 tiddler 上，用来决定列出哪些小节
        tagged = _tagged_by(builder, tag)
        n_entry = sum(1 for t in tagged if t.startswith("条目/"))
        n_couplet = sum(1 for t in tagged if t.startswith("联语/"))
        n_chapter = sum(1 for t in tagged if t.startswith("章节/"))
        n_entity = sum(1 for t in tagged if t.startswith("实体/"))

        def section(title: str, flt: str, n: int, field: str = "caption") -> None:
            """只在该小节确有内容时才写入（避免空标题）。"""
            if n <= 0:
                return
            body_parts.append(f"!! {title}（{n}）\n\n")
            body_parts.append(related_list(flt, field) + "\n")

        if tag in entity_pages:
            # 实体锚点：列出所有带这个实体标签的条目 / 联语。
            target = entity_pages[tag]
            kind = "实体"
            body_parts.append(
                f"本标签共出现在 {len(tagged)} 处 tiddler。"
                "下列条目与联语以该实体标签挂接。\n"
            )
            section("相关条目", f"[tag[{tag}]prefix[条目/]sort[序]]", n_entry)
            section("相关联语", f"[tag[{tag}]prefix[联语/]sort[来源]]", n_couplet)
            body_parts.append(f"规范页：[[{target}]]\n")

        elif tag in type_tags:
            # 类型锚点：列出该类型的全部实体。
            target = "实体索引"
            kind = "类型"
            body_parts.append(
                f"「{tag}」是实体类型分类。下表列出该类型下的全部实体。\n"
            )
            section("相关实体", f"[tag[{tag}]prefix[实体/]sort[规范名]]",
                    n_entity, field="规范名")
            body_parts.append(f"索引：[[{target}]]\n")

        elif tag == ANCHOR_TAG:
            # 锚点自身的标记标签。它也必须有个同名 tiddler，
            # 否则它自己会显示成 missing。
            # 它排在最后处理：此时其它锚点都已建好，
            # 「全部锚点」的计数才是准的（不含它自己）。
            target = "体例说明"
            kind = "标记"
            body_parts.append(
                "锚点 tiddler 的标记标签：凡本库自建的锚点页都挂这个标签。\n"
            )
            section("全部锚点", "[tag[锚点]sort[title]]", len(tagged),
                    field="title")
            body_parts.append(f"说明：[[{target}]]\n")

        else:
            # 结构 / 分类标签（书名、门类、联语类型……）：列出相关章节、
            # 条目、联语与实体。
            target = "楹联丛话全编"
            kind = "结构"
            body_parts.append(
                f"这是结构性标签：标出属于「{tag}」的章节、条目、联语与实体。\n"
            )
            section("相关章节", f"[tag[{tag}]prefix[章节/]sort[序]]", n_chapter)
            section("相关条目", f"[tag[{tag}]prefix[条目/]sort[序]]", n_entry)
            section("相关联语", f"[tag[{tag}]prefix[联语/]sort[来源]]", n_couplet)
            section("相关实体", f"[tag[{tag}]prefix[实体/]sort[规范名]]",
                    n_entity, field="规范名")
            body_parts.append(f"首页：[[{target}]]\n")

        body_parts.append(
            "\n本页是''标签锚点''：TiddlyWiki 用标签名查找同名 tiddler 来判断"
            "标签是否存在，缺少同名 tiddler 时，标签胶囊会被渲染成缺失样式，"
            "点进去也只会看到一句提示。本页列出与该标签相关的全部内容。\n"
        )
        body = "\n".join(body_parts)

        # 锚点**不给自己打同名标签**（自引用会污染 [tag[...]] 的筛选结果）。
        # 「锚点」这个标记标签自身也不例外，故它的锚点页不打任何标签。
        tags = [] if tag == ANCHOR_TAG else [ANCHOR_TAG]
        builder.add(tag, body, tags,
                    fields={"锚点": "true", "指向": target, "类别": kind},
                    anchor=True)
        created += 1
    return created


def _tagged_by(builder: TiddlyWikiBuilder, tag: str) -> list[str]:
    """列出挂了指定标签的 tiddler（用于统计）。"""
    return [t for t, rec in builder.tiddlers.items() if tag in rec["tags"]]


def build_index_tiddlers(
    builder: TiddlyWikiBuilder,
    structure: dict,
    headings: dict,
    couplets: list[dict],
    entity_tags: list[str],
    entity_count: Counter,
    paragraphs: dict,
    para_meta: dict,
) -> None:
    """生成首页、书目、实体索引、联语索引等入口 tiddler。"""
    books = [b for b in structure.get("books", [])]
    book_titles = [headings.get(b["id"], (0, b.get("title", "")))[1] or b.get("title", "")
                   for b in books]

    # ---- 首页 ----
    lines = ["!《楹联丛话全编》", ""]
    lines.append("梁章钜 等撰　清")
    lines.append("")
    lines.append("本库是《楹联丛话全编》的语义标注导出：每一条原文一个 tiddler，"
                 "其中的人名、地名、官职等实体以标签（tag）形式挂载，可直接筛选。")
    lines.append("")
    lines.append("!! 快速入口")
    lines.append("")
    lines.append("* [[书目]] — 九种联话著作的分区导航")
    lines.append("* [[实体索引]] — 按实体类型与出现次数浏览")
    lines.append("* [[联语索引]] — 全部联语，按类型与门类筛选")
    lines.append("* [[体例说明]] — 标注符号与筛选用法")
    lines.append("")
    lines.append("!! 统计")
    lines.append("")
    lines.append(f"| 条目 | {len(paragraphs)} |")
    lines.append("|---:|---|")
    lines.append(f"| 联语 | {len(couplets)} |")
    lines.append(f"| 实体标签 | {len(entity_tags)} |")
    lines.append(f"| 书 | {len(books)} |")
    lines.append("")
    lines.append("!! 按书浏览")
    lines.append("")
    for b, title in zip(books, book_titles):
            lines.append(f"* [[{title}|章节/{b['id']}]]")
    lines.append("")
    builder.add("楹联丛话全编", "\n".join(lines), ["首页", "楹联丛话全编"])

    # ---- 书目 ----
    lines = ["!书目", ""]
    for b, title in zip(books, book_titles):
        n = sum(1 for m in para_meta.values()
                if m[0] == title and m[5] in ("paragraph", "note"))
        lines.append(f"* [[{title}|章节/{b['id']}]] — {n} 条")
    lines.append("")
    builder.add("书目", "\n".join(lines), ["索引", "书目"])

    # ---- 实体索引 ----
    by_prefix: dict[str, list[str]] = defaultdict(list)
    for tag in entity_tags:
        by_prefix[tag.split("/", 1)[0]].append(tag)

    lines = ["!实体索引", ""]
    lines.append(f"共 {len(entity_tags)} 个实体标签，按类型分组。点击实体名可查看其出现位置。")
    lines.append("")
    for prefix in sorted(by_prefix, key=lambda p: -len(by_prefix[p])):
        tags = sorted(by_prefix[prefix], key=lambda t: (-entity_count[t], t))
        lines.append(f"!! {prefix}（{len(tags)}）")
        lines.append("")
        lines.append("| 实体 | 次数 |")
        lines.append("|---|---:|")
        for tag in tags:
            name = tag.split("/", 1)[1]
            # 表格单元格内不能直接用 [[显示|目标]]（会被当成纯文本），
            # 必须用 <$link> 构件。
            lines.append(f'| <$link to="实体/{prefix}/{name}">{name}</$link> | {entity_count[tag]} |')
        lines.append("")
    builder.add("实体索引", "\n".join(lines), ["索引", "实体"])

    # ---- 联语索引 ----
    lines = ["!联语索引", ""]
    lines.append(f"共 {len(couplets)} 副联语。")
    lines.append("")
    for ctype in sorted({c.get("type") or "" for c in couplets}):
        n = sum(1 for c in couplets if (c.get("type") or "") == ctype)
        lines.append(f"* {ctype} — {n} 副")
    lines.append("")
    lines.append("!! 全部")
    lines.append("")
    lines.append('<<list-links filter:"[prefix[联语/]sort[编号]]">>')
    lines.append("")
    builder.add("联语索引", "\n".join(lines), ["索引", "联语"])

    # ---- 体例说明 ----
    lines = ["!体例说明", ""]
    lines.append("本库由 `scripts/export_tiddlywiki.py` 从 "
                 "`data/楹联丛话全编.tagged.md` 及配套 JSON 导出，是**派生视图**，"
                 "权威语料仍以标注 Markdown 为准。")
    lines.append("")
    lines.append("!! 标签体系")
    lines.append("")
    lines.append("| 标签 | 含义 |")
    lines.append("|---|---|")
    lines.append("| `条目` | 原文条目 |")
    lines.append("| `联语` | 联语条目 |")
    lines.append("| `实体` | 实体条目 |")
    lines.append("| `章节` | 章节导航 |")
    lines.append("| `书名` | 所属著作 |")
    lines.append("| `书名/门类` | 所属门类 |")
    lines.append("| `人名/规范名` | 人名实体 |")
    lines.append("| `地点/规范名` | 地点实体 |")
    lines.append("| `官职/规范名` | 官职实体 |")
    lines.append("| `时间/规范名` | 时间实体 |")
    lines.append("| `氏族/规范名` | 氏族实体 |")
    lines.append("| `朝代/规范名` | 朝代实体 |")
    lines.append("| `名物/规范名` | 名物、制度实体 |")
    lines.append("| `典籍/规范名` | 典籍实体 |")
    lines.append("| `联语类型` | 庙联、挽联、春联… |")
    lines.append("")
    lines.append("!! 筛选示例")
    lines.append("")
    lines.append("```")
    lines.append("[tag[人名/林则徐]]                 所有提到林则徐的条目")
    lines.append("[tag[人名/林则徐]tag[楹联丛话]]     限定在《楹联丛话》")
    lines.append("[tag[地点/扬州]]                   所有提到扬州的条目")
    lines.append("[tag[挽联]]                         所有挽联")
    lines.append("[tag[楹联丛话/故事]]                《楹联丛话·故事》门类")
    lines.append("```")
    lines.append("")
    builder.add("体例说明", "\n".join(lines), ["索引", "说明"])


# 联语作者（字/号）→ 规范名，用于把 author 标签并入实体体系
def build_author_map(couplets: list[dict], alias_map: dict[tuple[str, str], str],
                     canonical_names: set[str]) -> dict[str, str]:
    """作者字段 → 规范名。作者多用字/号，需借别名表归一。"""
    mapping: dict[str, str] = {}
    for c in couplets:
        a = c.get("author")
        if not a:
            continue
        if a in canonical_names:
            mapping[a] = a
        elif ("@", a) in alias_map:
            mapping[a] = alias_map[("@", a)]
    return mapping


def entity_refs_by_paragraph(marked_text: str) -> dict[str, list[tuple[str, str]]]:
    """段落 id → [(类型符号, 规范名)]，按出现顺序去重。"""
    result: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for pid, text in parse_marked_markdown(DATA / "楹联丛话全编.tagged.md")["paragraphs"].items():
        seen: set[tuple[str, str]] = set()
        for m in ENTITY_RE.finditer(text):
            key = (m.group(1), m.group(3) or m.group(2))
            if key not in seen:
                seen.add(key)
                result[pid].append(key)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="导出《楹联丛话全编》TiddlyWiki")
    parser.add_argument("--out", default=str(ROOT / "tiddlywiki" / "楹联丛话全编"),
                        help="输出目录")
    args = parser.parse_args()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    marked_path = DATA / "楹联丛话全编.tagged.md"
    marked_text = marked_path.read_text(encoding="utf-8")
    parsed = parse_marked_markdown(marked_path)
    paragraphs = parsed["paragraphs"]
    headings = parsed["headings"]
    blocks = parsed["blocks"]

    entities_data = json.loads((DATA / "entities.json").read_text(encoding="utf-8"))
    couplets = json.loads((DATA / "couplets.json").read_text(encoding="utf-8"))["items"]
    structure = json.loads((DATA / "structure.json").read_text(encoding="utf-8"))

    alias_map = build_alias_map(marked_text)
    canonical_names = {e["canonical"] for e in entities_data["entities"]}
    author_map = build_author_map(couplets, alias_map, canonical_names)

    # 段落 → 实体引用
    para_entities = entity_refs_by_paragraph(marked_text)

    # 联语按 ref 分组
    couplets_by_ref: dict[str, list[dict]] = defaultdict(list)
    for c in couplets:
        couplets_by_ref[c["ref"]].append(c)

    builder = TiddlyWikiBuilder(out_dir)

    # ------------------------------------------------------------------
    # 1. 联语 tiddler
    # ------------------------------------------------------------------
    for c in couplets:
        tags = ["联语", c.get("type") or "联语"]
        book = c.get("book") or ""
        if book:
            tags.append(book)
        section = c.get("section") or ""
        if section:
            tags.append(f"{book}/{section}" if book else section)
        volume = c.get("volume") or ""
        if volume:
            tags.append(f"{book}/{volume}" if book else volume)

        author = c.get("author")
        if author:
            canon = author_map.get(author, author)
            tags.append(f"人名/{canon}")
        place = c.get("place")
        if place:
            tags.append(f"地点/{place}")
        src = c.get("lower_source")
        if src:
            tags.append(f"出处/{src}")

        lines = [f"!{c['upper']}", "", f"!{c['lower']}", ""]
        meta: list[str] = []
        if c.get("type"):
            meta.append(f"类型：{c['type']}")
        if author:
            canon = author_map.get(author, author)
            meta.append(f"作者：[[{author}|实体/人名/{canon}]]")
        elif c.get("author_near"):
            meta.append(f"作者（待核）：{c['author_near']}")
        if src:
            meta.append(f"下联出处：{src}")
        if place:
            meta.append(f"地点：[[{place}|实体/地点/{place}]]")
        if c.get("upper_len") is not None:
            meta.append(f"字数：上 {c['upper_len']} / 下 {c['lower_len']}")
        if c.get("editorial_markers"):
            meta.append(f"编者标记：{'、'.join(c['editorial_markers'])}")
        if meta:
            lines.append("  \n".join(meta))
            lines.append("")
        if c.get("context"):
            ctx = c["context"].strip()
            if len(ctx) > 120:
                ctx = ctx[:120] + "……"
            lines.append(f"> {ctx}")
            lines.append("")
        where = " › ".join(x for x in [book, volume, section, c.get("entry")] if x)
        if where:
            lines.append(f"〔{where}〕")
            lines.append("")
        lines.append(f"〔{c.get('ref','')}〕")

        builder.add(f"联语/{c['id']}", "\n".join(lines), tags,
                    fields={"来源": c.get("ref", ""), "类型": c.get("type", "")})

    # ------------------------------------------------------------------
    # 2. 条目（段落）tiddler —— 语料的基本单位
    # ------------------------------------------------------------------
    # 结构：段落 id → (书, 卷/门类, 条目, 路径)
    para_meta = build_paragraph_meta(structure, headings)
    # 紫色编号目录树（供 TOC 宏用标签建立父子关系）
    toc_tree = build_toc_tree(structure, headings)
    entry_couplets: dict[str, list[dict]] = defaultdict(list)
    for c in couplets:
        entry_couplets[c["ref"]].append(c)

    entity_usage: dict[str, list[str]] = defaultdict(list)   # 实体 tag → 出现的条目
    entity_type: dict[str, str] = {}                          # 实体 tag → 类型前缀
    entity_count: Counter[str] = Counter()

    for pid, text in paragraphs.items():
        meta = para_meta.get(pid)
        if meta is None:
            continue
        book, volume, section, entry, path, _kind = meta
        tags = ["条目", book]
        if volume:
            tags.append(f"{book}/{volume}")
        if section:
            tags.append(f"{book}/{section}")
        if entry:
            tags.append(f"{book}/{entry}")
        label = blocks.get(pid, "")

        # 目录树：打上父节点标签，使标准 TOC 宏能据此建立父子关系
        node = toc_tree.get(pid)
        if node:
            tags.append(node["父标题"])

        # 段落内实体 → tag
        for type_, canon in para_entities.get(pid, []):
            prefix = TYPE_PREFIX.get(type_)
            if not prefix:
                continue
            tag = f"{prefix}/{canon}"
            tags.append(tag)
            entity_usage[tag].append(pid)
            entity_type.setdefault(tag, prefix)
            entity_count[tag] += 1

        pcs = entry_couplets.get(pid, [])
        if pcs:
            tags.append("联语")

        # 正文
        lines: list[str] = []
        heading_parts = [x for x in [book, volume, section, entry] if x]
        lines.append(f"!{' › '.join(heading_parts) if heading_parts else '条目'}")
        lines.append("")
        if label:
            lines.append(f"//{label}//")
            lines.append("")
        lines.append(render_marked(text, alias_map))
        lines.append("")
        if pcs:
            lines.append("!! 本段联语")
            lines.append("")
            for c in pcs:
                lines.append(f"* [[{c['upper']} ／ {c['lower']}|联语/{c['id']}]]")
            lines.append("")

        builder.add(f"条目/{pid}", "\n".join(lines), tags,
                    fields={"编号": pid, "书": book, "门类": section or volume or "",
                            "条目名": entry or "", "语义块": label,
                            "caption": toc_caption(toc_tree.get(pid),
                                                  strip_markers(text)),
                            "序": sort_key(pid)})

    # ------------------------------------------------------------------
    # 3. 实体 tiddler
    # ------------------------------------------------------------------
    # 联语上的实体（作者/地点/出处）也并入实体体系
    couplet_entity_refs: dict[str, list[str]] = defaultdict(list)
    for c in couplets:
        cid = c["id"]
        for tag in (f"人名/{author_map.get(c['author'], c['author'])}" if c.get("author") else None,
                    f"地点/{c['place']}" if c.get("place") else None,
                    f"出处/{c['lower_source']}" if c.get("lower_source") else None):
            if not tag:
                continue
            prefix = tag.split("/", 1)[0]
            entity_type.setdefault(tag, prefix)
            entity_count[tag] += 1
            couplet_entity_refs[tag].append(cid)

    # 实体标签全集：正文引用 + 联语元数据
    entity_tags = sorted(set(entity_usage.keys()) | set(entity_type.keys()))
    for tag in entity_tags:
        prefix = entity_type[tag]
        name = tag.split("/", 1)[1]
        refs = entity_usage.get(tag, [])
        aliases = sorted(a for (t, a), c in alias_map.items() if c == name)
        title = f"实体/{prefix}/{name}"
        lines = []
        lines.append(f"出现次数：{entity_count[tag]}")
        lines.append("")
        if aliases:
            lines.append(f"又称：{'、'.join(aliases)}")
            lines.append("")
        lines.append(f"类型：{TYPE_DESC.get(next((t for t, p in TYPE_PREFIX.items() if p == prefix), ''), prefix)}")
        lines.append("")
        lines.append("!! 出现于")
        lines.append("")
        lines.append(f'<<list-links filter:"[tag[{tag}]sort[序]]">>')
        lines.append("")
        crefs = couplet_entity_refs.get(tag, [])
        if crefs:
            lines.append("!! 相关联语")
            lines.append("")
            for cid in crefs[:40]:
                lines.append(f"* [[联语/{cid}]]")
            if len(crefs) > 40:
                lines.append(f"* ……另有 {len(crefs) - 40} 副")
            lines.append("")
        builder.add(title, "\n".join(lines),
                    ["实体", prefix],
                    fields={"类型": prefix, "规范名": name, "出现次数": str(entity_count[tag])})

    # ------------------------------------------------------------------
    # 4. 章节 / 书目 导航
    # ------------------------------------------------------------------
    for nid, (level, title) in sorted(headings.items(), key=lambda kv: [int(x) for x in kv[0].split(".")]):
        meta = para_meta.get(nid)
        if meta is None:
            continue
        book, volume, section, entry, path, _kind = meta
        if level == 2:      # 书
            tag = book
        elif level == 3:    # 卷 / 门类
            tag = f"{book}/{volume or section}"
        else:               # 条目
            tag = f"{book}/{entry}"
        lines = [f"!{title or tag}", ""]
        if level == 2:
            n = sum(1 for p, m in para_meta.items()
                    if m[0] == book and m[5] in ("paragraph", "note"))
            lines.append(f"本书收录《{book}》，共 {n} 条。")
        else:
            lines.append(f"所属：{book} › {volume or section}")
        lines.append("")
        lines.append("!! 条目")
        lines.append("")
        lines.append(f'<<list-links filter:"[tag[{tag}]sort[序]]">>')
        lines.append("")
        chapter_tags = ["章节", book, tag]
        # 目录树：打上父节点标签，使标准 TOC 宏能据此建立父子关系
        node = toc_tree.get(nid)
        if node:
            chapter_tags.append(node["父标题"])
        builder.add(f"章节/{nid}", "\n".join(lines), chapter_tags,
                    fields={"编号": nid, "书": book, "层级": str(level),
                            "caption": toc_caption(toc_tree.get(nid)),
                            "序": sort_key(nid)})

    # ------------------------------------------------------------------
    # 5. 目录（紫色编号）
    # ------------------------------------------------------------------
    build_toc_tiddler(builder, toc_tree)

    # ------------------------------------------------------------------
    # 6. 首页与索引
    # ------------------------------------------------------------------
    build_index_tiddlers(builder, structure, headings, couplets, entity_tags,
                          entity_count, paragraphs, para_meta)

    # ------------------------------------------------------------------
    # 7. 锚点 tiddler（标签名同名页）
    # ------------------------------------------------------------------
    # 必须放在最后：此时所有 tiddler 都已登记，才能准确判断
    # 「哪些标签还没有同名 tiddler」。
    used_tags: set[str] = set()
    for rec in builder.tiddlers.values():
        used_tags.update(rec["tags"])
    n_anchors = build_anchor_tiddlers(builder, used_tags, entity_tags, entity_type)
    print(f"  锚点 tiddler {n_anchors} 个（与标签同名，消除 Missing tiddler）")

    # ------------------------------------------------------------------
    # 8. 写出
    # ------------------------------------------------------------------
    stats = builder.write()
    write_system_tiddlers(out_dir)
    write_wiki_info(out_dir, stats)

    print(f"输出目录：{out_dir}")
    for kind, n in sorted(stats.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:8} {n:6} 个 tiddler")
    print(f"  合计     {sum(stats.values()):6} 个 tiddler")
    if builder.duplicate_titles:
        print(f"！重复标题 {len(builder.duplicate_titles)} 个：{builder.duplicate_titles[:5]}")
    else:
        print("  无重复标题 ✓")

    # 覆盖率自检
    exported_entries = sum(1 for t in builder.tiddlers if t.startswith("条目/"))
    print(f"  段落 {len(paragraphs)} → 条目 tiddler {exported_entries}"
          f" {'✓' if exported_entries == len(paragraphs) else '！不一致'}")
    exported_couplets = sum(1 for t in builder.tiddlers if t.startswith("联语/"))
    print(f"  联语 {len(couplets)} → 联语 tiddler {exported_couplets}"
          f" {'✓' if exported_couplets == len(couplets) else '！不一致'}")


# ---------------------------------------------------------------------------
# 站点配置（系统 tiddler）
# ---------------------------------------------------------------------------

SITE_TITLE = "《楹联丛话全编》语义标注库"
SITE_SUBTITLE = "条目为 tiddler，实体为 tag"
DEFAULT_TIDDLER = "楹联丛话全编"
LANGUAGE = "zh-Hans"

# 系统 tiddler：标题 → 正文
SYSTEM_TIDDLERS: dict[str, str] = {
    "$:/SiteTitle": SITE_TITLE,
    "$:/SiteSubtitle": SITE_SUBTITLE,
    "$:/DefaultTiddlers": DEFAULT_TIDDLER,
    "$:/language": f"$:/languages/{LANGUAGE}",
}


def write_system_tiddlers(out_dir: Path) -> None:
    """写出站点级系统 tiddler。

    这些 tiddler 决定单文件 wiki 的站点标题、默认首页与界面语言。
    文件名可以任意取，标题以 .tid 的 `title:` 字段为准。
    """
    sys_dir = out_dir / "tiddlers" / "system"
    sys_dir.mkdir(parents=True, exist_ok=True)
    for title, text in SYSTEM_TIDDLERS.items():
        # 文件名用标题去掉 `$:/` 后的部分，非法字符替换为 _
        stem = re.sub(r"[^\w\u4e00-\u9fff.-]", "_", title.replace("$:/", ""))
        write_tid(sys_dir / f"{stem}.tid", title, text, {})


def write_wiki_info(out_dir: Path, stats: dict) -> None:
    """写出 tiddlywiki.info（编辑器/服务端加载用）。"""
    info = {
        "description": "《楹联丛话全编》语义标注导出 —— 条目为 tiddler，实体为 tag",
        "plugins": [],
        "themes": [
            "tiddlywiki/vanilla",
            "tiddlywiki/snowwhite",
        ],
        "languages": [LANGUAGE],
        "build": {
            "index": [
                "--render", "$:/core/save/all", "index.html", "text/plain",
            ],
            "static": [
                "--render", "$:/core/templates/alltiddlers.template.html",
                "alltiddlers.html", "text/plain",
            ],
        },
    }
    (out_dir / "tiddlywiki.info").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
