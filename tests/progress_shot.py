# -*- coding: utf-8 -*-
"""开发用：截「耗时操作进度条」的图（README 配图）。

不需要真跑一次导出 —— 直接把 BusyDialog 摆到某个进度上截屏，
所以几秒钟就完（真导出要起无头浏览器、一页一秒）。

用法：G:\\Conda\\python.exe tests/progress_shot.py
产物：docs/images/progress-load.png / progress-save.png / progress-export.png
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from shotutil import shot

import editor as ed

OUTDIR = os.path.join(ROOT, "docs", "images")
CASES = [
    # (文件名, 标题, 有没有取消按钮, done, total, 说明文字)
    ("progress-load.png", "正在打开工程", False, 42, 100, "解析工程"),
    ("progress-save.png", "正在保存工程", False, 812, 1600, "写入 812/1600 个音"),
    ("progress-export.png", "正在导出 2x 图片", True, 7, 12, "第 7/12 页"),
]


def main() -> int:
    os.makedirs(OUTDIR, exist_ok=True)
    root = tk.Tk()
    root.title("哨笛洞洞谱编谱器")
    root.geometry("900x600+60+60")
    root.update()
    for name, title, cancelable, done, total, label in CASES:
        dlg = ed.BusyDialog(root, title, cancelable=cancelable)
        dlg.report(done, total, label)
        dlg._t0 = time.monotonic() - 1.0        # 跳过「300ms 才弹窗」的延迟
        dlg.pump()
        root.update()
        dlg._win.update()
        dlg._win.lift()
        time.sleep(0.4)                         # 等窗口管理器画完
        root.update()
        out = os.path.join(OUTDIR, name)
        shot(dlg._win, out)
        print(f"saved: {out}  {os.path.getsize(out)} B", flush=True)
        dlg.close()
        root.update()
        time.sleep(0.2)
    root.destroy()
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
