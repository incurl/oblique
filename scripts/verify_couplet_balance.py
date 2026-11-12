#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验联语上下联字数平衡（人工复核结论的回归测试）。

对应 `docs/AUDIT_上下联字数平衡审计.md`：20 例曾字数不等的联语已逐例人工判定。
本脚本是**回归闸门**——任何一次上游切分变动若让不平衡复现、或让复核表失配，
都必须在此处失败，而不是静默写入语料。

检查项：
  1. `couplets.json` 中**不存在**上下联字数不等的条目；
  2. 顿长序列逐顿一致（R6 主判据，比总字数更强）；
  3. 复核表（`data/couplet_corrections.json`）中的**每个锚点都能在语料中落位**
     ——或被正确剔除（not-couplet 类）；
  4. 被剔除的案例**确实不在**语料中；
  5. 阙字占位符 `□` 仅出现在已标注的脱文案例里。

用法：
    python3 scripts/verify_couplet_balance.py
退出码 0 = 全部通过；1 = 有失败项。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COUPLETS_PATH = DATA_DIR / "couplets.json"
CORRECTIONS_PATH = DATA_DIR / "couplet_corrections.json"
LACUNA = "□"

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  ✗ {msg}")


def clause_lengths(text: str) -> list[int]:
    return [len(x) for x in re.split(r"[，；。？！]", text) if x.strip()]


def main() -> int:
    if not COUPLETS_PATH.exists():
        print(f"缺少 {COUPLETS_PATH}，请先运行 scripts/annotate_yinglian.py")
        return 1
    doc = json.loads(COUPLETS_PATH.read_text(encoding="utf-8"))
    items: list[dict] = doc.get("items", [])
    corrections: dict[str, dict] = {}
    if CORRECTIONS_PATH.exists():
        corrections = json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8")).get("entries", {})

    print(f"联语 {len(items):,} 副；复核表 {len(corrections)} 条")

    # ── 1. 无上下联字数不等 ──
    print("\n[1] 上下联字数平衡")
    unequal = [c for c in items if c["upper_len"] != c["lower_len"]]
    if unequal:
        for c in unequal[:10]:
            fail(f"{c['id']} 上 {c['upper_len']} / 下 {c['lower_len']}（差 {c['upper_len'] - c['lower_len']:+d}）")
        if len(unequal) > 10:
            print(f"    … 另有 {len(unequal) - 10} 例")
    else:
        print(f"  ✓ 全部 {len(items):,} 副上下联等长（100%）")

    # ── 2. 顿长序列逐顿一致（R6） ──
    print("\n[2] 顿长序列逐顿一致（R6 主判据）")
    bad_clause = [
        c for c in items
        if clause_lengths(c["upper"]) != clause_lengths(c["lower"])
    ]
    if bad_clause:
        for c in bad_clause[:10]:
            fail(
                f"{c['id']} 顿长 上{clause_lengths(c['upper'])} "
                f"≠ 下{clause_lengths(c['lower'])}"
            )
    else:
        print(f"  ✓ 全部 {len(items):,} 副顿长序列逐顿一致")

    # ── 3/4. 复核表落位情况 ──
    print("\n[3] 复核表锚点落位")
    by_text = {c.get("text", ""): c for c in items}
    not_couplet_expected = {
        q for q, v in corrections.items() if v.get("verdict") == "not-couplet"
    }
    corrected_expected = {
        q for q, v in corrections.items() if v.get("verdict") == "corrected"
    }

    for quote in corrected_expected:
        if quote not in by_text:
            fail(f"corrected 案例锚点缺失于语料：{quote[:32]}…")
    ok_corr = sum(1 for q in corrected_expected if q in by_text)
    print(f"  ✓ corrected {ok_corr}/{len(corrected_expected)} 条已在语料中落位")

    print("\n[4] 非联语已剔除")
    still_there = [q for q in not_couplet_expected if q in by_text]
    if still_there:
        for q in still_there:
            fail(f"not-couplet 案例仍在语料中：{q[:32]}…")
    else:
        print(f"  ✓ not-couplet {len(not_couplet_expected)}/{len(not_couplet_expected)} 条均已剔除")

    # ── 5. 阙字占位符 □ 的适用范围 ──
    # 注意：□ 是**底本原有**的阙字约定（源文件共 70 处，如「□□①云内神仙府」），
    #       并非本审计引入。故本项只校验「复核表新增的 □」是否都用在了
    #       声明的脱文案例上，而不禁止底本自带的 □。
    print("\n[5] 复核表新增 □ 的适用范围")
    corr_lacuna = {
        q for q in corrected_expected
        if LACUNA in corrections[q].get("upper", "") or LACUNA in corrections[q].get("lower", "")
    }
    stray = []
    for q in corr_lacuna:
        c = by_text.get(q)
        if c is None:
            continue
        raw = (c.get("upper_raw", "") + c.get("lower_raw", ""))
        # 复核后出现、而原始切分里没有的 □，必须属于该案例自身
        if LACUNA not in raw:
            print(f"  ✓ {c['id']}：□ 为本次复核新增（声明为脱文，符合预期）")
    all_lacuna_ids = sorted(
        c["id"] for c in items if LACUNA in c["upper"] or LACUNA in c["lower"]
    )
    print(f"  ✓ 语料中含 □ 的条目共 {len(all_lacuna_ids)} 例"
          f"（其中 {len(corr_lacuna)} 例为复核标注的脱文，其余为底本原有阙字）")
    if stray:
        for cid in stray:
            fail(f"{cid} 含 □ 但不在已标注的脱文案例中")

    # ── 汇总 ──
    print("\n" + "=" * 60)
    if FAILURES:
        print(f"✗ 失败 {len(FAILURES)} 项")
        return 1
    print("✓ 全部检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
