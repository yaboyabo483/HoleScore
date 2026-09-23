# -*- coding: utf-8 -*-
"""开发用：按 100% / 65% 各导一份长谱 SVG（并截图），用来看「谱面大小」的实际效果。

运行：python tests/scale_sample.py

用一份 24 小节、带连尾/连音/切音/歌词的长谱，才看得出 100% 与 65% 的分页差
（演示工程只有 34 个音，100% 也是 1 页）。输出到 output/谱面大小-<比例>%-p<N>.svg|.png，
并把两档的首页 PNG 抄一份到 docs/images/ 供 README 引用
（`score-scale-100.png` 3 行 2 页、`score-scale-65.png` 5 行 1 页）。
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinwhistle import imageout, project as pj, render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")
os.makedirs(OUT, exist_ok=True)

proj = pj.load(os.path.join(ROOT, "projects", "演示工程.json"))
proj["title"] = "谱面大小核对"
print("音符数", len(proj["notes"]), "纸型", proj.get("paper"))

# 演示工程只有 34 个音（1 页 4 行），看不出「一页 5 行」的差别。
# 这里补一段长谱（24 小节，带连尾/连音/切音/歌词），才看得出 100% vs 65% 的分页差。
LONG = ("5 6 7 1' 5/ 6/ 7 1' | 6 5 3 2 1 - - - | "
        "1( 2 3) 5 6 5 3 | 2 - - 0 5/ 5/ 6 6 | "
        "5! 6 5 3 2 1 2 3 | 5 6 5 3 2 - - - | "
        "3 3 2 1 6. 5 - - | 1 2 3 5 6 5 3 2 | "
        "1' 1' 7 6 5 6 5 3 | 2 3 5 6 1' - - - | "
        "6. 5 3 2 1 2 3 5 | 6 - 5 - 3 - 2 - |")
long_proj = pj.new_project("谱面大小核对（长谱）", "D", "D", "4/4", True)
long_proj["notes"] = [pj.token_to_doc(t) for t in LONG.split() if pj.token_to_doc(t)]
long_proj["content_scale"] = 100
print("长谱音符数", len(long_proj["notes"]))

for tag, target, keep_lyrics in (("100", 100, True), ("65", 65, True)):
    p = dict(long_proj)
    p["content_scale"] = target
    if keep_lyrics:                       # 给每个音配一行词，顺带核对歌词带的间距
        for n in p["notes"]:
            if n.get("kind", pj.KIND_NOTE) == pj.KIND_NOTE:
                pj.set_lyric(n, "词")
    paths = pj.export_svg_pages(p, OUT, paper="A4", content_scale=target)
    print(f"--- {tag}%: {len(paths)} 页")
    for i, path in enumerate(paths):
        with open(path, encoding="utf-8") as f:
            svg = f.read()
        w, h = imageout.svg_size(svg)
        rows = svg.count('data-row-measures')
        print(f"    第 {i + 1} 页 {w:.0f}x{h:.0f}px")
        os.replace(path, os.path.join(OUT, f"谱面大小-{tag}%-p{i + 1}.svg"))

# 截图：走 imageout.svg_to_png（内部 180s 超时 + 「PNG 是否写完」兜底）。
# **别再用裸 subprocess.run(msedge)**：这台机器的无头 Edge 会「截完图赖着不退出」，
# 没有超时就永远卡在那里（图其实早写好了）——2026-09-22 踩过，一次卡 5 分钟以上。
for tag in ("100", "65"):
    src = os.path.join(OUT, f"谱面大小-{tag}%-p1.svg")
    png = os.path.join(OUT, f"谱面大小-{tag}%-p1.png")
    imageout.svg_to_png(open(src, encoding="utf-8").read(), png, scale=1)
    print(tag, "截图 ->", png, "存在=", os.path.isfile(png))

# 再抄一份首页给 README 用（文档图固定名字，免得 README 里挂中文长文件名）
IMG = os.path.join(ROOT, "docs", "images")
os.makedirs(IMG, exist_ok=True)
for tag in ("100", "65"):
    src = os.path.join(OUT, f"谱面大小-{tag}%-p1.png")
    if os.path.isfile(src):
        shutil.copyfile(src, os.path.join(IMG, f"score-scale-{tag}.png"))
        print("文档图 ->", f"docs/images/score-scale-{tag}.png")

print("完成")
