---
name: skill-06
title: 语料构建与渲染
description: 从标注正文派生出三个 JSON 索引（实体/联语/结构），渲染静态 HTML，并导出 TiddlyWiki（条目为 tiddler、实体为 tag）。涵盖字段设计与可靠性分级、Markdown+JSON 双轨制、实体着色渲染、TiddlyWiki 的 tiddler 模型与 tag 体系、.tid 格式与三个常见坑、以及"唯一事实源"架构。当需要产出可被程序消费的语料、做可视化预览、或发布可交叉检索的知识库时使用。
version: 1.1
last_updated: 2026-11-11
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
| 产出 | `entities.json` / `couplets.json` / `structure.json` + `docs/index.html` + `tiddlywiki/` |
| 前置 | [SKILL_03](SKILL_03_实体标注.md)、[SKILL_04](SKILL_04_联语识别.md) |
| 后继 | 研究使用 |

### 1.3 成功标准

- [ ] 三个 JSON 可从 `.tagged.md` 完全重建
- [ ] 每个字段的可靠性有明确说明
- [ ] HTML 能显示实体类型着色与编号跳转
- [ ] TiddlyWiki 中无断链、无重复标题，条目与联语零遗漏

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

## 七、TiddlyWiki 导出

### 7.1 为什么导出 TiddlyWiki

静态 HTML 适合"读"，但**"查"**需要交叉检索。
TiddlyWiki 的 tag 机制天然适合：条目是 tiddler，实体是 tag，
于是"某人 + 某地 + 某书 + 某类联语"这种组合查询，
一条 filter 就能表达：

```
[tag[人名/林则徐]tag[地点/福州]tag[楹联丛话]]
```

这正是把实体标注**升级为可计算知识**的一步。

### 7.2 tiddler 模型

| 前缀 | 内容 | 数量 |
|---|---|---|
| `条目/` | 原文条目（段落级） | 2,254 |
| `联语/` | 单副联语 | 3,020 |
| `实体/` | 规范名实体 | 3,108 |
| `章节/` | 书 / 卷 / 门类 / 条目导航 | 223 |
| — | 首页与索引 | 5 |

**为什么按段落而非按书分 tiddler**：
一则联语、一条实体、一处出处常常只出现在一个段落里，
粒度过粗就失去互链能力；粒度过细则 tiddler 数量爆炸。

### 7.3 标签体系

| 类别 | 形式 | 例 |
|---|---|---|
| 类别 | `条目` `联语` `实体` `章节` | `[tag[条目]]` |
| 归属 | `书名`、`书名/门类` | `楹联丛话/故事` |
| 实体 | `类型/规范名` | `人名/林则徐` |
| 联语类型 | 类型名 | `挽联` |

**关键**：实体标签一律用**规范名**（`林则徐`）而非**显示名**（`林少穆`），
否则同一实体会分裂成多个 tag，筛选结果就漏了。

### 7.4 `.tid` 文件格式

TiddlyWiki 的 `.tid` 格式非常简单（见 TiddlyWiki5 `boot/boot.js` 的
`tiddlerdeserializer/tid`）：

```
title: 条目/1.3.1
编号: 1.3.1
书: 楹联丛话
tags: 条目 楹联丛话 楹联丛话/故事 人名/纪昀 地点/成都

!楹联丛话 › 故事

正文……

```

- 第一段是 `name: value` 字段，每行一个；`#` 开头是注释；
- **空行之后**才是正文；
- `tags` 用空格分隔，含空格的标签用 `[[...]]` 包裹。

### 7.5 三个容易踩的坑

#### 坑一：链接语法方向相反

TiddlyWiki 是 `[[显示文本|目标]]`，
而本项目的标注消歧语法是 `〖别名|规范名〗`，
**两者顺序正好相反**。直接照搬会生成"看起来像链接、其实是一坨纯文本"的链接。

```python
# ✗ 错：会渲染成纯文本「实体/人名/纪昀」
f"[[{target}|{display}]]"
# ✓ 对
f"[[{display}|{target}]]"
```

