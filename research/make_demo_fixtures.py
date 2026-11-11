#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_demo_fixtures.py —— 生成 agreement.py 的**冒烟测试**用演示数据。

⚠️ 重要声明
-----------
本脚本生成的标注文件是**合成数据**，仅用于验证 agreement.py 的读写、
计算与报告产出链路是否正确，**不得**用作论文 Table 2–4 的实验结果。
论文中的 κ、F1、工时等数值必须来自真实人工标注实验；
在真实实验数据产出之前，正文对应位置一律保留占位符。

合成方式
--------
以《楹联丛话全编》的真实段落为底稿，用上游规则标注器
（``scripts/yinglian_lib.py``）生成"自动预标注"结果，再按可调的
错误率注入各类分歧（边界漂移、类型混淆、漏标、规范名不一致等），
以此模拟两位标注者与一份金标准。

用法
----
    python make_demo_fixtures.py --out examples/ --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from yinglian_lib import (  # type: ignore
        find_candidates, select_candidates, find_couplets, parse_document,
    )
except ImportError as exc:  # pragma: no cover
    raise SystemExit("需要上游标注库：%s" % exc)


def build_source_units(n_units: int) -> list[dict]:
    """从真实底本中取出前 n_units 个段落，并跑一遍规则标注器。"""
    lines = (ROOT / "楹联丛话全编.txt").read_text(encoding="utf-8").split("\n")
    doc = parse_document(lines)
    paras: list = []

    def walk(node):
        if node.kind == "paragraph":
            paras.append(node)
        for child in node.children:
            walk(child)

    walk(doc.author_intro)
    for book in doc.books:
        walk(book)

    units: list[dict] = []
    for node in paras:
        text = node.text.strip()
        if len(text) < 20:
            continue
        cands = select_candidates(find_candidates(text))
        entities = [
            {"char_start": c.start, "char_end": c.end, "type": c.type,
             "canonical_id": "%s:%s" % (c.type, (c.canonical or c.display)),
             "text": text[c.start:c.end]}
            for c in cands if c.layer == "noun"
        ]
        couplets = find_couplets(text)
        relations = []
        for cp in couplets:
            relations.append({
                "relation_type": "用典",
                "head": {"kind": "couplet", "couplet_id": "%s#%d" % (node.id, cp["start"])},
                "tail": {"kind": "entity", "char_start": 0, "char_end": 0,
                         "type": "{", "canonical_id": "{:待考", "text": ""},
            })
        units.append({
            "unit_id": node.id,
            "chars": len(text),
            "entities": entities,
            "relations": relations,
            "attributes": {},
        })
        if len(units) >= n_units:
            break
    return units


def perturb(unit: dict, rng: random.Random, p_miss: float, p_boundary: float,
            p_type: float, p_canon: float) -> dict:
    """在一份标注上注入受控分歧。"""
    out = json.loads(json.dumps(unit, ensure_ascii=False))
    ents = out.get("entities", [])
    kept = []
    for e in ents:
        r = rng.random()
        if r < p_miss:
            continue                      # 漏标
        if r < p_miss + p_boundary:
            e = dict(e)                   # 边界漂移
            if e["char_end"] - e["char_start"] > 1:
                e["char_end"] -= 1
            else:
                e["char_start"] += 1
        elif r < p_miss + p_boundary + p_type:
            e = dict(e)                   # 类型混淆
            e["type"] = "=" if e["type"] != "=" else "@"
            e["canonical_id"] = "%s:%s" % (e["type"], e.get("text", ""))
        elif r < p_miss + p_boundary + p_type + p_canon:
            e = dict(e)                   # 规范名不一致（同名异人/异实同指）
            e["canonical_id"] = "%s:%s(异)" % (e["type"], e.get("text", ""))
        kept.append(e)
    out["entities"] = kept
    out["attributes"] = {"联类": rng.choice(["集句", "联语", "庙联", "挽联", "春联"])}
    return out


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 agreement.py 的演示夹具")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "examples")
    ap.add_argument("--units", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    units = build_source_units(args.units)

    gold, ann_a, ann_b, base_list = [], [], [], []
    for u in units:
        g = json.loads(json.dumps(u, ensure_ascii=False))
        g["annotator"] = "GOLD"
        g["condition"] = "gold"
        g["elapsed_minutes"] = round(u["chars"] / 1000.0 * 12.0, 2)
        gold.append(g)

        a = perturb(u, rng, 0.03, 0.02, 0.01, 0.01)
        a["annotator"] = "A"
        a["condition"] = "treatment"
        a["elapsed_minutes"] = round(u["chars"] / 1000.0 * 8.0, 2)
        ann_a.append(a)

        b = perturb(u, rng, 0.05, 0.03, 0.02, 0.01)
        b["annotator"] = "B"
        b["condition"] = "treatment"
        b["elapsed_minutes"] = round(u["chars"] / 1000.0 * 9.0, 2)
        ann_b.append(b)

        base = perturb(u, rng, 0.12, 0.06, 0.05, 0.03)
        base["annotator"] = "BASELINE"
        base["condition"] = "baseline"
        base["elapsed_minutes"] = round(u["chars"] / 1000.0 * 11.0, 2)
        base_list.append(base)

    write_jsonl(args.out / "gold.jsonl", gold)
    write_jsonl(args.out / "ann_a.jsonl", ann_a)
    write_jsonl(args.out / "ann_b.jsonl", ann_b)
    write_jsonl(args.out / "baseline.jsonl", base_list)
    print("wrote 4 fixture files to %s (%d units)" % (args.out, len(units)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
