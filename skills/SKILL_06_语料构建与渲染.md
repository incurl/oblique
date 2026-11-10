---
name: skill-06
title: 语料构建与渲染
description: 从标注正文派生出三个 JSON 索引（实体/联语/结构）并渲染静态 HTML。涵盖字段设计与可靠性分级、Markdown+JSON 双轨制、实体着色渲染、以及"唯一事实源"架构。当需要产出可被程序消费的语料、或做可视化预览时使用。
version: 1.0
last_updated: 2026-11-10
---

# SKILL 06: 语料构建与渲染

> **核心理念**：**唯一事实源是 `.tagged.md`，其余全部派生。**
> 派生而非并存，才能保证索引与正文永不失同步。

---

## 一、任务定义

### 1.2 输入与产出

| | 内容 |
|---|---|
| 输入 | `.tagged.md` + 文档树 |
| 产出 | `entities.json` / `couplets.json` / `structure.json` + `docs/index.html` |
| 前置 | [SKILL_03](SKILL_03_实体标注.md)、[SKILL_04](SKILL_04_联语识别.md) |
| 后继 | 研究使用 |

### 1.3 成功标准

- [ ] 三个 JSON 可从 `.tagged.md` 完全重建
- [ ] 每个字段的可靠性有明确说明
- [ ] HTML 能显示实体类型着色与编号跳转

---

## 二、Markdown + JSON 双轨制

### 2.1 为什么两种格式并存

| 格式 | 面向 | 用途 |
|---|---|---|
| `.tagged.md` | **人** | 阅读、校勘、git diff |
| `.json` | **机** | 检索、统计、二次开发 |

**原则**：Markdown 是权威，JSON 是**索引**。
任何时候重跑 `annotate_yinglian.py` 都能重建 JSON，
因此二者不可能不一致。

### 2.2 产物分层

```
data/楹联丛话全编.tagged.md      ← 唯一事实源
        │
        ├── data/entities.json      实体索引
        ├── data/couplets.json      联语语料
        ├── data/structure.json     结构树
        │
        └── docs/index.html         渲染产物
```

---

## 三、`entities.json`

### 3.1 结构

```json
{
  "schema": "yinglian-semantic-v1",
  "total": 13135,
  "distinct": 2979,
  "counts_by_type": {"=": 2509, ";": 1984, "@": 1572, ...},
  "entities": [
    {
      "type": "@",
      "name": "苏轼",
      "canonical": "苏轼",
      "count": 168,
      "refs": ["1.3.1", "1.3.6", "..."]
    }
  ]
}
```

### 3.2 关键设计：`refs` 只存前 200 条

高频实体（苏轼 168 次）若存全部 refs，文件会膨胀。
`refs[:200]` 足够定位，超出部分由正文 `grep` 补充。

### 3.3 `total` vs `distinct`

- `total` = 标注处数（同一实体出现多次算多次）
- `distinct` = 规范名个数

**两个数字都要给**，否则读者会误判覆盖度。

---

## 四、`couplets.json`

### 4.1 字段与可靠性分级

```json
{
  "id": "C0001",
  "book": "楹联丛话", "volume": "", "section": "故事", "entry": "",
  "ref": "1.3.1",
  "type": "春联",
  "upper": "新年纳余庆",
  "lower": "嘉节号长春",
  "lower_source": "",
  "editorial_markers": [],
  "upper_len": 6,
  "lower_len": 6,
  "text": "新年纳余庆；嘉节号长春",
  "author": "孟昶",
  "author_near": "孟昶",
  "place": "成都",
  "context": "……自命笔云："
}
```

| 字段 | 来源 | 可靠性 |
|---|---|---|
| `upper`/`lower` | 原文切分，剥离三样杂质 | **高** |
| `lower_source` | 形制自证 + 词典确认 | **高**（168 副） |
| `editorial_markers` | 剥离出的编者标记 | **高** |
| `upper_len`/`lower_len` | 计算 | **高** |
| `book`/`section`/`ref` | 结构树 | **高** |
| `type` | 上下文关键词 | **中**（启发式） |
| `author` | 人名 + 撰/题/书联 | **高精度低召回**（91） |
| `author_near` | 联前最近人名 | **低**，仅线索 |
| `place` | 联前最近地名 | **低**，仅线索 |
| `context` | 联前 100 字 | **高**，供复核 |
| `text` | 引号内原文 | **高** |

### 4.2 为什么存 `context`

**关键决定**：它让研究者不必打开源文件就能判断元数据对不对，
也给 `author` 这类不确定字段一个**申诉渠道**。

### 4.3 顶层统计

```json
{
  "total": 3020,
  "counts_by_type": {"集句": 613, "联语": 579, ...},
  "with_lower_source": 168,
  "equal_length": 3000,
  "equal_length_ratio": 0.9934
}
```

**把质量指标写进产物**，使用者一眼能判断可信度。

---

## 五、`structure.json`

