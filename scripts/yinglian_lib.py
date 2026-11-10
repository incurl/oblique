#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""楹联丛话全编语义标注公共库。

设计原则与 shiji-kb 一致：
1. 只添加标记，不修改原文字符；
2. 结构用 Purple Numbers（[1.2.3]）标识；
3. 名词实体用 〖TYPE 内容〗，域外扩展两类联语标记 〖聯〗/〖對〗；
4. 结构块用 Pandoc fenced div（::: 序 / ::: 联 / ::: 校注）。

本模块被 annotate_yinglian.py / lint_text_integrity.py / render_yinglian.py 共用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Iterator

try:  # 兼容 python -m scripts.xxx 与直接运行
    from .yinglian_dict import (
        ARTIFACTS,
        ASTRONOMY,
        BIOLOGY,
        CHENGYU,
        CLANS,
        CONCEPTS,
        COUPLET_TERMS,
        DATE_RE,
        DEITIES,
        DURATION_RE,
        DYNASTIES,
        ERA_GANZHI_RE,
        ERA_STANDALONE_RE,
        ETHNIC_GROUPS,
        FESTIVALS,
        GANZHI_RE,
        IDENTITIES,
        INSTITUTIONS,
        LAW_TERMS,
        MONTH_RE,
        RANK_RE,
        OFFICIALS,
        PERSONS,
        PLACES,
        QUANTITY_RE,
        QUOTE_SOURCE_ALIASES,
        QUOTE_SOURCE_NAMES,
        QUOTE_SOURCE_SUFFIX,
        QUOTE_SOURCE_WORKS,
        RITUAL_TERMS,
        SINGLE_DYNASTY_RE,
        STRICT_DYNASTY_RE,
        TIME_DEIXIS,
        TIME_RE,
    )
except ImportError:  # pragma: no cover
    from yinglian_dict import (
        ARTIFACTS,
        ASTRONOMY,
        BIOLOGY,
        CHENGYU,
        CLANS,
        CONCEPTS,
        COUPLET_TERMS,
        DATE_RE,
        DEITIES,
        DURATION_RE,
        DYNASTIES,
        ERA_GANZHI_RE,
        ERA_STANDALONE_RE,
        ETHNIC_GROUPS,
        FESTIVALS,
        GANZHI_RE,
        IDENTITIES,
        INSTITUTIONS,
        LAW_TERMS,
        MONTH_RE,
        RANK_RE,
        OFFICIALS,
        PERSONS,
        PLACES,
        QUANTITY_RE,
        QUOTE_SOURCE_ALIASES,
        QUOTE_SOURCE_NAMES,
        QUOTE_SOURCE_SUFFIX,
        QUOTE_SOURCE_WORKS,
        RITUAL_TERMS,
        SINGLE_DYNASTY_RE,
        STRICT_DYNASTY_RE,
        TIME_DEIXIS,
        TIME_RE,
    )

ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = ROOT / "楹联丛话全编.txt"
DATA_DIR = ROOT / "data"

# ---------------------------------------------------------------------------
# 一、原书结构
# ---------------------------------------------------------------------------

# (编号, 书名, 起始行, 结束行) —— 行号为 1-based，包含首尾。
BOOKS: list[tuple[int, str, int, int]] = [
    (1, "楹联丛话", 89, 739),
    (2, "楹联续话", 740, 1059),
    (3, "楹联三话", 1060, 1335),
    (4, "楹联四话", 1336, 1679),
    (5, "巧对录", 1680, 2137),
    (6, "巧对续录", 2138, 2454),
    (7, "楹联剩话", 2455, 2471),
    (8, "巧对补录", 2472, 2521),
    (9, "楹联散话", 2522, 2588),
]

