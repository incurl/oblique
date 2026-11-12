#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联语人工复核结论的加载与应用（上下联字数平衡审计的落地层）。

审计过程见 `docs/AUDIT_上下联字数平衡审计.md`：逐例人工判定 20 例「上下联字数不等」
的联语，归纳为 R1–R16 十六条规则。本模块把**人工判定结论**固化为可复现的数据层，
供 `annotate_yinglian.py` 在生成 `couplets.json` 时应用。

设计要点
--------
1. **以原文引文（quote）为锚点**，不用位置序号 `C####`。
   `C####` 由 enumerate 生成，若上游切分变动则会漂移；
   原文引文是稳定键。加载时会校验锚点存在，缺失即报错。
2. **两类处置**：
   - `not-couplet`：引文其实不是联语（议论散文 / 问答 / 叙述），整条剔除；
   - `corrected`：给出人工判定后的权威上联 / 下联（及可选出处）。
3. **不臆造**：底本确实脱字而无法考定者（C2298、C2629）以 `□` 占位，
   字数为形制所需之数，一字一 `□`。
4. 本层**只作用于派生索引** `couplets.json`，不改 `tagged.md` 正文
   （`lint_text_integrity.py` 校验的「只加标记、不改原文」不受影响）。

用法
----
    from couplet_corrections import load_corrections, apply_corrections
    corr = load_corrections()
    kept, excluded = apply_corrections(raw_couplets, corr)
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CORRECTIONS_PATH = DATA_DIR / "couplet_corrections.json"

# 占位符：底本脱字、暂未考定
LACUNA = "□"


def load_corrections(path: Path = CORRECTIONS_PATH) -> dict[str, dict]:
    """读入复核结论，返回以原文引文为键的映射。"""
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    entries = doc.get("entries", {})
    return {k: v for k, v in entries.items() if k and not k.startswith("_")}


def apply_corrections(
    couplets: list[dict], corrections: dict[str, dict]
) -> tuple[list[dict], list[dict]]:
    """把复核结论应用到联语列表。

    参数
    ----
    couplets
        原始联语列表，每项须有 `quote`（原文引文）与 `upper` / `lower` 字段。
    corrections
        `load_corrections()` 的返回值。

    返回
    ----
    (保留的联语, 被剔除的联语)
        保留项会带上 `review` 字段（有复核结论时）；
        剔除项带上 `excluded_reason`。

    异常
    ----
    KeyError
        复核表中的锚点在联语列表里找不到 —— 说明上游切分已变动，
        必须重新核对审计结论，不能静默跳过。
    """
    by_quote: dict[str, dict] = {}
    for c in couplets:
        by_quote.setdefault(c.get("quote", ""), c)

    missing = [q for q in corrections if q not in by_quote]
    if missing:
        preview = "；".join(repr(m[:24]) for m in missing[:3])
        raise KeyError(
            f"复核表有 {len(missing)} 个锚点在当前联语列表中不存在"
            f"（前三个：{preview}）。上游切分可能已变动，请重新核对审计结论。"
        )

    kept: list[dict] = []
    excluded: list[dict] = []
    for c in couplets:
        quote = c.get("quote", "")
        rule_info = corrections.get(quote)
        if rule_info is None:
            kept.append(c)
            continue

        verdict = rule_info.get("verdict", "")
        review = {
            "case": rule_info.get("case"),
            "rule": rule_info.get("rule"),
            "verdict": verdict,
            "note": rule_info.get("note", ""),
        }

        if verdict == "not-couplet":
            item = dict(c)
            item["excluded_reason"] = review
            excluded.append(item)
            continue

        if verdict == "corrected":
            item = dict(c)
            item["upper_raw"] = c.get("upper", "")
            item["lower_raw"] = c.get("lower", "")
            item["upper"] = rule_info["upper"]
            item["lower"] = rule_info["lower"]
            if rule_info.get("lower_source") is not None:
                item["lower_source"] = rule_info["lower_source"]
            if rule_info.get("upper_source") is not None:
                item["upper_source"] = rule_info["upper_source"]
            item["review"] = review
            kept.append(item)
            continue

        # 未知 verdict：保守起见保留原样并告警
        item = dict(c)
        item["review"] = review
        kept.append(item)

    return kept, excluded


def count_lacunae(text: str) -> int:
    """统计一段文本中的阙字占位符个数（每字一 □）。"""
    return text.count(LACUNA)
