#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agreement.py —— 《楹联丛话全编》语义标注一致性度量工具。

用途
----
对《楹联丛话全编》的语义标注，计算标注者之间（以及系统与金标准之间）的
一致性指标，并产出可被论文表格逐格溯源的报告。

命令行
------
    python agreement.py --gold gold.jsonl --ann ann_a.jsonl,ann_b.jsonl \
        --config schema.yaml --out reports/

可选参数
--------
    --baseline  baseline.jsonl   参与对比的基线系统输出（不计入标注者一致性）
    --cases     cases.json       已仲裁的分歧案例（8 条），缺失时自动取 top-8
    --units     entity,relation,attribute
                                 只跑指定单元族，默认全部
    --no-f1     跳过 F1/显著性计算（只有一致性评估时用）

输入格式（JSONL，每行一条记录）
--------------------------------
标注者文件（ann_*.jsonl）与金标准文件（gold.jsonl）使用同一 schema：

    {
      "unit_id":      "1.3.1",          # 段落级 Purple Number，标注单元主键
      "annotator":    "A",              # 标注者标识（gold 可为 "GOLD"）
      "condition":    "treatment",      # 可选："treatment" | "baseline"（用于工时配对）
      "chars":        186,              # 可选：该单元的字符数（工时归一化用）
      "elapsed_minutes": 7.5,           # 可选：该单元的净标注耗时
      "entities": [
        {"char_start": 12, "char_end": 14, "type": "@",
         "canonical_id": "P:纪昀", "text": "纪文达"}
      ],
      "relations": [
        {"relation_type": "撰联",
         "head": {"kind": "entity", "char_start": 12, "char_end": 14,
                  "type": "@", "canonical_id": "P:纪昀"},
         "tail": {"kind": "couplet", "couplet_id": "C0001"}}
      ],
      "attributes": {"联类": "春联", "品第": "上"}
    }

约束
----
* ``char_start`` / ``char_end`` 为**原文**（未加标记）段落内的字符偏移，左闭右开。
* ``canonical_id`` 缺省时按 ``{type}:{text}`` 自动生成。
* 关系的 head/tail 端点 ``kind`` 取 ``entity`` 或 ``couplet``；
  ``couplet`` 端点以 ``couplet_id`` 定位（联语切分由语料侧固定）。
* ``attributes`` 为「联语 -> 属性名 -> 属性值」的单值字典。

确定性
------
* 所有随机过程使用固定种子（schema.yaml ``metrics.bootstrap.seed``，默认 42）。
* 所有迭代按 key 排序后进行；浮点求和使用 ``math.fsum``（对排序后的序列求和），
  不依赖字典插入顺序。
* 同一输入重复运行必得同一输出（逐字节一致）。

依赖
----
仅需 PyYAML（读取 schema.yaml）；数值计算使用标准库 ``math`` / ``statistics``，
若环境中存在 numpy 则自动用于加速自助法（不影响结果定义）。

许可
----
MIT。数据与标注规范以 CC-BY-4.0 释出。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

try:  # numpy 仅用于加速，不影响结果定义
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None

try:
    import yaml
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "需要 PyYAML：pip install -r requirements.txt（%s）" % exc
    )


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

NONE_LABEL = "∅"          # 未标注 / 未覆盖
BOOTSTRAP_SEED_DEFAULT = 42
BOOTSTRAP_B_DEFAULT = 1000
PAIRED_BOOTSTRAP_B_DEFAULT = 10000
FCE_CITATION = "Fleiss, Cohen & Everitt (1969)"
BYRT_CITATION = "Byrt, Bishop & Carlin (1993)"


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Entity:
    """实体标注单元：(char_start, char_end, type, canonical_id)。"""

    char_start: int
    char_end: int
    type: str
    canonical_id: str
    text: str = ""

    @property
    def span(self) -> tuple[int, int]:
        return (self.char_start, self.char_end)

    @property
    def strict_key(self) -> tuple[int, int, str]:
        """span 检测口径：字符跨度 + 类型。"""
        return (self.char_start, self.char_end, self.type)

    @property
    def canonical_key(self) -> tuple[str, str]:
        """实体链接口径：类型 + 规范名。"""
        return (self.type, self.canonical_id)

    @property
    def surface_key(self) -> str:
        """字面形式（用于「同名异人」判定）。"""
        return self.text or self.canonical_id.split(":", 1)[-1]


@dataclass(frozen=True)
class Endpoint:
    """关系端点：实体 span 或联语 id。"""

    kind: str                      # "entity" | "couplet"
    span: tuple[int, int] | None = None
    type: str | None = None
    canonical_id: str | None = None
    couplet_id: str | None = None

    @property
    def strict_key(self) -> tuple:
        if self.kind == "couplet":
            return ("couplet", self.couplet_id)
        return ("entity", self.span[0], self.span[1], self.type)

    @property
    def canonical_key(self) -> tuple:
        if self.kind == "couplet":
            return ("couplet", self.couplet_id)
        return ("entity", self.type, self.canonical_id)

    @property
    def surface_key(self) -> str:
        if self.kind == "couplet":
            return str(self.couplet_id)
        return str(self.canonical_id)


@dataclass(frozen=True)
class Relation:
    """关系标注单元：三元组 (head, relation_type, tail)。"""

    head: Endpoint
    relation_type: str
    tail: Endpoint

    @property
    def strict_key(self) -> tuple:
        return (self.head.strict_key, self.relation_type, self.tail.strict_key)

    @property
    def canonical_key(self) -> tuple:
        return (self.head.canonical_key, self.relation_type, self.tail.canonical_key)


@dataclass
class Annotation:
    """一位标注者（或系统）对一个标注单元的完整输出。"""

    unit_id: str
    annotator: str
    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)
    condition: str = ""
    chars: int | None = None
    elapsed_minutes: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Schema:
    """schema.yaml 的结构化视图。"""

    raw: dict[str, Any]

    # -- 实体类型 -------------------------------------------------------
    @property
    def entity_codes(self) -> list[str]:
        return [e["code"] for e in self.raw.get("entity_types", [])]

    @property
    def entity_labels(self) -> dict[str, str]:
        return {e["code"]: e.get("label_name", e["code"])
                for e in self.raw.get("entity_types", [])}

    @property
    def relation_names(self) -> list[str]:
        return [r["name"] for r in self.raw.get("relation_types", [])]

    @property
    def attribute_names(self) -> list[str]:
        return [a["name"] for a in self.raw.get("attribute_types", [])]

    def attribute_measurement(self, name: str) -> str:
        for a in self.raw.get("attribute_types", []):
            if a["name"] == name:
                return a.get("measurement", "nominal")
        return "nominal"

    def attribute_values(self, name: str) -> list[str]:
        for a in self.raw.get("attribute_types", []):
            if a["name"] == name:
                return list(a.get("values", []))
        return []

    def error_codes(self) -> list[str]:
        rows = sorted(self.raw.get("error_taxonomy", []),
                      key=lambda r: (r.get("priority", 99), r.get("code", "")))
        return [r["code"] for r in rows]

    # -- 度量参数 -------------------------------------------------------
    @property
    def bootstrap_b(self) -> int:
        return int(self.raw.get("metrics", {}).get("bootstrap", {})
                   .get("resamples", BOOTSTRAP_B_DEFAULT))

    @property
    def bootstrap_seed(self) -> int:
        return int(self.raw.get("metrics", {}).get("bootstrap", {})
                   .get("seed", BOOTSTRAP_SEED_DEFAULT))

    @property
    def paired_bootstrap_b(self) -> int:
        return int(self.raw.get("metrics", {}).get("significance", {})
                   .get("paired_bootstrap_resamples", PAIRED_BOOTSTRAP_B_DEFAULT))

    @property
    def primary_weight(self) -> str:
        return self.raw.get("metrics", {}).get("ordinal_weight", {}) \
            .get("primary", "quadratic")

    @property
    def sensitivity_weight(self) -> str:
        return self.raw.get("metrics", {}).get("ordinal_weight", {}) \
            .get("sensitivity", "linear")


def load_schema(path: Path) -> Schema:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return Schema(raw)


# ---------------------------------------------------------------------------
# 读取与解析
# ---------------------------------------------------------------------------