# 行号 -> (层级, 标题)
# 层级说明：volume=卷；section=门类/小标题
HEADINGS: dict[int, tuple[str, str]] = {
    # 楹联丛话
    89: ("section", "序"),
    91: ("section", "自序"),
    93: ("section", "故事"),
    136: ("section", "应制"),
    161: ("section", "庙祀--上"),
    215: ("section", "庙祀--下"),
    263: ("section", "廨宇"),
    321: ("section", "胜迹--上"),
    404: ("section", "胜迹--下"),
    479: ("section", "格言"),
    528: ("section", "佳话"),
    570: ("section", "挽词"),
    625: ("section", "集句集字附"),
    658: ("section", "杂缀谐语附"),
    # 楹联续话
    740: ("section", "序"),
    742: ("section", "故事"),
    771: ("section", "应制"),
    778: ("section", "庙祀"),
    819: ("section", "廨宇"),
    849: ("section", "胜迹"),
    879: ("section", "格言"),
    908: ("section", "佳话"),
    942: ("section", "挽词"),
    981: ("section", "集句集字附"),
    1005: ("section", "杂缀谐语附"),
    # 楹联三话
    1060: ("section", "序"),
    1062: ("volume", "卷上"),
    1219: ("volume", "卷下"),
    # 楹联四话
    1336: ("section", "厅宇--酬赠"),
    1415: ("section", "名胜--庙祀"),
    1491: ("section", "佳话"),
    1533: ("section", "挽联"),
    1598: ("section", "杂缀"),
    1665: ("section", "诙谐"),
    # 巧对录
    1680: ("section", "序"),
    1683: ("volume", "巧对录卷之一"),
    1773: ("volume", "巧对录卷之二"),
    1815: ("volume", "巧对录卷之三"),
    1860: ("volume", "巧对录卷之四"),
    1894: ("volume", "巧对录卷之五"),
    1927: ("volume", "巧对录卷之六"),
    1976: ("volume", "巧对录卷之七"),
    2065: ("volume", "巧对录卷之八"),
    # 巧对续录
    2138: ("volume", "巧对续录卷上"),
    2282: ("volume", "巧对续录卷下"),
    # 楹联散话
    2522: ("section", "楹联散话"),
    2523: ("section", "《浪迹丛谈》中散见联话"),
    2553: ("section", "《浪迹续谈》中散见联话"),
    2579: ("section", "《浪迹三谈》中散见联话"),
}

# 这些书里的非缩进行是“条目小标题”，不是门类。
ENTRY_TITLE_BOOKS = {3, 9}

# 作者简介（源文件第 79-88 行，现代整理者所加）
AUTHOR_INTRO_HEADING_LINE = 79
AUTHOR_INTRO_START = 80
AUTHOR_INTRO_END = 88

# 源文件卷首目录（第 4-78 行）为电子本自动生成，正文不重复收录。
SOURCE_TOC_RANGE = (4, 78)


def read_source(path: Path = SOURCE_PATH) -> list[str]:
    """读取源文件，返回不含换行符的行列表（保留行首制表符）。"""
    return path.read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------------------
# 二、树结构
# ---------------------------------------------------------------------------


@dataclass
class Node:
    kind: str                      # book / volume / section / entry / paragraph / note
    text: str                      # 标题或首行原文
    line_no: int                   # 源文件行号（1-based）
    children: list["Node"] = field(default_factory=list)
    # 段落续行（源文件因排版断行产生的非缩进行）
    cont: list[tuple[int, str]] = field(default_factory=list)
    id: str = ""

    def walk(self) -> Iterator["Node"]:
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class Document:
    metadata: dict[str, str]
    author_intro: Node | None
    books: list[Node]

    def walk(self) -> Iterator[Node]:
        if self.author_intro:
            yield from self.author_intro.walk()
        for book in self.books:
            yield from book.walk()


def _is_content_line(line: str) -> bool:
    """非缩进行是否是正文续行（而非标题）。"""
    if not line:
        return False
    if line.startswith("\t"):
        return True
    if line.endswith(("。", "！", "？", "；", "：", "…")):
        return True
    # 长行通常是续行，短行通常是条目标题
    return len(line) >= 24


def _is_note_start(line: str) -> bool:
    return line.startswith("恶人谷注")


def _assign_child_ids(parent: Node) -> None:
    """递归分配子节点编号（同一父节点下所有子节点共用一个序号）。"""
    for i, child in enumerate(parent.children, 1):
        child.id = f"{parent.id}.{i}"
        _assign_child_ids(child)


