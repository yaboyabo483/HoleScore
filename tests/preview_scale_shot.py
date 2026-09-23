# -*- coding: utf-8 -*-
"""开发用：把「整谱预览」在 65% 谱面大小下的样子截下来（核对预览与导出口径一致）。

运行：G:\\Conda\\python.exe tests/_shot_preview_scale.py
"""

import os
import sys
import time
import tkinter as tk
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import editor as ed
from tinwhistle import project as pj
from shotutil import shot

messagebox.askyesno = lambda *a, **k: False
messagebox.showinfo = lambda *a, **k: None
if os.path.exists(ed.AUTOSAVE_PATH):
    os.remove(ed.AUTOSAVE_PATH)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")

LONG = ("5 6 7 1' 5/ 6/ 7 1' | 6 5 3 2 1 - - - | "
        "1( 2 3) 5 6 5 3 | 2 - - 0 5/ 5/ 6 6 | "
        "5! 6 5 3 2 1 2 3 | 5 6 5 3 2 - - - | "
        "3 3 2 1 6. 5 - - | 1 2 3 5 6 5 3 2 | "
        "1' 1' 7 6 5 6 5 3 | 2 3 5 6 1' - - - | "
        "6. 5 3 2 1 2 3 5 | 6 - 5 - 3 - 2 - |")


def main():
    root = tk.Tk()
    try:
        root.state("zoomed")
    except tk.TclError:
        pass
    app = ed.EditorApp(root)
    app.proj = pj.new_project("预览与导出口径", "D", "D", "4/4", True)
    app.proj["notes"] = [pj.token_to_doc(t) for t in LONG.split() if pj.token_to_doc(t)]
    for n in app.proj["notes"]:
        if n.get("kind", pj.KIND_NOTE) == pj.KIND_NOTE:
            pj.set_lyric(n, "词")
    app.title_var.set("预览与导出口径")
    app.content_scale_var.set("65")
    app._sync_project_meta()
    app.redraw_all()
    root.update()

    app.open_page_preview()
    root.update()
    win = app._page_win
    win.lift()
    win.focus_set()
    # 抓屏抓的是屏幕像素：窗口刚弹出来时还没完全重绘，别的窗口会从没刷新的像素里
    # 透出来（上一版截图里标题那一条就混进了主窗口的按钮）。多等几帧再抓。
    for _ in range(12):
        root.update()
        win.update()
        time.sleep(0.1)

    print("信息栏：", app._page_info.cget("text"))
    p = os.path.join(OUT, "预览-谱面大小65.png")
    shot(win, p)
    print("截图 ->", p, os.path.isfile(p))
    # 主画布也来一张：谱面大小只改导出，画布必须还是原尺寸
    p2 = os.path.join(OUT, "画布-谱面大小65-不受影响.png")
    shot(app.score, p2)
    print("截图 ->", p2, os.path.isfile(p2))

    sf = __import__("shotutil").screen_scale()
    print("屏幕缩放系数", sf)

    app.on_close()
    root.update()
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)
