# Handoff：TiddlyWiki 实体标签 “Missing tiddler” 修复

> 状态：**✅ 已修复并验证**（2026-11-12）。
> 记录时间：2026-11-11；实施与收尾：2026-11-12
> 仓库：`/home/peter/GolandProjects/oblique`
> 基线 HEAD：`24309f3 fix(tw): 修复筛选器少一个 ] 导致的 "Filter error"，并加第 9 项校验`
> 最终方案：生成 **3,369 个锚点 tiddler**（标题 = 标签名），全部 12 项校验通过。
> 详见本文档末尾的 **§14 实施记录**。

---

## 1. 结论速览（TL;DR）

**根因**：TiddlyWiki 的标签胶囊（tag pill）会用**标签名本身**去查找同名 tiddler 来判断“存在 / 缺失”。
我们的实体**标签**叫 `典籍/古格言`，而实体 **tiddler** 叫 `实体/典籍/古格言`——名字对不上，
于是标签被渲染成 missing 状态。

**已实施的修复**：为每个标签生成一个与**标签同名**的轻量“锚点 tiddler”（`典籍/古格言`）。
锚点正文用**筛选器**动态列出该标签关联的全部内容（相关条目 / 相关联语 /
相关章节 / 相关实体），并保留一个指向规范页的链接。
**未重命名**现有实体 tiddler。

**TOC 风险已排除**（原 §6 的阻塞项，Q1）：
`core/wiki/macros/toc.tid` 的层级算子确为「tag 值 = 父 tiddler 标题」
（`[all[shadows+tiddlers]tag<__tag__>…]`），
但本库的 TOC 链**只**由 `TableOfContents` → `章节/*` → `条目/*` 构成（2,478 个标题），
与实体标签**完全不相交**（交集 = 0）。
→ 实测：修复前后 TOC 节点数（2,477）与顺序、caption **逐字节一致**（md5 相同）。

**修复前后的直接对照**（用 TiddlyWiki 自身渲染 `core/ui/Components/tag-link`）：

| | 标签链接的 class | 标签页正文 |
|---|---|---|
| 修复前 | `tc-tiddlylink tc-tiddlylink-missing` | `Missing tiddler "典籍/古格言" – click … to create` |
| 修复后 | `tc-tiddlylink tc-tiddlylink-resolves` | 相关条目 / 相关联语清单（筛选器动态生成）+ 规范页链接 |

---

## 2. 已确认的根因（带证据）

### 2.1 判定 missing 的那一行

`/home/peter/github.com/TiddlyWiki5/core/wiki/macros/tag.tid:24`

```tid
<span class={{{ [<__tag__>is[missing]then[tc-tag-missing]else[tc-tag-exists]] }}}>
	<$view tiddler=<<__tag__>> field="title" format="text" />
</span>
```

`[<__tag__>is[missing]` 的操作数就是**标签名字符串**。
只要 wiki 里不存在标题恰为 `典籍/古格言` 的 tiddler，该标签就渲染成 missing。

同文件 `:37` 还提供了 fallback 配色：

```tid
fallbackTarget={{$palette$##tag-background}}
```

### 2.2 点击标签会跳到一个不存在的 tiddler

`/home/peter/github.com/TiddlyWiki5/core/ui/Components/tag-link.tid:4-8`

```tid
<$link>
<$set name="backgroundColor" value={{{ [<currentTiddler>] ... }}}>
<span style=<<tag-styles>> class="tc-tag-label">
```

`$link` 的目标就是 tag 名 → 侧栏 Tag 面板里的每个实体标签都是**指向不存在页面的链接**，
并会被 `core/modules/widgets/link.js:79` 打上 `tc-tiddlylink-missing`
（样式见 `themes/tiddlywiki/vanilla/base.tid:481`）。

### 2.3 “Missing tiddler …” 文案的出处

`/home/peter/github.com/TiddlyWiki5/core/ui/TagTemplate.tid:14-17`