def parse_document(lines: list[str] | None = None) -> Document:
    """将源文件解析为书 / 卷 / 门类 / 条目 / 段落树。"""
    if lines is None:
        lines = read_source()

    metadata = {
        "title": "楹联丛话全编",
        "author": "梁章钜 等",
        "dynasty": "清",
        "source": SOURCE_PATH.name,
        "source_lines": str(len(lines)),
        "schema": "yinglian-semantic-v1",
    }

    # 作者简介
    author_intro = Node(
        kind="section",
        text=lines[AUTHOR_INTRO_HEADING_LINE - 1].strip(),
        line_no=AUTHOR_INTRO_HEADING_LINE,
    )
    for no in range(AUTHOR_INTRO_START, AUTHOR_INTRO_END + 1):
        raw = lines[no - 1]
        if raw.strip():
            author_intro.children.append(
                Node(kind="paragraph", text=raw, line_no=no)
            )

    books: list[Node] = []
    current_book: Node | None = None
    current_volume: Node | None = None
    current_section: Node | None = None
    current_entry: Node | None = None
    current_para: Node | None = None
    note_node: Node | None = None
    book_ranges = [(no, title, start, end) for no, title, start, end in BOOKS]

    def ensure_book(no: int, title: str, line_no: int) -> Node:
        nonlocal current_book, current_volume, current_section, current_entry, current_para, note_node
        node = Node(kind="book", text=title, line_no=line_no)
        node.id = str(no)
        books.append(node)
        current_book = node
        current_volume = None
        current_section = None
        current_entry = None
        current_para = None
        note_node = None
        return node

    def append_child(node: Node) -> None:
        nonlocal current_volume, current_section, current_entry, current_para, note_node
        if node.kind == "volume":
            assert current_book is not None
            current_book.children.append(node)
            current_volume = node
            current_section = None
            current_entry = None
            current_para = None
        elif node.kind == "section":
            if current_volume is not None:
                current_volume.children.append(node)
            elif current_book is not None:
                current_book.children.append(node)
            current_section = node
            current_entry = None
            current_para = None
        elif node.kind == "entry":
            if current_section is not None:
                current_section.children.append(node)
            elif current_volume is not None:
                current_volume.children.append(node)
            elif current_book is not None:
                current_book.children.append(node)
            current_entry = node
            current_para = None
        elif node.kind == "paragraph":
            if current_entry is not None:
                current_entry.children.append(node)
            elif current_section is not None:
                current_section.children.append(node)
            elif current_volume is not None:
                current_volume.children.append(node)
            elif current_book is not None:
                current_book.children.append(node)
            current_para = node
        elif node.kind == "note":
            if current_section is not None:
                current_section.children.append(node)
            elif current_book is not None:
                current_book.children.append(node)
            current_para = None
            note_node = node

    # 遍历正文（第 89 行起）
    for idx in range(88, len(lines)):
        line_no = idx + 1
        raw = lines[idx]
        if not raw.strip():
            continue

        # 进入新的书
        for no, title, start, end in book_ranges:
            if line_no == start:
                ensure_book(no, title, line_no)
                break

        if current_book is None:
            continue

        # 特殊：恶人谷校注
        if _is_note_start(raw):
            note_node = Node(kind="note", text=raw, line_no=line_no)
            append_child(note_node)
            continue
        if raw.startswith("----------------------"):
            continue

        # 已知标题
        if line_no in HEADINGS:
            level, title = HEADINGS[line_no]
            if level == "section" and title == current_book.text:
                continue
            append_child(Node(kind=level, text=title, line_no=line_no))
            continue

        # 书名行本身已由 ensure_book 建节点，不重复建条目标题
        if line_no == current_book.line_no and raw.strip() == current_book.text:
            continue

        # 缩进行：新段落
        if raw.startswith("\t"):
            para = Node(kind="paragraph", text=raw, line_no=line_no)
            append_child(para)
            continue

        # 非缩进行：正文续行或条目标题
        if _is_content_line(raw):
            if current_para is not None:
                current_para.cont.append((line_no, raw))
            elif note_node is not None:
                note_node.cont.append((line_no, raw))
            else:
                para = Node(kind="paragraph", text=raw, line_no=line_no)
                append_child(para)
            continue

        # 短的非缩进行：条目小标题（三话/散话为主）
        append_child(Node(kind="entry", text=raw.strip(), line_no=line_no))

    doc = Document(metadata=metadata, author_intro=author_intro, books=books)
    author_intro.id = "0"
    _assign_child_ids(author_intro)
    for book in doc.books:
        _assign_child_ids(book)
    return doc


# ---------------------------------------------------------------------------
# 三、实体标注
# ---------------------------------------------------------------------------

