# 《楹联丛话全编》语义标注一致性度量工具

本目录是《楹联丛话全编》语义标注工作的**可复现实验代码**，与论文
`research/MANUSCRIPT.md` 一一对应。

## 目录

| 路径 | 说明 |
|---|---|
| `agreement.py` | 一致性度量主程序（CLI），产出 `reports/` 全部文件 |
| `schema.yaml` | 标签集与单元定义的**唯一来源**（single source of truth） |
| `tests/test_agreement.py` | 单元测试（37 例），含与 `krippendorff` / `scipy` 的逐例对照 |
| `make_demo_fixtures.py` | 生成**合成演示夹具**（仅供冒烟测试，**不是**实验数据） |
| `examples/` | 合成演示夹具（`gold.jsonl` / `ann_a.jsonl` / `ann_b.jsonl` / `baseline.jsonl`） |
| `reports/` | 度量报告输出目录 |
| `numbers_map.md` | 论文表格单元格 → 报告文件的逐格映射 |
| `MANUSCRIPT.md` | 论文正文（Markdown）；§8 为单文件 TiddlyWiki 知识库部署一章 |
| `TABLES.md` | 论文表格 T1–T6（可直接粘贴） |

## 一条命令复现

```bash
cd research
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) 生成演示夹具（可选，仅用于验证链路是否跑通）
python make_demo_fixtures.py --out examples/ --seed 42

# 2) 运行度量
python agreement.py \
  --gold examples/gold.jsonl \
  --ann examples/ann_a.jsonl,examples/ann_b.jsonl \
  --config schema.yaml \
  --out reports/

# 3) 跑测试
python -m unittest discover -s tests -v
```

真实实验请把 `--gold/--ann/--baseline` 指向人工标注导出的 JSONL，
并把 `--out` 指向 `reports/`。

## 输入格式

JSONL，每行一个标注单元（详见 `agreement.py` 顶部文档字符串）：

```json
{"unit_id": "1.3.1", "annotator": "A", "chars": 186, "elapsed_minutes": 7.5,
 "entities": [{"char_start": 12, "char_end": 14, "type": "@",
               "canonical_id": "P:纪昀", "text": "纪文达"}],
 "relations": [{"relation_type": "撰联",
                "head": {"kind": "entity", "char_start": 12, "char_end": 14,
                         "type": "@", "canonical_id": "P:纪昀"},
                "tail": {"kind": "couplet", "couplet_id": "C0001"}}],
 "attributes": {"联类": "春联"}}
```

## 输出契约

```
reports/
├── kappa_by_type.csv            # T2：各类型 κ / p_o / PI / BI / 95%CI / FCE SE / α / 加权 κ / Scott's Pi
├── kappa_by_type_canonical.csv  # T2 附表：实体链接口径（规范名）的一致性
├── f1_by_type.csv               # T3：实体抽取 P/R/F1（strict 与 relaxed）
├── relation_f1.csv              # T3：关系抽取 P/R/F1（strict 与 relaxed）
├── timing.csv                   # T3：每 1000 字符的中位耗时与 IQR
├── significance.csv             # T3：配对自助法与 Wilcoxon 检验结果
├── error_taxonomy.csv           # T4：错误类型分布（受控词表）
├── confusion_matrices/          # T4：逐类型 / 逐关系的混淆矩阵
├── ci.json                      # 全部置信区间与统计量的机读版本
├── disagreement_cases.md        # 8 条分歧案例（仲裁记录）
└── SUMMARY.md                   # 与论文 Table 2–4 一一对应的汇总
```

## 确定性

* 自助法固定种子（`schema.yaml` → `metrics.bootstrap.seed`，默认 42）；
* 所有迭代按 key 排序；浮点求和用 `math.fsum`（对排序后的序列），不依赖字典插入顺序；
* `tests/test_agreement.py::TestDeterminism` 断言同一输入两次运行产出**逐字节一致**。

## 论文 §8：单文件 TiddlyWiki 知识库部署

本目录的度量代码对应论文 §5；论文 §8 描述的知识库部署由**仓库根目录**的脚本承担：

```bash
cd ..   # 仓库根目录
python3 scripts/annotate_yinglian.py       # 上游：生成标注产物
python3 scripts/lint_text_integrity.py     # 反演校验（只加标记、不改原文）
python3 scripts/export_tiddlywiki.py       # 导出为 tiddler 目录（11,985 个）
python3 scripts/build_tiddlywiki.py --tw /path/to/TiddlyWiki5   # 编译为单文件
python3 scripts/verify_tiddlywiki.py       # 独立校验（14 项，全部通过）
```

产物：`tiddlywiki/oblique.html`（11.70 MB，双击即开，无需服务器与网络）。
「导出 → 编译」链路可重建，且重建结果与提交版本**逐字节一致**。

## 许可

* 代码：MIT（与仓库根目录 `LICENSE` 一致）。
* `schema.yaml` 中的标注规范与标签集、数据集：**CC-BY-4.0**。