def _canonical_of(type_code: str, text: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    name = text.strip() if text else ""
    return "%s:%s" % (type_code, name)


def _parse_entity(obj: dict[str, Any]) -> Entity:
    text = str(obj.get("text", "") or "")
    tcode = str(obj.get("type", ""))
    return Entity(
        char_start=int(obj["char_start"]),
        char_end=int(obj["char_end"]),
        type=tcode,
        canonical_id=_canonical_of(tcode, text, obj.get("canonical_id")),
        text=text,
    )


def _parse_endpoint(obj: dict[str, Any]) -> Endpoint:
    kind = str(obj.get("kind", "entity"))
    if kind == "couplet":
        return Endpoint(kind="couplet", couplet_id=str(obj["couplet_id"]))
    text = str(obj.get("text", "") or "")
    tcode = str(obj.get("type", ""))
    return Endpoint(
        kind="entity",
        span=(int(obj["char_start"]), int(obj["char_end"])),
        type=tcode,
        canonical_id=_canonical_of(tcode, text, obj.get("canonical_id")),
    )


def _parse_relation(obj: dict[str, Any]) -> Relation:
    return Relation(
        head=_parse_endpoint(obj["head"]),
        relation_type=str(obj["relation_type"]),
        tail=_parse_endpoint(obj["tail"]),
    )


def load_annotations(path: Path) -> list[Annotation]:
    """读取一个 JSONL 标注文件。"""
    out: list[Annotation] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("%s:%d JSON 解析失败：%s" % (path, lineno, exc))
            ann = Annotation(
                unit_id=str(obj["unit_id"]),
                annotator=str(obj.get("annotator", path.stem)),
                entities=[_parse_entity(e) for e in obj.get("entities", [])],
                relations=[_parse_relation(r) for r in obj.get("relations", [])],
                attributes=dict(obj.get("attributes", {}) or {}),
                condition=str(obj.get("condition", "") or ""),
                chars=int(obj["chars"]) if obj.get("chars") is not None else None,
                elapsed_minutes=(float(obj["elapsed_minutes"])
                                 if obj.get("elapsed_minutes") is not None else None),
                extra={k: v for k, v in obj.items()
                       if k not in {"unit_id", "annotator", "condition", "chars",
                                    "elapsed_minutes", "entities", "relations",
                                    "attributes"}},
            )
            out.append(ann)
    return out


def index_by_unit(anns: Sequence[Annotation]) -> dict[str, Annotation]:
    """按 unit_id 建立索引；同一标注者对同一 unit 只允许一条记录。"""
    idx: dict[str, Annotation] = {}
    for a in anns:
        if a.unit_id in idx:
            raise ValueError("unit_id 重复：%s" % a.unit_id)
        idx[a.unit_id] = a
    return idx


def pair_records(a: Sequence[Annotation], b: Sequence[Annotation]
                 ) -> list[tuple[Annotation, Annotation | None]]:
    """把两位标注者的记录按 unit_id 对齐；缺失的一方记为 None。"""
    ia, ib = index_by_unit(a), index_by_unit(b)
    keys = sorted(set(ia) | set(ib))
    return [(ia.get(k), ib.get(k)) for k in keys]


# ---------------------------------------------------------------------------
# 基础一致性统计量
# ---------------------------------------------------------------------------

def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def observed_agreement(cm: dict[tuple[str, str], int], labels: Sequence[str]) -> float:
    """p_o = Σ_k O_kk / N。"""
    n = sum(cm.values())
    if not n:
        return 0.0
    diag = math.fsum(cm.get((l, l), 0) for l in labels)
    return diag / n


def expected_agreement(cm: dict[tuple[str, str], int], labels: Sequence[str]) -> float:
    """p_e = Σ_k (O_k. * O_.k) / N^2。"""
    n = sum(cm.values())
    if not n:
        return 0.0
    row = {l: math.fsum(cm.get((l, k), 0) for k in labels) for l in labels}
    col = {l: math.fsum(cm.get((k, l), 0) for k in labels) for l in labels}
    return math.fsum((row[l] * col[l]) / (n * n) for l in labels)


def cohen_kappa(cm: dict[tuple[str, str], int], labels: Sequence[str]) -> float | None:
    """Cohen's κ = (p_o - p_e)/(1 - p_e)。退化情形（p_e == 1）返回 None。"""
    n = sum(cm.values())
    if not n:
        return None
    po = observed_agreement(cm, labels)
    pe = expected_agreement(cm, labels)
    if math.isclose(pe, 1.0):
        return None
    return (po - pe) / (1.0 - pe)


def weighted_kappa(cm: dict[tuple[str, str], int], labels: Sequence[str],
                   weight: str = "quadratic") -> float | None:
    """加权 κ（Cohen 1968 定义）。

    观察与期望的加分母均取 n，权重矩阵 w_ii = 0，
    w_ij = |i-j|/(k-1)（linear）或 (i-j)^2/(k-1)^2（quadratic）。
    """
    k = len(labels)
    if k < 2:
        return None
    n = sum(cm.values())
    if not n:
        return None
    idx = {l: i for i, l in enumerate(labels)}

    def w(i: int, j: int) -> float:
        d = abs(i - j)
        if weight == "linear":
            return d / (k - 1)
        if weight == "quadratic":
            return (d * d) / ((k - 1) * (k - 1))
        raise ValueError("未知权重：%s" % weight)

    obs_num = math.fsum(w(idx[a], idx[b]) * c for (a, b), c in sorted(cm.items()))
    row = {l: math.fsum(cm.get((l, kk), 0) for kk in labels) for l in labels}
    col = {l: math.fsum(cm.get((kk, l), 0) for kk in labels) for l in labels}
    exp_num = math.fsum(
        w(idx[a], idx[b]) * (row[a] * col[b]) / n for a in labels for b in labels)
    denom = n - exp_num
    if math.isclose(denom, 0.0):
        return None
    return 1.0 - (obs_num / n) / (exp_num / n)


def fleiss_kappa(counts: Sequence[Sequence[int]], labels: Sequence[str]
                 ) -> float | None:
    """Fleiss' κ（完全交叉、每单元标注者数相同）。

    ``counts`` 的形状为 **(单元数 × 类别数)**：``counts[u][i]`` 是第 u 个单元
    被判为第 i 类的次数，每行之和应相等（= 每单元的标注者数）。
    """
    n_units = len(counts)
    if n_units == 0:
        return None
    n_per = len(counts[0])
    if n_per < 2:
        return None
    # 类别的边际比例 p_j
    totals = [math.fsum(c[i] for c in counts) for i in range(len(labels))]
    grand = math.fsum(totals)
    if not grand:
        return None
    p_j = [totals[i] / grand for i in range(len(labels))]
    p_e = math.fsum(v * v for v in p_j)
    # 单元内的观察一致度 P_i
    p_i_list = []
    for c in counts:
        m = math.fsum(c)
        if m < 2:
            continue
        p_i_list.append((math.fsum(x * x for x in c) - m) / (m * (m - 1)))
    if not p_i_list:
        return None
    p_o = math.fsum(p_i_list) / len(p_i_list)
    if math.isclose(p_e, 1.0):
        return None
    return (p_o - p_e) / (1.0 - p_e)


def _krippendorff_alpha(reliability: Sequence[Sequence[Any]], metric: str,
                        order: dict[Any, int] | None = None) -> float | None:
    """Krippendorff's α（coincidence matrix 口径）。

    ``reliability`` 为「每个单元一行、每行是该单元各标注者的取值」的表，
    缺失以 ``None`` 表示；只有至少两个有效取值的单元参与计算。
    结果与 ``krippendorff`` 包的 nominal / ordinal 口径一致（见 tests/）。
    """
    usable: list[tuple[list[Any], int]] = []
    for row in reliability:
        vals = [v for v in row if v is not None]
        if len(vals) >= 2:
            usable.append((vals, len(vals)))
    if not usable:
        return None

    values = sorted({v for vals, _ in usable for v in vals},
                    key=lambda v: (order.get(v, 0) if order else str(v)))
    vindex = {v: i for i, v in enumerate(values)}
    nv = len(values)
    if nv < 2:
        return None

    # o_ck = Σ_u (n_uc · n_uk - δ_ck·n_uc) / (m_u - 1)
    # 注：自配对（c == k）不计入可观察一致对。
    coincidence = [[0.0] * nv for _ in range(nv)]
    for vals, m in usable:
        counts = Counter(vals)
        for c in values:
            nc = counts.get(c, 0)
            if not nc:
                continue
            for k in values:
                nk = counts.get(k, 0)
                if not nk:
                    continue
                term = nc * nk - (nc if c == k else 0)
                if term:
                    coincidence[vindex[c]][vindex[k]] += term / (m - 1)

    n_c = [math.fsum(coincidence[i][j] for j in range(nv)) for i in range(nv)]
    total = math.fsum(n_c)
    if total <= 1:
        return None

    # 距离矩阵 d
    if metric == "nominal":
        dist = [[1.0 if i != j else 0.0 for j in range(nv)] for i in range(nv)]
    elif metric == "ordinal":
        # d(i,j)^2 = (Σ_{g=i}^{j} n_g - (n_i + n_j)/2)^2（i ≤ j，符号对称）
        dist = [[0.0] * nv for _ in range(nv)]
        for i in range(nv):
            for j in range(nv):
                lo, hi = min(i, j), max(i, j)
                if lo == hi:
                    dist[i][j] = 0.0
                    continue
                cum = math.fsum(n_c[g] for g in range(lo, hi + 1))
                val = cum - (n_c[lo] + n_c[hi]) / 2.0
                dist[i][j] = val * val
    else:
        raise ValueError("未知测度层级：%s" % metric)

    # 观察不一致 D_o = Σ o_ck · d_ck
    d_obs = math.fsum(coincidence[i][j] * dist[i][j]
                      for i in range(nv) for j in range(nv))
    # 期望不一致 D_e = Σ e_ck · d_ck
    # e_ck = (n_c·n_k - δ_ck n_c) / (Σn_c - 1)
    e_sum = total - 1.0
    d_exp = math.fsum(
        ((n_c[i] * n_c[j] - (n_c[i] if i == j else 0)) / e_sum) * dist[i][j]
        for i in range(nv) for j in range(nv))
    if math.isclose(d_exp, 0.0):
        return None
    return 1.0 - d_obs / d_exp


def scott_pi(cm: dict[tuple[str, str], int], labels: Sequence[str]) -> float | None:
    """Scott's Pi：把两位标注者的边际**合并**后计算期望一致度。

        p_j = (O_j. + O_.j) / (2N)，p_e = Σ_j p_j²

    与 Cohen's κ 的差别只在 p_e 的边际口径：前者合并两位标注者的边际，
    后者分别计算。**两位标注者时 Fleiss' κ 约等于 Scott's Pi，而非 Cohen's κ**，
    因此报告 κ 时必须同时写明估计量名称，否则跨研究不可比。
    """
    n = sum(cm.values())
    if not n:
        return None
    po = observed_agreement(cm, labels)
    row = {l: math.fsum(cm.get((l, k), 0) for k in labels) for l in labels}
    col = {l: math.fsum(cm.get((k, l), 0) for k in labels) for l in labels}
    p_e = math.fsum(((row[l] + col[l]) / (2.0 * n)) ** 2 for l in labels)
    if math.isclose(p_e, 1.0):
        return None
    return (po - p_e) / (1.0 - p_e)


def krippendorff_alpha_nominal(reliability: Sequence[Sequence[Any]]) -> float | None:
    """Krippendorff's α（nominal）。"""
    return _krippendorff_alpha(reliability, metric="nominal")


def krippendorff_alpha_ordinal(reliability: Sequence[Sequence[Any]],
                               levels: Sequence[Any]) -> float | None:
    """Krippendorff's α（ordinal），等级距离 d^2 = Σ_{g≤i, h≤j} n_g n_h。"""
    order = {v: i for i, v in enumerate(levels)}
    return _krippendorff_alpha(reliability, metric="ordinal", order=order)


def fleiss_cohen_everitt_se(cm: dict[tuple[str, str], int],
                            labels: Sequence[str]) -> float | None:
    """Fleiss–Cohen–Everitt (1969) 渐近标准误。

        Var(κ) = [p_o + p_e - p_o·p_e - Σ_j p_j q_j (p_j + q_j)] / [n (1 - p_e)^2]

    其中 p_j、q_j 为第 j 类的边际比例，n 为单元数。
    """
    n = sum(cm.values())
    if n < 2:
        return None
    po = observed_agreement(cm, labels)
    pe = expected_agreement(cm, labels)
    if math.isclose(pe, 1.0):
        return None
    row = {l: math.fsum(cm.get((l, k), 0) for k in labels) for l in labels}
    col = {l: math.fsum(cm.get((k, l), 0) for k in labels) for l in labels}
    pj = {l: row[l] / n for l in labels}
    qj = {l: col[l] / n for l in labels}
    s = math.fsum(pj[l] * qj[l] * (pj[l] + qj[l]) for l in labels)
    var = (po + pe - po * pe - s) / (n * (1.0 - pe) ** 2)
    if var < 0:
        return None
    return math.sqrt(var)


def per_class_prevalence_bias(cm: dict[tuple[str, str], int],
                              labels: Sequence[str]) -> dict[str, tuple[float, float]]:
    """逐类 PI/BI 明细（Byrt 等 1993 的二值化口径）。

        PI = |N11 - N22| / N      （流行度：阳性与阴性的分布失衡）
        BI = |N1. - N.1| / N       （偏倚：两位标注者的边际不一致）

    对每个候选类 b 把标签二值化为「b / 非 b」后分别计算。
    """
    n = sum(cm.values())
    if not n:
        return {}
    out: dict[str, tuple[float, float]] = {}
    for l in labels:
        n11 = cm.get((l, l), 0)
        n22 = math.fsum(cm.get((a, b), 0)
                        for a in labels for b in labels if a != l and b != l)
        n1_ = math.fsum(cm.get((l, b), 0) for b in labels)
        n_1 = math.fsum(cm.get((a, l), 0) for a in labels)
        out[l] = (abs(n11 - n22) / n, abs(n1_ - n_1) / n)
    return out


def prevalence_and_bias(cm: dict[tuple[str, str], int],
                         labels: Sequence[str]) -> tuple[float | None, float | None]:
    """返回 PI 与 BI 的**代表值**：取逐类绝对值最大者的对应值。"""
    detail = per_class_prevalence_bias(cm, labels)
    if not detail:
        return None, None
    worst_pi = max(detail.items(), key=lambda kv: (kv[1][0], kv[0]))
    worst_bi = max(detail.items(), key=lambda kv: (kv[1][1], kv[0]))
    return worst_pi[1][0], worst_bi[1][1]


# ---------------------------------------------------------------------------
# 自助法置信区间
# ---------------------------------------------------------------------------

def bootstrap_ci(values: Sequence[Any],
                 statistic: Callable[[Sequence[Any]], float | None],
                 b: int = BOOTSTRAP_B_DEFAULT,
                 seed: int = BOOTSTRAP_SEED_DEFAULT,
                 alpha: float = 0.05) -> tuple[float | None, float | None]:
    """按单元重采样的 percentile bootstrap CI。

    ``statistic`` 接收重采样后的取值序列，返回标量或 None；
    使用固定种子的 ``random.Random``，保证逐次运行完全一致。
    """
    if not values:
        return None, None
    rng = random.Random(seed)
    n = len(values)
    samples: list[float] = []
    for _ in range(b):
        resampled = [values[rng.randrange(n)] for _ in range(n)]
        stat = statistic(resampled)
        if stat is not None and math.isfinite(stat):
            samples.append(stat)
    if len(samples) < 2:
        return None, None
    samples.sort()
    lo_idx = max(0, min(int(math.floor((alpha / 2) * len(samples))),
                        len(samples) - 1))
    hi_idx = max(0, min(int(math.ceil((1 - alpha / 2) * len(samples))) - 1,
                        len(samples) - 1))
    return samples[lo_idx], samples[hi_idx]


def bootstrap_ci_kappa(pairs: Sequence[tuple[str, str]], labels: Sequence[str],
                       b: int = BOOTSTRAP_B_DEFAULT,
                       seed: int = BOOTSTRAP_SEED_DEFAULT,
                       weight: str | None = None) -> tuple[float | None, float | None]:
    """κ 的 bootstrap CI：在 (a 标签, b 标签) 配对序列上重采样单元。"""
    def stat(sample: Sequence[tuple[str, str]]) -> float | None:
        cm: dict[tuple[str, str], int] = {}
        for x, y in sample:
            cm[(x, y)] = cm.get((x, y), 0) + 1
        if weight:
            return weighted_kappa(cm, labels, weight)
        return cohen_kappa(cm, labels)

    return bootstrap_ci(list(pairs), stat, b=b, seed=seed)


def bootstrap_ci_alpha(reliability: Sequence[Sequence[Any]], metric: str,
                       levels: Sequence[Any] | None = None,
                       b: int = BOOTSTRAP_B_DEFAULT,
                       seed: int = BOOTSTRAP_SEED_DEFAULT) -> tuple[float | None, float | None]:
    """α 的 bootstrap CI：在单元层面重采样。"""
    def stat(sample: Sequence[Sequence[Any]]) -> float | None:
        if metric == "ordinal" and levels is not None:
            return krippendorff_alpha_ordinal(sample, levels)
        return krippendorff_alpha_nominal(sample)

    return bootstrap_ci(list(reliability), stat, b=b, seed=seed)


# ---------------------------------------------------------------------------
# 精确匹配 / 宽松匹配下的 F1
# ---------------------------------------------------------------------------

def match_entities(gold: Sequence[Entity], pred: Sequence[Entity],
                   mode: str = "strict") -> tuple[int, int, int,
                                                list[tuple[Entity, Entity]]]:
    """实体匹配的 TP / FP / FN。

    ``strict``：字符跨度与类型完全相同；
    ``relaxed``：跨度重叠 ≥ 1 字符且类型相同。

    返回 (tp, fp, fn, 配对列表)；配对列表供错误分析使用。
    """
    if mode == "strict":
        gmap: dict[tuple, list[Entity]] = defaultdict(list)
        for g in gold:
            gmap[g.strict_key].append(g)
        used: set[int] = set()
        tp = fp = 0
        pairs: list[tuple[Entity, Entity]] = []
        for p in pred:
            bucket = gmap.get(p.strict_key, [])
            hit = None
            for idx, g in enumerate(bucket):
                if idx not in used:
                    hit = (idx, g)
                    break
            if hit is not None:
                used.add(hit[0])
                tp += 1
                pairs.append((hit[1], p))
            else:
                fp += 1
        fn = len(gold) - len(used)
        return tp, fp, fn, pairs

    unmatched = list(gold)
    tp = fp = 0
    pairs: list[tuple[Entity, Entity]] = []
    for p in pred:
        best: int | None = None
        best_len = -1
        for gi, g in enumerate(unmatched):
            if g.type != p.type:
                continue
            if g.char_start < p.char_end and p.char_start < g.char_end:
                overlap = min(g.char_end, p.char_end) - max(g.char_start, p.char_start)
                if overlap > best_len:
                    best, best_len = gi, overlap
        if best is not None:
            tp += 1
            pairs.append((unmatched[best], p))
            unmatched.pop(best)
        else:
            fp += 1
    fn = len(unmatched)
    return tp, fp, fn, pairs


def match_relations(gold: Sequence[Relation], pred: Sequence[Relation],
                    mode: str = "strict") -> tuple[int, int, int]:
    """关系三元组匹配的 TP / FP / FN。

    ``strict``：head/tail 的 span 键与 relation_type 全同；
    ``relaxed``：head/tail 按 canonical_id 匹配，relation_type 相同。
    """
    key = (lambda r: r.strict_key) if mode == "strict" else (lambda r: r.canonical_key)
    gmap: Counter = Counter(key(x) for x in gold)
    tp = 0
    for p in pred:
        k = key(p)
        if gmap.get(k, 0) > 0:
            gmap[k] -= 1
            tp += 1
    fp = len(pred) - tp
    fn = len(gold) - tp
    return tp, fp, fn


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """precision / recall / F1（分母为零时取 0）。"""
    p = _safe_div(tp, tp + fp)
    r = _safe_div(tp, tp + fn)
    f = _safe_div(2 * p * r, p + r)
    return p, r, f


def _chunks_from_iob(seq: Sequence[str | None]) -> list[tuple[int, int, str, str]]:
    """把 IOB2 序列还原为 (start, end, type, text) 块列表。"""
    chunks: list[tuple[int, int, str, str]] = []
    start: int | None = None
    cur_type = ""
    cur_text: list[str] = []
    for i, tok in enumerate(seq):
        if tok is None or tok == "O":
            if start is not None:
                chunks.append((start, i, cur_type, "".join(cur_text)))
                start, cur_type, cur_text = None, "", []
            continue
        prefix, _, etype = tok.partition("-")
        if prefix == "B" or start is None or etype != cur_type:
            if start is not None:
                chunks.append((start, i, cur_type, "".join(cur_text)))
            start, cur_type, cur_text = i, etype, [tok]
        else:
            cur_text.append(tok)
    if start is not None:
        chunks.append((start, len(seq), cur_type, "".join(cur_text)))
    return chunks


def seqeval_conformance(gold_seqs: Sequence[Sequence[str | None]],
                        pred_seqs: Sequence[Sequence[str | None]]) -> dict[str, float]:
    """seqeval 风格的 conformance 统计。

    标签为 IOB2 实体序列（``B-type`` / ``I-type`` / ``O``），
    precision / recall / F1 按**实体个数**计，与 :func:`match_entities` 口径一致。
    """
    tp = fp = fn = 0
    for g_seq, p_seq in zip(gold_seqs, pred_seqs):
        g_chunks = _chunks_from_iob(g_seq)
        p_chunks = _chunks_from_iob(p_seq)
        gtp, gfp, gfn, _ = match_entities(
            [Entity(c[0], c[1], c[2], c[2], c[3]) for c in g_chunks],
            [Entity(c[0], c[1], c[2], c[2], c[3]) for c in p_chunks],
            mode="strict")
        tp += gtp
        fp += gfp
        fn += gfn
    p, r, f = prf(tp, fp, fn)
    return {"precision": p, "recall": r, "f1": f,
            "tp": float(tp), "fp": float(fp), "fn": float(fn)}


def entities_to_iob(entities: Sequence[Entity], length: int) -> list[str | None]:
    """把实体列表展开为 IOB2 序列（长度 ``length``）。"""
    seq: list[str | None] = [None] * length
    for e in sorted(entities, key=lambda x: (x.char_start, x.char_end)):
        if not (0 <= e.char_start < e.char_end <= length):
            continue
        for i in range(e.char_start, e.char_end):
            seq[i] = ("B-" if i == e.char_start else "I-") + e.type
    return seq


# ---------------------------------------------------------------------------
# 显著性检验与效应量
# ---------------------------------------------------------------------------

def paired_bootstrap_diff(a: Sequence[float], b: Sequence[float],
                           b_resamples: int = PAIRED_BOOTSTRAP_B_DEFAULT,
                           seed: int = BOOTSTRAP_SEED_DEFAULT,
                           alpha: float = 0.05) -> dict[str, Any]:
    """配对自助法：比较 a 与 b 的均值差。

    在**配对单元**层面重采样（每次抽一个下标，同时取 a[i] 与 b[i]），
    返回均值差、95% percentile CI、双侧 p 值。
    """
    n = min(len(a), len(b))
    if n < 2:
        return {"mean_diff": None, "ci_low": None, "ci_high": None, "p_value": None,
                "n_pairs": n, "method": "paired bootstrap"}
    diffs = [a[i] - b[i] for i in range(n)]
    observed = math.fsum(diffs) / n
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(b_resamples):
        s = math.fsum(diffs[rng.randrange(n)] for _ in range(n)) / n
        samples.append(s)
    samples.sort()
    lo = samples[max(0, min(int(math.floor((alpha / 2) * len(samples))),
                            len(samples) - 1))]
    hi = samples[max(0, min(int(math.ceil((1 - alpha / 2) * len(samples))) - 1,
                            len(samples) - 1))]
    # 双侧 p 值：自助分布中与 0 同侧的比例（中心化）
    centered = [abs(s - observed) for s in samples]
    p_le = (math.fsum(1 for c in centered if c >= abs(observed)) + 1) / (len(samples) + 1)
    p = min(1.0, 2.0 * p_le)
    return {"mean_diff": observed, "ci_low": lo, "ci_high": hi, "p_value": p,
            "n_pairs": n, "method": "paired bootstrap"}


def mcnemar_exact(b: int, c: int) -> float:
    """McNemar 精确检验（双侧，二项分布口径）。

    b、c 为两种条件下结果不一致的配对计数（其中一个为"正确"）。
    """
    if b + c == 0:
        return 1.0
    n = b + c
    k = min(b, c)
    tail = math.fsum(math.comb(n, i) for i in range(0, k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def wilcoxon_signed_rank(a: Sequence[float], b: Sequence[float]) -> dict[str, Any]:
    """配对 Wilcoxon 符号秩检验（不假设正态；小样本亦适用）。

    返回统计量 W+、双侧 p 值（正态近似并做连续性校正；当所有差值均为 0 时
    p = 1.0），以及效应量 Cliff's delta 与 matched-pairs rank-biserial r。
    """
    n = min(len(a), len(b))
    if n < 2:
        return {"statistic": None, "p_value": None, "cliffs_delta": None,
                "rank_biserial_r": None, "n_pairs": n}
    diffs = [a[i] - b[i] for i in range(n)]
    nz = [d for d in diffs if d != 0]
    if not nz:
        return {"statistic": 0.0, "p_value": 1.0, "cliffs_delta": 0.0,
                "rank_biserial_r": 0.0, "n_pairs": n}
    # 秩（按**绝对值**排序，并列取平均秩）
    # 注：Wilcoxon 符号秩检验统计量使用 |d_i| 的秩。
    abs_nz = [abs(d) for d in nz]
    order = sorted(range(len(nz)), key=lambda i: (abs_nz[i], i))
    ranks = [0.0] * len(nz)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and abs_nz[order[j + 1]] == abs_nz[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    w_plus = math.fsum(r for r, d in zip(ranks, nz) if d > 0)
    n_nz = len(nz)
    mu = n_nz * (n_nz + 1) / 4.0
    # 并列校正：平均秩的方差和
    sigma = 0.0
    tied = 0
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and abs_nz[order[j + 1]] == abs_nz[order[i]]:
            j += 1
        cnt = j - i + 1
        if cnt > 1:
            tied += cnt ** 3 - cnt
        i = j + 1
    n0 = n_nz
    sigma = math.sqrt((n0 * (n0 + 1) * (2 * n0 + 1) - tied / 2.0) / 24.0)
    if sigma == 0:
        p = 1.0
    else:
        # 双侧 p：取 W+ 与 W- 中远离期望值远者为尾部概率的两倍
        w_minus = math.fsum(r for r, d in zip(ranks, nz) if d < 0)
        dev = max(abs(w_plus - mu), abs(w_minus - mu))
        z = (dev - 0.5) / sigma
        p = math.erfc(max(0.0, z) / math.sqrt(2.0))
    # 效应量：Cliff's delta（基于配对差值的优势计数）
    gt = sum(1 for d in nz if d > 0)
    lt = sum(1 for d in nz if d < 0)
    cliff = (gt - lt) / (n_nz * (n_nz - 1) / 2.0) if n_nz > 1 else 0.0
    # matched-pairs rank-biserial r = (W+ - W-) / (W+ + W-)
    r_rb = (w_plus - w_minus) / (w_plus + w_minus) if (w_plus + w_minus) else 0.0
    # 统计量报告使用较小者，与 SciPy 口径一致
    stat = min(w_plus, w_minus)
    p_exact = _wilcoxon_exact_p(ranks, [1 if d > 0 else -1 for d in nz])
    return {"statistic": stat, "w_plus": w_plus, "w_minus": w_minus,
            "p_value": p, "p_value_exact": p_exact, "cliffs_delta": cliff,
            "rank_biserial_r": r_rb, "n_pairs": n, "n_nonzero": n_nz,
            "method": "normal approximation (tie-corrected) + exact sign permutation"}


def _wilcoxon_exact_p(ranks: Sequence[float], signs: Sequence[int]) -> float | None:
    """Wilcoxon 符号秩检验的精确 p 值（按符号翻转枚举）。

    枚举 ``n_nonzero`` 个非零差值的所有 2^n 种符号组合，统计与观测值同样极端者；
    n > 20 时返回 None（改用正态近似）。
    """
    n = len(ranks)
    if n == 0 or n > 20:
        return None
    total = math.fsum(ranks)
    observed = math.fsum(r for r, s in zip(ranks, signs) if s > 0)
    mu = total / 2.0
    count = 0
    total_cases = 0
    for mask in range(1 << n):
        s = math.fsum(ranks[i] for i in range(n) if mask >> i & 1)
        total_cases += 1
        if abs(s - mu) >= abs(observed - mu) - 1e-12:
            count += 1
    return count / total_cases


def median_iqr(values: Sequence[float]) -> dict[str, float | None]:
    """中位数与四分位距（IQR）。"""
    vals = sorted(v for v in values if v is not None and math.isfinite(v))
    if not vals:
        return {"median": None, "q1": None, "q3": None, "iqr": None, "n": 0}
    q1, q3 = _percentile(vals, 0.25), _percentile(vals, 0.75)
    return {"median": statistics.median(vals), "q1": q1, "q3": q3,
            "iqr": q3 - q1, "n": len(vals)}


def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    """线性插值分位数（与 numpy 默认 'linear' 口径一致）。"""
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_vals[lo])
    return float(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo))


# ---------------------------------------------------------------------------
# 错误分类
# ---------------------------------------------------------------------------

def classify_entity_error(gold: Entity | None, pred: Entity | None,
                          codes: Sequence[str]) -> str:
    """把一处实体分歧归入受控的错误类型。

    判定顺序（与 schema.yaml ``error_taxonomy.priority`` 一致）：
    漏标 > 类型混淆 > 边界切分歧义 > 同实异指 > 异实同指。
    """
    if gold is None or pred is None:
        return "漏标"
    # 完全一致：无分歧
    if gold.strict_key == pred.strict_key and gold.canonical_id == pred.canonical_id:
        return ""
    if gold.type != pred.type:
        return "类型混淆" if "类型混淆" in codes else codes[0]
    if gold.canonical_id != pred.canonical_id:
        # 规范名不同
        if gold.surface_key == pred.surface_key:
            # 字面相同、实体不同：同名异人 / 同名异书
            return "异实同指" if "异实同指" in codes else codes[0]
        # 字面与规范名都不同，但跨度一致：边界切分歧义优先
        if gold.span != pred.span:
            return "边界切分歧义" if "边界切分歧义" in codes else codes[0]
        return "同实异指" if "同实异指" in codes else codes[-1]
    # 规范名相同：分歧只可能来自边界或字面写法
    if gold.span != pred.span:
        # 跨度不一致：边界切分歧义（优先级高于别名差异）
        return "边界切分歧义" if "边界切分歧义" in codes else codes[0]
    # 跨度一致而字面不同（字号 / 异体 / 简称）：同实异指
    if gold.surface_key != pred.surface_key:
        return "同实异指" if "同实异指" in codes else codes[0]
    return ""


def classify_relation_error(gold: Relation | None, pred: Relation | None,
                            codes: Sequence[str]) -> str:
    """把一处关系分歧归入受控的错误类型。"""
    if gold is None or pred is None:
        return "漏标"
    if gold.relation_type != pred.relation_type:
        return "典故误溯" if gold.relation_type == "用典" and "典故误溯" in codes \
            else ("评点归属错误" if gold.relation_type == "评骘"
                  and "评点归属错误" in codes else codes[0])
    if gold.relation_type == "用典" and (
            gold.tail.canonical_key != pred.tail.canonical_key
            or gold.head.canonical_key != pred.head.canonical_key):
        return "典故误溯" if "典故误溯" in codes else codes[0]
    if gold.relation_type == "评骘" and (
            gold.head.canonical_key != pred.head.canonical_key):
        return "评点归属错误" if "评点归属错误" in codes else codes[0]
    if (gold.head.canonical_key == pred.head.canonical_key
            and gold.tail.canonical_key == pred.tail.canonical_key):
        return "边界切分歧义" if "边界切分歧义" in codes else codes[0]
    return "漏标"


def classify_attribute_error(gold: str | None, pred: str | None,
                             codes: Sequence[str]) -> str:
    """属性分歧归类：品第不一致属「评点归属错误」，其余为「类型混淆」。"""
    if gold is None or pred is None:
        return "漏标"
    if gold == pred:
        return ""
    return "评点归属错误" if "评点归属错误" in codes else codes[0]


# ---------------------------------------------------------------------------
# 报告写出
# ---------------------------------------------------------------------------

def _fmt(value: Any, digits: int = 4) -> str:
    """统一的数值格式化：None -> 空串，浮点保留固定位数。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return "%.*f" % (digits, value)
    return str(value)


def write_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    """写出 UTF-8 BOM 的 CSV（Excel 友好；R/pandas 亦可直读）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(list(header))
        for row in rows:
            writer.writerow([_fmt(c) for c in row])


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


# ---------------------------------------------------------------------------
# 分析主流程
# ---------------------------------------------------------------------------

@dataclass
class TypeAgreement:
    """某一类型的致性结果（论文 Table 2 的一行）。"""

    unit_family: str          # entity / relation / attribute
    type_name: str            # 实体类型码 / 关系名 / 属性名
    n_units: int
    p_o: float | None
    kappa: float | None
    ci_low: float | None
    ci_high: float | None
    pi: float | None
    bi: float | None
    fce_se: float | None
    fce_ci_low: float | None
    fce_ci_high: float | None
    alpha: float | None
    alpha_ci_low: float | None
    alpha_ci_high: float | None
    weighted_kappa: float | None
    weighted_kappa_linear: float | None
    scott_pi: float | None
    estimator: str
    note: str = ""


def _entity_type_pairs(records: Sequence[tuple[Annotation | None, Annotation | None]],
                        type_code: str) -> list[tuple[str, str]]:
    """按实体类型抽取 (A 标签, B 标签) 配对；未标注记为 ∅。"""
    pairs: list[tuple[str, str]] = []
    for ra, rb in records:
        # 逐单元比较该类型的标注集合
        sa = _entities_by_type(ra, type_code)
        sb = _entities_by_type(rb, type_code)
        keys_a = sorted(e.strict_key for e in sa)
        keys_b = sorted(e.strict_key for e in sb)
        if not keys_a and not keys_b:
            continue
        # 以较短的一侧为基线，逐个配对；多出的一侧记 ∅
        n = max(len(keys_a), len(keys_b))
        for i in range(n):
            a = _type_label(sa, keys_a, i, type_code)
            b = _type_label(sb, keys_b, i, type_code)
            pairs.append((a, b))
    return pairs


def _entities_by_type(ann: Annotation | None, type_code: str) -> list[Entity]:
    if ann is None:
        return []
    return sorted((e for e in ann.entities if e.type == type_code),
                  key=lambda e: (e.char_start, e.char_end, e.canonical_id))


def _type_label(entities: Sequence[Entity], keys: Sequence[tuple[int, int, str]],
                i: int, type_code: str) -> str:
    """返回第 i 个标注的标签字符串；缺失时为 ∅。"""
    if i >= len(keys):
        return NONE_LABEL
    s, e, _ = keys[i]
    return "%s@%d-%d" % (type_code, s, e)


def entity_agreement_by_type(records, schema: Schema,
                             b: int, seed: int) -> list[TypeAgreement]:
    """按实体类型计算一致性（论文 Table 2 上半部）。"""
    out: list[TypeAgreement] = []
    for code in schema.entity_codes:
        pairs = _entity_type_pairs(records, code)
        labels = sorted({NONE_LABEL} | {x for p in pairs for x in p})
        cm: dict[tuple[str, str], int] = {}
        for x, y in pairs:
            cm[(x, y)] = cm.get((x, y), 0) + 1
        po = observed_agreement(cm, labels) if pairs else None
        kap = cohen_kappa(cm, labels) if pairs else None
        lo, hi = bootstrap_ci_kappa(pairs, labels, b=b, seed=seed) if pairs else (None, None)
        se = fleiss_cohen_everitt_se(cm, labels) if pairs else None
        fce_lo = fce_hi = None
        if se is not None:
            fce_lo, fce_hi = kap - 1.959963985 * se, kap + 1.959963985 * se
        pi, bi = prevalence_and_bias(cm, labels) if pairs else (None, None)
        spi = scott_pi(cm, labels) if pairs else None
        out.append(TypeAgreement(
            unit_family="entity", type_name=code, n_units=len(pairs),
            p_o=po, kappa=kap, ci_low=lo, ci_high=hi, pi=pi, bi=bi,
            fce_se=se, fce_ci_low=fce_lo, fce_ci_high=fce_hi,
            alpha=None, alpha_ci_low=None, alpha_ci_high=None,
            weighted_kappa=None, weighted_kappa_linear=None,
            scott_pi=spi,
            estimator="Cohen's kappa",
            note="" if pairs else "该类型在本批数据中无标注单元"))
    return out


def relation_agreement_by_type(records, schema: Schema,
                               b: int, seed: int) -> list[TypeAgreement]:
    """按关系类型计算一致性（论文 Table 2 中部）。

    关系以「单元 + 关系类型」为比较单位：在同一单元内，
    取 head/tail 的 span 键排序后与另一方对齐；数量不等时多出者记 ∅。
    """
    out: list[TypeAgreement] = []
    for rname in schema.relation_names:
        pairs: list[tuple[str, str]] = []
        for ra, rb in records:
            la = sorted(_relation_labels(ra, rname))
            lb = sorted(_relation_labels(rb, rname))
            if not la and not lb:
                continue
            for i in range(max(len(la), len(lb))):
                pairs.append((la[i] if i < len(la) else NONE_LABEL,
                              lb[i] if i < len(lb) else NONE_LABEL))
        labels = sorted({NONE_LABEL} | {x for p in pairs for x in p})
        cm: dict[tuple[str, str], int] = {}
        for x, y in pairs:
            cm[(x, y)] = cm.get((x, y), 0) + 1
        po = observed_agreement(cm, labels) if pairs else None
        kap = cohen_kappa(cm, labels) if pairs else None
        lo, hi = bootstrap_ci_kappa(pairs, labels, b=b, seed=seed) if pairs else (None, None)
        se = fleiss_cohen_everitt_se(cm, labels) if pairs else None
        fce_lo = fce_hi = None
        if se is not None and kap is not None:
            fce_lo, fce_hi = kap - 1.959963985 * se, kap + 1.959963985 * se
        pi, bi = prevalence_and_bias(cm, labels) if pairs else (None, None)
        spi = scott_pi(cm, labels) if pairs else None
        out.append(TypeAgreement(
            unit_family="relation", type_name=rname, n_units=len(pairs),
            p_o=po, kappa=kap, ci_low=lo, ci_high=hi, pi=pi, bi=bi,
            fce_se=se, fce_ci_low=fce_lo, fce_ci_high=fce_hi,
            alpha=None, alpha_ci_low=None, alpha_ci_high=None,
            weighted_kappa=None, weighted_kappa_linear=None,
            scott_pi=spi,
            estimator="Cohen's kappa",
            note="" if pairs else "该关系类型在本批数据中无标注单元"))
    return out


def _relation_labels(ann: Annotation | None, rname: str) -> list[str]:
    if ann is None:
        return []
    out = []
    for r in ann.relations:
        if r.relation_type != rname:
            continue
        h = r.head.strict_key
        t = r.tail.strict_key
        hs = "%s:%s" % (h[0], "-".join(str(x) for x in h[1:])) if h[0] == "entity" \
            else "couplet:%s" % h[1]
        ts = "%s:%s" % (t[0], "-".join(str(x) for x in t[1:])) if t[0] == "entity" \
            else "couplet:%s" % t[1]
        out.append("%s|%s->%s" % (rname, hs, ts))
    return out


def attribute_agreement_by_type(records, schema: Schema,
                               b: int, seed: int) -> list[TypeAgreement]:
    """按属性类型计算一致性（论文 Table 2 下半部）。

    * 名义属性（联类）：Cohen's κ；
    * 有序属性（品第、时代层级）：以**二次权重**加权 κ 为主，线性权重作敏感性检查，
      同时给出 Krippendorff's α（ordinal）。
    """
    out: list[TypeAgreement] = []
    for aname in schema.attribute_names:
        levels = schema.attribute_values(aname)
        measurement = schema.attribute_measurement(aname)
        pairs: list[tuple[str, str]] = []
        reliability: list[list[Any]] = []
        for ra, rb in records:
            va = (ra.attributes.get(aname) if ra else None)
            vb = (rb.attributes.get(aname) if rb else None)
            if va is None and vb is None:
                continue
            pairs.append((va if va is not None else NONE_LABEL,
                          vb if vb is not None else NONE_LABEL))
            reliability.append([va, vb])
        labels = sorted({NONE_LABEL} | {x for p in pairs for x in p})
        cm: dict[tuple[str, str], int] = {}
        for x, y in pairs:
            cm[(x, y)] = cm.get((x, y), 0) + 1
        po = observed_agreement(cm, labels) if pairs else None
        kap = cohen_kappa(cm, labels) if pairs else None
        lo, hi = bootstrap_ci_kappa(pairs, labels, b=b, seed=seed) if pairs else (None, None)
        se = fleiss_cohen_everitt_se(cm, labels) if pairs else None
        fce_lo = fce_hi = None
        if se is not None and kap is not None:
            fce_lo, fce_hi = kap - 1.959963985 * se, kap + 1.959963985 * se
        pi, bi = prevalence_and_bias(cm, labels) if pairs else (None, None)

        wq = wl = None
        alpha = alpha_lo = alpha_hi = None
        estimator = "Cohen's kappa"
        note = ""
        if measurement == "ordinal" and levels:
            # 加权 κ 的标签空间用真实等级序（不含 ∅）
            wlabels = [l for l in levels]
            wcm = {k: v for k, v in cm.items()
                   if k[0] in wlabels and k[1] in wlabels}
            wq = weighted_kappa(wcm, wlabels, "quadratic")
            wl = weighted_kappa(wcm, wlabels, "linear")
            alpha = krippendorff_alpha_ordinal(reliability, levels)
            alpha_lo, alpha_hi = bootstrap_ci_alpha(
                reliability, "ordinal", levels, b=b, seed=seed)
            estimator = "weighted kappa (quadratic, primary)"
            note = "有序变量：主指标为二次权重加权 κ，另报线性权重与 ordinal α"
        out.append(TypeAgreement(
            unit_family="attribute", type_name=aname, n_units=len(pairs),
            p_o=po, kappa=kap, ci_low=lo, ci_high=hi, pi=pi, bi=bi,
            fce_se=se, fce_ci_low=fce_lo, fce_ci_high=fce_hi,
            alpha=alpha, alpha_ci_low=alpha_lo, alpha_ci_high=alpha_hi,
            weighted_kappa=wq, weighted_kappa_linear=wl,
            scott_pi=scott_pi(cm, labels) if pairs else None,
            estimator=estimator,
            note=note if pairs else "该属性在本批数据中无标注单元"))
    return out


# ---------------------------------------------------------------------------
# 与金标准 / 基线的对比
# ---------------------------------------------------------------------------

def entity_f1_by_type(gold: list[Annotation], pred: list[Annotation],
                      schema: Schema, mode: str = "strict"
                      ) -> list[dict[str, Any]]:
    """按实体类型计算 P/R/F1（严格或宽松口径）。"""
    ig, ip = index_by_unit(gold), index_by_unit(pred)
    keys = sorted(set(ig) | set(ip))
    agg: dict[str, dict[str, float]] = {}
    for k in keys:
        g = ig.get(k)
        p = ip.get(k)
        for code in schema.entity_codes:
            ge = _entities_by_type(g, code)
            pe = _entities_by_type(p, code)
            tp, fp, fn, _ = match_entities(ge, pe, mode=mode)
            row = agg.setdefault(code, {"tp": 0, "fp": 0, "fn": 0})
            row["tp"] += tp
            row["fp"] += fp
            row["fn"] += fn
    out = []
    for code in schema.entity_codes:
        row = agg.get(code, {"tp": 0, "fp": 0, "fn": 0})
        pr, rc, f1 = prf(int(row["tp"]), int(row["fp"]), int(row["fn"]))
        out.append({"type": code, "label": schema.entity_labels.get(code, code),
                    "tp": int(row["tp"]), "fp": int(row["fp"]), "fn": int(row["fn"]),
                    "precision": pr, "recall": rc, "f1": f1, "mode": mode})
    return out


def relation_f1_by_type(gold: list[Annotation], pred: list[Annotation],
                        schema: Schema, mode: str = "strict"
                        ) -> list[dict[str, Any]]:
    """按关系类型计算三元组 P/R/F1。"""
    ig, ip = index_by_unit(gold), index_by_unit(pred)
    keys = sorted(set(ig) | set(ip))
    agg: dict[str, dict[str, float]] = {}
    for k in keys:
        g, p = ig.get(k), ip.get(k)
        for rname in schema.relation_names:
            gr = [r for r in (g.relations if g else []) if r.relation_type == rname]
            pr_ = [r for r in (p.relations if p else []) if r.relation_type == rname]
            tp, fp, fn = match_relations(gr, pr_, mode=mode)
            row = agg.setdefault(rname, {"tp": 0, "fp": 0, "fn": 0})
            row["tp"] += tp
            row["fp"] += fp
            row["fn"] += fn
    out = []
    for rname in schema.relation_names:
        row = agg.get(rname, {"tp": 0, "fp": 0, "fn": 0})
        pr, rc, f1 = prf(int(row["tp"]), int(row["fp"]), int(row["fn"]))
        out.append({"type": rname, "tp": int(row["tp"]), "fp": int(row["fp"]),
                    "fn": int(row["fn"]), "precision": pr, "recall": rc,
                    "f1": f1, "mode": mode})
    return out


def seqeval_report(gold: list[Annotation], pred: list[Annotation]
                   ) -> dict[str, float]:
    """seqeval 风格的整体 conformance（IOB2 展开后按实体计数）。"""
    ig, ip = index_by_unit(gold), index_by_unit(pred)
    keys = sorted(set(ig) | set(ip))
    g_seqs, p_seqs = [], []
    for k in keys:
        g, p = ig.get(k), ip.get(k)
        length = max((g.chars or 0) if g else 0, (p.chars or 0) if p else 0)
        if length <= 0:
            length = max([e.char_end for e in (g.entities if g else [])] +
                         [e.char_end for e in (p.entities if p else [])] + [0])
        g_seqs.append(entities_to_iob(g.entities if g else [], length))
        p_seqs.append(entities_to_iob(p.entities if p else [], length))
    return seqeval_conformance(g_seqs, p_seqs)


# ---------------------------------------------------------------------------
# 错误分析
# ---------------------------------------------------------------------------

def error_analysis(records, schema: Schema) -> dict[str, Any]:
    """错误分类计数与 top-10 混淆对。

    返回：
      * ``counts``：受控词表下各错误类型的计数（实体 + 关系 + 属性合并）；
      * ``by_family``：按单元族分开的计数；
      * ``top_confusions``：出现次数最多的 10 组混淆（实体按类型对，关系按关系名对）。
    """
    codes = schema.error_codes()
    counts = Counter({c: 0 for c in codes})
    by_family = {"entity": Counter({c: 0 for c in codes}),
                 "relation": Counter({c: 0 for c in codes}),
                 "attribute": Counter({c: 0 for c in codes})}
    confusions: Counter = Counter()

    for ra, rb in records:
        # --- 实体 ---
        # 分征口径（与 schema.yaml 的判定顺序一致）：
        #   1) 先用宽松口径（跨度重叠）配对，以捕获边界分歧与规范名分歧；
        #   2) 未配对与类型错配的一方计为漏标；
        #   3) 同跨度但类型不同者单独计为类型混淆。
        for code in schema.entity_codes:
            ga = _entities_by_type(ra, code)
            gb = _entities_by_type(rb, code)
            _, _, _, relaxed_pairs = match_entities(ga, gb, mode="relaxed")
            used_a = {id(g) for g, _ in relaxed_pairs}
            used_b = {id(p) for _, p in relaxed_pairs}
            for g, p in relaxed_pairs:
                if g.span != p.span:
                    # 边界分歧（优先级最高）
                    cls = classify_entity_error(g, p, codes)
                elif g.canonical_id != p.canonical_id:
                    # 跨度一致，规范名不一致
                    cls = classify_entity_error(g, p, codes)
                else:
                    continue
                counts[cls] += 1
                by_family["entity"][cls] += 1
            # 未配对：任一方未被宽松口径匹配到
            for _ in [e for e in ga if id(e) not in used_a]:
                counts["漏标"] += 1
                by_family["entity"]["漏标"] += 1
            for _ in [e for e in gb if id(e) not in used_b]:
                counts["漏标"] += 1
                by_family["entity"]["漏标"] += 1
        # 类型混淆：同跨度但类型不同（全层只统计一次）
        sa = {(e.char_start, e.char_end): e.type for e in (ra.entities if ra else [])}
        sb = {(e.char_start, e.char_end): e.type for e in (rb.entities if rb else [])}
        for span, ta in sorted(sa.items()):
            tb = sb.get(span)
            if tb is not None and ta != tb:
                counts["类型混淆"] += 1
                by_family["entity"]["类型混淆"] += 1
                confusions[("实体类型", ta, tb)] += 1

        # --- 关系 ---
        for rname in schema.relation_names:
            la = _relation_labels(ra, rname)
            lb = _relation_labels(rb, rname)
            for i in range(max(len(la), len(lb))):
                a = la[i] if i < len(la) else None
                b = lb[i] if i < len(lb) else None
                if a is None or b is None:
                    cls = "漏标"
                    counts[cls] += 1
                    by_family["relation"][cls] += 1
                    continue
                if a != b:
                    cls = classify_relation_error(
                        _rel_from_label(a), _rel_from_label(b), codes)
                    counts[cls] += 1
                    by_family["relation"][cls] += 1
                    confusions[("关系类型", rname, rname)] += 1

        # --- 属性 ---
        for aname in schema.attribute_names:
            va = ra.attributes.get(aname) if ra else None
            vb = rb.attributes.get(aname) if rb else None
            if va is None and vb is None:
                continue
            cls = classify_attribute_error(va, vb, codes)
            if cls:
                counts[cls] += 1
                by_family["attribute"][cls] += 1
                confusions[("属性", aname, aname)] += 1

    return {
        "counts": {c: counts.get(c, 0) for c in codes},
        "by_family": {f: {c: by_family[f].get(c, 0) for c in codes}
                      for f in by_family},
        "top_confusions": [
            {"kind": k[0], "a": k[1], "b": k[2], "count": v}
            for k, v in sorted(confusions.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        ],
    }


_REL_LABEL_RE = re.compile(r"^(?P<rname>[^|]+)\|(?P<head>[^>]+)->(?P<tail>.+)$")


def _rel_from_label(label: str) -> Relation:
    """从 ``关系名|head->tail`` 的标签反解出一个 Relation（供错误归类用）。"""
    m = _REL_LABEL_RE.match(label)
    if not m:
        return Relation(Endpoint("entity", (0, 0), "?", label), "?", Endpoint("entity", (0, 0), "?", label))
    rname = m.group("rname")

    def parse(tok: str) -> Endpoint:
        if tok.startswith("couplet:"):
            return Endpoint(kind="couplet", couplet_id=tok.split(":", 1)[1])
        parts = tok.split(":")
        kind = parts[0]
        nums = parts[1].split("-")
        span = (int(nums[0]), int(nums[1]))
        tcode = nums[2] if len(nums) > 2 else "?"
        return Endpoint(kind="entity", span=span, type=tcode, canonical_id=tcode)

    return Relation(parse(m.group("head")), rname, parse(m.group("tail")))


# ---------------------------------------------------------------------------
# 工时分析
# ---------------------------------------------------------------------------

def timing_analysis(anns: Sequence[Annotation]) -> dict[str, Any]:
    """每 1000 字符的中位耗时（分钟）及 IQR；按 condition 分组。"""
    groups: dict[str, list[float]] = defaultdict(list)
    for a in anns:
        if a.elapsed_minutes is None or not a.chars:
            continue
        rate = a.elapsed_minutes / (a.chars / 1000.0)
        groups[a.condition or "unspecified"].append(rate)
    out: dict[str, Any] = {}
    for cond, vals in sorted(groups.items()):
        stats = median_iqr(vals)
        out[cond] = stats
    return out


def paired_timing_test(treatment: Sequence[Annotation],
                       baseline: Sequence[Annotation]) -> dict[str, Any]:
    """两种标注条件的配对工时比较（Wilcoxon 符号秩检验）。"""
    it = index_by_unit(treatment)
    ib = index_by_unit(baseline)
    keys = sorted(set(it) & set(ib))
    a_vals, b_vals = [], []
    for k in keys:
        ta, tb = it[k], ib[k]
        if ta.elapsed_minutes is None or tb.elapsed_minutes is None:
            continue
        if not ta.chars or not tb.chars:
            continue
        a_vals.append(ta.elapsed_minutes / (ta.chars / 1000.0))
        b_vals.append(tb.elapsed_minutes / (tb.chars / 1000.0))
    res = wilcoxon_signed_rank(a_vals, b_vals)
    res["treatment_median"] = median_iqr(a_vals)["median"]
    res["baseline_median"] = median_iqr(b_vals)["median"]
    res["treatment_iqr"] = median_iqr(a_vals)["iqr"]
    res["baseline_iqr"] = median_iqr(b_vals)["iqr"]
    res["confound"] = ("标注者存在学习效应；两种条件的先后顺序采用拉丁方式反平衡，"
                       "但该混杂无法完全消除。")
    return res


# ---------------------------------------------------------------------------
# 分歧案例（8 条）
# ---------------------------------------------------------------------------

def collect_disagreement_cases(records, schema: Schema, limit: int = 8
                               ) -> list[dict[str, Any]]:
    """收集标注者分歧案例，按严重度排序后取前 ``limit`` 条。

    严重度 = 该处分歧是否同时造成「跨度」「类型」「规范名」三者全不同。
    """
    cases: list[dict[str, Any]] = []
    for ra, rb in records:
        if ra is None or rb is None:
            continue
        for code in schema.entity_codes:
            ga = _entities_by_type(ra, code)
            gb = _entities_by_type(rb, code)
            tp, fp, fn, pairs = match_entities(ga, gb, mode="relaxed")
            for g, p in pairs:
                if g.strict_key == p.strict_key and g.canonical_id == p.canonical_id:
                    continue
                sev = 0
                if g.span != p.span:
                    sev += 1
                if g.type != p.type:
                    sev += 1
                if g.canonical_id != p.canonical_id:
                    sev += 1
                cases.append({
                    "unit_id": ra.unit_id,
                    "family": "entity",
                    "type": code,
                    "severity": sev,
                    "a": {"char_start": g.char_start, "char_end": g.char_end,
                          "type": g.type, "canonical_id": g.canonical_id,
                          "text": g.text},
                    "b": {"char_start": p.char_start, "char_end": p.char_end,
                          "type": p.type, "canonical_id": p.canonical_id,
                          "text": p.text},
                    "adjudication": "",
                    "rule": "",
                })
        for rname in schema.relation_names:
            la = _relation_labels(ra, rname)
            lb = _relation_labels(rb, rname)
            for i in range(min(len(la), len(lb))):
                if la[i] != lb[i]:
                    cases.append({
                        "unit_id": ra.unit_id, "family": "relation",
                        "type": rname, "severity": 2,
                        "a": {"label": la[i]}, "b": {"label": lb[i]},
                        "adjudication": "", "rule": "",
                    })
    cases.sort(key=lambda c: (-c["severity"], c["unit_id"], c["type"]))
    return cases[:limit]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _fmt_ci(lo: Any, hi: Any) -> str:
    if lo is None or hi is None:
        return ""
    return "[%s, %s]" % (_fmt(lo), _fmt(hi))


def build_summary_md(schema: Schema, tables: dict[str, Any]) -> str:
    """生成 reports/SUMMARY.md（与论文 Table 2–4 一一对应）。"""
    lines: list[str] = []
    lines.append("# 《楹联丛话全编》标注一致性度量报告")
    lines.append("")
    lines.append("> 由 `agreement.py` 自动生成；本文件是论文 Table 2–4 的**唯一数值来源**。")
    lines.append("> schema 版本：%s；度量版本：%s" % (
        schema.raw.get("meta", {}).get("schema_version"),
        schema.raw.get("meta", {}).get("metrics_version")))
    lines.append("")
    lines.append("## T2 各类型一致性（κ / p_o / PI / BI / 95%CI）")
    lines.append("")
    lines.append("对应文件：`kappa_by_type.csv`、`kappa_by_type_canonical.csv`、`ci.json`")
    lines.append("")
    lines.append("| 单元族 | 类型 | n | p_o | κ | 95%CI (bootstrap) | PI | BI | "
                 "FCE SE | FCE 95%CI | α | Scott's Pi | 估计量 |")
    lines.append("|---|---|---:|---:|---:|---|---:|---:|---:|---|---:|---:|---|")
    for row in tables["agreement"]:
        lines.append("| %s | %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            row["unit_family"], row["type_name"], row["n_units"],
            _fmt(row["p_o"]), _fmt(row["kappa"]), _fmt_ci(row["ci_low"], row["ci_high"]),
            _fmt(row["pi"]), _fmt(row["bi"]), _fmt(row["fce_se"]),
            _fmt_ci(row["fce_ci_low"], row["fce_ci_high"]),
            _fmt(row["alpha"]), _fmt(row.get("scott_pi")),
            row["estimator"]))
    lines.append("")
    lines.append("## T3 与基线的对比（F1、工时、显著性）")
    lines.append("")
    lines.append("对应文件：`f1_by_type.csv`、`relation_f1.csv`、`timing.csv`、"
                 "`significance.csv`")
    lines.append("")
    lines.append("### 实体抽取 F1（strict / relaxed）")
    lines.append("")
    lines.append("| 类型 | 口径 | P | R | F1 | TP | FP | FN |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for row in tables["f1"]:
        lines.append("| %s | %s | %s | %s | %s | %d | %d | %d |" % (
            row["label"], row["mode"], _fmt(row["precision"]), _fmt(row["recall"]),
            _fmt(row["f1"]), row["tp"], row["fp"], row["fn"]))
    lines.append("")
    lines.append("### 关系抽取 F1")
    lines.append("")
    lines.append("| 关系 | 口径 | P | R | F1 | TP | FP | FN |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for row in tables["relation_f1"]:
        lines.append("| %s | %s | %s | %s | %s | %d | %d | %d |" % (
            row["type"], row["mode"], _fmt(row["precision"]), _fmt(row["recall"]),
            _fmt(row["f1"]), row["tp"], row["fp"], row["fn"]))
    lines.append("")
    lines.append("### 工时（每 1000 字符分钟数）")
    lines.append("")
    lines.append("| 条件 | 中位数 | Q1 | Q3 | IQR | n |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cond, st in sorted(tables["timing"].items()):
        lines.append("| %s | %s | %s | %s | %s | %d |" % (
            cond, _fmt(st["median"]), _fmt(st["q1"]), _fmt(st["q3"]),
            _fmt(st["iqr"]), st["n"]))
    lines.append("")
    if tables.get("paired_timing"):
        pt = tables["paired_timing"]
        lines.append("配对 Wilcoxon 符号秩检验：W = %s，p = %s（精确 p = %s），"
                     "Cliff's delta = %s，matched-pairs rank-biserial r = %s，"
                     "n = %d 对。" % (
                         _fmt(pt.get("statistic"), 2), _fmt(pt.get("p_value")),
                         _fmt(pt.get("p_value_exact")), _fmt(pt.get("cliffs_delta")),
                         _fmt(pt.get("rank_biserial_r")), pt.get("n_pairs", 0)))
        lines.append("")
        lines.append("> 混杂说明：%s" % pt.get("confound", ""))
        lines.append("")
    lines.append("## T4 错误类型分布")
    lines.append("")
    lines.append("对应文件：`error_taxonomy.csv`、`confusion_matrices/`")
    lines.append("")
    lines.append("| 错误类型 | 合计 | 实体 | 关系 | 属性 |")
    lines.append("|---|---:|---:|---:|---:|")
    for code, total in tables["error_counts"]["counts"].items():
        fam = tables["error_counts"]["by_family"]
        lines.append("| %s | %d | %d | %d | %d |" % (
            code, total, fam["entity"].get(code, 0), fam["relation"].get(code, 0),
            fam["attribute"].get(code, 0)))
    lines.append("")
    lines.append("### Top-10 混淆对")
    lines.append("")
    lines.append("| 类别 | A | B | 次数 |")
    lines.append("|---|---|---|---:|")
    for c in tables["error_counts"]["top_confusions"]:
        lines.append("| %s | %s | %s | %d |" % (c["kind"], c["a"], c["b"], c["count"]))
    lines.append("")
    return "\n".join(lines) + "\n"


def write_confusion_matrices(outdir: Path, records, schema: Schema) -> list[str]:
    """写出每个类型与每个关系的混淆矩阵 CSV。"""
    cm_dir = outdir / "confusion_matrices"
    cm_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for code in schema.entity_codes:
        pairs = _entity_type_pairs(records, code)
        if not pairs:
            continue
        labels = sorted({NONE_LABEL} | {x for p in pairs for x in p})
        cm: dict[tuple[str, str], int] = {}
        for x, y in pairs:
            cm[(x, y)] = cm.get((x, y), 0) + 1
        name = "entity_%s.csv" % _safe_name(code)
        write_csv(cm_dir / name, ["A\\B"] + labels,
                  [[a] + [cm.get((a, b), 0) for b in labels] for a in labels])
        written.append("confusion_matrices/" + name)
    for rname in schema.relation_names:
        pairs = []
        for ra, rb in records:
            la = sorted(_relation_labels(ra, rname))
            lb = sorted(_relation_labels(rb, rname))
            if not la and not lb:
                continue
            for i in range(max(len(la), len(lb))):
                pairs.append((la[i] if i < len(la) else NONE_LABEL,
                              lb[i] if i < len(lb) else NONE_LABEL))
        if not pairs:
            continue
        labels = sorted({NONE_LABEL} | {x for p in pairs for x in p})
        cm = {}
        for x, y in pairs:
            cm[(x, y)] = cm.get((x, y), 0) + 1
        name = "relation_%s.csv" % _safe_name(rname)
        write_csv(cm_dir / name, ["A\\B"] + labels,
                  [[a] + [cm.get((a, b), 0) for b in labels] for a in labels])
        written.append("confusion_matrices/" + name)
    return written


def _safe_name(text: str) -> str:
    """把类型名转为安全的文件名片段。"""
    out = re.sub(r"[^0-9A-Za-z一-鿿]+", "_", text).strip("_")
    return out or "x"


def _agreement_rows_to_dicts(rows: Sequence[TypeAgreement]) -> list[dict[str, Any]]:
    return [
        {
            "unit_family": r.unit_family, "type_name": r.type_name, "n_units": r.n_units,
            "p_o": r.p_o, "kappa": r.kappa,
            "ci_low": r.ci_low, "ci_high": r.ci_high,
            "pi": r.pi, "bi": r.bi,
            "fce_se": r.fce_se, "fce_ci_low": r.fce_ci_low, "fce_ci_high": r.fce_ci_high,
            "alpha": r.alpha, "alpha_ci_low": r.alpha_ci_low, "alpha_ci_high": r.alpha_ci_high,
            "weighted_kappa_quadratic": r.weighted_kappa,
            "weighted_kappa_linear": r.weighted_kappa_linear,
            "scott_pi": r.scott_pi,
            "estimator": r.estimator, "note": r.note,
        } for r in rows
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="《楹联丛话全编》语义标注一致性度量")
    parser.add_argument("--gold", required=True, type=Path,
                        help="金标准标注文件（JSONL）")
    parser.add_argument("--ann", required=True, type=str,
                        help="标注者文件，逗号分隔（如 ann_a.jsonl,ann_b.jsonl）")
    parser.add_argument("--config", required=True, type=Path,
                        help="schema.yaml 路径")
    parser.add_argument("--out", required=True, type=Path,
                        help="报告输出目录")
    parser.add_argument("--baseline", type=Path, default=None,
                        help="基线系统输出（JSONL），用于 T3 对比")
    parser.add_argument("--cases", type=Path, default=None,
                        help="已仲裁的分歧案例（JSON），含 8 条样例")
    parser.add_argument("--units", type=str, default="entity,relation,attribute",
                        help="要计算的单元族，逗号分隔")
    parser.add_argument("--no-f1", action="store_true",
                        help="跳过 F1 与显著性计算")
    parser.add_argument("--seed", type=int, default=None,
                        help="覆盖 schema.yaml 中的自助法随机种子")
    args = parser.parse_args(argv)

    schema = load_schema(args.config)
    seed = args.seed if args.seed is not None else schema.bootstrap_seed
    b = schema.bootstrap_b
    families = [f.strip() for f in args.units.split(",") if f.strip()]

    ann_paths = [Path(p.strip()) for p in args.ann.split(",") if p.strip()]
    if len(ann_paths) < 2:
        parser.error("--ann 至少需要两个标注者文件")
    anns = [load_annotations(p) for p in ann_paths]
    gold = load_annotations(args.gold)

    outdir = args.out
    outdir.mkdir(parents=True, exist_ok=True)

    # --- 标注者之间的一致性 -------------------------------------------
    records = pair_records(anns[0], anns[1])
    agreement_rows: list[TypeAgreement] = []
    if "entity" in families:
        agreement_rows += entity_agreement_by_type(records, schema, b, seed)
    if "relation" in families:
        agreement_rows += relation_agreement_by_type(records, schema, b, seed)
    if "attribute" in families:
        agreement_rows += attribute_agreement_by_type(records, schema, b, seed)

    # --- 规范名（实体链接口径）的一致性 --------------------------------
    canonical_rows = _canonical_agreement_by_type(records, schema, b, seed)

    # --- 与金标准 / 基线的对比 -----------------------------------------
    f1_rows: list[dict[str, Any]] = []
    rel_f1_rows: list[dict[str, Any]] = []
    significance: list[dict[str, Any]] = []
    if not args.no_f1:
        for mode in ("strict", "relaxed"):
            f1_rows += entity_f1_by_type(gold, anns[0], schema, mode=mode)
        rel_f1_rows += relation_f1_by_type(gold, anns[0], schema, mode="strict")
        rel_f1_rows += relation_f1_by_type(gold, anns[0], schema, mode="relaxed")
        # 配对自助法：标注者 A 与金标准（逐单元 F1 差）
        sig = _paired_f1_significance(gold, anns[0], schema, b=schema.paired_bootstrap_b,
                                      seed=seed, label="gold_vs_annotator_A")
        if sig:
            significance.append(sig)
        if args.baseline:
            base = load_annotations(args.baseline)
            sig_b = _paired_f1_significance(base, anns[0], schema,
                                            b=schema.paired_bootstrap_b, seed=seed,
                                            label="baseline_vs_annotator_A")
            if sig_b:
                significance.append(sig_b)

    # --- 工时 ----------------------------------------------------------
    timing = timing_analysis(anns[0])
    paired_timing = None
    if args.baseline:
        base = load_annotations(args.baseline)
        timing = {**timing_analysis(base), **timing}
        paired_timing = paired_timing_test(anns[0], base)

    # --- 错误分析 ------------------------------------------------------
    err = error_analysis(records, schema)

    # --- 分歧案例 ------------------------------------------------------
    cases: list[dict[str, Any]] = []
    if args.cases and args.cases.exists():
        with open(args.cases, "r", encoding="utf-8") as fh:
            cases = json.load(fh)
    else:
        cases = collect_disagreement_cases(records, schema, limit=8)

    # --- 写文件 --------------------------------------------------------
    rows = _agreement_rows_to_dicts(agreement_rows)
    write_csv(outdir / "kappa_by_type.csv",
              ["unit_family", "type_name", "n_units", "p_o", "kappa",
               "ci_low", "ci_high", "pi", "bi", "fce_se", "fce_ci_low",
               "fce_ci_high", "alpha", "alpha_ci_low", "alpha_ci_high",
               "weighted_kappa_quadratic", "weighted_kappa_linear",
               "scott_pi", "estimator", "note"],
              [[r[k] for k in rows[0]] for r in rows] if rows else [])
    write_csv(outdir / "kappa_by_type_canonical.csv",
              ["unit_family", "type_name", "n_units", "p_o", "kappa",
               "ci_low", "ci_high", "pi", "bi", "estimator", "note"],
              [[r[k] for k in canonical_rows[0]] for r in canonical_rows]
              if canonical_rows else [])
    write_csv(outdir / "f1_by_type.csv",
              ["type", "label", "mode", "tp", "fp", "fn",
               "precision", "recall", "f1"],
              [[r["type"], r["label"], r["mode"], r["tp"], r["fp"], r["fn"],
                r["precision"], r["recall"], r["f1"]] for r in f1_rows])
    write_csv(outdir / "relation_f1.csv",
              ["type", "mode", "tp", "fp", "fn", "precision", "recall", "f1"],
              [[r["type"], r["mode"], r["tp"], r["fp"], r["fn"],
                r["precision"], r["recall"], r["f1"]] for r in rel_f1_rows])
    write_csv(outdir / "timing.csv",
              ["condition", "n", "median_min_per_1k_chars", "q1", "q3", "iqr"],
              [[c, st["n"], st["median"], st["q1"], st["q3"], st["iqr"]]
               for c, st in sorted(timing.items())])
    write_csv(outdir / "significance.csv",
              ["comparison", "metric", "n_pairs", "mean_diff", "ci_low",
               "ci_high", "p_value", "method"],
              [[s.get("comparison"), s.get("metric"), s.get("n_pairs"),
                s.get("mean_diff"), s.get("ci_low"), s.get("ci_high"),
                s.get("p_value"), s.get("method")] for s in significance])
    write_csv(outdir / "error_taxonomy.csv",
              ["error_code", "total", "entity", "relation", "attribute"],
              [[c, err["counts"][c], err["by_family"]["entity"].get(c, 0),
                err["by_family"]["relation"].get(c, 0),
                err["by_family"]["attribute"].get(c, 0)]
               for c in schema.error_codes()])
    write_json(outdir / "ci.json", {
        "seed": seed, "bootstrap_resamples": b,
        "agreement": rows, "canonical": canonical_rows,
        "timing": timing, "paired_timing": paired_timing,
        "significance": significance,
        "fce_citation": FCE_CITATION, "byrt_citation": BYRT_CITATION,
    })
    write_confusion_matrices(outdir, records, schema)
    (outdir / "disagreement_cases.md").write_text(
        _render_cases_md(cases), encoding="utf-8")

    tables = {
        "agreement": rows,
        "f1": f1_rows,
        "relation_f1": rel_f1_rows,
        "timing": timing,
        "paired_timing": paired_timing,
        "error_counts": err,
        "significance": significance,
    }
    (outdir / "SUMMARY.md").write_text(build_summary_md(schema, tables),
                                       encoding="utf-8")

    print("reports written to %s" % outdir)
    print("  kappa_by_type.csv (%d rows)" % len(rows))
    print("  kappa_by_type_canonical.csv (%d rows)" % len(canonical_rows))
    print("  f1_by_type.csv (%d rows), relation_f1.csv (%d rows)"
          % (len(f1_rows), len(rel_f1_rows)))
    print("  error_taxonomy.csv, confusion_matrices/, ci.json, SUMMARY.md")
    return 0


def _canonical_agreement_by_type(records, schema: Schema, b: int,
                                 seed: int) -> list[dict[str, Any]]:
    """实体链接口径的一致性（跨度相同但规范名是否一致）。

    对每个实体类型，取双方在该类型上的标注集合，
    以**跨度**对齐后比较 canonical_id；这与 span 口径正交，
    用来分离"边界检测"与"实体链接"两类能力。
    """
    out: list[dict[str, Any]] = []
    for code in schema.entity_codes:
        pairs: list[tuple[str, str]] = []
        for ra, rb in records:
            ga = _entities_by_type(ra, code)
            gb = _entities_by_type(rb, code)
            keys_a = [e.span for e in ga]
            keys_b = [e.span for e in gb]
            if not keys_a and not keys_b:
                continue
            for i in range(max(len(keys_a), len(keys_b))):
                a = ga[i].canonical_id if i < len(ga) else NONE_LABEL
                b_ = gb[i].canonical_id if i < len(gb) else NONE_LABEL
                pairs.append((a, b_))
        if not pairs:
            out.append({"unit_family": "entity", "type_name": code, "n_units": 0,
                        "p_o": None, "kappa": None, "ci_low": None, "ci_high": None,
                        "pi": None, "bi": None, "estimator": "Cohen's kappa",
                        "note": "该类型在本批数据中无标注单元"})
            continue
        labels = sorted({NONE_LABEL} | {x for p in pairs for x in p})
        cm: dict[tuple[str, str], int] = {}
        for x, y in pairs:
            cm[(x, y)] = cm.get((x, y), 0) + 1
        kap = cohen_kappa(cm, labels)
        lo, hi = bootstrap_ci_kappa(pairs, labels, b=b, seed=seed)
        pi, bi = prevalence_and_bias(cm, labels)
        out.append({"unit_family": "entity", "type_name": code, "n_units": len(pairs),
                    "p_o": observed_agreement(cm, labels), "kappa": kap,
                    "ci_low": lo, "ci_high": hi, "pi": pi, "bi": bi,
                    "estimator": "Cohen's kappa (canonical_id)",
                    "note": "链接口径：比较规范名而非跨度"})
    return out


def _paired_f1_significance(system: list[Annotation], annotator: list[Annotation],
                            schema: Schema, b: int, seed: int,
                            label: str = "system_vs_annotator"
                            ) -> dict[str, Any] | None:
    """逐单元 F1 的配对自助法比较（系统 vs 标注者）。

    严禁对 F1 使用非配对 t 检验：这里按单元重采样，两侧取同一单元。
    """
    isys, iann = index_by_unit(system), index_by_unit(annotator)
    keys = sorted(set(isys) & set(iann))
    if len(keys) < 2:
        return None
    sys_f1: list[float] = []
    ann_f1: list[float] = []
    for k in keys:
        s, a = isys[k], iann[k]
        for mode in ("strict",):
            ts, fs, ns, _ = match_entities(s.entities, a.entities, mode=mode)
            _, _, f_sys = prf(ts, fs, ns)
            ts2, fs2, ns2, _ = match_entities(a.entities, s.entities, mode=mode)
            _, _, f_ann = prf(ts2, fs2, ns2)
            sys_f1.append(f_sys)
            ann_f1.append(f_ann)
    res = paired_bootstrap_diff(sys_f1, ann_f1, b_resamples=b, seed=seed)
    res["comparison"] = label
    res["metric"] = "entity_strict_F1"
    return res


def _render_cases_md(cases: Sequence[dict[str, Any]]) -> str:
    """把分歧案例渲染为 Markdown（论文 §6.6 的 8 条样例来源）。"""
    lines = ["# 标注分歧案例（仲裁记录）", "",
             "> 每条给出双方标注、仲裁结论，以及一条可防止复发的规则。", ""]
    for i, c in enumerate(cases, 1):
        lines.append("## 案例 %d（unit_id = %s，类型 = %s）" % (
            i, c.get("unit_id", ""), c.get("type", "")))
        lines.append("")
        a, b = c.get("a", {}), c.get("b", {})
        lines.append("- 标注者 A：%s" % json.dumps(a, ensure_ascii=False))
        lines.append("- 标注者 B：%s" % json.dumps(b, ensure_ascii=False))
        lines.append("- 仲裁结论：%s" % (c.get("adjudication") or "（待补）"))
        lines.append("- 预防规则：%s" % (c.get("rule") or "（待补）"))
        lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
