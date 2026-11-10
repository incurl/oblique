---
name: skill-08
title: 文档与版本管理
description: 本项目四份文档的分工、数字必须可复算的纪律、以及提交规范。当要写文档、更新统计数字、或提交代码时使用。提交前必读。
version: 1.0
last_updated: 2026-11-10
---

# SKILL 08: 文档与版本管理

> **核心理念**：**文档里的每个数字都要能复算。**
> 一个过期的数字，比没有数字更危险。

---

## 一、任务定义

### 1.1 何时使用

- 要写/改文档
- 改了数据，需要同步更新数字
- 提交代码前

### 1.2 输入与产出

| | 内容 |
|---|---|
| 输入 | 改动后的代码与数据 |
| 产出 | 一致的文档 + 规范的提交 |
| 前置 | [SKILL_05](SKILL_05_形制校验.md) 通过
| 后继 | 交接 |

---

## 二、四份文档的分工

**不要把它们写成同一份。**

| 文档 | 面向 | 回答的问题 | 稳定性 |
|---|---|---|---|
| `README.md` | 新访客 | "这是什么？怎么跑起来？" | 稳定 |
| `SPEC_楹联语义标注.md` | 使用者 | "每个字段什么意思？什么可靠性？" | 稳定 |
| `BOOK_楹联语义标注方法论.md` | 研究者 | "为什么这么做？哪些做法被证伪？" | 半稳定 |
| `skills/` | **Agent / 维护者** | "具体怎么操作？" | 随实践更新 |

### 2.1 判断该写进哪一份

```
"这个字段是什么意思"        → SPEC
"为什么用 Token 不用 TEI"    → BOOK
"改词表的具体步骤"          → skills/
"pip install 什么"          → README
```

### 2.2 三份文档的共同要求

- 数字必须与 `data/*.json` 一致
- 已知缺陷必须列出，不粉饰
- 示例必须是从真实数据里取的

---

## 三、数字可复算纪律

### 3.1 唯一的数字来源

**所有统计数字只能来自 `data/*.json`，不能手工算、不能凭印象写。**

```bash
python3 - <<'PY'
import json
E = json.load(open('data/entities.json', encoding='utf-8'))
C = json.load(open('data/couplets.json', encoding='utf-8'))
print('实体:', E['total'], '/', E['distinct'])
print('联语:', C['total'], '等长:', C['equal_length'], C['equal_length_ratio'])
print('带出处:', C['with_lower_source'])
PY
```

### 3.2 改完数据后必须同步的位置

| 位置 | 会出现的数字 |
|---|---|
| `README.md` 产物表 | 实体总数、联语数 |
| `SPEC` 类型表 | 每类标注数与规范名数 |
| `BOOK` 第十八章 | 全部统计 |
| `SKILL_00` §五 基线 | 全部统计 |
| 各 SKILL 的示例 | 局部数字 |

**这是一个真实的隐患**：数字散落在 5 处，改一处忘一处就会不一致。

### 3.3 自动校验脚本

```bash
python3 - <<'PY'
import json
E = json.load(open('data/entities.json', encoding='utf-8'))
C = json.load(open('data/couplets.json', encoding='utf-8'))
docs = {f: open(f, encoding='utf-8').read()
        for f in ['README.md','SPEC_楹联语义标注.md','BOOK_楹联语义标注方法论.md']}
fails = []
for name, txt in docs.items():
    if '13,135' not in txt and name != 'README.md':
        fails.append(f'{name}: 缺实体总数')
    if '3,020' not in txt:
        fails.append(f'{name}: 缺联语总数')
print('不一致:', fails or '无')
PY
```

### 3.4 一次真实的翻车

修订过程中做过一次全局替换 `161 → 168`，
结果把**贺联的数量 168** 也改成了 161（后来发现是巧合）。

**教训**：

> 全局字符串替换在统计数字上**极其危险**。
> 改数字要带上下文（`**161 副**` 而不是 `161`），改完必须复核。

---

## 四、提交规范

### 4.1 提交前必做

```bash
python3 scripts/annotate_yinglian.py
python3 scripts/lint_text_integrity.py    # 必须 OK
python3 scripts/render_yinglian.py
git status --short
git diff --stat
```

### 4.2 提交信息格式

采用 **Conventional Commits + 中文正文分组**：

```
<type>(<scope>): <50 字以内的总结>

<模块>:
- 改动 1
- 改动 2

<影响/效果>:
- 指标变化

Co-Authored-By: ...
```

