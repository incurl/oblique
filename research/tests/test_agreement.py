#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agreement.py 的单元测试。

运行：
    python -m unittest discover -s tests -v
    # 或
    python tests/test_agreement.py

其中 Krippendorff α 与 Wilcoxon 精确 p 值的对照用例依赖 ``krippendorff``
与 ``scipy`` 两个包；若环境中没有，将自动跳过（skip），而不是让测试失败。
"""

from __future__ import annotations

import json
import math
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agreement as ag  # noqa: E402

SCHEMA_PATH = ROOT / "schema.yaml"
CODES = ["漏标", "类型混淆", "边界切分歧义", "同实异指", "异实同指",
         "典故误溯", "评点归属错误"]


class TestKappa(unittest.TestCase):
    """κ 的口径校验（手算可验的例子）。"""

    def test_perfect_agreement(self):
        cm = {("A", "A"): 10, ("B", "B"): 10}
        self.assertAlmostEqual(ag.cohen_kappa(cm, ["A", "B"]), 1.0, places=10)

    def test_single_category_is_undefined(self):
        """只有一个类别时 p_e = 1，κ 无定义 -> 返回 None 而非抛异常。"""
        self.assertIsNone(ag.cohen_kappa({("A", "A"): 10}, ["A"]))

    def test_chance_level(self):
        # p_o = 0.5, p_e = 0.5 -> κ = 0
        cm = {("A", "A"): 25, ("A", "B"): 25, ("B", "A"): 25, ("B", "B"): 25}
        self.assertAlmostEqual(ag.cohen_kappa(cm, ["A", "B"]), 0.0, places=10)

    def test_known_value(self):
        cm = {("A", "A"): 40, ("A", "B"): 5, ("B", "A"): 10, ("B", "B"): 45}
        po = 0.85
        pe = 0.5
        self.assertAlmostEqual(ag.cohen_kappa(cm, ["A", "B"]), 0.7, places=10)
        self.assertAlmostEqual(ag.observed_agreement(cm, ["A", "B"]), po, places=10)
        self.assertAlmostEqual(ag.expected_agreement(cm, ["A", "B"]), pe, places=10)

    def test_degenerate_pe_one(self):
        # 只有一个类别时 p_e = 1 -> 返回 None 而非抛异常
        self.assertIsNone(ag.cohen_kappa({("A", "A"): 5}, ["A"]))

    def test_weighted_kappa_perfect(self):
        cm = {("下下", "下下"): 10, ("下", "下"): 10, ("中", "中"): 10,
              ("上", "上"): 10, ("上上", "上上"): 10}
        labels = ["下下", "下", "中", "上", "上上"]
        self.assertAlmostEqual(
            ag.weighted_kappa(cm, labels, "quadratic"), 1.0, places=10)
        self.assertAlmostEqual(
            ag.weighted_kappa(cm, labels, "linear"), 1.0, places=10)

    def test_weighted_kappa_penalises_distance(self):
        base = {("下下", "下下"): 10, ("下", "下"): 10, ("中", "中"): 10,
                ("上", "上"): 10, ("上上", "上上"): 10}
        labels = ["下下", "下", "中", "上", "上上"]
        near = dict(base)
        near[("下", "下下")] = 1
        near[("下下", "下")] = 1
        far = dict(base)
        far[("上上", "下下")] = 1
        far[("下下", "上上")] = 1
        w_near = ag.weighted_kappa(near, labels, "quadratic")
        w_far = ag.weighted_kappa(far, labels, "quadratic")
        self.assertGreater(w_near, w_far)
        self.assertLess(w_far, 1.0)

    def test_fleiss_kappa_hand_computed(self):
        """Fleiss' κ 的手算对照（p_e 用**类别**边际平方和）。

        4 个单元，每单元 2 位标注者：
          单元 1 [2,0]  单元 2 [1,1]  单元 3 [1,1]  单元 4 [0,2]
          P_i = 1, 0, 0, 1  -> p_o = 0.5
          类别边际 A=4, B=4 -> p_e = 0.5
          κ = (0.5 - 0.5) / (1 - 0.5) = 0
        """
        counts = [[2, 0], [1, 1], [1, 1], [0, 2]]
        self.assertAlmostEqual(ag.fleiss_kappa(counts, ["A", "B"]), 0.0,
                               places=12)

    def test_fleiss_and_cohen_use_different_marginals(self):
        """Fleiss' κ 用类别边际，Cohen's κ 用两位标注者各自的边际，二者一般不同。

        本例（已手工核算）：
          Cohen's κ  = 0.25     （p_e = 0.5，两位标注者边际各为 (4,4)）
          Scott's Pi = 0.238095…（p_e = 0.53125，合并两位标注者的边际）
          Fleiss' κ  = 0.0      （p_e = 0.5，类别边际为 (4,4)）
        这正是论文 §5.2 强调"必须写明估计量名称"的原因。
        """
        labels = ["A", "B"]
        units = [[("A", "A"), ("A", "A")], [("A", "B"), ("B", "B")],
                 [("A", "B"), ("B", "A")], [("B", "B"), ("B", "B")]]
        cm: dict[tuple[str, str], int] = {}
        for u in units:
            for x, y in u:
                cm[(x, y)] = cm.get((x, y), 0) + 1
        counts = [[2, 0], [1, 1], [1, 1], [0, 2]]
        self.assertAlmostEqual(ag.cohen_kappa(cm, labels), 0.25, places=12)
        self.assertAlmostEqual(ag.scott_pi(cm, labels),
                               0.23809523809523808, places=12)
        self.assertAlmostEqual(ag.fleiss_kappa(counts, labels), 0.0, places=12)
        self.assertNotAlmostEqual(ag.scott_pi(cm, labels),
                                  ag.cohen_kappa(cm, labels), places=6)

    def test_fleiss_vs_cohen_differ_when_marginals_unbalanced(self):
        """边际不平衡时，三种 κ 的 p_e 口径不同，数值可显著不同。

        本例（已手工核算）：
          Cohen's κ  = 0.1578947368…   （p_e = 0.5，分别用两位标注者的边际）
          Scott's Pi = -0.0666666667…   （p_e = 0.53125，合并两位标注者的边际）
          Fleiss' κ  = 0.4666666667…    （p_e = 类别边际平方和）
        这正说明论文中必须写明估计量名称，否则跨研究不可比。
        """
        labels = ["A", "B"]
        units = [[("A", "B"), ("A", "B")], [("A", "B"), ("A", "B")],
                 [("A", "A"), ("B", "B")], [("B", "B"), ("B", "B")]]
        cm: dict[tuple[str, str], int] = {}
        for u in units:
            for x, y in u:
                cm[(x, y)] = cm.get((x, y), 0) + 1
        counts = []
        for u in units:
            row = [0, 0]
            for x, _ in u:
                row[labels.index(x)] += 1
            counts.append(row)
        self.assertAlmostEqual(ag.cohen_kappa(cm, labels),
                               0.15789473684210525, places=12)
        self.assertAlmostEqual(ag.scott_pi(cm, labels),
                               -0.06666666666666667, places=12)
        self.assertAlmostEqual(ag.fleiss_kappa(counts, labels),
                               0.4666666666666667, places=12)
        self.assertNotAlmostEqual(ag.fleiss_kappa(counts, labels),
                                  ag.cohen_kappa(cm, labels), places=6)


class TestAlpha(unittest.TestCase):
    """Krippendorff α：与 ``krippendorff`` 参考包逐例对照。"""

    def test_perfect(self):
        rel = [["A", "A"], ["B", "B"], ["A", "A"], ["C", "C"]]
        self.assertAlmostEqual(ag.krippendorff_alpha_nominal(rel), 1.0, places=10)

    def test_reference_package(self):
        try:
            import numpy as np
            import krippendorff
        except ImportError:
            self.skipTest("未安装 krippendorff 参考包")
        rng = random.Random(11)
        labels = ["A", "B", "C"]
        for _ in range(50):
            n_units = rng.randint(4, 10)
            n_ann = rng.randint(2, 4)
            rel = []
            for _u in range(n_units):
                rel.append([None if rng.random() < 0.12 else rng.choice(labels)
                            for _a in range(n_ann)])
            # 参考包要求「标注者 × 单元」矩阵
            m = [[(np.nan if rel[u][a] is None else labels.index(rel[u][a]))
                  for u in range(n_units)] for a in range(n_ann)]
            try:
                ref = krippendorff.alpha(reliability_data=np.array(m),
                                         level_of_measurement="nominal")
            except Exception:
                continue
            mine = ag.krippendorff_alpha_nominal(rel)
            if math.isnan(ref):
                self.assertIsNone(mine)
            else:
                self.assertAlmostEqual(mine, ref, places=9)

    def test_ordinal_reference(self):
        try:
            import numpy as np
            import krippendorff
        except ImportError:
            self.skipTest("未安装 krippendorff 参考包")
        rng = random.Random(13)
        labels = ["A", "B", "C", "D"]
        for _ in range(30):
            n_units = rng.randint(4, 10)
            n_ann = rng.randint(2, 3)
            rel = [[None if rng.random() < 0.1 else rng.choice(labels)
                    for _a in range(n_ann)] for _u in range(n_units)]
            m = [[(np.nan if rel[u][a] is None else labels.index(rel[u][a]))
                  for u in range(n_units)] for a in range(n_ann)]
            try:
                ref = krippendorff.alpha(
                    reliability_data=np.array(m),
                    level_of_measurement="ordinal",
                    value_domain=np.arange(len(labels)))
            except Exception:
                continue
            mine = ag.krippendorff_alpha_ordinal(rel, labels)
            if math.isnan(ref):
                self.assertIsNone(mine)
            else:
                self.assertAlmostEqual(mine, ref, places=9)


class TestPrevalenceBias(unittest.TestCase):
    """PI / BI（Byrt 等 1993 的二值化口径）。"""

    def test_binary_pi_bi(self):
        # 10 个单元：8 个一致同意、2 个一致反对。
        # PI = |N11 - N22| / N = |8 - 2| / 10 = 0.6
        # BI = |N1. - N.1| / N = |10 - 10| / 10 = 0
        cm = {("A", "A"): 8, ("B", "B"): 2}
        pi, bi = ag.prevalence_and_bias(cm, ["A", "B"])
        self.assertAlmostEqual(pi, 0.6, places=10)
        self.assertAlmostEqual(bi, 0.0, places=10)

    def test_bias_detects_marginal_difference(self):
        # A 全部判为 A（10），B 全部判为 B（0）
        # BI = |N12 - N21| / N = |5 - 0| / 10 = 0.5
        # PI = |N11 - N22| / N = |5 - 0| / 10 = 0.5
        cm = {("A", "A"): 5, ("A", "B"): 5, ("B", "A"): 0, ("B", "B"): 0}
        pi, bi = ag.prevalence_and_bias(cm, ["A", "B"])
        self.assertAlmostEqual(bi, 0.5, places=10)
        self.assertAlmostEqual(pi, 0.5, places=10)


class TestFce(unittest.TestCase):
    """Fleiss–Cohen–Everitt 渐近标准误。"""

    def test_se_positive_and_ci_brackets_kappa(self):
        cm = {("A", "A"): 40, ("A", "B"): 5, ("B", "A"): 10, ("B", "B"): 45}
        se = ag.fleiss_cohen_everitt_se(cm, ["A", "B"])
        self.assertIsNotNone(se)
        self.assertGreater(se, 0.0)
        kappa = ag.cohen_kappa(cm, ["A", "B"])
        lo = kappa - 1.959963985 * se
        hi = kappa + 1.959963985 * se
        self.assertLess(lo, kappa)
        self.assertGreater(hi, kappa)


class TestMatching(unittest.TestCase):
    """实体 / 关系匹配口径。"""

    def test_strict_exact(self):
        g = [ag.Entity(0, 2, "@", "P:甲", "甲")]
        p = [ag.Entity(0, 2, "@", "P:甲", "甲")]
        tp, fp, fn, _ = ag.match_entities(g, p, "strict")
        self.assertEqual((tp, fp, fn), (1, 0, 0))

    def test_strict_rejects_boundary_drift(self):
        g = [ag.Entity(0, 2, "@", "P:甲", "甲")]
        p = [ag.Entity(0, 3, "@", "P:甲", "甲乙")]
        tp, fp, fn, _ = ag.match_entities(g, p, "strict")
        self.assertEqual((tp, fp, fn), (0, 1, 1))

    def test_relaxed_accepts_boundary_drift(self):
        g = [ag.Entity(0, 2, "@", "P:甲", "甲")]
        p = [ag.Entity(0, 3, "@", "P:甲", "甲乙")]
        tp, fp, fn, _ = ag.match_entities(g, p, "relaxed")
        self.assertEqual((tp, fp, fn), (1, 0, 0))

    def test_relaxed_rejects_type_mismatch(self):
        g = [ag.Entity(0, 2, "@", "P:甲", "甲")]
        p = [ag.Entity(0, 3, "=", "=:甲", "甲乙")]
        tp, fp, fn, _ = ag.match_entities(g, p, "relaxed")
        self.assertEqual((tp, fp, fn), (0, 1, 1))

    def test_relation_strict_vs_canonical(self):
        h1 = ag.Endpoint("entity", (0, 2), "@", "P:甲")
        h2 = ag.Endpoint("entity", (0, 2), "@", "P:甲")
        t = ag.Endpoint("couplet", couplet_id="C1")
        g = [ag.Relation(h1, "撰联", t)]
        # canonical 相同但 span 不同
        h3 = ag.Endpoint("entity", (5, 7), "@", "P:甲")
        p = [ag.Relation(h3, "撰联", t)]
        self.assertEqual(ag.match_relations(g, p, "strict"), (0, 1, 1))
        self.assertEqual(ag.match_relations(g, p, "relaxed"), (1, 0, 0))


class TestClassification(unittest.TestCase):
    """错误分类受控词表。"""

    def test_identical_is_no_error(self):
        e = ag.Entity(0, 2, "@", "P:甲", "甲")
        self.assertEqual(ag.classify_entity_error(e, e, CODES), "")

    def test_type_confusion(self):
        g = ag.Entity(0, 2, "@", "P:甲", "甲")
        p = ag.Entity(0, 2, "=", "=:甲", "甲")
        self.assertEqual(ag.classify_entity_error(g, p, CODES), "类型混淆")

    def test_boundary(self):
        g = ag.Entity(0, 2, "@", "P:甲", "甲")
        p = ag.Entity(0, 3, "@", "P:甲", "甲乙")
        self.assertEqual(ag.classify_entity_error(g, p, CODES), "边界切分歧义")

    def test_same_entity_different_surface(self):
        g = ag.Entity(0, 2, "@", "P:纪昀", "纪昀")
        p = ag.Entity(0, 3, "@", "P:纪昀", "纪文达")
        self.assertEqual(ag.classify_entity_error(g, p, CODES), "边界切分歧义")

    def test_same_surface_different_entity(self):
        g = ag.Entity(0, 2, "@", "P:甲", "甲")
        p = ag.Entity(0, 2, "@", "P:乙", "甲")
        self.assertEqual(ag.classify_entity_error(g, p, CODES), "异实同指")

    def test_missed(self):
        g = ag.Entity(0, 2, "@", "P:甲", "甲")
        self.assertEqual(ag.classify_entity_error(g, None, CODES), "漏标")
        self.assertEqual(ag.classify_entity_error(None, g, CODES), "漏标")


class TestStatistics(unittest.TestCase):
    """显著性检验与效应量。"""

    def test_mcnemar_matches_binomtest(self):
        try:
            from scipy.stats import binomtest
        except ImportError:
            self.skipTest("未安装 scipy")
        for b, c in [(10, 2), (5, 5), (20, 0), (3, 7)]:
            self.assertAlmostEqual(ag.mcnemar_exact(b, c),
                                   binomtest(b, b + c, 0.5).pvalue, places=12)

    def test_wilcoxon_statistic_matches_scipy(self):
        try:
            from scipy.stats import wilcoxon
        except ImportError:
            self.skipTest("未安装 scipy")
        rng = random.Random(3)
        for _ in range(30):
            n = rng.randint(5, 25)
            a = [rng.gauss(0, 1) for _ in range(n)]
            b = [a[i] + rng.gauss(0, 0.3) for i in range(n)]
            mine = ag.wilcoxon_signed_rank(a, b)
            ref = wilcoxon(a, b, alternative="two-sided", zero_method="wilcox")
            self.assertAlmostEqual(mine["statistic"], ref.statistic, places=9)

    def test_wilcoxon_exact_p_matches_scipy(self):
        try:
            from scipy.stats import wilcoxon
        except ImportError:
            self.skipTest("未安装 scipy")
        rng = random.Random(5)
        for _ in range(25):
            n = rng.randint(5, 12)
            a = [rng.gauss(0, 1) for _ in range(n)]
            b = [a[i] + rng.gauss(0, 0.4) for i in range(n)]
            mine = ag.wilcoxon_signed_rank(a, b)
            ref = wilcoxon(a, b, alternative="two-sided",
                           zero_method="wilcox", method="exact")
            if mine["p_value_exact"] is not None:
                self.assertAlmostEqual(mine["p_value_exact"], ref.pvalue, places=12)

    def test_cliffs_delta_extremes(self):
        self.assertEqual(
            ag.wilcoxon_signed_rank([3, 4, 5], [1, 2, 3])["cliffs_delta"], 1.0)
        self.assertEqual(
            ag.wilcoxon_signed_rank([1, 2, 3], [1, 2, 3])["cliffs_delta"], 0.0)

    def test_percentile_matches_numpy(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("未安装 numpy")
        vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        q1 = ag._percentile(vals, 0.25)
        q3 = ag._percentile(vals, 0.75)
        self.assertAlmostEqual(q1, float(np.percentile(vals, 25)), places=12)
        self.assertAlmostEqual(q3, float(np.percentile(vals, 75)), places=12)


class TestBootstrap(unittest.TestCase):
    """自助法置信区间的确定性。"""

    def test_deterministic(self):
        pairs = [("A", "A")] * 40 + [("A", "B")] * 5 + [("B", "A")] * 10 + \
                [("B", "B")] * 45
        labels = ["A", "B"]
        lo1, hi1 = ag.bootstrap_ci_kappa(pairs, labels, b=200, seed=42)
        lo2, hi2 = ag.bootstrap_ci_kappa(pairs, labels, b=200, seed=42)
        self.assertEqual((lo1, hi1), (lo2, hi2))

    def test_ci_brackets_point_estimate(self):
        pairs = [("A", "A")] * 40 + [("A", "B")] * 5 + [("B", "A")] * 10 + \
                [("B", "B")] * 45
        labels = ["A", "B"]
        kappa = ag.cohen_kappa(
            {("A", "A"): 40, ("A", "B"): 5, ("B", "A"): 10, ("B", "B"): 45},
            labels)
        lo, hi = ag.bootstrap_ci_kappa(pairs, labels, b=500, seed=42)
        self.assertLessEqual(lo, kappa)
        self.assertGreaterEqual(hi, kappa)


class TestSchemaAndIO(unittest.TestCase):
    """schema.yaml 与 JSONL 读写。"""

    def test_schema_loads(self):
        schema = ag.load_schema(SCHEMA_PATH)
        self.assertEqual(len(schema.entity_codes), 18)
        self.assertIn("用典", schema.relation_names)
        self.assertIn("联类", schema.attribute_names)
        self.assertEqual(schema.attribute_measurement("品第"), "ordinal")
        self.assertEqual(schema.bootstrap_seed, 42)

    def test_roundtrip(self):
        tmp = ROOT / "tests" / "_tmp_ann.jsonl"
        rec = {
            "unit_id": "1.3.1", "annotator": "A", "chars": 10,
            "elapsed_minutes": 1.5,
            "entities": [{"char_start": 0, "char_end": 2, "type": "@",
                          "text": "甲"}],
            "relations": [],
            "attributes": {"联类": "春联"},
        }
        tmp.write_text(json.dumps(rec, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        try:
            anns = ag.load_annotations(tmp)
            self.assertEqual(len(anns), 1)
            self.assertEqual(anns[0].entities[0].canonical_id, "@:甲")
            self.assertEqual(anns[0].attributes["联类"], "春联")
            self.assertEqual(anns[0].chars, 10)
        finally:
            tmp.unlink(missing_ok=True)


class TestDeterminism(unittest.TestCase):
    """整体流程的确定性：同一输入两次运行产出逐字节一致。"""

    def test_cli_is_deterministic(self):
        import shutil
        import subprocess
        ex = ROOT / "examples"
        if not (ex / "gold.jsonl").exists():
            self.skipTest("缺少演示夹具；先运行 make_demo_fixtures.py")
        out1 = ROOT / "tests" / "_rep1"
        out2 = ROOT / "tests" / "_rep2"
        try:
            for out in (out1, out2):
                subprocess.run(
                    [sys.executable, str(ROOT / "agreement.py"),
                     "--gold", str(ex / "gold.jsonl"),
                     "--ann", "%s,%s" % (ex / "ann_a.jsonl", ex / "ann_b.jsonl"),
                     "--config", str(SCHEMA_PATH), "--out", str(out),
                     "--no-f1"],
                    check=True, capture_output=True)
            for name in ("kappa_by_type.csv", "kappa_by_type_canonical.csv",
                         "error_taxonomy.csv", "ci.json", "SUMMARY.md"):
                a = (out1 / name).read_bytes()
                b = (out2 / name).read_bytes()
                self.assertEqual(a, b, "%s 两次运行不一致" % name)
        finally:
            shutil.rmtree(out1, ignore_errors=True)
            shutil.rmtree(out2, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
