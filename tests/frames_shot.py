"""开发用：把带框类记号（整段括号 / 第 n 结尾框）的工程放进编谱器截图，肉眼核对画布。

运行：python tests/frames_shot.py     （要 tkinter，用 G:/Conda/python.exe）

出三张图：
  output/框类记号-编谱器.png       —— 画布左端（括号那一段）
  output/框类记号-编谱器-右端.png  —— 画布往右滚一屏（结尾框在最右端，不滚看不到）
  output/框类记号-预览.png         —— 整谱预览窗口

之所以要两张画布图：画布是**一条横向滚动条**，结尾框落在整谱最右端，
默认停在最左边就完全看不到，只看左端会误判成「结尾框没画出来」。
"""
import os
import sys
import tkinter as tk
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinwhistle import project as pj
import editor as ed
from shotutil import shot

messagebox.askyesno = lambda *a, **k: False
messagebox.showinfo = lambda *a, **k: None
if os.path.exists(ed.AUTOSAVE_PATH):
    os.remove(ed.AUTOSAVE_PATH)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")

# 注意：`[1` / `2]` 里的数字是**标号**（与 `[n` 呼应），不会被当成音符 ——
# 所以 `[1 3( 2( 1 2) 3) 1]` 在第一结尾里是 3 2 1 2 3 五个音，`1]` 只是收尾记号。
TUNE = ("（ 5 6 5 3 ） 1 2 3 4 1 2 3 4 |: 5 5 6 5 "
        "[1 3( 2( 1 2) 3) 1] :| [2 2 2 1 - - - 2]")


def main():
    root = tk.Tk()
    try:
        root.state("zoomed")
    except tk.TclError:
        pass
    app = ed.EditorApp(root)
    app.proj = pj.new_project("框类记号", "D", "D", "4/4", True)
    app.proj["notes"] = [pj.token_to_doc(t) for t in TUNE.split() if pj.token_to_doc(t)]
    app.proj["_path"] = None
    app.sel = -1
    app.autobar_var.set(1)
    app._meta_changed()
    for _ in range(30):
        root.update()
    path = os.path.join(OUT, "框类记号-编谱器.png")
    shot(root, path, ox=0, oy=0, w=1320, h=560)
    print("shot ->", path, os.path.isfile(path))
    # 画布默认停在最左边，结尾框在最右端看不到 —— 往右滚一屏再截一张
    app.score.xview_moveto(1.0)
    for _ in range(20):
        root.update()
    path2 = os.path.join(OUT, "框类记号-编谱器-右端.png")
    shot(root, path2, ox=0, oy=0, w=1320, h=560)
    print("shot ->", path2, os.path.isfile(path2))
    app.score.xview_moveto(0.0)
    app.open_page_preview()
    for _ in range(30):
        root.update()
    if app._page_win is not None:
        pw = os.path.join(OUT, "框类记号-预览.png")
        shot(app._page_win, pw, ox=0, oy=0, w=760, h=760)
        print("preview ->", pw, os.path.isfile(pw))
        app._close_page_preview()
    root.destroy()


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)