```tid
<$reveal state=<<qualify "$:/state/popup/tag">> type="popup" position="below" animate="yes" class="tc-drop-down">
	<$set name="tv-show-missing-links" value="yes">
		<$transclude tiddler="$:/core/ui/ListItemTemplate"/>
	</$set>
```

标签胶囊的下拉面板里 transclude 了 `$:/core/ui/ListItemTemplate`；
当 tag 对应的 tiddler 不存在时，该模板输出 `Missing tiddler "<标题>"`。
→ **待办小项**：确认这句文案确实出自 `core/ui/ListItemTemplate.tid`（本轮未读该文件）。

### 2.4 我们的数据现状（单一样本）

`tiddlywiki/楹联丛话全编/tiddlers/条目/1.1.1.tid:8`

```
tags: 条目 楹联丛话 楹联丛话/序 章节/1.1 时间/曩者 官职/提刑 朝代/唐五代 典籍/古格言 …
```

同文件正文第 12 行：

```
[[古格言|实体/典籍/古格言]]
```

`tiddlywiki/楹联丛话全编/tiddlers/实体/典籍/古格言.tid:5`

```
tags: 实体 典籍
```

即：

| | 值 |
|---|---|
| 实体 tiddler 标题 | `实体/典籍/古格言` ✅ 存在 |
| 实体 tag | `典籍/古格言` ❌ 无同名 tiddler |
| 正文 wikilink | `[[古格言\|实体/典籍/古格言]]` ✅ 可解析（指向 tiddler，不是 tag） |

**结论**：正文链接没问题；坏掉的只有**标签胶囊本身**。

---

## 3. 数据统计（避免再次打印全量）

统计口径：遍历 `tiddlywiki/楹联丛话全编/tiddlers/**/*.tid`，
收集所有 `tags:` 字段里的 tag，去重后检查“是否存在同名 tiddler”。

- 使用中的 tag 约 **3,652** 个
- **实体 tag（`类型/规范名`）共约 3,108 个，全部都有对应的 `实体/<tag>` tiddler**
  → 这批不是名字不一致，而是**纯粹缺一个同名 tiddler**
- 合计 **256 个 distinct tag 没有同名 tiddler**，分类如下：

| 类别 | 数量 | 样例 |
|---|---|---|
| `TYPE_CATEGORY`（实体类型分类） | 18 | `人名` `典籍` `刑法` `名物` `器物` `地点` `天文` `官职` `思想` `数量` `族群` `时间` `朝代` `氏族` `生物` `礼仪` `神祇` `身份` |
| `BOOK_SECTION`（书/卷/篇） | 214 | `楹联丛话/序` `楹联丛话/格言` `楹联丛话/故事` `楹联三话/卷上` `巧对录/序` `楹联散话/卓公祠` `楹联丛话全编/作者简介` … |
| `BOOK`（书名） | 6 | `楹联丛话` `楹联续话` `楹联三话` `楹联四话` `巧对录` `巧对续录` |
| `ENTITY_ROOT` | 1 | `实体` |
| `OTHER`（门类/结构性） | 17 | `联语` `会馆联` `堂联` `寿联` `庙联` `挽联` `春联` `贺联` `门联` `巧对` `巧对补录` `楹联剩话` `楹联散话` `出处` `作者简介` `说明` |

**⚠ 重要**：`BOOK_SECTION` / `BOOK` / `OTHER` 这 237 个 tag **不能**盲目加同名锚点 tiddler——
它们很可能就是 TOC 的层级锚（见 §6）。

---

## 4. 推荐修复方案：同名“锚点 tiddler”

### 4.1 做法

保留现有实体 tiddler（`实体/典籍/古格言`）不动，
为实体额外生成一个**与 tag 同名**的轻量 tiddler：

```tid
title: 典籍/古格言
tags: 实体索引

[[实体/典籍/古格言|古格言]]
```

