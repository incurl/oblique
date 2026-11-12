#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 `data/couplets.json` 导出为 CSV，便于表格软件与统计工具直接读取。

用法：
    python3 scripts/export_couplets_csv.py
    python3 scripts/export_couplets_csv.py --out data/couplets.csv

输出列（UTF-8 with BOM，Excel 直接可读）：
    id, ref, book, volume, section, entry, type,
    upper, lower, upper_len, lower_len, lower_source,
    author, author_near, place,
    review_case, review_rule, review_verdict, review_note,
    upper_raw, lower_raw
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COUPLETS_PATH = DATA_DIR / "couplets.json"
DEFAULT_OUT = DATA_DIR / "couplets.csv"

COLUMNS = [
    "id", "ref", "book", "volume", "section", "entry", "type",
    "upper", "lower", "upper_len", "lower_len", "lower_source",
    "author", "author_near", "place",
    "review_case", "review_rule", "review_verdict", "review_note",
    "upper_raw", "lower_raw",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    doc = json.loads(COUPLETS_PATH.read_text(encoding="utf-8"))
    items = doc.get("items", [])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig：带 BOM，Excel 双击不乱码
    with args.out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for c in items:
            review = c.get("review") or {}
            writer.writerow({
                **{k: c.get(k, "") for k in COLUMNS},
                "review_case": review.get("case", ""),
                "review_rule": review.get("rule", ""),
                "review_verdict": review.get("verdict", ""),
                "review_note": review.get("note", ""),
                "upper_raw": c.get("upper_raw", ""),
                "lower_raw": c.get("lower_raw", ""),
            })

    reviewed = sum(1 for c in items if c.get("review"))
    unequal = sum(1 for c in items if c["upper_len"] != c["lower_len"])
    print(f"written {args.out}  ({len(items):,} 行)")
    print(f"  等长 {len(items) - unequal:,}/{len(items):,}"
          f"（{100 * (len(items) - unequal) / max(len(items), 1):.2f}%）")
    print(f"  已复核 {reviewed} 例")


if __name__ == "__main__":
    main()