# 标注类型 -> 优先级（数字越大越优先）
PRIORITY = {
    "{": 100,   # 典籍
    "=": 80,    # 地名
    "@": 70,    # 人名
    "&": 65,    # 氏族
    "?": 60,    # 神祇
    "~": 55,    # 族群
    ";": 50,    # 官职
    "^": 45,    # 名物/制度
    "!": 40,    # 天文
    "[": 38,    # 刑法
    ":": 35,    # 礼仪
    "◆": 30,    # 朝代/邦国
    "%": 25,    # 时间
    "#": 20,    # 身份
    "•": 15,    # 器物
    "_": 12,    # 思想概念
    "+": 10,    # 生物
    "$": 8,     # 数量
}

NOUN_TYPES = set(PRIORITY)
RHETORIC_TYPE = "※"


def _alternation(terms: set[str] | dict[str, object]) -> str:
    """把词表编译成按长度降序排列的正则分支。"""
    return "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))


# 预编译词典正则
PLACE_RE = re.compile(_alternation(PLACES))
PERSON_RE = re.compile(_alternation(PERSONS))
CLAN_RE = re.compile(_alternation(CLANS))
DEITY_RE = re.compile(_alternation(DEITIES))
ETHNIC_RE = re.compile(_alternation(ETHNIC_GROUPS))
OFFICIAL_RE = re.compile(_alternation(OFFICIALS))
COUPLET_TERM_RE = re.compile(_alternation(COUPLET_TERMS))
INSTITUTION_RE = re.compile(_alternation(INSTITUTIONS))
ASTRONOMY_RE = re.compile(_alternation(ASTRONOMY))
LAW_RE = re.compile(_alternation(LAW_TERMS))
RITUAL_RE = re.compile(_alternation(RITUAL_TERMS))
DYNASTY_RE = re.compile(_alternation(DYNASTIES))
IDENTITY_RE = re.compile(_alternation(IDENTITIES))
ARTIFACT_RE = re.compile(_alternation(ARTIFACTS))
CONCEPT_RE = re.compile(_alternation(CONCEPTS))
BIOLOGY_RE = re.compile(_alternation(BIOLOGY))
CHENGYU_RE = re.compile(_alternation(CHENGYU))
BOOK_RE = re.compile(r"《([^》\n]{1,40})》")


@dataclass
class Candidate:
    start: int
    end: int
    type: str                 # 名词类型或 ※
    display: str
    canonical: str | None = None
    priority: int = 0
    layer: str = "noun"       # noun / rhetoric

    def tag(self) -> str:
        if self.layer == "rhetoric":
            return f"〘{self.type}{self.display}〙"
        if self.canonical and self.canonical != self.display:
            return f"〖{self.type}{self.display}|{self.canonical}〗"
        return f"〖{self.type}{self.display}〗"


def _add_dict_candidates(
    text: str,
    pattern: re.Pattern[str],
    type_: str,
    out: list[Candidate],
    canonical_map: dict[str, str | None] | None = None,
) -> None:
    for m in pattern.finditer(text):
        display = m.group(0)
        canonical = canonical_map.get(display) if canonical_map else None
        out.append(
            Candidate(
                start=m.start(),
                end=m.end(),
                type=type_,
                display=display,
                canonical=canonical,
                priority=PRIORITY[type_],
            )
        )


