# oblique · 《楹联丛话全编》语义标注

把清代梁章钜《楹联丛话全编》从纯文本转化为可检索、可引用的语义标注语料。

标注体系参考 [shiji-kb](https://github.com/shiji-kb)：

- **Purple Numbers**：书 / 卷 / 门类 / 条目 / 段落永久编号；
- **18 类名词实体**：`〖@人名〗`、`〖=地名〗`、`〖;官职〗`、`〖%时间〗`、`〖{典籍〗` 等；
- **联语层**：`〖聯〗` 前置标记 + `data/couplets.json` 上下联语料；
- **Fenced Div**：`::: 序`、`::: 小传`、`::: 校注`、`::: 联`；
- **文本完整性校验**：去除全部标记后与源文件逐字比对。

## 快速开始

```bash
python3 scripts/annotate_yinglian.py   # 生成标注正文与索引
python3 scripts/lint_text_integrity.py # 校验“只加标记，不改原文”
python3 scripts/render_yinglian.py     # 生成 docs/index.html 预览
python3 scripts/export_tiddlywiki.py   # 导出 TiddlyWiki（条目为 tiddler，实体为 tag）
python3 scripts/verify_tiddlywiki.py   # 校验导出结果自洽
```

## 产物

| 文件 | 内容 |
|---|---|
| `data/楹联丛话全编.tagged.md` | 标注正文（1.2 MB，7,967 行） |
| `data/entities.json` | 13,135 处实体标注 / 2,979 个规范名 |
| `data/couplets.json` | 3,020 副联语（上下联、类型、作者线索、出处） |
| `data/structure.json` | 9 部书 / 卷 / 门类 / 条目结构 |
| `docs/index.html` | 静态 HTML 预览（实体按类型着色） |
| `tiddlywiki/楹联丛话全编/` | **TiddlyWiki 导出**（8,610 个 tiddler，可直接打开/服务端浏览） |
| `SPEC_楹联语义标注.md` | 标注规范：符号体系、字段定义、校验方法、已知限制 |
| `BOOK_楹联语义标注方法论.md` | **配套方法论**：20 章六编，讲清"为什么这么做"与"哪些做法被证伪" |
| `skills/` | **操作手册**：11 篇 SKILL，从底本分层到迁移到新书，自成闭环 |


当前统计：

```
源文件          2,588 行 / 332,547 字
正文段落        2,289 段
实体标注        13,135 处
联语            3,020 副
结构块          96 个
```

## TiddlyWiki 导出

`scripts/export_tiddlywiki.py` 把标注语料导出为**单个 TiddlyWiki**：
原文条目是 tiddler，实体是 tag，因此可以直接用 TiddlyWiki 的筛选器做交叉检索。

### tiddler 模型

| 前缀 | 含义 | 数量 | 典型标题 |
|---|---|---|---|
| `条目/` | 原文条目（段落级） | 2,254 | `条目/1.3.1` |
| `联语/` | 单副联语 | 3,020 | `联语/C0002` |
| `实体/` | 规范名实体 | 3,108 | `实体/人名/林则徐` |
| `章节/` | 书 / 卷 / 门类 / 条目导航 | 223 | `章节/1.3` |
| `锚点/` | 与标签同名的锚点页（见下） | 3,369 | `典籍/古格言` |
| — | 首页与索引 | 5 | `楹联丛话全编`、`实体索引` |
| — | 侧栏目录（TOC） | 2 | `TableOfContents`、`样式/紫色编号` |

### 标签锚点：为什么实体标签要多一个同名页

TiddlyWiki 的**标签胶囊**用**标签名本身**去查同名 tiddler，
以此判断标签「存在」还是「缺失」
（`core/wiki/macros/tag.tid` 的 `[<__tag__>is[missing]then[tc-tag-missing]else[tc-tag-exists]]`；
`is[missing]` 只认真 tiddler，不认 shadow）。

本项目的实体标签叫 `典籍/古格言`，真正的实体页却叫 `实体/典籍/古格言`——
**名字对不上**，于是三千多个标签一律被渲染成缺失样式，点进去只剩一句
"Missing tiddler …"。

修法是给每个标签补一个**与标签同名**的轻量锚点 tiddler，
**不重命名**现有实体 tiddler：

| | 名称 | 说明 |
|---|---|---|
| 实体标签 | `典籍/古格言` | 挂在条目 / 联语上，用于 `[tag[…]]` 筛选 |
| 实体页 | `实体/典籍/古格言` | 规范页：出现次数、别名、出现位置 |
| 锚点页 | `典籍/古格言` | **与标签同名**，动态列出该标签的全部相关内容 |

锚点页正文不是静态链接，而是**筛选器**驱动的清单：

| 锚点类型 | 正文列出 |
|---|---|
| 实体（`典籍/古格言`） | 相关条目、相关联语 + 规范页链接 |
| 类型（`典籍`） | 该类型下的全部实体 + 实体索引链接 |
| 结构（`楹联丛话`、`楹联丛话/序`、`挽联`） | 相关章节、相关条目、相关联语、相关实体 |

每个小节都标注条数，空的小节自动省略：

```
!! 相关条目（1）

<$list filter="[tag[典籍/古格言]prefix[条目/]sort[序]]">…</$list>
```

锚点 tiddler 存在 `tiddlers/锚点/` 目录下（**仅是文件路径**，
标题仍是标签名本身），只挂一个 `锚点` 标记标签，
**不给自己打同名标签**——否则 `[tag[典籍/古格言]]` 会把锚点也捞进筛选结果。

### 紫色编号目录

侧栏首位是「目录」标签页，用 TiddlyWiki **标准目录宏**
（`<<toc-selective-expandable>>`）生成，层级按《楹联丛话全编》原编号：

```
0 作者简介
1 楹联丛话
  1.3 故事
    1.3.1  尝闻纪文达师言：楹帖始于桃符……
```

紫色编号沿用语料原有编号体系（`structure.json` 的节点 id），不重新编号。
目录节点之间用**标签**表达父子关系（标准机制所要求的），
并用零填充的 `序` 字段保证 `1.3.2` 排在 `1.3.10` 之前。

### 标签体系

| 标签 | 含义 | 示例 |
|---|---|---|
| `条目` `联语` `实体` `章节` | 类别 | `[tag[条目]]` |
| `书名` | 所属著作 | `楹联丛话` |
| `书名/门类` | 所属门类 | `楹联丛话/故事` |
| `人名/规范名` | 人名实体 | `人名/林则徐` |
| `地点/规范名` | 地点实体 | `地点/扬州` |
| `官职` `时间` `氏族` `朝代` `名物` `典籍` … | 其余 18 类实体 | `典籍/蜀梼杌` |
| `联语类型` | 庙联、挽联、春联… | `挽联` |

### 筛选示例

```
[tag[人名/林则徐]]              所有提到林则徐的条目
[tag[人名/林则徐]tag[楹联丛话]]  限定在《楹联丛话》
[tag[地点/扬州]]                所有提到扬州的条目
[tag[挽联]]                      所有挽语
[tag[楹联丛话/故事]]             《楹联丛话·故事》门类
```

### 构建单文件 wiki

`scripts/build_tiddlywiki.py` 把导出目录编译成**单个自包含 HTML**，
双击即可在浏览器打开，无需服务器、无需联网：

```bash
python3 scripts/build_tiddlywiki.py
# → tiddlywiki/oblique.html（约 8.2 MB）

# 指定 TiddlyWiki5 源码目录（默认自动查找，也可用环境变量 TIDDLYWIKI5）
python3 scripts/build_tiddlywiki.py --tw /path/to/TiddlyWiki5
```

脚本会在打包后自动核对：单文件里是否装下了全部 tiddler、
`$:/SiteTitle` / `$:/DefaultTiddlers` 是否生效、是否带上了中文语言包。

也可以直接用 TiddlyWiki 5 打包，或启动本地服务浏览：

```bash
node /path/to/TiddlyWiki5/tiddlywiki.js tiddlywiki/楹联丛话全编 \
     --output dist --build index

node /path/to/TiddlyWiki5/tiddlywiki.js tiddlywiki/楹联丛话全编 --listen
```

### 校验

`scripts/verify_tiddlywiki.py` 用**独立于导出器**的数据源（`structure.json`、
`couplets.json`）交叉核对导出结果：

```
✓ 0. 全部 .tid 的头/正文分隔正确（正文不会被当成字段吞掉）
✓ 1. 无重复标题
✓ 2. 全部 25,368 处内部链接均可解析
✓ 3. 3,545 个实体标签均有对应 tiddler
✓ 4. 全部 2,254 个源段落均已导出
✓ 5. 全部 3,020 副联语均已导出
✓ 6. 2,254 个条目的实体 tag 与正文标注一致
✓ 7. 紫色编号目录完整（2,477 个节点，父子标签关系全部正确）
✓ 8. 目录排序正确（224 个父节点下，同级「序」与紫色编号一致）
✓ 9. 筛选器参数括号全部配平（7,389 处）
✓ 10. 全部 3,595 个标签均有同名 tiddler（标签不会显示 Missing tiddler）
✓ 10b. 3,369 个锚点 tiddler 指向有效，且无自引用标签
✓ 10c. 锚点正文无 “Missing tiddler” 残留
✓ 10d. 4,057 个锚点筛选器都能选出存在的 tiddler（且排序字段有效）
```

> TiddlyWiki 导出是**派生视图**，不替代标注 Markdown；
> 权威语料仍以 `data/楹联丛话全编.tagged.md` 为准。


## 标注示例

```markdown
<a id="pn-1.3.1"></a>
[1.3.1] 尝闻〖@纪文达|纪昀〗师言：〖^楹帖〗始于〖^桃符〗，蜀〖@孟昶〗“余庆”“长春”一联最古。
……自命笔云：〖聯〗“新年纳余庆；嘉节号长春。”〖◆后蜀〗平，朝廷以〖@吕余庆〗知〖=成都〗。
```

- `〖@纪文达|纪昀〗`：显示“纪文达”，索引归到“纪昀”；
- `〖聯〗`：其后引号内是一副联语，上下联以 `；` 分隔；
- `[1.3.1]`：可点击的 Purple Number，锚点为 `#pn-1.3.1`。

## 规范与限制

完整规范见 [`SPEC_楹联语义标注.md`](SPEC_楹联语义标注.md)；
方法论与设计理由见 [`BOOK_楹联语义标注方法论.md`](BOOK_楹联语义标注方法论.md)；
具体操作步骤见 [`skills/INDEX.md`](skills/INDEX.md)。

要点：

- 只加标记，不改原文；校验脚本逐段比对；
- 实体识别是词典 + 规则驱动，高精度但非全量；
- `couplets.json` 的 `author` 是高精度线索，`author_near` 是最近人名线索，均需人工复核；
- 动词层 `⟦◈⟧` 语法已预留，暂未启用。

## 目录

```
scripts/
  yinglian_dict.py        词典
  yinglian_lib.py         解析 / 标注引擎
  annotate_yinglian.py    生成 Markdown 与 JSON
  lint_text_integrity.py  完整性校验
  render_yinglian.py      HTML 预览
  export_tiddlywiki.py    导出 TiddlyWiki（.tid 目录）
  verify_tiddlywiki.py    导出结果校验
  build_tiddlywiki.py     编译成单文件 HTML
data/                     标注产物
docs/                     预览页
tiddlywiki/oblique.html   单文件 wiki（交付物，约 8.2 MB）
tiddlywiki/楹联丛话全编/  TiddlyWiki 导出（中间产物，不入版本库）
```