效果：
- 标签胶囊 `典籍/古格言` 不再 missing（`is[missing]` 判定通过）
- 点击标签 → 打开锚点页 → 里面一跳到真正的实体页
- `[tag[典籍/古格言]]` 筛选语义完全不变（筛选的是**打标签的条目**，锚点自己不打这个标签）
- 正文 `[[古格言|实体/典籍/古格言]]` 不需要改

### 4.2 代码草图（`scripts/export_tiddlywiki.py`）

实体 tiddler 生成处（按交接记录约在 820–900 行，实体标题形如 `实体/{prefix}/{name}`）：

```python
ENTITY_TYPE_PREFIXES = {
    "人名", "地点", "官职", "时间", "氏族", "朝代",
    "名物", "族群", "器物", "天文", "神祇", "生物",
    "典籍", "礼仪", "刑法", "思想", "身份", "数量",
}

# ... 生成实体 tiddler 之后追加：

anchor_title = f"{prefix}/{name}"          # 例：典籍/古格言
if anchor_title not in builder.tiddlers:   # 绝不覆盖已有 tiddler
    builder.tiddlers[anchor_title] = {
        "title": anchor_title,
        "tags": "实体索引",                 # 关键：不打 anchor_title 自身
        "正文": f"[[{prefix}/{name}...]]",  # 见下
    }
```

### 4.3 必须遵守的约束

| # | 约束 | 原因 |
|---|---|---|
| C1 | anchor **不要**打 `anchor_title` 这个 tag | 否则自引用：`[tag[典籍/古格言]]` 会把锚点自己也捞进来 |
| C2 | anchor **不要**打 `实体` tag | 否则 `[tag[实体]]` 的实体数量被锚点污染；用独立标记 tag（如 `实体索引`） |
| C3 | 写入前必须 `if anchor_title not in builder.tiddlers` | 防止覆盖章节/联语/条目/系统 tiddler；冲突要记日志并单独核验 |
| C4 | 类型分类 tag（`人名` `典籍` … 共 18 个）**单独处理** | 它们也是 missing，但语义上是“分类索引页”，可另建 `人名` → 列出全部 `人名/*` 实体的索引页 |
| C5 | `实体` 根 tag 也要一个同名 tiddler | 同样是 missing |
| C6 | `.tid` 头/正文之间的空行规则不变 | 上一轮刚修过（commit `2a053b5`），别回退 |

### 4.4 明确**不**采用备选方案（统一重命名实体 tiddler 标题）

把 `实体/典籍/古格言` 改名成 `典籍/古格言` 的方案已评估并否决：

- 正文链接、实体索引、实体列表、字段链接需全量同步，改动面大
- 可能与结构 tag 撞名（例如 `楹联丛话/故事`、`楹联丛话/格言` 这类 BOOK_SECTION tag）
- 与 §6 的 TOC `children-of` 风险叠加
- 锚点方案能以**零正文改动**达成同样效果 → 没有理由冒险

---

## 5. 备选/补充方案（按需评估，非必须）

1. **只修实体 tag，不修类型分类 tag**：改完 `典籍/古格言` 消失，但 `典籍`、`人名` 这 18 个仍 missing。
   用户可能也会点它们 → 建议一并修（§4.3 C4）。
2. **改 tag 字段本身**：把实体 tag 从 `典籍/古格言` 改成 `实体/典籍/古格言`。
   → 会破坏 `[tag[典籍/古格言]]` 筛选，且与 TOC 用的 `章节/…`/`条目/…` tag 风格不一致。**否决**。
3. **隐藏 missing 标签**（`tv-show-missing-links=no` / CSS）→ 治标不治本，点击仍跳空页。**否决**。

---

## 6. ⚠ 动手前必做：TOC 父节点排查

**这是本方案唯一的真实风险，必须先排除。**

TiddlyWiki 的 TOC 层级建立在 `children-of` 过滤器上——
**tag 值 == 父 tiddler 标题**。因此：

> 若某个 tag（例如 `楹联丛话/序`）当前**没有**同名 tiddler，
> 我们新建一个同名 tiddler 之后，它就**突然变成**所有带该 tag 条目的父节点 →
> TOC 可能多出一层、层级错位或节点数暴涨。