def find_candidates(text: str) -> list[Candidate]:
    """在原文字符串中找出所有候选实体（尚未解决重叠）。"""
    out: list[Candidate] = []

    # 典籍：只标书名号内部，书名号保留在标记外
    for m in BOOK_RE.finditer(text):
        inner = m.group(1)
        start, end = m.start(1), m.end(1)
        out.append(
            Candidate(start, end, "{", inner, inner, PRIORITY["{"])
        )

    _add_dict_candidates(text, PLACE_RE, "=", out)
    _add_dict_candidates(text, PERSON_RE, "@", out, PERSONS)
    _add_dict_candidates(text, CLAN_RE, "&", out)
    _add_dict_candidates(text, DEITY_RE, "?", out)
    _add_dict_candidates(text, ETHNIC_RE, "~", out)
    _add_dict_candidates(text, OFFICIAL_RE, ";", out)
    _add_dict_candidates(text, COUPLET_TERM_RE, "^", out)
    _add_dict_candidates(text, INSTITUTION_RE, "^", out)
    _add_dict_candidates(text, ASTRONOMY_RE, "!", out)
    _add_dict_candidates(text, LAW_RE, "[", out)
    _add_dict_candidates(text, RITUAL_RE, ":", out)
    _add_dict_candidates(text, DYNASTY_RE, "◆", out)
    _add_dict_candidates(text, IDENTITY_RE, "#", out)
    _add_dict_candidates(text, ARTIFACT_RE, "•", out)
    _add_dict_candidates(text, CONCEPT_RE, "_", out)
    _add_dict_candidates(text, BIOLOGY_RE, "+", out)
    # 成语层优先级低于实体，避免覆盖人名、地名
    for m in CHENGYU_RE.finditer(text):
        out.append(
            Candidate(
                m.start(),
                m.end(),
                RHETORIC_TYPE,
                m.group(0),
                None,
                5,
                layer="rhetoric",
            )
        )

    # 单字朝代
    for m in SINGLE_DYNASTY_RE.finditer(text):
        # “聪明人”不是明朝人
        if m.group(0) == "明" and text[m.start() - 1:m.start()] == "聪":
            continue
        out.append(
            Candidate(m.start(), m.end(), "◆", m.group(0), None, PRIORITY["◆"])
        )
    for m in STRICT_DYNASTY_RE.finditer(text):
        out.append(
            Candidate(m.start(), m.end(), "◆", m.group(0), None, PRIORITY["◆"])
        )

    # 年号纪年
    for m in TIME_RE.finditer(text):
        out.append(
            Candidate(m.start(), m.end(), "%", m.group(0), None, PRIORITY["%"])
        )

    # 年号 + 干支：整体标注
    for m in ERA_GANZHI_RE.finditer(text):
        out.append(
            Candidate(
                m.start(), m.end(), "%", m.group(0), None, PRIORITY["%"]
            )
        )

    # 独立干支
    for m in GANZHI_RE.finditer(text):
        out.append(
            Candidate(m.start(), m.end(), "%", m.group(0), None, PRIORITY["%"])
        )

    # 节令
    for word in FESTIVALS:
        for m in re.finditer(re.escape(word), text):
            out.append(
                Candidate(m.start(), m.end(), "%", word, None, PRIORITY["%"])
            )

    # 月份 / 朔望
    for m in MONTH_RE.finditer(text):
        out.append(
            Candidate(m.start(), m.end(), "%", m.group(0), None, PRIORITY["%"])
        )

    # 初一到初十
    for m in DATE_RE.finditer(text):
        out.append(
            Candidate(m.start(), m.end(), "%", m.group(0), None, PRIORITY["%"])
        )

    # 单独年号，如“康熙间”“咸丰初年”
    for m in ERA_STANDALONE_RE.finditer(text):
        out.append(
            Candidate(m.start(), m.end(), "%", m.group(0), None, PRIORITY["%"])
        )

    # 时间指代
    for word in TIME_DEIXIS:
        for m in re.finditer(re.escape(word), text):
            out.append(
                Candidate(m.start(), m.end(), "%", word, None, PRIORITY["%"])
            )

    # 官阶
    for m in RANK_RE.finditer(text):
        out.append(
            Candidate(m.start(), m.end(), ";", m.group(0), None, PRIORITY[";"])
        )

    # 无年号的时长/日期
    for m in DURATION_RE.finditer(text):
        out.append(
            Candidate(m.start(), m.end(), "%", m.group(0), None, PRIORITY["%"])
        )

    # 数量
    for m in QUANTITY_RE.finditer(text):
        out.append(
            Candidate(m.start(), m.end(), "$", m.group(0), None, PRIORITY["$"])
        )

    return out


def select_candidates(cands: list[Candidate]) -> list[Candidate]:
    """按起点、长度、优先级贪心选择互不重叠的候选。"""
    cands.sort(key=lambda c: (c.start, -(c.end - c.start), -c.priority))
    selected: list[Candidate] = []
    cursor = 0
    for c in cands:
        if c.start < cursor:
            continue
        selected.append(c)
        cursor = c.end
    return selected


# ---------------------------------------------------------------------------
# 四、联语识别
# ---------------------------------------------------------------------------

QUOTE_RE = re.compile(r"“([^“”]{1,300})”")

# 这些开头多为叙述、按语，不是联语
COUPLET_BAD_PREFIX = (
    "按", "此", "余", "今", "又", "故", "盖", "然", "而", "且", "若", "如",
    "所谓", "云", "曰", "或者", "或", "有", "无", "其", "之", "以", "为",
)


