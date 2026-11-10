#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把带标记的 Markdown 渲染为静态 HTML 预览。

用法：
    python3 scripts/render_yinglian.py
    python3 scripts/render_yinglian.py --out docs/index.html
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

import markdown

from yinglian_lib import DATA_DIR, ROOT

TAGGED_PATH = DATA_DIR / "楹联丛话全编.tagged.md"
DEFAULT_OUT = ROOT / "docs" / "index.html"

TYPE_CLASS = {
    "@": ("person", "人名", "#8B4513"),
    "=": ("place", "地名", "#B8860B"),
    ";": ("official", "官职", "#8B0000"),
    "%": ("time", "时间", "#008B8B"),
    "&": ("clan", "氏族", "#9370DB"),
    "◆": ("state", "朝代/邦国", "#4B0082"),
    "^": ("term", "名物/制度", "#4682B4"),
    "~": ("tribe", "族群", "#2F4F4F"),
    "•": ("artifact", "器物", "#CD853F"),
    "!": ("astro", "天文", "#483D8B"),
    "?": ("deity", "神祇", "#8B008B"),
    "+": ("biology", "生物", "#228B22"),
    "{": ("book", "典籍", "#8B4513"),
    ":": ("ritual", "礼仪", "#DAA520"),
    "[": ("law", "刑法", "#B22222"),
    "_": ("concept", "思想", "#708090"),
    "#": ("identity", "身份", "#DC143C"),
    "$": ("quantity", "数量", "#4169E1"),
}

BLOCK_CLASS = {
    "序": "preface",
    "小传": "bio",
    "校注": "note",
    "联": "couplet-block",
}


def replace_entities(text: str) -> str:
    """把轻量标记替换为带 class/title 的 span。"""

    def noun(m: re.Match[str]) -> str:
        type_ = m.group(1)
        body = m.group(2)
        canonical = m.group(3)
        display, _, _ = body.partition("|")
        cls, name, color = TYPE_CLASS.get(type_, ("unknown", type_, "#666"))
        title = name + (f" · {canonical}" if canonical else "")
        return (
            f'<span class="ent {cls}" style="--c:{color}" '
            f'title="{html.escape(title, quote=True)}">{html.escape(display)}</span>'
        )

    text = re.sub(
        r"〖([@=;%&◆^~•!?+{:[_#$])([^〗|]*)(?:\|([^〗]*))?〗",
        noun,
        text,
    )
    text = text.replace("〖聯〗", '<span class="lian" title="联语">聯</span>')
    text = text.replace("〖對〗", '<span class="lian" title="巧对">對</span>')
    text = re.sub(
        r"〘(.)([^〙]*)〙",
        r'<span class="chengyu" title="成语">\2</span>',
        text,
    )
    text = re.sub(
        r"⟦(.)([^⟧]*)⟧",
        r'<span class="verb" title="动词">\2</span>',
        text,
    )
    return text


def convert_blocks(md: str) -> str:
    """把 ::: 标签 转成 <div markdown=1>。"""
    lines = md.splitlines()
    out: list[str] = []
    stack: list[str] = []
    for line in lines:
        if line.startswith(":::"):
            tag = line[3:].strip()
            if tag:
                cls = BLOCK_CLASS.get(tag, "custom")
                out.append(
                    f'<div class="block {cls}" data-tag="{html.escape(tag, quote=True)}" markdown="1">'
                )
                stack.append(tag)
            else:
                if stack:
                    out.append("</div>")
                    stack.pop()
        else:
            out.append(line)
    while stack:
        out.append("</div>")
        stack.pop()
    return "\n".join(out)


def strip_front_matter(md: str) -> str:
    if not md.startswith("---\n"):
        return md
    end = md.find("\n---\n", 4)
    if end == -1:
        return md
    return md[end + 5:]


def add_purple_numbers(md: str) -> str:
    """把行首 [1.2.3] 变成可点击的紫色编号。"""

    def repl(m: re.Match[str]) -> str:
        pid = m.group(1)
        return f'<a class="pn" href="#pn-{pid}">{pid}</a> '

    return re.sub(r"^\[([0-9.]+)\] ", repl, md, flags=re.MULTILINE)