### 排查步骤

```bash
# 1) 读 TOC 宏，确认层级算子
sed -n '1,80p' /home/peter/github.com/TiddlyWiki5/core/wiki/macros/toc.tid
grep -rn 'children-of' /home/peter/github.com/TiddlyWiki5/core/wiki/macros/toc.tid \
                         /home/peter/github.com/TiddlyWiki5/core/modules/filters/

# 2) 当前哪些 tag 已经是 TOC 父节点（存在同名 tiddler）
cd /home/peter/GolandProjects/oblique
python3 - <<'PY'
import re, pathlib
root = pathlib.Path('tiddlywiki/楹联丛话全编/tiddlers')
titles, tags = set(), set()
for p in root.rglob('*.tid'):
    t = p.read_text(encoding='utf-8')
    m = re.search(r'^title:\s*(.+)$', t, re.M)
    if m: titles.add(m.group(1).strip())
    m = re.search(r'^tags:\s*(.+)$', t, re.M)
    if m:
        for x in re.findall(r'\[\[(.+?)\]\]|(?<= )([^ ]+?)(?= |$)', m.group(1)):
            g = (x[0] or x[1]).strip()
            if g: tags.add(g)
print("TOC parents already existing (sample 40):")
print(sorted(t for t in titles & tags)[:40])
print("total existing parents:", len(titles & tags))
PY

# 3) 确认当前 TOC 节点数基线
grep -c 'tc-tiddler' tiddlywiki/oblique.html   # 或用之前的 verify 脚本里的 TOC 计数
```

### 判定规则

- 若 §6.2 列出的“已有同名 tiddler 的 tag”里**不包含** `楹联丛话/序` 这类 BOOK_SECTION tag
  → 说明 TOC 层级走的是**另一套** tag（如 `章节/…`、`条目/…`），锚点方案安全。
- 若**包含** → 锚点只能给**实体类型 tag**（`类型/规范名`）和**类型分类 tag** 用，
  **绝对不给** `BOOK_SECTION` / `BOOK` / `OTHER` 建同名 tiddler
  （或改用完全不同的标题，如 `索引/楹联丛话/序`，从而绝不与 TOC 父标题冲突）。

> 交接记录声称“TOC 关系使用 `章节/...`、`条目/...` tag，与实体 tag 分离”，
> 但**这一点尚未用 `toc.tid` 源码确认**，请务必实测。

---

## 7. 校验器需要新增的检查（`scripts/verify_tiddlywiki.py`）

在现有 9 项校验之后追加：

```python
ENTITY_PREFIXES = {
    "人名", "地点", "官职", "时间", "氏族", "朝代",
    "名物", "族群", "器物", "天文", "神祇", "生物",
    "典籍", "礼仪", "刑法", "思想", "身份", "数量",
}

# 1) 每个实体 tag `类型/规范名` 都有同名 tiddler
for tag in entity_tags:
    assert tag in titles, f"实体 tag 缺少同名 tiddler: {tag}"

# 2) 同名 tiddler 是实体 anchor，且指向真实实体页
#    anchor 正文必须含 [[实体/<tag>|...]]
# 3) anchor 未覆盖章节/联语/条目/系统 tiddler
# 4) anchor 未把自身 tag 打在自己身上（防自引用）
# 5) 类型分类 tag（ENTITY_PREFIXES 本身）也有同名 tiddler
# 6) 锚点数量 == 实体数量（一一对应，无多余）
```

**注意**：只输出计数与失败样本，**不要**打印全量 tag / 全量 tiddler 列表。

---

## 8. 最小验证流程（照此执行，别打印全量）

### 8.1 重新导出

```bash
cd /home/peter/GolandProjects/oblique
python3 scripts/export_tiddlywiki.py
```

### 8.2 检查两个文件存在