def _strip_line_ending(line: str) -> str:
    """去掉联句末尾的句读（下联常有句号）。"""
    return line.rstrip("。！？!?，、；; ")


def _split_couplet(quote: str) -> tuple[str, str]:
    """按第一个全角分号切分上下联，并剥离末尾句读。

    原文引号内常写作“上联；下联。”，句号属于引文而非联句本身，
    若不剥离，下联字数会凭空多一字，破坏“上下联等字数”的基本形制。
    """
    upper, lower = quote.split("；", 1)
    return _strip_line_ending(upper.strip()), _strip_line_ending(lower.strip())


# 集句对：下联前置“出处冠名”（如“王勃桃溪柳陌好经过”）
# 判定不依赖词典，靠形制自证：剥离首 k 字后若上下联等长，则该 k 字为冠名。
MAX_SOURCE_PREFIX = 4

# 出处冠名的三类形态：
#   1) 诗人名        —— 杜甫、王勃、刘长卿
#   2) “X句”缩写    —— 苏句、山谷句、东坡句
#   3) 文献题名      —— 高后碑、庾信马射赋、水经注
SOURCE_SUFFIX_CHARS = "句碑赋传册集记序颂诏书篇卷品话录志谱表经解引"

# 后置出处：下联结尾的“人、X”（多以顿号连缀二人）
# 出处可能紧接正文，也可能与正文之间有一字（如「落笔超群英少陵、太白」）。
TRAILING_SOURCE_RE = re.compile(r"([\u4e00-\u9fff]{2,4}、[\u4e00-\u9fff]{2,4})$")


def _extract_name_pair(tail: str) -> str:
    """从尾部文本中取出“人、X”式的出处人名对。

    尾部可能含正文残留字（如「群英少陵、太白」），
    故从各个位置尝试匹配“X、Y”并返回最长的合法匹配。
    """
    best = ""
    for m in re.finditer(r"[\u4e00-\u9fff]{2,4}、[\u4e00-\u9fff]{2,4}", tail):
        cand = m.group(0)
        if len(cand) > len(best):
            best = cand
    return best


def _build_known_source_pairs() -> frozenset[str]:
    """构造已知出处人名对集合（X、Y），供后置出处识别。"""
    names = QUOTE_SOURCE_NAMES | QUOTE_SOURCE_ALIASES
    pairs: set[str] = set()
    for a in names:
        for b in names:
            if a != b:
                pairs.add(f"{a}、{b}")
    return frozenset(pairs)


_KNOWN_SOURCE_PAIRS = _build_known_source_pairs()


def _looks_like_source(prefix: str) -> bool:
    """判断一个前缀是否像“出处冠名”。"""
    if prefix in QUOTE_SOURCE_NAMES or prefix in QUOTE_SOURCE_WORKS:
        return True
    # “X句”缩写
    if prefix.endswith(QUOTE_SOURCE_SUFFIX) and len(prefix) <= 5:
        return True
    # 文献题名（以碑/赋/传/册…结尾）
    if len(prefix) >= 3 and prefix[-1] in SOURCE_SUFFIX_CHARS:
        return True
    # 二人以上连缀：“夏承、韩敕”“少陵、太白”
    if "、" in prefix and 2 <= len(prefix) <= 10:
        parts = [p for p in prefix.split("、") if p]
        if parts and all(
            p in QUOTE_SOURCE_NAMES
            or p in QUOTE_SOURCE_ALIASES
            or p in QUOTE_SOURCE_WORKS
            or (p.endswith(QUOTE_SOURCE_SUFFIX) and len(p) <= 5)
            for p in parts
        ):
            return True
    return False