#### 坑二：表格单元格内不能用 `[[...]]`

表格的单元格正则 `\|([^\n\|]*)\|` 不允许出现竖线，
所以单元格里的 `[[显示|目标]]` 会被当成纯文本。必须改用 `<$link>` 构件：

```
| <$link to="实体/人名/林则徐">林则徐</$link> | 37 |
```

#### 坑三：没有 `<<list>>` 宏

TiddlyWiki 核心**没有** `<<list>>` 宏。
列举某标签下的 tiddler 要用：

```
<<list-links filter:"[tag[人名/林则徐]sort[编号]]">>
```

#### 坑四：`sort[编号]` 是字典序，不是数值序

`编号` 形如 `1.3.10`，字典序下 `1.3.10` 会排在 `1.3.2` **前面**。
所以凡是要按编号排序，一律用零填充的 `序` 字段（`0001.0003.0010`）：

```
<<list-links filter:"[tag[楹联丛话/故事]sort[序]">>
```

TOC 宏则直接用自然排序 `sortan[序]`。

#### 坑五：`[tag[联语]]` 会把条目也捞进来

条目 tiddler 只要含联语，也会被打上 `联语` 标签。
要只列联语 tiddler，得用前缀限定：

```
<<list-links filter:"[prefix[联语/]sort[编号]]">>
```

### 7.6 校验：必须用独立数据源交叉核对

导出器自己写的数据不能用来校验导出器。
`scripts/verify_tiddlywiki.py` 改用 `structure.json` / `couplets.json`
（由标注管线独立产出）来核对：

```
✓ 0. 全部 .tid 的头/正文分隔正确（正文不会被当成字段吞掉）
✓ 1. 无重复标题
✓ 2. 全部 21,999 处内部链接均可解析
✓ 3. 3,545 个实体标签均有对应 tiddler
✓ 4. 全部 2,254 个源段落均已导出
✓ 5. 全部 3,020 副联语均已导出
✓ 6. 2,254 个条目的实体 tag 与正文标注一致
✓ 7. 紫色编号目录完整（2,477 个节点，父子标签关系全部正确）
✓ 8. 目录排序正确（224 个父节点下，同级「序」与紫色编号一致）
```

第 6 项尤其重要：它逐条比对"正文里标了什么"与"tag 里挂了什么"，
能立刻抓出标签漏挂、错挂、类型错分。

第 7、8 项针对目录：逐个节点核对"父 tiddler 的标题"这个标签有没有挂上，
以及同一父节点下"序"与紫色编号的次序是否一致。

### 7.7 紫色编号目录（TOC）

侧栏首位的「目录」标签页用 TiddlyWiki **标准目录宏**生成，
不另造轮子。标准机制的关键：**用标签表达父子关系**——
子 tiddler 被打上父 tiddler 的**标题**。

```
TableOfContents                     ← 目录根，标签 $:/tags/SideBar
  └─ 章节/1   （挂标签 TableOfContents）
       └─ 章节/1.3  （挂标签 章节/1）
            └─ 条目/1.3.1  （挂标签 章节/1.3）
```

目录根 tiddler 的正文：

```
<<toc-selective-expandable 'TableOfContents' "sortan[序]">>
```

每个节点用 `caption` 字段承载显示文本（`caption` 优先于 `title`）：

```
caption: <span class="pn">1.3.1</span> 尝闻纪昀师言：楹帖始于桃符…
```

紫色编号直接沿用 `structure.json` 的节点 id，不重新编号。
样式由 `样式/紫色编号` 这个 `$:/tags/Stylesheet` tiddler 提供。

### 7.8 打包与浏览

`scripts/build_tiddlywiki.py` 把导出目录编译成**单个自包含 HTML**：

```bash
python3 scripts/build_tiddlywiki.py
# → tiddlywiki/oblique.html（约 8.2 MB，8,623 个 tiddler）
```

