#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 TiddlyWiki 导出目录编译成单个 HTML 文件。

用法：
    python3 scripts/build_tiddlywiki.py
    python3 scripts/build_tiddlywiki.py --tw /path/to/TiddlyWiki5
    python3 scripts/build_tiddlywiki.py --out dist/oblique.html

需要一个 TiddlyWiki 5 的源码目录（含 `tiddlywiki.js` 与 `boot/boot.js`）。
查找顺序：
    1. `--tw` 参数
    2. 环境变量 TIDDLYWIKI5
    3. 常见安装位置（~/github.com/TiddlyWiki5 等）

产物是一个自包含的 HTML：双击即可在浏览器打开，无需服务器、无需联网。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = ROOT / "tiddlywiki" / "楹联丛话全编"
DEFAULT_OUT = ROOT / "tiddlywiki" / "oblique.html"

# 常见 TiddlyWiki5 安装位置（展开 ~）
CANDIDATE_PATHS = [
    "/home/peter/github.com/TiddlyWiki5",
    "~/github.com/TiddlyWiki5",
    "~/TiddlyWiki5",
    "/usr/lib/tiddlywiki5",
    "/usr/local/lib/tiddlywiki5",
    "/opt/TiddlyWiki5",
]


def find_tiddlywiki(explicit: str | None) -> Path:
    """定位 TiddlyWiki5 源码目录（含 tiddlywiki.js）。"""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if (p / "tiddlywiki.js").exists():
            return p
        raise SystemExit(f"指定的目录不是 TiddlyWiki5：{p}（缺 tiddlywiki.js）")

    env = os.environ.get("TIDDLYWIKI5")
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "tiddlywiki.js").exists():
            return p

    for cand in CANDIDATE_PATHS:
        p = Path(cand).expanduser()
        if (p / "tiddlywiki.js").exists():
            return p.resolve()

    # 兜底：某些发行版把 tiddlywiki.js 放在 /usr/share 下
    for guess in ("/usr/share/tiddlywiki5", "/usr/share/tiddlywiki"):
        g = Path(guess)
        if (g / "tiddlywiki.js").exists():
            return g.resolve()

    raise SystemExit(
        "找不到 TiddlyWiki5。请用 --tw /path/to/TiddlyWiki5 指定，"
        "或设置环境变量 TIDDLYWIKI5。"
    )


def check_wiki_dir(wiki_dir: Path) -> None:
    """检查导出目录是否齐全。"""
    if not wiki_dir.exists():
        raise SystemExit(f"找不到导出目录：{wiki_dir}\n先运行 scripts/export_tiddlywiki.py")
    if not (wiki_dir / "tiddlywiki.info").exists():
        raise SystemExit(f"缺少 tiddlywiki.info：{wiki_dir}")
    n = sum(1 for _ in (wiki_dir / "tiddlers").rglob("*.tid"))
    if n == 0:
        raise SystemExit(f"tiddlers/ 下没有 .tid 文件：{wiki_dir}")



def build(tw_dir: Path, wiki_dir: Path, out_file: Path) -> None:
    """调用 tiddlywiki.js 的 build index 目标，产出单文件 HTML。"""
    build_dir = out_file.parent / ".build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "node", str(tw_dir / "tiddlywiki.js"), str(wiki_dir),
        "--output", str(build_dir),
        "--build", "index",
    ]
    print("执行：" + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    if proc.returncode != 0:
        raise SystemExit(f"打包失败（退出码 {proc.returncode}）")

    produced = build_dir / "index.html"
    if not produced.exists():
        raise SystemExit(f"未生成 index.html：{produced}")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(produced, out_file)
    shutil.rmtree(build_dir)


def read_tid_titles(wiki_dir: Path) -> set[str]:
    """读出所有 .tid 的标题（标题在 title: 字段里，不等于文件名）。"""
    titles: set[str] = set()
    for p in (wiki_dir / "tiddlers").rglob("*.tid"):
        head = p.read_text(encoding="utf-8").split("\n\n", 1)[0]
        for line in head.split("\n"):
            if line.startswith("title:"):
                titles.add(line[6:].strip())
                break
    return titles


def verify(out_file: Path, wiki_dir: Path) -> None:
    """检查单文件里确实装下了全部 tiddler，且站点配置生效。"""
    html = out_file.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r'<script class="tiddlywiki-tiddler-store" type="application/json">\[(.*?)\]</script>',
        html, re.S)
    if not m:
        raise SystemExit("单文件里找不到 tiddler store —— 不是有效的单文件 wiki")
    try:
        store = json.loads("[" + m.group(1) + "]")
    except json.JSONDecodeError as e:
        raise SystemExit(f"tiddler store 不是合法 JSON：{e}")

    titles = {t.get("title") for t in store}
    expected = read_tid_titles(wiki_dir)

    missing = expected - titles
    if missing:
        raise SystemExit(f"单文件缺少 {len(missing)} 个 tiddler：{sorted(missing)[:5]}")

    def text_of(title: str) -> str:
        for t in store:
            if t.get("title") == title:
                return (t.get("text") or "").strip()
        return ""

    problems = []
    if not text_of("$:/SiteTitle"):
        problems.append("$:/SiteTitle 为空")
    if not text_of("$:/DefaultTiddlers"):
        problems.append("$:/DefaultTiddlers 为空")
    if not any(t.startswith("$:/languages/") for t in titles):
        problems.append("未打包语言插件")
    if problems:
        raise SystemExit("单文件配置有问题：" + "；".join(problems))

    size_mb = out_file.stat().st_size / 1024 / 1024
    print()
    print(f"✓ 单文件：{out_file}")
    print(f"  体积     {size_mb:.2f} MB")
    print(f"  tiddler  {len(store)} 个（其中本站 {len(expected)} 个）")
    print(f"  站点标题 {text_of('$:/SiteTitle')}")
    print(f"  默认首页 {text_of('$:/DefaultTiddlers')}")
    print(f"  界面语言 {text_of('$:/language')}")


def main() -> None:
    ap = argparse.ArgumentParser(description="把 TiddlyWiki 导出目录编译成单个 HTML")
    ap.add_argument("--tw", default=None, help="TiddlyWiki5 源码目录")
    ap.add_argument("--wiki", default=str(WIKI_DIR), help="导出目录")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出的单文件 HTML")
    ap.add_argument("--no-verify", action="store_true", help="跳过产物检查")
    args = ap.parse_args()

    wiki_dir = Path(args.wiki).resolve()
    out_file = Path(args.out).resolve()
    check_wiki_dir(wiki_dir)

    tw_dir = find_tiddlywiki(args.tw)
    print(f"TiddlyWiki5：{tw_dir}")
    print(f"导出目录：{wiki_dir}")
    print(f"输出文件：{out_file}")
    print()

    build(tw_dir, wiki_dir, out_file)

    if not args.no_verify:
        verify(out_file, wiki_dir)

    print()
    print(f"完成：{out_file}（浏览器直接打开即可）")


if __name__ == "__main__":
    main()