**类型**：`feat` / `fix` / `docs` / `chore` / `refactor`

**本项目实际的提交历史**：

```
fix(couplets): 补全出处冠名的四种位置并剥离编者标记
feat(couplets): 集句联出处冠名独立成字段并取消 balanced 标记
docs(book): 新增《楹联语义标注方法论》配套书并修复联语切分缺陷
fix(docs): 修复规范表格中竖线未转义导致的列数错位
feat(yinglian): 建立《楹联丛话全编》语义标注体系
```

### 4.3 危险操作清单

| 禁止 | 原因 |
|---|---|
| `git add -A` / `git add .` | 会把 `.idea/`、临时文件一起提交 |
| `git checkout -- <file>` | **不可逆**覆盖工作区，丢失未提交修改 |
| `git reset --hard` | 同上 |
| `git push --force` | 覆盖远程历史 |
| 未审查就 commit | 提交信息是唯一的变更记录 |

**正确做法**：

- 显式列出要提交的路径
- 用 HEREDOC 传多行 commit message
- 不自动 push，由人决定

### 4.4 一次提交一个主题

标注改动与文档修复**分开提交**。
否则 `git log` 无法回答"哪次改动导致指标变化"。

---

## 五、文档写作规范

### 5.1 结构

每份文档开头要有：

```markdown
> **版本**：v1.0（YYYY-MM-DD）
> **配套**：<链接>
```

### 5.2 表格优先

对比信息用表格，不用长段落：

```markdown
| 维度 | 方案 A | 方案 B |
|---|---|---|
| 成本 | 低 | 高 |
```

### 5.3 明确说"不知道"

```markdown
⚠️ **已知限制**：作者字段覆盖仅 3.0%，
长尾人物未识别，需人工复核。
```

**不要用模糊措辞掩盖不确定性**（"基本准确"、"大体可靠"）。

### 5.4 引用真实数据

```markdown
✅ 等长率 99.34%（3,000/3,020）
❌ 等长率很高
```

---

## 六、禁止事项与推荐做法

### 6.1 禁止

❌ **手工编辑 `data/*.json`** —— 下次重跑即被覆盖。

❌ **凭印象写数字** —— 必须从 JSON 里取。

❌ **全局替换统计数字** —— 会误伤同名数字（§3.4）。

❌ **提交前不跑校验**。

### 6.2 推荐

✅ **改完数据立刻同步 5 处数字**（§3.2）。

✅ **用带上下文的替换**（`**161 副**` 而非 `161`）。

✅ **文档里写"为什么"，不只写"是什么"**。

✅ **保留历史失败记录**（BOOK 第十三章、SKILL_07 §5）。

---

## 七、工具与脚本

| 用途 | 命令 |
|---|---|
| 生成 | `python3 scripts/annotate_yinglian.py` |
| 校验 | `python3 scripts/lint_text_integrity.py` |
| 渲染 | `python3 scripts/render_yinglian.py` |
| 查状态 | `git status --short` |
| 查差异 | `git diff --stat` |

---

## 八、检查清单

### 8.1 提交前

- [ ] `lint_text_integrity.py` 通过
- [ ] 文档中的数字与 JSON 一致
- [ ] 新增的规律/缺陷已写进对应文档
- [ ] `.idea/` 等本地文件未被 `git add`
- [ ] commit message 符合格式，首行 ≤ 50 字

### 8.2 提交后

- [ ] `git log -1` 显示的 message 正确
- [ ] `git status` 工作区干净
- [ ] 未自动 push

---

## 九、FAQ

**Q：为什么文档要分四份而不是一份？**
A：读者不同。新访客要"能跑起来"，使用者要"字段含义"，
研究者要"为什么"，Agent 要"具体操作"。
混在一起会让每一类读者都要读无关内容。

**Q：BOOK 有必要写那么长吗？**
A：它记录的是**判断的理由**和**被否决的方案**。
这些信息在 SPEC 和 skills 里都没有位置，但它们是"下次遇到类似问题"的关键。

**Q：数字能不能只在一个地方维护？**
A：理想是。当前是"JSON 为源、文档引用"，
未做自动注入。这是一个已知的改进点。

---

## 十、相关

- 上游：[SKILL_05 形制校验](SKILL_05_形制校验.md)
- 相关：[SKILL_00 §五 基线](SKILL_00_管线总览.md)
