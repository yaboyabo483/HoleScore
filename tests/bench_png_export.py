# -*- coding: utf-8 -*-
"""开发用：量 PNG 导出的耗时，并验证「滚动提交 + 取消」在真浏览器下成立。

`PNG_WORKERS = 4` 这个数就是这么定出来的：一页要起一次无头浏览器，
**启动**才是主要开销，所以并行很划算（实测 17 页 19.5s → 9.4s）；
但一次性把整批任务塞进线程池的话 `cancel()` 没机会被调用（「取消」按钮就成了摆设），
所以要滚动提交——最后一段专门验证「取消后真的不再开新的页」。

用法：G:\\Conda\\python.exe tests/bench_png_export.py [页数，默认 6]
产物：output/_bench2/（已 gitignore）
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinwhistle import imageout, project as pj, render  # noqa: E402

NPAGES = int(sys.argv[1]) if len(sys.argv) > 1 else 6
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "output", "_bench2")
os.makedirs(TMP, exist_ok=True)

DEG = [1, 2, 3, 5, 6, 1, 2, 3, 5]
N = 400 * NPAGES
notes = []
for i in range(N):
    notes.append(pj.new_note(DEG[i % len(DEG)], 0, (i // 7) % 2))
    if len(notes) % 4 == 0:
        notes.append(pj.new_simple(pj.KIND_BAR))
proj = pj.new_project(title="PNG基准", key="G", whistle="D", beats="4/4")
proj["notes"] = notes
proj["content_scale"] = 0.65

score, results, warns, key = pj.build_render_inputs(proj)
pages = render.render_svg_pages(score, results, title=proj["title"], key=key,
                                whistle_key="D", warnings=warns, beats="4/4",
                                paper="A4", watermark="", row_measures=0,
                                content_scale=0.65)
print(f"音符 {N} → {len(pages)} 页（PNG_WORKERS={imageout.PNG_WORKERS}）", flush=True)
n = len(pages)

t0 = time.perf_counter()
seq = imageout.pages_to_png(pages, os.path.join(TMP, "seq"), "seq", scale=1,
                            max_workers=1)
d1 = time.perf_counter() - t0
print(f"  串行（max_workers=1） {d1:8.3f}s  出 {len(seq)} 张", flush=True)

t0 = time.perf_counter()
par = imageout.pages_to_png(pages, os.path.join(TMP, "par"), "par", scale=1)
d2 = time.perf_counter() - t0
print(f"  并行（默认 {imageout.PNG_WORKERS} 路） {d2:8.3f}s  出 {len(par)} 张", flush=True)
print(f"  提速 {d1 / max(d2, 1e-6):.2f}x", flush=True)

# 取消：出完第 1 张就喊停
seen = {"n": 0}
orig = imageout.svg_to_png


def counting(svg_text, out_path, **kw):
    seen["n"] += 1
    return orig(svg_text, out_path, **kw)


imageout.svg_to_png = counting
t0 = time.perf_counter()
can = imageout.pages_to_png(pages, os.path.join(TMP, "cancel"), "cancel", scale=1,
                            cancel=lambda: seen["n"] >= 1)
d3 = time.perf_counter() - t0
imageout.svg_to_png = orig
print(f"  取消（第 1 张后停）  {d3:8.3f}s  起了 {seen['n']} 次浏览器 / 出了 {len(can)} 张",
      flush=True)
print(f"  -> 取消生效：{seen['n'] < n}（并行路数上限内才合理）", flush=True)
sys.stdout.flush()
os._exit(0)
