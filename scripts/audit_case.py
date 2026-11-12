#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打印字数不等的联语案例，供人工复核。

用法：
    python3 scripts/audit_case.py              # 列出全部不平衡案例
    python3 scripts/audit_case.py C0018        # 打印某一例的完整现场
    python3 scripts/audit_case.py --next C0018 # 打印下一例（按候选表顺序）

「现场」包含：上联 / 下联 / 字数 / 联语全文 / 上下文 / 原始底本行 /
命中的判定规则，便于人工判断根因。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = ROOT / "楹联丛话全编.txt"
STRUCTURE = DATA / "structure.json"


def load_couplets() -> list[dict]:
    return json.loads((DATA / "couplets.json").read_text(encoding="utf-8"))["items"]


def load_lines() -> list[str]:
    return RAW.read_text(encoding="utf-8").splitlines()


def line_index_for(ref: str) -> int | None:
    """按 structure.json 的 ref（段落编号）找原始底本的行号。"""
    if not ref:
        return None
    try:
        struct = json.loads(STRUCTURE.read_text(encoding="utf-8"))
    except Exception:
        return None

    def walk(node):
        if isinstance(node, dict):
            if node.get("id") == ref:
                return node
            for v in node.values():
                got = walk(v)
                if got:
                    return got
        elif isinstance(node, list):
            for v in node:
                got = walk(v)
                if got:
                    return got
        return None

    node = walk(struct)
    return node.get("line_no") if node else None


def show(cid: str) -> None:
    items = load_couplets()
    match = [c for c in items if c["id"] == cid]
    if not match:
        raise SystemExit(f"找不到 {cid}")
    c = match[0]
    lines = load_lines()

    print("=" * 72)
    print(f"案例 {c['id']}    书={c['book']} 门类={c['section']} 段落={c['ref']}  类型={c['type']}")
    print("=" * 72)
    print()
    print("【当前标注】")
    print(f"  上联（{c['upper_len']} 字）：{c['upper']}")
    print(f"  下联（{c['lower_len']} 字）：{c['lower']}")
    print(f"  差：{c['upper_len'] - c['lower_len']:+d}")
    print()
    print("【联语全文 text】")
    print(f"  {c['text']}")
    print()
    print("【编者标记】", c["editorial_markers"] or "（无）")
    print("【出处冠名 lower_source】", repr(c["lower_source"]))
    print()
    print("【上下文 context】")
    print(c["context"].rstrip())
    print()

    ln = line_index_for(c.get("ref", ""))
    if ln and 1 <= ln <= len(lines):
        print(f"【原始底本第 {ln} 行】")
        print(lines[ln - 1].rstrip())
        print()

    # 命中了哪条规则
    print("【本次切分由哪条规则产生】")
    print("  1) QUOTE_RE：只取中文引号内文字 “…”")
    print("  2) _is_couplet_quote：含「；」、无内嵌句号、长度比 0.3–3.3 等宽松阈值")
    print("  3) _split_couplet：按**第一个**全角分号「；」切成上下联")
    print("  4) _strip_line_ending：各自去掉末尾的 。！？!?，、；;")
    print("  5) 字数 = len(字符串)，**标点计入**")
    print()
    # 逐字对照，帮助看出多出/少掉的是哪一段
    for label, s in (("上联", c["upper"]), ("下联", c["lower"])):
        marks = "".join(
            "。" if ch in "。！？" else "，" if ch == "，" else " " for ch in s
        )
        print(f"  {label}逐字：{s}")
        print(f"  {label}标点：{marks}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cid", nargs="?", help="案例 ID，如 C0018")
    ap.add_argument("--next", dest="nxt", help="打印下一例")
    args = ap.parse_args()

    items = load_couplets()
    bad = [c for c in items if c["upper_len"] != c["lower_len"]]
    if not args.cid and not args.nxt:
        print(f"共 {len(bad)} 例字数不等的联语：\n")
        print(f"{'ID':8} {'上联':>5} {'下联':>5} {'差':>5}")
        for c in bad:
            d = c["upper_len"] - c["lower_len"]
            print(f"{c['id']:8} {c['upper_len']:5} {c['lower_len']:5} {d:+5}")
        return

    if args.nxt:
        ids = [c["id"] for c in bad]
        try:
            i = ids.index(args.nxt)
        except ValueError:
            raise SystemExit(f"{args.nxt} 不在不平衡清单里")
        if i + 1 >= len(ids):
            print("已经是最后一例。")
            return
        show(ids[i + 1])
        return

    show(args.cid)


if __name__ == "__main__":
    main()