```bash
ls tiddlywiki/楹联丛话全编/tiddlers/典籍/古格言.tid        # 锚点（新增）
ls tiddlywiki/楹联丛话全编/tiddlers/实体/典籍/古格言.tid  # 原实体页（不变）
```

### 8.3 渲染单一条目，只看 300 字符窗口

渲染 `条目/1.1.1`，检查：

- `典籍/古格言` 不再带 `tc-tag-missing`
- 正文 `古格言` 链接仍解析（不是 `tc-tiddlylink-missing`）
- **只输出匹配点附近约 300 字符**，不输出整份 HTML

```bash
cd /home/peter/github.com/TiddlyWiki5
node ./tiddlywiki.js \
  '/home/peter/GolandProjects/oblique/tiddlywiki/楹联丛话全编' \
  --output /tmp/tw-check --rendertiddler 条目/1.1.1 render.html
grep -o 'tc-tag-missing' /tmp/tw-check/render.html | wc -l   # 期望 0
grep -o 'tc-tiddlylink-missing' /tmp/tw-check/render.html | wc -l   # 期望 0
```

### 8.4 跑校验器

```bash
cd /home/peter/GolandProjects/oblique
python3 scripts/verify_tiddlywiki.py
```

### 8.5 重建单文件

```bash
python3 scripts/build_tiddlywiki.py
```

### 8.6 筛选仍然有效（回归）

```bash
cd /home/peter/github.com/TiddlyWiki5
node ./tiddlywiki.js \
  '/home/peter/GolandProjects/oblique/tiddlywiki/楹联丛话全编' \
  --output /tmp/tw-check \
  --savetiddlers '[tag[典籍/古格言]]' hits
ls /tmp/tw-check/hits | head   # 期望：条目列表，且**不含**锚点 tiddler 自身
```

### 8.7 TOC 回归（关键）

对比修复前后的 TOC 节点数（基线约 **2,477**）与排序：

- 节点数不应因新增锚点而暴涨
- 紫色编号顺序不变
- `sortan[序]` 排序正常

### 8.8 提交前

```bash
cd /home/peter/GolandProjects/oblique
git status --short
git --no-pager diff --stat
```

---

## 9. 需要一并更新的文档

| 文件 | 要补的内容 |
|---|---|
| `README.md` | 说明“实体 tag 与实体 tiddler 标题不同名，锚点 tiddler 的作用” |
| `SPEC_楹联语义标注.md` | 命名规范章节补充 `类型/规范名`（tag） ↔ `实体/类型/规范名`（tiddler） ↔ `类型/规范名`（锚点）三者的关系 |
| `skills/**/SKILL_06*`（原交接提到的 SKILL_06） | 同上，加一句“实体 tag 必须有同名锚点 tiddler，否则 TiddlyWiki 显示 Missing tiddler” |
| `BOOK_楹联语义标注方法论.md` | 若有命名/标签规范章节，同步 |
| `docs/HANDOFF_实体tag-missing修复.md`（本文） | 实施完成后把 §1 状态改为“已修复”，并记录最终方案 |

---

## 10. 注意事项（务必遵守）

1. **不要**再次打印全部 tiddlers / 全部 tags / 完整 HTML。
   每次只输出：计数、文件名列表、或匹配点附近 **~300 字符**片段。
2. **不要**破坏以下已验证通过的机制：
   - `[tag[人名/林则徐]]` 等筛选语义
   - 紫色编号 TOC 的父标签链与排序
   - 正文实体 wikilink（`[[古格言|实体/典籍/古格言]]`）
   - `.tid` 头/正文空行规则
   - filter 参数括号配平检查（现有 3,332 个参数）
3. 写锚点前一律 `if anchor_title not in builder.tiddlers`，**绝不覆盖**。
4. 锚点**不要**给自己打 tag（自引用会污染筛选结果）。
5. 本轮结束时工作区应为干净状态；如需中断，先 `git stash` 或提交。

---

## 11. 已知未决问题清单（**已于 2026-11-12 全部结清**）

