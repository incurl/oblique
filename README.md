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
```

## 产物

| 文件 | 内容 |
|---|---|
| `data/楹联丛话全编.tagged.md` | 标注正文（1.2 MB，7,967 行） |
| `data/entities.json` | 13,135 处实体标注 / 2,979 个规范名 |
| `data/couplets.json` | 3,021 副联语（上下联、类型、作者线索、出处） |
| `data/structure.json` | 9 部书 / 卷 / 门类 / 条目结构 |
| `docs/index.html` | 静态 HTML 预览（实体按类型着色） |

当前统计：

```
源文件          2,588 行 / 332,547 字
正文段落        2,289 段
实体标注        13,135 处
联语            3,021 副
结构块          96 个
```

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

完整规范见 [`SPEC_楹联语义标注.md`](SPEC_楹联语义标注.md)。

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
data/                     标注产物
docs/                     预览页
```