脚本会自动查找 TiddlyWiki5 源码目录（`--tw` 参数或 `TIDDLYWIKI5` 环境变量），
打包后核对单文件里是否装下全部 tiddler、站点配置是否生效、是否带中文语言包。

也可以直接用 TiddlyWiki 5 打包，或启动本地服务浏览：

```bash
node /path/to/TiddlyWiki5/tiddlywiki.js tiddlywiki/楹联丛话全编 \
     --output dist --build index

node /path/to/TiddlyWiki5/tiddlywiki.js tiddlywiki/楹联丛话全编 --listen
```

单文件浏览器直接打开即可，无需服务器、无需联网。

### 7.9 `.tid` 的头/正文分隔（踩过的坑）

TiddlyWiki 的 `.tid` 反序列化器用 `text.split(/\r?\n\r?\n/mg)` 切分头与正文，
**头与正文之间必须有一个真正的空行**。

漏掉这个空行时，`parseFields` 会把正文第一行当成 `name: value` 字段解析，
于是**正文的第一行被静默吞掉**——不报错，只是内容丢失。
本项目 8,613 个 `.tid` 文件全部踩了这个坑（每副联语的上联、每个条目的标题行都没了）。

因此 `verify_tiddlywiki.py` 增加了第 0 项检查：头部每行都必须是合法字段，
且文件必须含有 `\n\n`。这一项能挡住整类"静默丢数据"的错误。

---

## 八、禁止事项与推荐做法

### 8.1 禁止

❌ **手工编辑 JSON** —— 下次重跑就被覆盖，且可能引入与正文不一致。

❌ **在 JSON 里存完整正文** —— 重复存储，且会不同步。

❌ **渲染时修改原文** —— 渲染是只读转换。

❌ **用显示名做实体标签** —— 同一实体会分裂，筛选漏结果。

### 8.2 推荐

✅ **JSON 全部由脚本派生** —— 保证与 `.tagged.md` 一致。

✅ **字段可靠性写进文档** —— 使用者才能正确解读。

✅ **顶层放质量指标** —— `equal_length_ratio` 等一眼可见。

✅ **`preview` 截断** —— 索引只需"认得出"。

✅ **导出结果用独立数据源校验** —— 自己不能验自己。

---

## 九、工具与脚本

| 脚本 | 产出 |
|---|---|
| `scripts/annotate_yinglian.py` | 三个 JSON + `.tagged.md` |
| `scripts/render_yinglian.py` | `docs/index.html` |
| `scripts/export_tiddlywiki.py` | `tiddlywiki/楹联丛话全编/` |
| `scripts/verify_tiddlywiki.py` | 导出结果校验报告 |

```bash
python3 scripts/annotate_yinglian.py
python3 scripts/render_yinglian.py
python3 scripts/export_tiddlywiki.py
python3 scripts/verify_tiddlywiki.py
```

---

## 十、检查清单

- [ ] 三个 JSON 的 `schema` 字段一致
- [ ] `entities.json` 的 `total` == 正文实体标记数
- [ ] `couplets.json` 的 `total` == 正文 `〖聯〗` 数
- [ ] `structure.json` 的 `line_no` 单调递增
- [ ] HTML 中实体着色正常、编号可跳转
- [ ] HTML 中无残留 `〖`
- [ ] TiddlyWiki 中无重复标题
- [ ] TiddlyWiki 中无断链（`tc-tiddlylink-missing` 为 0）
- [ ] 每个实体标签都有对应的实体 tiddler
- [ ] 条目 tiddler 数 == `structure.json` 的段落数

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

## 十一、FAQ

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

**Q：TiddlyWiki 导出会取代标注 Markdown 吗？**
A：不会。TiddlyWiki 是**派生视图**，用于检索与浏览；
权威语料始终是 `.tagged.md`，校验与复核仍以它为准。

---

## 十二、相关

- 上游：[SKILL_04 联语识别](SKILL_04_联语识别.md)、[SKILL_05 形制校验](SKILL_05_形制校验.md)
- 规范：[../SPEC_楹联语义标注.md](../SPEC_楹联语义标注.md) §五