| # | 问题 | 状态 |
|---|---|---|
| Q1 | TOC 层级是否用 `children-of`（tag == 父 tiddler 标题）？ | ✅ **是**，但与实体标签不相交 → 无风险。`toc.tid` 用 `[all[shadows+tiddlers]tag<__tag__>…]`；本库 TOC 链仅 `TableOfContents`→`章节/*`→`条目/*`，与 missing tag 交集 = **0**。实测修复前后 TOC 逐字节一致。 |
| Q2 | 256 个 missing tag 中，BOOK_SECTION/BOOK/OTHER 共 237 个是否也需修？ | ✅ **都要修**，且实际数量远不止 256。TiddlyWiki 自己的 `[all[tiddlers]tags[]is[missing]]` 返回 **3,371** 个（3,108 实体 + 19 类型名 + 243 结构/分类 + 2 系统）。本次**全部**修掉，剩余 0。 |
| Q3 | “Missing tiddler” 文案是否出自 `core/ui/ListItemTemplate.tid`？ | ❌ **不是**。出自 `core/language/en-GB/Misc.multids` 的 `MissingTiddler/Hint`，由 `core/ui/ViewTemplate/body/default.tid`（及 `body/code.tid`）在 tiddler 缺失时 transclude。`ListItemTemplate.tid` 只有一行 `<div class="tc-menu-list-item"><$link /></div>`，与此文案无关。 |
| Q4 | 锚点用独立标记 tag（如 `实体索引`）还是复用 `实体`？ | ✅ **独立标记**：采用 `锚点`。复用 `实体` 会让 `[tag[实体]]` 的计数被 3,369 个锚点污染。 |
| Q5 | 新增 ~3,100 个锚点 tiddler 后单文件体积增量 | ✅ **实测**：8.17 MB → 9.87 MB，增量 **+1.70 MB**（+21%）。tiddler 数 8,623 → 11,992。 |

---

## 12. 关键文件索引

### 需读（本项目）

- `/home/peter/GolandProjects/oblique/scripts/export_tiddlywiki.py` — 实体生成处（标题 `实体/{prefix}/{name}`，约 820–900 行）
- `/home/peter/GolandProjects/oblique/scripts/verify_tiddlywiki.py` — 需加第 10+ 项校验
- `/home/peter/GolandProjects/oblique/scripts/build_tiddlywiki.py` — 单文件编译
- `/home/peter/GolandProjects/oblique/tiddlywiki/oblique.html` — 产物

### 需读（TiddlyWiki5 源码）

- `/home/peter/github.com/TiddlyWiki5/core/wiki/macros/tag.tid` — **`:24` 是 missing 判定源头**
- `/home/peter/github.com/TiddlyWiki5/core/ui/TagTemplate.tid` — 标签下拉面板
- `/home/peter/github.com/TiddlyWiki5/core/ui/Components/tag-link.tid` — 侧栏 tag 链接
- `/home/peter/github.com/TiddlyWiki5/core/ui/ListItemTemplate.tid` — **与 “Missing tiddler” 无关**（Q3 已更正）
- `/home/peter/github.com/TiddlyWiki5/core/language/en-GB/Misc.multids:69` — **“Missing tiddler” 文案的真正出处**（`MissingTiddler/Hint`）
- `/home/peter/github.com/TiddlyWiki5/core/ui/ViewTemplate/body/default.tid` — 缺失时 transclude 上述文案
- `/home/peter/github.com/TiddlyWiki5/core/modules/filters/is/missing.js` — `is[missing]` 只认真 tiddler，不认 shadow
- `/home/peter/github.com/TiddlyWiki5/core/wiki/macros/toc.tid` — **TOC 层级算子（Q1 关键）**
- `/home/peter/github.com/TiddlyWiki5/core/modules/filters/children.js` — `children-of` 实现
- `/home/peter/github.com/TiddlyWiki5/core/modules/widgets/link.js:79` — `tc-tiddlylink-missing`

### 样本数据（仅供核对，勿全量打印）

