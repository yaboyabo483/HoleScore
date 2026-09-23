# -*- coding: utf-8 -*-
"""开发用：导一份带「整段括号 + 第 n 结尾框」的样谱（SVG + PNG），供 README 引用。

运行：python tests/frames_sample.py

样谱里刻意塞全了这几样，好一眼看出口径对不对：
  * 一段**整段括号**（前奏/间奏那种），左右括号贴在起止格边缘、高度与数字齐平；
  * 一个**带连音线的第一结尾** `[1 … 1]`：横线要压在那几条弧线之上（头顶让位按内容算）；
  * 一个**朴素第二结尾** `[2 … 2]`：不额外占行高；
  * 外面套一对 `|: :|` 反复记号 —— 结尾框本来就是配合它用的。

输出 output/整段括号与结尾框示例.svg|.png，并抄一份 docs/images/score-frames.png。
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinwhistle import imageout, project as pj

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")
IMG = os.path.join(ROOT, "docs", "images")
os.makedirs(OUT, exist_ok=True)
os.makedirs(IMG, exist_ok=True)

TUNE = ("（ 5 6 5 3 ） 1 2 3 4 | "
        "1 2 3 4 |: 5 5 6 5 [1 3( 2( 1 2) 3) 1] :| "
        "[2 2 2 1 - - - 2]")
# 注意 `2]` 那种「终点」必须紧跟数字：`-]` 解析不出记号（`-` 是延音那一支），
# 只写 `[2` 而没写 `2]` 的话框子画不出来 —— 导出前会提示「缺另一半」。

BASE = "整段括号与结尾框示例"
proj = pj.new_project(BASE, "D", "D", "4/4", True)
proj["notes"] = [pj.token_to_doc(t) for t in TUNE.split() if pj.token_to_doc(t)]
proj["paper"] = "A4"
proj["content_scale"] = 100              # 100% 出图：记号看得清，样例本来就只有几行

paths = pj.export_svg_pages(proj, OUT, paper="A4", content_scale=100)
print("导出页数", len(paths))
for p in paths:
    print("  ", p)

svg = open(paths[0], encoding="utf-8").read()
w, h = imageout.svg_size(svg)
png = os.path.join(OUT, BASE + ".png")
imageout.svg_to_png(svg, png, scale=1)
print("PNG", png, int(w), "x", int(h))

doc = os.path.join(IMG, "score-frames.png")
shutil.copyfile(png, doc)
print("文档图 ->", "docs/images/score-frames.png")
