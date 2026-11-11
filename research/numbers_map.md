# numbers_map.md —— 论文数值 ↔ 报告文件 逐格映射

本文件是**论文数值可溯源契约**的载体。论文（`MANUSCRIPT.md`）中出现的每一个
统计量，都必须能经由本表定位到 `reports/` 下的具体文件与具体单元格。

> **当前状态：论文正文的实验数值均为占位符。**
> 演示数据（`examples/`）是合成的，**不得**用于填表。
> 真实实验数据产出后，按本表逐格回填，并同步更新
> `MANUSCRIPT.md` 中的 `[...]` 占位符。

## 一、填表流程

1. 真实人工标注导出为 JSONL（格式见 `agreement.py` 顶部文档字符串）。
2. 运行：
   ```bash
   python agreement.py --gold <gold.jsonl> \
       --ann <ann_a.jsonl>,<ann_b.jsonl> \
       --config schema.yaml --out reports/ \
       --baseline <baseline.jsonl>
   ```
3. 依下表把 `reports/` 中的数值回填到论文表格，**逐格核对**。
4. 提交时把 `reports/` 一并归档，作为论文的补充材料。

## 二、论文表格 → 报告文件映射

### Table 1（实体/关系类型与规模）

| 论文位置 | 报告文件 | 定位方式 | 回填状态 |
|---|---|---|---|
| T1 行：18 类实体及其出现次数 | `reports/../data/entities.json` | `counts_by_type` 字段（上游标注产物） | ✅ 已由语料实测填入（见 `schema.yaml: corpus_reference`） |
| T1 行：6 类关系及其标注量 | `reports/kappa_by_type.csv` | `unit_family == "relation"` 各行的 `n_units` | ⬜ 待真实标注填入 |
| T1 行：11 类联类及数量 | `data/couplets.json` | `counts_by_type` 字段 | ✅ 已由语料实测填入 |

### Table 2（各类型 κ / p_o / PI / BI / 95%CI）

| 论文位置 | 报告文件 | 定位方式 | 回填状态 |
|---|---|---|---|
| T2 行 1–18（实体类型） | `reports/kappa_by_type.csv` | `unit_family == "entity"`，按 `type_name` 定位 | ⬜ 待填 |
| T2 行 19–24（关系类型） | `reports/kappa_by_type.csv` | `unit_family == "relation"`，按 `type_name` 定位 | ⬜ 待填 |
| T2 行 25–27（属性类型） | `reports/kappa_by_type.csv` | `unit_family == "attribute"`，按 `type_name` 定位 | ⬜ 待填 |
| T2 列：`p_o` | 同上 | `p_o` 列 | ⬜ |
| T2 列：`κ` | 同上 | `kappa` 列 | ⬜ |
| T2 列：95%CI | 同上 | `ci_low` / `ci_high` 列（bootstrap，B=1000，seed=42） | ⬜ |
| T2 列：PI / BI | 同上 | `pi` / `bi` 列（Byrt 等 1993 二值化口径） | ⬜ |
| T2 列：FCE 渐近 SE 与 CI | 同上 | `fce_se` / `fce_ci_low` / `fce_ci_high` 列 | ⬜ |
| T2 列：α | 同上 | `alpha` / `alpha_ci_low` / `alpha_ci_high` 列 | ⬜ |
| T2 列：加权 κ（二次/线性） | 同上 | `weighted_kappa_quadratic` / `weighted_kappa_linear` 列 | ⬜ |
| T2 列：Scott's Pi（对照） | 同上 | `scott_pi` 列 | ⬜ |
| T2 附表：实体链接口径 | `reports/kappa_by_type_canonical.csv` | 按 `type_name` 定位 | ⬜ |

> **示例（格式示范，非真实结果）**：
> `reports/kappa_by_type.csv#relation=用典` → T2 中「用典」那一行的 κ / p_o / PI / BI / CI。

### Table 3（与基线的对比）