def _detect_source_prefix(
    upper: str, lower: str
) -> tuple[str, str]:
    """识别并剥离下联的出处冠名（前置或后置）。

    集句联的常见形制是把出处与联句并置，有两种位置：

    **前置**（出处在下联开头）：

        上：紫阁丹楼纷照耀
        下：王勃桃溪柳陌好经过        → 出处「王勃」

    **后置**（出处在下联结尾，多为二人连缀）：

        上：举杯邀明月
        下：太白、右丞                  → 出处「太白、右丞」

        上：读书破万卷
        下：落笔超群英少陵、太白        → 出处「少陵、太白」

    判定方法：尝试剥离下联首 k 字或末 k 字，若剥离后与上联等长，
    且该段形似出处（人名／“X句”／文献题名／“人、X”连缀），
    则认定为出处冠名。

    返回 (冠名, 剥离后的下联)。
    """
    # 前置
    for k in range(min(6, len(lower) - 2), 1, -1):
        if len(lower) - k != len(upper):
            continue
        prefix = lower[:k]
        rest = lower[k:]
        if _looks_like_source(prefix):
            return prefix, rest

    # 后置：形如「…正文A、B」
    # 出处名可能与正文连写（如「落笔超群英少陵、太白」），
    # 故遍历切分位置，取“尾部含已知人名对、且剩余部分与上联等长”者。
    for cut in range(len(lower) - 2, 2, -1):
        tail = lower[cut:]
        rest = lower[:cut]
        if "、" not in tail or len(tail) > 12:
            continue
        if len(rest) != len(upper):
            continue
        # 尾部形如 “…X、Y”，允许 X 前有若干正文残留字
        pair = _extract_name_pair(tail)
        if pair and pair in _KNOWN_SOURCE_PAIRS:
            return pair, rest

    return "", lower


def _is_couplet_quote(quote: str) -> bool:
    """判断引号内文字是否像一副联语。"""
    if "；" not in quote:
        return False
    if len(quote) < 5 or len(quote) > 260:
        return False
    if "。" in quote.rstrip("。"):
        return False
    if quote.count("；") > 4:
        return False
    if quote.count("，") > 12:
        return False
    upper, lower = _split_couplet(quote)
    if len(upper) < 2 or len(lower) < 2:
        return False
    ratio = len(upper) / max(1, len(lower))
    if ratio < 0.3 or ratio > 3.3:
        return False
    if quote.startswith(COUPLET_BAD_PREFIX):
        return False
    return True


def find_couplets(text: str) -> list[dict[str, object]]:
    """找出文本中带引号的联语，返回上下联与位置。"""
    result: list[dict[str, object]] = []
    for m in QUOTE_RE.finditer(text):
        quote = m.group(1)
        if not _is_couplet_quote(quote):
            continue
        upper, lower = _split_couplet(quote)
        source, lower_body = _detect_source_prefix(upper, lower)
        result.append(
            {
                "start": m.start(),
                "end": m.end(),
                "quote": quote,
                "upper": upper,
                "lower": lower_body,
                "lower_source": source,
            }
        )
    return result


def is_block_couplet(text: str) -> bool:
    """判断整段是否为无引号的巧对/联语排比。"""
    if "“" in text or "；" not in text:
        return False
    semis = text.count("；")
    if semis < 2:
        return False
    if text.count("。") > semis + 2:
        return False
    segments = [s for s in re.split(r"[；。]", text) if s.strip()]
    if len(segments) < 4:
        return False
    avg = sum(len(s) for s in segments) / len(segments)
    return avg <= 26


AUTHOR_VERB_RE = re.compile(
    r"^[^。；\n]{0,8}(?:撰|题|手题|自题|敬题|谨撰|书联|书楹|书此|"
    r"作联|作楹|集句|集字)(?=[联楹此一云曰：，、于]|$)"
)

PLACE_SUFFIXES = (
    "书院", "宫", "祠", "庙", "楼", "亭", "山", "崖", "墓", "碑",
    "县", "府", "州", "寺", "观", "殿", "堂", "宅", "林",
)


def _context_person(text: str, start: int) -> str | None:
    """从联语前的上下文提取“撰/题/书联/作联”前的人名。

    这是一个高精度、低召回的作者线索：宁可返回 None，也不把祠庙主神、
    受赠者、书院名误当成作者。JSON 中同时保留 context，便于人工复核。
    """
    context = text[max(0, start - 120):start]
    matches = list(PERSON_RE.finditer(context))
    filtered: list[re.Match[str]] = []
    for m in matches:
        # 去掉被更长人名包含的短名（如“紫阳”在“朱紫阳”中）
        if any(
            o.start() <= m.start() and m.end() <= o.end()
            and (o.end() - o.start()) > (m.end() - m.start())
            for o in matches
        ):
            continue
        # “紫阳书院”之类的地名后缀，不当作人名
        if context[m.end():m.end() + 2] in PLACE_SUFFIXES:
            continue
        filtered.append(m)

    found = None
    for m in filtered:
        tail = context[m.end():m.end() + 12]
        if AUTHOR_VERB_RE.match(tail):
            found = m.group(0)
    return found


