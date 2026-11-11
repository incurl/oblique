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
| — | 首页与索引 | 5 | `楹联丛话全编`、`实体索引` |

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

导出目录本身即是标准 TiddlyWiki 目录（含 `tiddlywiki.info` 与 `tiddlers/`），
用任意 TiddlyWiki 5 即可打包或启动服务：

```bash
# 用本地的 TiddlyWiki5 打包成单个 HTML
node /path/to/TiddlyWiki5/tiddlywiki.js tiddlywiki/楹联丛话全编 \
     --output dist --build index

# 或者启动本地服务浏览
node /path/to/TiddlyWiki5/tiddlywiki.js tiddlywiki/楹联丛话全编 --listen
```

### 校验

`scripts/verify_tiddlywiki.py` 用**独立于导出器**的数据源（`structure.json`、
`couplets.json`）交叉核对导出结果：

```
✓ 1. 无重复标题
✓ 2. 全部 21,999 处内部链接均可解析
✓ 3. 3,322 个实体标签均有对应 tiddler
✓ 4. 全部 2,254 个源段落均已导出
✓ 5. 全部 3,020 副联语均已导出
✓ 6. 2,254 个条目的实体 tag 与正文标注一致
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
  export_tiddlywiki.py    导出 TiddlyWiki
  verify_tiddlywiki.py    导出结果校验
data/                     标注产物
docs/                     预览页
tiddlywiki/楹联丛话全编/  TiddlyWiki 导出（tiddlers/ + tiddlywiki.info）
```
