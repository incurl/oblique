---
name: skill-02
title: 结构切分与段落编号
description: 把纯文本解析成 书/卷/门类/条目/段落 五级树，并分配永久段落编号（Purple Numbers）与 HTML 锚点。当需要给古籍建立可引用的结构、处理排版断行、或重建目录时使用。
version: 1.0
last_updated: 2026-11-10
---

# SKILL 02: 结构切分与段落编号

> **核心理念**：**结构错了，后面全错。**
> 这是整条管线里唯一"看起来没产出、但必须最先做"的一步。

---

## 一、任务定义

### 1.1 何时使用

- 拿到纯文本，要建立可引用的段落单元
- 文本有排版断行（一段被拆成多行）
- 需要给每个节点一个永远不变的编号

### 1.2 输入与产出

| | 内容 |
|---|---|
| 输入 | 分层后的源文本（见 SKILL_01） |
| 产出 | `structure.json` + 正文中的 `[1.3.1]` 编号与 `<a id="pn-1.3.1">` 锚点 |
| 前置 | [SKILL_01](SKILL_01_底本分层与符号原则.md) |
| 后继 | [SKILL_03](SKILL_03_实体标注.md)、[SKILL_04](SKILL_04_联语识别.md) |

### 1.3 成功标准

- [ ] 正文段落数（校验口径）与源文件可逐行对齐
- [ ] 每个节点有唯一编号与锚点
- [ ] 续行已并入父段落，未虚增段落数

**当前基线**：正文缩进段落 2,244 个，其中 31 个段落带续行（续行共 36 行），
另有作者小传 9 行，校验口径合计 **2,289** 行（9 + 2,244 + 36）。

---

## 二、五级结构

### 2.1 层级与编号

| 层级 | 编号 | 例 | 锚点 |
|---|---|---|---|
| 全书 | `[0]` | 楹联丛话全编 | `#pn-0` |
| 书 | `[1]` | 楹联丛话 | `#pn-1` |
| 卷 | `[3.2]` | 卷上 | `#pn-3.2` |
| 门类 section | `[1.3]` | 故事 | `#pn-1.3` |
| 条目标题 entry | `[3.2.1]` | 扬州旧联 | `#pn-3.2.1` |
| 段落 | `[1.3.1]` | 故事门第一则 | `#pn-1.3.1` |
| **续行** | `[1.3.1.1]` | 源文件断行的后半 | `#pn-1.3.1.1` |

### 2.2 编号规则

**由位置决定，不由人工指定。**

```python
def _assign_child_ids(parent: Node) -> None:
    """同一父节点下的所有子节点共用一个序号。"""
    for i, child in enumerate(parent.children, 1):
        child.id = f"{parent.id}.{i}"
        _assign_child_ids(child)
```

**为什么不用"每种类型各编一套号"**：
早期实现按 kind 分别计数，导致 `section` 与 `volume` 都拿到 `3.1`，
出现**重复编号**。改为"同一父节点共用一个计数器"后消失。

---

## 三、解析规则

### 3.1 识别信号：排版而非语义

联话原文的层级**靠排版区分**，不靠内容：

```
第 1 层  书名        楹联丛话            ← 无缩进，已知行号
第 2 层  卷 / 门类   卷之一 / 故事        ← 无缩进，已知行号
第 3 层  条目标题    扬州旧联            ← 无缩进，短行
第 4 层  段落        \t尝闻纪文达师言…   ← 以制表符开头
```

| 判据 | 规则 |
|---|---|
| 新段落 | 行首是制表符 `\t` |
| 已知标题 | 命中行号表 `HEADINGS` |
| **续行** | 非缩进，以句末标点结尾，**或**长度 ≥ 24 |
| 条目标题 | 非缩进、短行（< 24 字）、不以句末标点结尾 |

### 3.2 为什么需要"续行"这一级

电子本把个别段落拆成了两行。例（第 583–584 行是同一段）：

```
583: \t昌平陈紫澜宫詹浩与钱唐陈句山太仆兆仑并负重名……
584: 心廷璋、陆费丹叔墀、谢蕴山启昆诸公，皆有跋。以一联而集成巨观……
```

若不处理，第 584 行会被当成独立段落 → **段落数虚增、引用失准**。

**解法**：给续行分配"父编号 + `.n`"后缀。

### 3.3 三话/散话的特例

不同书的编排方式不同：

| 书 | 编排 | 解析影响 |
|---|---|---|
| 楹联丛话 / 续话 / 四话 | 门类下直接是段落 | 用 `HEADINGS` 判门类 |
| **楹联三话 / 散话** | 每条先有一个小标题 | 非缩进短行 = 条目 `entry` |
| 巧对录 / 续录 | 卷下直接是段落 | 「卷之X」行 = `volume` |

**统一规则**：非缩进短行 → `entry`。
结果自然分化，不必为每部书写一套解析器。