```json
{
  "id": "1.3", "kind": "section", "line_no": 93, "title": "故事",
  "children": [
    {"id": "1.3.1", "kind": "paragraph", "line_no": 94,
     "preview": "尝闻纪文达师言：楹帖始于桃符…", "chars": 180, "children": []}
  ]
}
```

**三种检索入口**：层级路径 / 源行号 / 文本预览。

⚠️ `preview` 只存 80 字，**不要存完整正文**——
那是 `.tagged.md` 的职责，重复存储会让文件膨胀且可能不同步。

---

## 六、渲染

### 6.1 标记 → HTML

```python
TYPE_CLASS = {
    "@": ("person", "人名", "#8B4513"),
    "=": ("place", "地名", "#B8860B"),
    ";": ("official", "官职", "#8B0000"),
    ...
}

def replace_entities(text):
    def noun(m):
        type_, body, canonical = m.group(1), m.group(2), m.group(3)
        display = body.partition("|")[0]
        cls, name, color = TYPE_CLASS[type_]
        return (f'<span class="ent {cls}" style="--c:{color}" '
                f'title="{name} · {canonical}">{display}</span>')
    return re.sub(r"〖([@=;%&◆^~•!?+{:[_#$])([^〗|]*)(?:\|([^〗]*))?〗", noun, text)
```

### 6.2 三层结构保留

| Markdown | HTML | 用途 |
|---|---|---|
| `::: 序` … `:::` | `<div class="block preface">` | 序言底色 |
| `::: 小传` | `<div class="block bio">` | 现代附录 |
| `::: 校注` | `<div class="block note">` | 校勘按语 |
| `::: 联` | `<div class="block couplet-block">` | 巧对排比 |
| `[1.3.1]` | `<a class="pn" href="#pn-1.3.1">1.3.1</a>` | 紫色编号 |
| `〖聯〗` | `<span class="lian">聯</span>` | 联语徽标 |

### 6.3 渲染的职责边界

**渲染器不负责"解释"**，只负责"呈现"：

- 不判断实体标得对不对
- 不改动任何原文
- 只把标记映射成样式

---

## 七、禁止事项与推荐做法

### 7.1 禁止

❌ **手工编辑 JSON** —— 下次重跑就被覆盖，且可能引入与正文不一致。

❌ **在 JSON 里存完整正文** —— 重复存储，且会不同步。

❌ **渲染时修改原文** —— 渲染是只读转换。

### 7.2 推荐

✅ **JSON 全部由脚本派生** —— 保证与 `.tagged.md` 一致。

✅ **字段可靠性写进文档** —— 使用者才能正确解读。

✅ **顶层放质量指标** —— `equal_length_ratio` 等一眼可见。

✅ **`preview` 截断** —— 索引只需"认得出"。

---

## 八、工具与脚本

| 脚本 | 产出 |
|---|---|
| `scripts/annotate_yinglian.py` | 三个 JSON + `.tagged.md` |
| `scripts/render_yinglian.py` | `docs/index.html` |

```bash
python3 scripts/annotate_yinglian.py
python3 scripts/render_yinglian.py
```

---

## 九、检查清单

- [ ] 三个 JSON 的 `schema` 字段一致
- [ ] `entities.json` 的 `total` == 正文实体标记数
- [ ] `couplets.json` 的 `total` == 正文 `〖聯〗` 数
- [ ] `structure.json` 的 `line_no` 单调递增
- [ ] HTML 中实体着色正常、编号可跳转
- [ ] HTML 中无残留 `〖`

**自检**：

```bash
python3 - <<'PY'
import json, re
md = open('data/楹联丛话全编.tagged.md', encoding='utf-8').read()
E = json.load(open('data/entities.json', encoding='utf-8'))
C = json.load(open('data/couplets.json', encoding='utf-8'))
print('正文实体标记:', len(re.findall(r'〖[@=;%&◆^~•!?+{:[_#$]', md)), '| entities.total:', E['total'])
print('正文 〖聯〗:', md.count('〖聯〗'), '| couplets.total:', C['total'])
PY
```

---

## 十、FAQ

**Q：能不能直接输出 TEI XML？**
A：可以，映射是机械的（`@`→`<persName>`，`聯`→`<lg><l>`…），
但本项目未实现。选择 Token 不是拒绝标准化，而是**推迟标准化**——
等确有交换需求时再导出。

**Q：`entities.json` 600KB 太大了，能压吗？**
A：可以砍 `refs` 上限，但当前规模（616KB）在可接受范围。
真正的膨胀源是 `couplets.json` 的 `context` 字段（2.0MB），
那是刻意保留的复核依据。

**Q：HTML 2.2MB 太大怎么办？**
A：当前是单文件预览，可接受。
若需发布，改为分页渲染或按书拆分。

---

## 十一、相关

- 上游：[SKILL_04 联语识别](SKILL_04_联语识别.md)、[SKILL_05 形制校验](SKILL_05_形制校验.md)
- 规范：[../SPEC_楹联语义标注.md](../SPEC_楹联语义标注.md) §五