| 论文位置 | 报告文件 | 定位方式 | 回填状态 |
|---|---|---|---|
| T3 实体抽取 strict F1 | `reports/f1_by_type.csv` | `mode == "strict"`，按 `type` 定位 | ⬜ 待填 |
| T3 实体抽取 relaxed F1 | `reports/f1_by_type.csv` | `mode == "relaxed"`，按 `type` 定位 | ⬜ 待填 |
| T3 关系抽取 F1（两口径） | `reports/relation_f1.csv` | 按 `type` 与 `mode` 定位 | ⬜ 待填 |
| T3 工时中位数与 IQR | `reports/timing.csv` | 按 `condition` 定位 | ⬜ 待填 |
| T3 配对 Wilcoxon 结果 | `reports/ci.json` | `paired_timing` 对象（`statistic` / `p_value` / `p_value_exact` / `cliffs_delta` / `rank_biserial_r`） | ⬜ 待填 |
| T3 F1 显著性 | `reports/significance.csv` | 按 `comparison` 定位（`gold_vs_annotator_A` / `baseline_vs_annotator_A`） | ⬜ 待填 |
| T3 seqeval conformance | `reports/ci.json` | `agreement` 段的 `seqeval` 字段 | ⬜ 待填 |

### Table 4（错误类型分布）

| 论文位置 | 报告文件 | 定位方式 | 回填状态 |
|---|---|---|---|
| T4 各错误类型计数 | `reports/error_taxonomy.csv` | 按 `error_code` 定位 | ⬜ 待填 |
| T4 分单元族计数 | 同上 | `entity` / `relation` / `attribute` 列 | ⬜ 待填 |
| T4 Top-10 混淆对 | `reports/SUMMARY.md` §「Top-10 混淆对」 | 按 `kind`/`a`/`b` 定位 | ⬜ 待填 |
| T4 逐类型混淆矩阵 | `reports/confusion_matrices/entity_<type>.csv` | 文件名中的 `<type>` | ⬜ 待填 |
| T4 逐关系混淆矩阵 | `reports/confusion_matrices/relation_<name>.csv` | 文件名中的 `<name>` | ⬜ 待填 |

### Table 5（数据集字段字典）

| 论文位置 | 来源 | 回填状态 |
|---|---|---|
| T5 各字段名、类型、说明 | `schema.yaml` → `units` / `corpus_reference` 与 `README.md` 输入格式说明 | ✅ 已填（字段定义不依赖实验结果） |

## 三、正文散见的数值

| 论文位置 | 报告文件 | 定位方式 | 回填状态 |
|---|---|---|---|
| §5 各阶段耗时占比 | `reports/timing.csv` | 按 `condition` 定位后自行换算 | ⬜ 待填（需补记各阶段起止时间戳） |
| §6.3 的 8 条分歧案例 | `reports/disagreement_cases.md` | 按案例序号定位 | ⬜ 待填（需补 `adjudication` 与 `rule` 字段） |
| §8 案例研究的计数 | `data/couplets.json` / `data/entities.json` | 见 §8 各小节的"数据来源"标注 | ✅ 已填（均为语料实测统计） |

## 四、当前不可填的项（需实验完成后回填）

- [ ] Table 2 全部数值（实体、关系、属性三类）
- [ ] Table 3 全部数值（F1、工时、显著性）
- [ ] Table 4 全部数值（错误分布）
- [ ] §5 各阶段耗时占比
- [ ] §6.3 八条分歧案例的仲裁结论与预防规则
- [ ] 论文 §7 数据集版本号（待首次公开发布时确定）

## 五、禁止事项

- 不得用 `examples/` 下的**合成演示数据**填写任何论文表格；
- 不得手工调整 `reports/` 中的数字以迎合正文叙述；
- 若某单元在某类型下无标注（如 `n_units == 0`），正文应写「本批数据中无该类型单元」，
  而不是留空或填 0；
- 任何在正文中出现、但无法在上表定位的统计量，都必须在提交前补入本表。
