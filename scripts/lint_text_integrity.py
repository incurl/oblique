#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验标注文件是否只加标记、未改原文。

用法：
    python3 scripts/lint_text_integrity.py
    python3 scripts/lint_text_integrity.py data/楹联丛话全编.tagged.md

校验项：
1. 去除 〖TYPE ...〗 / 〘TYPE...〙 / ⟦TYPE...⟧ / 〖聯〗 后，正文逐行等于源文件；
2. 标记括号配对；
3. 无嵌套标注；
4. 未引入半角引号（U+0022 / U+0027）；
5. 只使用约定的标记类型。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from yinglian_lib import BOOKS, DATA_DIR, HEADINGS, SOURCE_PATH

DEFAULT_TAGGED = DATA_DIR / "楹联丛话全编.tagged.md"

AUTHOR_INTRO_RANGE = range(80, 89)

SKIP_LINES = {
    1, 2, 3, 79, 1043,  # 卷首标题、作者简介标题、恶人谷分隔线
}
for _no, _title, _start, _end in BOOKS:
    SKIP_LINES.add(_start)

ALLOWED_TYPES = set("@=;%&◆^~•!?+{:[_#$")


def source_content_lines(lines: list[str]) -> list[tuple[int, str]]:
    """提取源文件中应出现在正文里的行（与标注文件中的 [id] 行一一对应）。"""
    out: list[tuple[int, str]] = []
    for no in AUTHOR_INTRO_RANGE:
        raw = lines[no - 1]
        if raw.strip():
            out.append((no, raw))

    for idx in range(88, len(lines)):
        no = idx + 1
        raw = lines[idx]
        if not raw.strip():
            continue
        if no in SKIP_LINES:
            continue
        if no in HEADINGS:
            continue
        if raw.startswith("----------------------"):
            continue
        if raw.startswith("\t"):
            out.append((no, raw))
            continue
        # 非缩进行：标题不进入正文，续行进入正文
        if raw.endswith(("。", "！", "？", "；", "：", "…")) or len(raw) >= 24:
            out.append((no, raw))
    return out


def strip_markup(text: str) -> str:
    """去掉所有标注符号，保留原文字符。"""
    # 联语/巧对前置标记
    text = text.replace("〖聯〗", "").replace("〖對〗", "")
    # 名词实体：〖TYPE 显示名|规范名〗 -> 显示名
    text = re.sub(r"〖([@=;%&◆^~•!?+{:[_#$])([^〗|]*)(?:\|[^〗]*)?〗", r"\2", text)
    # 修辞层：〘※成语〙 -> 成语
    text = re.sub(r"〘(.)([^〙]*)〙", r"\2", text)
    # 动词层：⟦◈伐⟧ -> 伐
    text = re.sub(r"⟦(.)([^⟧]*)⟧", r"\2", text)
    return text


def tagged_content_lines(text: str) -> list[tuple[int, str, str]]:
    """提取标注文件中带 [id] 的正文行，返回 (行号, 去标记文本, 原始标记文本)。"""
    out: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^\[([0-9.]+)\] (.*)$", line)
        if not m:
            continue
        raw = m.group(2)
        out.append((lineno, strip_markup(raw), raw))
    return out


def check_balance(text: str) -> list[str]:
    errors: list[str] = []
    pairs = [("〖", "〗"), ("〘", "〙"), ("⟦", "⟧")]
    for left, right in pairs:
        if text.count(left) != text.count(right):
            errors.append(f"括号不配对：{left}={text.count(left)} {right}={text.count(right)}")
    return errors


def check_nested(text: str) -> list[str]:
    errors: list[str] = []
    if re.search(r"〖[^〗]*〖", text):
        errors.append("发现名词实体嵌套：〖 ... 〖")
    if re.search(r"〖[^〗]*[〘⟦]", text):
        errors.append("发现实体标记内嵌修辞/动词标记")
    if re.search(r"〘[^〙]*[〖⟦]", text):
        errors.append("发现修辞标记内嵌实体/动词标记")
    if re.search(r"⟦[^⟧]*[〖〘]", text):
        errors.append("发现动词标记内嵌实体/修辞标记")
    return errors


def check_types(text: str) -> list[str]:
    errors: list[str] = []
    for m in re.finditer(r"〖(.)", text):
        ch = m.group(1)
        if ch in {"聯", "對"}:
            continue
        if ch not in ALLOWED_TYPES:
            errors.append(f"未知标记类型：〖{ch}")
    return errors


def check_quotes(source_text: str, tagged_text: str) -> list[str]:
    errors: list[str] = []
    for ch, name in [('"', "半角双引号"), ("'", "半角单引号")]:
        s, t = source_text.count(ch), tagged_text.count(ch)
        if t > s:
            errors.append(f"引入{name}：源文件 {s} 个，标注文件 {t} 个")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tagged", nargs="?", type=Path, default=DEFAULT_TAGGED)
    parser.add_argument("--source", type=Path, default=SOURCE_PATH)
    args = parser.parse_args()

    source_lines = args.source.read_text(encoding="utf-8").splitlines()
    tagged_text = args.tagged.read_text(encoding="utf-8")

    expected = source_content_lines(source_lines)
    actual = tagged_content_lines(tagged_text)

    print(f"source: {args.source} ({len(source_lines):,} lines)")
    print(f"tagged: {args.tagged} ({len(tagged_text):,} chars)")
    print(f"content paragraphs: source={len(expected):,} tagged={len(actual):,}")

    errors: list[str] = []

    # 1. 逐行比对
    limit = min(len(expected), len(actual))
    mismatches = 0
    for i in range(limit):
        (sno, s), (tno, t, _raw) = expected[i], actual[i]
        if s != t:
            mismatches += 1
            if mismatches <= 10:
                errors.append(
                    f"正文不一致：源第 {sno} 行 vs 标注第 {tno} 行\n"
                    f"  源：{s!r}\n"
                    f"  标：{t!r}"
                )
    if len(expected) != len(actual):
        errors.append(
            f"正文行数不一致：source={len(expected)} tagged={len(actual)}"
        )

    # 2. 括号、嵌套、类型、引号（只检查正文，不检查凡例/锚点）
    raw_content = "\n".join(raw for _, _, raw in actual)
    errors.extend(check_balance(raw_content))
    errors.extend(check_nested(raw_content))
    errors.extend(check_types(raw_content))
    errors.extend(check_quotes("\n".join(s for _, s in expected), raw_content))

    # 3. 统计
    types = Counter(m.group(1) for m in re.finditer(r"〖(.)", raw_content))
    print("tag counts:", " ".join(f"{k}:{v}" for k, v in sorted(types.items())))
    print(f"couplet markers: {raw_content.count('〖聯〗'):,}")

    if errors:
        print("\nFAILED")
        for e in errors[:20]:
            print("-", e)
        return 1

    print("\nOK: text integrity verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
