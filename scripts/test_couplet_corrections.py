#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联语复核层（couplet_corrections）与字数平衡的单元测试。

运行：
    python3 -m unittest discover -s scripts -p 'test_*.py' -v
或：
    python3 scripts/test_couplet_corrections.py
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from couplet_corrections import (  # noqa: E402
    LACUNA,
    apply_corrections,
    count_lacunae,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def clause_lengths(text: str) -> list[int]:
    return [len(x) for x in re.split(r"[，；。？！]", text) if x.strip()]


def _mk(quote: str, upper: str, lower: str) -> dict:
    return {
        "quote": quote,
        "upper": upper,
        "lower": lower,
        "lower_source": "",
        "editorial_markers": [],
    }


class TestApplyCorrections(unittest.TestCase):
    def test_corrected_replaces_upper_lower_and_keeps_raw(self) -> None:
        corr = {
            "Q1": {
                "case": 7,
                "rule": "R3",
                "verdict": "corrected",
                "note": "n",
                "upper": "看儿曹整顿乾坤",
                "lower": "任老子婆娑风月",
            }
        }
        kept, excluded = apply_corrections(
            [_mk("Q1", "看儿曹整顿旋转乾坤", "任老子婆娑风月")], corr
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(excluded, [])
        item = kept[0]
        self.assertEqual(item["upper"], "看儿曹整顿乾坤")
        self.assertEqual(item["upper_raw"], "看儿曹整顿旋转乾坤")
        self.assertEqual(item["review"]["rule"], "R3")
        self.assertEqual(item["review"]["case"], 7)

    def test_not_couplet_is_excluded(self) -> None:
        corr = {"Q": {"case": 1, "rule": "R1", "verdict": "not-couplet", "note": "n"}}
        kept, excluded = apply_corrections([_mk("Q", "a" * 14, "b" * 16)], corr)
        self.assertEqual(kept, [])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["excluded_reason"]["rule"], "R1")

    def test_untouched_items_pass_through_unchanged(self) -> None:
        kept, excluded = apply_corrections([_mk("OTHER", "甲乙", "丙丁")], {})
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(excluded), 0)
        self.assertNotIn("review", kept[0])
        self.assertNotIn("upper_raw", kept[0])

    def test_missing_anchor_raises(self) -> None:
        corr = {"NOT_THERE": {"case": 1, "rule": "R1", "verdict": "not-couplet", "note": ""}}
        with self.assertRaises(KeyError):
            apply_corrections([_mk("Q", "ab", "cd")], corr)

    def test_upper_source_applied(self) -> None:
        corr = {
            "Q": {
                "case": 14,
                "rule": "R12",
                "verdict": "corrected",
                "note": "",
                "upper": "至人无心亦无法",
                "lower": "古者养民如养儿",
                "upper_source": "子由",
                "lower_source": "放翁",
            }
        }
        kept, _ = apply_corrections([_mk("Q", "x", "y")], corr)
        self.assertEqual(kept[0]["upper_source"], "子由")
        self.assertEqual(kept[0]["lower_source"], "放翁")


class TestLacuna(unittest.TestCase):
    def test_count(self) -> None:
        self.assertEqual(count_lacunae("赞□□从舅从姑"), 2)
        self.assertEqual(count_lacunae("无阙字"), 0)

    def test_placeholder_is_full_width_box(self) -> None:
        self.assertEqual(LACUNA, "□")


class TestLiveCorpus(unittest.TestCase):
    """对**真实产物**的断言：每次重新生成语料后都应成立。"""

    @classmethod
    def setUpClass(cls) -> None:
        path = DATA_DIR / "couplets.json"
        if not path.exists():
            raise unittest.SkipTest("couplets.json 不存在，请先运行 annotate_yinglian.py")
        cls.doc = json.loads(path.read_text(encoding="utf-8"))
        cls.items = cls.doc["items"]
        cpath = DATA_DIR / "couplet_corrections.json"
        cls.corr = (
            json.loads(cpath.read_text(encoding="utf-8"))["entries"] if cpath.exists() else {}
        )

    def test_no_unequal_length(self) -> None:
        bad = [c["id"] for c in self.items if c["upper_len"] != c["lower_len"]]
        self.assertEqual(bad, [], f"仍有上下联不等长：{bad}")

    def test_clause_sequences_match(self) -> None:
        bad = [
            c["id"] for c in self.items
            if clause_lengths(c["upper"]) != clause_lengths(c["lower"])
        ]
        self.assertEqual(bad, [], f"顿长序列不一致：{bad}")

    def test_unequal_length_ids_field_is_empty(self) -> None:
        self.assertEqual(self.doc["unequal_length_ids"], [])

    def test_totals_consistent(self) -> None:
        self.assertEqual(self.doc["total"], len(self.items))
        self.assertEqual(self.doc["equal_length"], len(self.items))

    def test_all_corrected_anchors_present_and_applied(self) -> None:
        by_text = {c["text"]: c for c in self.items}
        for quote, meta in self.corr.items():
            if meta.get("verdict") != "corrected":
                continue
            self.assertIn(quote, by_text, f"corrected 锚点缺失：{quote[:24]}…")
            c = by_text[quote]
            self.assertEqual(c["upper"], meta["upper"], f"{c['id']} 上联未按复核结论落位")
            self.assertEqual(c["lower"], meta["lower"], f"{c['id']} 下联未按复核结论落位")
            self.assertEqual(c.get("review", {}).get("rule"), meta["rule"])

    def test_all_not_couplets_removed(self) -> None:
        present = {c["text"] for c in self.items}
        for quote, meta in self.corr.items():
            if meta.get("verdict") == "not-couplet":
                self.assertNotIn(quote, present, f"非联语仍在语料中：{quote[:24]}…")

    def test_lacunae_only_from_reviewed_cases(self) -> None:
        """复核新增的 □ 必须落在声明为脱文的案例上。"""
        by_text = {c["text"]: c for c in self.items}
        for quote, meta in self.corr.items():
            text = meta.get("upper", "") + meta.get("lower", "")
            if LACUNA not in text:
                continue
            c = by_text.get(quote)
            self.assertIsNotNone(c)
            raw = c.get("upper_raw", "") + c.get("lower_raw", "")
            self.assertNotIn(LACUNA, raw, "原始切分不应含复核新增的 □")

    def test_every_reviewed_item_has_review_field(self) -> None:
        reviewed = [c for c in self.items if c.get("review")]
        self.assertEqual(len(reviewed), 16, "复核 corrected 案例应为 16 例")


class TestIdStability(unittest.TestCase):
    """剔除案例后，其余联语的 C#### 编号不得漂移。"""

    @classmethod
    def setUpClass(cls) -> None:
        path = DATA_DIR / "couplets.json"
        if not path.exists():
            raise unittest.SkipTest("couplets.json 不存在")
        cls.items = json.loads(path.read_text(encoding="utf-8"))["items"]

    def test_ids_are_unique(self) -> None:
        ids = [c["id"] for c in self.items]
        self.assertEqual(len(ids), len(set(ids)), "存在重复 ID")

    def test_ids_sorted_and_within_original_range(self) -> None:
        nums = [int(c["id"][1:]) for c in self.items]
        self.assertEqual(nums, sorted(nums), "ID 未按序号排列")
        self.assertLessEqual(max(nums), 3020, "ID 超出原始范围，说明编号漂移")
        self.assertEqual(len(nums), 3016)
        gaps = sorted(set(range(1, 3021)) - set(nums))
        self.assertEqual(len(gaps), 4, f"应恰有 4 个空号，实际 {gaps}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