- `tiddlywiki/楹联丛话全编/tiddlers/条目/1.1.1.tid`
- `tiddlywiki/楹联丛话全编/tiddlers/实体/典籍/古格言.tid`

---

## 13. 相关历史提交

```
24309f3 fix(tw): 修复筛选器少一个 ] 导致的 "Filter error"，并加第 9 项校验
1e1a2f5 feat(tw): 用标准 TOC 宏生成侧栏紫色编号目录
2a053b5 fix(tw): 修正 .tid 头/正文分隔丢数据，并编译出单文件 oblique.html
2174d97 feat(tw): 导出《楹联丛话全编》为单个 TiddlyWiki（条目=tiddler，实体=tag）
7fe52ea docs(skills): 建立自足的 SKILL 操作手册体系
```

---

## 14. 实施记录（2026-11-12）

### 14.1 改了什么

| 文件 | 改动 |
|---|---|
| `scripts/export_tiddlywiki.py` | 新增 `ANCHOR_TAG` / `ANCHOR_DIR` 常量、`related_list()` 与 `build_anchor_tiddlers()` 函数；`TiddlyWikiBuilder.add()` 增加 `anchor` 参数，`write()` 把锚点落到 `tiddlers/锚点/` 目录；`main()` 在全部 tiddler 登记完毕后调用建锚点；锚点清单用 `<$genesis>` 生成 `<ul>`/`<li>`（一项一行），并加 `tc-anchor-list` / `tc-anchor-item` 样式 |
| `scripts/verify_tiddlywiki.py` | 新增第 10 / 10b / 10c / 10d / 10e 项校验 |
| `README.md` | 补「标签锚点」一节 + tiddler 模型表加 `锚点/` 行 + 校验输出 |
| `SPEC_楹联语义标注.md` | 新增 §8.3「三名关系」与 §8.4「锚点页的正文」，后续小节重新编号 |
| `skills/SKILL_06_语料构建与渲染.md` | 新增「坑六 / 坑七 / 坑八 / 坑九」+ 校验输出 |
| `docs/HANDOFF_实体tag-missing修复.md` | 本文：状态改为已修复、§11 问题清单结清、§12 索引更正、本节 |

### 14.2 锚点是怎么建的

1. 收集**全部已用标签**（含实体标签、类型名标签、书名 / 门类 / 联语类型等结构标签）；
2. 跳过已有同名 tiddler 的标签、跳过 `$:/` 系统标签；
3. 为其余标签各建一个 tiddler，**标题 = 标签名**，
   正文用**筛选器**动态列出该标签关联的全部内容：
   - 实体标签 → 相关条目、相关联语（+ 规范页链接）；
   - 类型名标签（`人名` `典籍` …）→ 该类型下的全部实体（+ 实体索引链接）；
   - 结构 / 分类标签（`楹联丛话` `楹联丛话/序` `挽联` …）→
     相关章节、相关条目、相关联语、相关实体（+ 首页链接）；
   - 每个小节标注条数，空的小节自动省略；
4. 锚点只挂 `锚点` 一个标记标签，**绝不挂自己的同名标签**（否则 `[tag[…]]` 筛选会多出锚点本身）。

### 14.3 实现中踩到的三个 TiddlyWiki 坑（已写进 SPEC §8.4 / SKILL_06 坑七·八·九）

| 坑 | 现象 | 规避 |
|---|---|---|
| `<$list>` 起 `variable` | 列表项的 `currentTiddler` 上下文丢失，链接全变 `tc-tiddlylink-missing` | 不给 `<$list>` 起 `variable`；链接目标用 `<<currentTiddler>>` 而非 `{{!!title}}` |
| `<$genesis>` 的 `$type` 写成变量 | 属性右值 `>>` 的后一个 `>` 被并进属性值，整个标签泄漏成纯文本 | `$type` 写字面量（`$type="ul"` / `$type="li"`） |
| `<<list-links>>` 宏 | `class=<<__class__>>` 在 `__class__` 为空时同样触发上述解析问题，列表渲染为空 | 改用原生 `<$list>` + `<$genesis>` + `<$link>` 构件 |