---

## 四、代码骨架

```python
from dataclasses import dataclass, field

@dataclass
class Node:
    kind: str          # book / volume / section / entry / paragraph / note
    text: str
    line_no: int
    children: list["Node"] = field(default_factory=list)
    cont: list[tuple[int, str]] = field(default_factory=list)  # 续行
    id: str = ""


def parse_document(lines):
    books = []
    cur = {k: None for k in ("book", "volume", "section", "entry", "para")}

    for idx in range(88, len(lines)):        # 第 89 行起是正文
        no, raw = idx + 1, lines[idx]
        if not raw.strip():
            continue

        # ① 进入新书（行号命中 BOOKS）
        # ② 已知标题（行号命中 HEADINGS）
        # ③ 缩进行 → 新段落
        # ④ 非缩进长行/句末标点 → 续行，挂到当前段落
        # ⑤ 非缩进短行 → 条目标题
        ...
    return doc
```

完整实现见 `scripts/yinglian_lib.py` 的 `parse_document()`。

---

## 五、禁止事项与推荐做法

### 5.1 禁止

❌ **人工指定编号** —— 一旦插入新章节，后续全部要重排，等于编号不可信。

❌ **按 kind 分别计数** —— 会造成不同类型拿到相同编号（真实踩过的坑）。

❌ **把续行当独立段落** —— 段落数虚增，引用错位。

❌ **让 Fenced Div 跨越标题** —— 块与标题是同级结构，跨了会破坏解析。

### 5.2 推荐

✅ **行号常量集中管理** —— `BOOKS`、`HEADINGS` 写在模块顶部，便于核对。

✅ **编号由脚本确定性生成** —— 任何人重跑得到同一套编号。

✅ **同时记源行号** —— `structure.json` 存 `line_no`，
即使编号将来变化，也能回溯原文位置。

✅ **目录由结构树生成** —— 而不是手工维护一份。

---

## 六、工具与脚本

| 脚本 | 功能 |
|---|---|
| `scripts/yinglian_lib.py` → `parse_document()` | 解析为 Document 树 |
| `scripts/annotate_yinglian.py` → `build_structure()` | 输出 `structure.json` |

**`structure.json` 的节点结构**：

```json
{
  "id": "1.3",
  "kind": "section",
  "line_no": 93,
  "title": "故事",
  "children": [
    {
      "id": "1.3.1",
      "kind": "paragraph",
      "line_no": 94,
      "preview": "尝闻纪文达师言：楹帖始于桃符…",
      "chars": 180,
      "children": []
    }
  ]
}
```

> `preview` 只存 80 字。完整正文在 `.tagged.md` 里，
> 结构索引只需要"认得出"，不需要重复存储。

---

## 七、检查清单

### 7.1 执行前

- [ ] SKILL_01 的分层结论已确定（目录/正文/附注的行号区间）
- [ ] 已确认哪些书用条目标题编排

### 7.2 执行后

- [ ] `paragraph` 数 == 源文件缩进行数
- [ ] `cont` 总数 == 非缩进续行数（当前 31 段）
- [ ] 每个 `id` 全局唯一（用 `collections.Counter` 查重复）
- [ ] `structure.json` 中 `line_no` 单调递增
- [ ] 校验口径段落数 == 2,289

**快速自检**：

```bash
python3 - <<'PY'
import sys, collections; sys.path.insert(0,'scripts')
from yinglian_lib import parse_document
d = parse_document()
ids = [n.id for n in d.walk()]
dup = [k for k,v in collections.Counter(ids).items() if v>1]
print('重复编号:', dup or '无')
print('段落:', sum(1 for n in d.walk() if n.kind=='paragraph'))
print('含续行:', sum(1 for n in d.walk() if n.kind=='paragraph' and n.cont))
PY
```

---

## 八、FAQ

**Q：编号会变吗？改了前面会不会全乱？**
A：会。这是"位置决定编号"的固有代价。
缓解：① 编号由脚本生成，任何时候可重算；
② `structure.json` 记了源行号，可回溯。
若某条引用必须永久稳定，**引用源行号 + 段落首句**，不要只引编号。

**Q：为什么不直接把每段存成一个文件？**
A：2,289 个文件无法人读、diff 不可控。
单文件 + 编号，是"可读性"与"可引用性"的平衡。

**Q：`kind` 为什么有 `note`？**
A：整理者校注不是正常段落（不能按联语扫描、不该计入正文统计），
单列一类便于区别对待。

---

## 九、相关

- 上游：[SKILL_01 底本分层与符号原则](SKILL_01_底本分层与符号原则.md)
- 下游：[SKILL_03 实体标注](SKILL_03_实体标注.md)、[SKILL_04 联语识别](SKILL_04_联语识别.md)
- 规范：[../SPEC_楹联语义标注.md](../SPEC_楹联语义标注.md) §三
