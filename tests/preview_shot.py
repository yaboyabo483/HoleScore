# -*- coding: utf-8 -*-
"""开发用：截「谱面区滚动条」「整谱预览窗口」和「歌词」几张图，便于肉眼核对。

运行：G:\\Conda\\python.exe tests/preview_shot.py

产物：
  output/编谱器界面-谱面滚动条.png
  output/整谱预览窗口.png
  output/编谱器界面-歌词.png
  output/整谱预览窗口-歌词.png
  output/歌词示例.svg

**抓屏的坑（本机实测）**：显示器是 150% 缩放，Tk 与外部截图进程都是 DPI-unaware。
Tk 报的是虚拟坐标（1707x1067），而 `CopyFromScreen` 把这些数字当**物理像素**用，
于是「真实位置 = Tk 坐标 x 1.5」——不换算就会偏半屏。见 `screen_scale()`。
"""

import os
import sys
import tkinter as tk
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinwhistle import project as pj, render
import editor as ed
from shotutil import shot            # 抓屏（DPI 正确版，见 shotutil 里的说明）

messagebox.askyesno = lambda *a, **k: False
messagebox.showinfo = lambda *a, **k: None
if os.path.exists(ed.AUTOSAVE_PATH):
    os.remove(ed.AUTOSAVE_PATH)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")

# 够长（要横向滚动）、够多行（预览里能换行），并带上切音/连音线/连尾/十六分
MELODY = [
    "5.", "1", "5!", "6", "2", "3",
    "5/", "6/", "1'/", "2'/", "5/", "6/", "5/", "3/",
    "5//", "5//", "6//", "6//", "5/", "3/", "2/", "1/", "1",
    "1'(", "2'", "3'", "2')", "1'",
    "6~", "6", "5", "3",
    "5", "-", "0", "5.",
    "1", "2", "3", "5", "6", "5", "3", "2",
    "1", "3", "5", "6", "1'", "6", "5", "3",
]

# 一个音一个字（休止/延音不给词）；字不够就后面的音空着
LYRIC = "长亭外古道边芳草碧连天晚风拂柳笛声残夕阳山外山天之涯地角知交半零落一壶浊酒尽余欢"


def page_box(win, app):
    """第 1 页纸张在**窗口坐标系**里的 (ox, oy, w, h)，逻辑像素。

    口径与 `_draw_page_preview` 一致：纸摆在画布 (pad, pad) 处，尺寸 页宽×页高（都乘预览缩放）。
    """
    shown, _i = pj.display_notes(app.proj)
    score, _r, warnings, _k = pj.build_render_inputs(app.proj)
    render._build_layout(score.events, app.paper_var.get())
    ed.set_lyric_shift(shown)
    k = app._page_scale()
    cv = app._page_cv
    return (cv.winfo_rootx() - win.winfo_rootx() + ed.PREVIEW_PAD,
            cv.winfo_rooty() - win.winfo_rooty() + ed.PREVIEW_PAD,
            int(render.PAGE_WIDTH * k),
            int(render._page_height(0, len(render.page_rows(0)), len(warnings)) * k))


def main():
    root = tk.Tk()
    # 窗口铺满屏幕 → 主窗口不会从抓屏区边缘把别的窗口露进来
    try:
        root.state("zoomed")
    except tk.TclError:
        pass
    app = ed.EditorApp(root)
    app.beats_var.set("4/4")
    app.autobar_var.set(1)
    app.key_var.set("G")
    app.title_var.set("滚动条与预览示例")
    app.proj["notes"] = [pj.token_to_doc(t) for t in MELODY]
    app.sel = 4
    app.redraw_all()
    app._sync_mode_box()
    app.status.config(text="谱面是一条长横带：下方横向滚动条可以整条拖动；按 F5 看整谱预览")
    root.update()
    root.lift()
    root.attributes("-topmost", True)
    root.update()
    root.after(400, lambda: None)
    root.update()

    p1 = os.path.join(OUT, "编谱器界面-谱面滚动条.png")
    # 只截谱面区（含滚动条）：从属性条上方往上到工具栏下方
    sy = app.score.master.winfo_y() - 4
    sh = app.score.master.winfo_height() + 8
    sz = shot(root, p1, 0, sy, root.winfo_width(), sh)
    print(f"谱面区截图 {p1}  {sz[0]}x{sz[1]}  "
          f"画布 {app.score.winfo_width()}x{app.score.winfo_height()}  "
          f"横条 {app.score_hs.winfo_width()}x{app.score_hs.winfo_height()}")

    app.open_page_preview()
    root.update()
    win = app._page_win
    root.attributes("-topmost", False)     # 主窗口让位，别压住预览窗口
    win.lift()
    win.attributes("-topmost", True)
    win.update()
    win.after(400, lambda: None)
    win.update()
    p2 = os.path.join(OUT, "整谱预览窗口.png")
    sz2 = shot(win, p2, *page_box(win, app))          # 只抓纸面那一块
    print(f"预览截图 {p2}  {sz2[0]}x{sz2[1]}  {app._page_info.cget('text')}")

    # 顺便导出这张示例谱，方便对照预览与导出是否一致
    app._sync_project_meta()
    svg = pj.export_svg(app.proj, OUT)
    print("导出 SVG :", svg)

    # ---------------- 歌词 ----------------
    it = iter(LYRIC)
    for doc in app.proj["notes"]:
        if doc.get("kind") == pj.KIND_NOTE:
            pj.set_lyric(doc, next(it, ""))
    app.title_var.set("歌词示例")
    app.proj["title"] = "歌词示例"
    app.sel = 0
    app._sel_user = False
    app.redraw_all()
    app.refresh_page_preview()
    app.status.config(text="歌词填在「数字与洞洞之间」：歌词框里打字即写入当前音，"
                           "按空格保存并跳到下一个音；点×关窗不会报错")
    root.lift()
    root.attributes("-topmost", True)
    root.update()
    root.after(400, lambda: None)
    root.update()
    p3 = os.path.join(OUT, "编谱器界面-歌词.png")
    sz3 = shot(root, p3)
    print(f"歌词界面截图 {p3}  {sz3[0]}x{sz3[1]}")

    root.attributes("-topmost", False)      # 主窗口刚才是置顶的，先让位给预览窗口
    win.lift()
    win.attributes("-topmost", True)
    win.update()
    win.after(400, lambda: None)
    win.update()
    p4 = os.path.join(OUT, "整谱预览窗口-歌词.png")
    sz4 = shot(win, p4, *page_box(win, app))
    print(f"歌词预览截图 {p4}  {sz4[0]}x{sz4[1]}  {app._page_info.cget('text')}")

    app._sync_project_meta()
    svg2 = pj.export_svg(app.proj, OUT)
    print("导出歌词 SVG :", svg2)

    win.attributes("-topmost", False)
    root.attributes("-topmost", False)
    app._close_page_preview()
    root.destroy()


if __name__ == "__main__":
    main()