**清单一项一行**：裸 `<$list>` 的多个链接会挤在同一行（`<a>…</a><a>…</a>`），
所以每项都套一层 `<$genesis $type="li">`，外面再包 `<$genesis $type="ul">`，
并配 `tc-anchor-list` / `tc-anchor-item` 两个 CSS 类（去项目符号、缩进对齐、收紧行距）。

实测确认（用 TiddlyWiki 自身的 `core/ui/Components/tag-link` 与正文渲染）：

| 锚点 | 渲染大小 | `<li>` 行数 | 链接数 | `tc-tiddlylink-missing` |
|---|---|---|---|---|
| `典籍/古格言` | 1 KB | 1 | 2 | **0** |
| `楹联丛话/序` | 1 KB | 2 | 3 | **0** |
| `典籍` | 151 KB | 901 | 902 | **0** |
| `楹联丛话` | 305 KB | 2,124 | 2,125 | **0** |
| `实体` | 400 KB | 3,108 | 3,109 | **0** |
| `锚点` | 382 KB | 3,368 | 3,369 | **0** |

（链接数 = `<li>` 行数 + 1，多出来的那一个是末尾的「规范页 / 首页 / 索引」链接，
它不属于清单。）

### 14.4 验证结果

```
✓ 0. 全部 .tid 的头/正文分隔正确
✓ 1. 无重复标题
✓ 2. 全部 25,368 处内部链接均可解析
✓ 3. 3,545 个实体标签均有对应 tiddler
✓ 4. 全部 2,254 个源段落均已导出
✓ 5. 全部 3,020 副联语均已导出
✓ 6. 2,254 个条目的实体 tag 与正文标注一致
✓ 7. 紫色编号目录完整（2,477 个节点）
✓ 8. 目录排序正确
✓ 9. 筛选器参数括号全部配平（7,389 处）
✓ 10. 全部 3,595 个标签均有同名 tiddler
✓ 10b. 3,369 个锚点 tiddler 指向有效，且无自引用标签
✓ 10c. 锚点正文无 “Missing tiddler” 残留
✓ 10d. 4,057 个锚点筛选器都能选出存在的 tiddler（且排序字段有效）
✓ 10e. 4,057 个锚点清单均一项一行（<li> 包裹）
全部校验通过 ✓
```

回归（修复前 vs 修复后，用同一份数据各自导出一份 wiki 对比）：

| 项目 | 修复前 | 修复后 | 结论 |
|---|---|---|---|
| TOC 节点数 | 2,477 | 2,477 | ✅ 不变 |
| TOC 顺序 + `序` + `caption` | md5 `6230bba3…` | md5 `6230bba3…` | ✅ **逐字节一致** |
| `[tag[…]]` 筛选（12 个代表标签） | — | — | ✅ 结果集合完全相同（锚点未污染筛选） |
| 标签链接 class | `tc-tiddlylink-missing` | `tc-tiddlylink-resolves` | ✅ 症状消除 |
| 标签页正文 | `Missing tiddler "…"` | 锚点页正文 | ✅ 症状消除 |
| 单文件体积 | 8.17 MB | 9.87 MB | +1.70 MB（+21%） |

### 14.5 遗留说明

- 剩余 2 个 `$:/` 系统标签（`$:/tags/SideBar`、`$:/tags/Stylesheet`）**仍然**没有同名 tiddler。
  它们是 TiddlyWiki 的机制标签，由核心 / 主题提供，**不在本项目责任范围内**；
  实测它们不会出现在任何标签胶囊里（`TableOfContents` 与 `样式/紫色编号` 的 ViewTemplate 渲染中
  `tc-tag-missing` 计数为 0），因此无需处理。
  校验器第 10 项已显式排除 `$:/` 前缀。
- 锚点页正文里刻意**不写** “Missing tiddler” 字样（避免页面自身误导读者），
  校验器第 10c 项对此做了断言。