def _context_person_near(text: str, start: int) -> str | None:
    """联语前最近的人名（仅作线索，不保证是作者）。"""
    context = text[max(0, start - 90):start]
    matches = list(PERSON_RE.finditer(context))
    filtered: list[re.Match[str]] = []
    for m in matches:
        if any(
            o.start() <= m.start() and m.end() <= o.end()
            and (o.end() - o.start()) > (m.end() - m.start())
            for o in matches
        ):
            continue
        if context[m.end():m.end() + 2] in PLACE_SUFFIXES:
            continue
        filtered.append(m)
    return filtered[-1].group(0) if filtered else None


def _context_place(text: str, start: int) -> str | None:
    """从联语前的上下文提取最后一个地名。"""
    context = text[max(0, start - 90):start]
    matches = list(PLACE_RE.finditer(context))
    if not matches:
        return None
    return matches[-1].group(0)


def _couplet_type(text: str, start: int, section: str = "") -> str:
    """根据上下文判断联语类型。"""
    context = (section or "") + text[max(0, start - 60):start]
    if "挽" in context:
        return "挽联"
    if "寿" in context or "祝" in context:
        return "寿联"
    if "贺" in context or "喜" in context:
        return "贺联"
    if "春" in context or "桃符" in context:
        return "春联"
    if "集" in context and ("句" in context or "字" in context):
        return "集句"
    if "庙" in context or "祠" in context or "寺" in context or "观" in context:
        return "庙联"
    if "会馆" in context:
        return "会馆联"
    if "门" in context:
        return "门联"
    if "堂" in context:
        return "堂联"
    if "巧对" in context or "对语" in context:
        return "巧对"
    return "联语"


# ---------------------------------------------------------------------------
# 五、标注渲染
# ---------------------------------------------------------------------------


@dataclass
class AnnotationResult:
    text: str
    entities: list[dict[str, object]]
    couplets: list[dict[str, object]]
    block_couplet: bool


def annotate_text(
    text: str,
    paragraph_id: str = "",
    section: str = "",
) -> AnnotationResult:
    """对一段原文加实体标记、联语标记，并返回实体/联语索引。"""
    cands = find_candidates(text)
    selected = select_candidates(cands)
    couplets = find_couplets(text)

    entities: list[dict[str, object]] = []
    for c in selected:
        if c.layer != "noun":
            continue
        entities.append(
            {
                "type": c.type,
                "display": c.display,
                "canonical": c.canonical or c.display,
                "ref": paragraph_id,
            }
        )

    # 事件：标记与实体按位置排序；同一位置先插 〖聯〗
    events: list[tuple[int, int, str, object]] = []
    for c in selected:
        events.append((c.start, 1, "entity", c))
    for cp in couplets:
        events.append((int(cp["start"]), 0, "couplet", cp))
    events.sort(key=lambda e: (e[0], e[1]))

    out: list[str] = []
    cursor = 0
    for pos, order, kind, payload in events:
        if pos < cursor:
            # 标记落在实体内部时跳过，保证不嵌套
            continue
        out.append(text[cursor:pos])
        if kind == "couplet":
            out.append("〖聯〗")
            cursor = pos
        else:
            c = payload
            raw = text[c.start:c.end]
            if c.layer == "rhetoric":
                out.append(f"〘{c.type}{raw}〙")
            elif c.canonical and c.canonical != raw:
                out.append(f"〖{c.type}{raw}|{c.canonical}〗")
            else:
                out.append(f"〖{c.type}{raw}〗")
            cursor = c.end
    out.append(text[cursor:])
    annotated = "".join(out)

    # 联语元数据
    enriched: list[dict[str, object]] = []
    for cp in couplets:
        cp = dict(cp)
        cp["author"] = _context_person(text, int(cp["start"]))
        cp["author_near"] = _context_person_near(text, int(cp["start"]))
        cp["place"] = _context_place(text, int(cp["start"]))
        cp["type"] = _couplet_type(text, int(cp["start"]), section)
        cp["ref"] = paragraph_id
        cp["context"] = text[max(0, int(cp["start"]) - 100):int(cp["start"])]
        enriched.append(cp)

    return AnnotationResult(
        text=annotated,
        entities=entities,
        couplets=enriched,
        block_couplet=is_block_couplet(text),
    )