CSS = """
:root { --bg:#fbfaf7; --fg:#2b2b2b; --muted:#777; --line:#e5e0d8; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
  font-family: "Noto Serif SC","Songti SC","STSong",serif; line-height:1.9; }
header { padding:2rem max(1rem,8vw) 1rem; border-bottom:1px solid var(--line); }
header h1 { margin:0 0 .4rem; font-size:1.8rem; letter-spacing:.08em; }
header p { margin:.2rem 0; color:var(--muted); }
main { max-width: 980px; margin: 0 auto; padding: 1.5rem 1rem 6rem; }
h1,h2,h3,h4 { font-weight:600; line-height:1.4; }
h1 { font-size:1.7rem; margin:2.2rem 0 1rem; }
h2 { font-size:1.4rem; margin:2rem 0 .8rem; border-left:4px solid #b08d57; padding-left:.6rem; }
h3 { font-size:1.18rem; margin:1.6rem 0 .6rem; color:#5a4632; }
h4 { font-size:1.05rem; margin:1.2rem 0 .4rem; color:#6b5540; }
p { margin:.55rem 0; text-align:justify; }
a { color:#8a5a2b; text-decoration:none; }
a:hover { text-decoration:underline; }
.pn { font-family: ui-monospace,monospace; font-size:.72em; color:#9b7bb5;
  vertical-align:.15em; margin-right:.15em; }
.ent { border-bottom:1px dashed var(--c,#999); color:var(--c,#333);
  padding:0 .05em; cursor:help; }
.ent:hover { background:color-mix(in srgb, var(--c) 12%, transparent); }
.lian { display:inline-block; font-size:.66em; color:#fff; background:#b08d57;
  border-radius:3px; padding:0 .3em; margin-right:.15em; vertical-align:.18em;
  font-family: ui-monospace,monospace; }
.chengyu { background:#fff1c9; border-bottom:1px solid #d9b44a; padding:0 .08em; }
.verb { color:#7a4b8a; border-bottom:1px dotted #7a4b8a; }
.block { margin:1rem 0; padding:.8rem 1rem; border-radius:6px; }
.block.preface { background:#f6f1e7; border-left:4px solid #b08d57; }
.block.bio { background:#eef4f8; border-left:4px solid #6e8fa8; }
.block.note { background:#f7f2f7; border-left:4px solid #9b7bb5; font-size:.92em; }
.block.couplet-block { background:#fbf6ea; border:1px solid #eadcc2; }
table { border-collapse:collapse; width:100%; margin:1rem 0; font-size:.92rem; }
th,td { border:1px solid var(--line); padding:.35rem .5rem; text-align:left; }
th { background:#f1ece2; }
blockquote { margin:1rem 0; padding:.5rem 1rem; border-left:3px solid #d8cdbb;
  color:#666; background:#faf7f1; }
hr { border:0; border-top:1px solid var(--line); margin:2rem 0; }
.toc ul { padding-left:1.2rem; }
footer { max-width:980px; margin:0 auto; padding:2rem 1rem 4rem; color:var(--muted);
  font-size:.85rem; border-top:1px solid var(--line); }
"""


def render(md_path: Path = TAGGED_PATH, out_path: Path = DEFAULT_OUT) -> None:
    md = md_path.read_text(encoding="utf-8")
    md = strip_front_matter(md)
    md = replace_entities(md)
    md = add_purple_numbers(md)
    md = convert_blocks(md)

    body = markdown.markdown(
        md,
        extensions=["tables", "md_in_html", "sane_lists", "attr_list"],
    )
    body = body.replace("<h2>目录</h2>", '<h2 class="toc-title">目录</h2>')

    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>楹联丛话全编 · 语义标注预览</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>楹联丛话全编 · 语义标注预览</h1>
  <p>清·梁章钜 等撰　|　18 类名词实体 · 联语标记 · Purple Numbers</p>
  <p>数据：<a href="../data/entities.json">entities.json</a> ·
     <a href="../data/couplets.json">couplets.json</a> ·
     <a href="../data/structure.json">structure.json</a></p>
</header>
<main>
{body}
</main>
<footer>
  本页由 <code>scripts/render_yinglian.py</code> 从
  <code>data/楹联丛话全编.tagged.md</code> 生成。标记只加不改原文。
</footer>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    print(f"written {out_path} ({len(page):,} chars)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--md", type=Path, default=TAGGED_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    render(args.md, args.out)


if __name__ == "__main__":
    main()
