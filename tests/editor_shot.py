"""开发用：构建一个示例工程 → 截取编谱器界面 → 导出 SVG

输出 output/编谱器界面.png（整窗）与 output/编谱器界面-下半.png（下半屏特写），
整窗那张会抄一份到 docs/images/editor.png 供 README 引用。

运行：G:\\Conda\\python.exe tests/editor_shot.py
"""

import os
import shutil
import sys
import tkinter as tk
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinwhistle import project as pj
import editor as ed
from shotutil import shot            # 抓屏（DPI 正确版，见 shotutil 里的说明）

# 演示脚本不要被「恢复未完成工程」弹窗打断
messagebox.askyesno = lambda *a, **k: False
messagebox.showinfo = lambda *a, **k: None
if os.path.exists(ed.AUTOSAVE_PATH):
    os.remove(ed.AUTOSAVE_PATH)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")
IMG = os.path.join(ROOT, "docs", "images")

MELODY = [
    "5.", "1", "5!", "6", "2", "3",          # 第 3 个音是切音：自占一个小窄格（小数字＋小斜杠＋小指法图），排在 6 前面
    "5/", "6/", "1'/", "2'/", "5/", "6/", "5/", "3/",
    "5//", "5//", "6//", "6//", "5/", "3/", "2/", "1/", "1",
    "1'(", "2'", "3'", "2')", "1'",
    "6~", "6", "5", "3",
    "5", "-", "0", "5.",
]


def main():
    root = tk.Tk()
    # 抓屏是「屏幕像素」而非「窗口像素」：窗口若小于屏幕，别的置顶窗口会从边缘露出来，
    # 截出来就带一条别人的界面。最大化盖满屏幕即可根治。
    try:
        root.state("zoomed")
    except tk.TclError:
        pass
    app = ed.EditorApp(root)
    app.beats_var.set("4/4")
    app.autobar_var.set(1)
    app.key_var.set("G")            # 1=G → D 调哨笛即「全按作5」
    app.title_var.set("编谱器界面示例")
    app.proj["notes"] = []
    for token in MELODY:
        doc = pj.token_to_doc(token)
        if doc:
            app.proj["notes"].append(doc)
    # 演示附点：把第 12 个音改成附点八分
    if len(app.proj["notes"]) > 12:
        app.proj["notes"][12]["duration"] = 0.75
    app.sel = 3
    app.redraw_all()
    app._sync_mode_box()
    app.status.config(text="D 调哨笛 · 1=G · 全按作5 · 走谱分隔自动按 4/4 排列")
    root.update()
    root.lift()
    root.attributes("-topmost", True)
    root.update()
    for name, w in (("toolbar/score", app.score), ("chart", app.chart)):
        print(f"  {name}: {w.winfo_width()}x{w.winfo_height()}")
    print(f"  window: {root.winfo_width()}x{root.winfo_height()} "
          f"screen: {root.winfo_screenwidth()}x{root.winfo_screenheight()}")

    png = os.path.join(OUT, "编谱器界面.png")
    png_bottom = os.path.join(OUT, "编谱器界面-下半.png")
    # 抓屏按逻辑像素给坐标（shotutil 内部换算成物理像素，见那里的说明）
    shot(root, png)
    shot(root, png_bottom, 0, int(root.winfo_height() * 0.46),
         root.winfo_width(), int(root.winfo_height() * 0.54))

    app._sync_project_meta()
    svg = pj.export_svg(app.proj, OUT)
    print("截图:", png, os.path.isfile(png))
    print("SVG :", svg)
    doc = os.path.join(IMG, "editor.png")
    shutil.copyfile(png, doc)
    print("文档图 ->", "docs/images/editor.png")
    root.destroy()


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)          # 别用 raise SystemExit：会挂在 Tcl 清理上（见 tests 目录的约定）
