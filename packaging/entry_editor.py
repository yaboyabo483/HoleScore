# -*- coding: utf-8 -*-
"""笛洞工坊 exe 的入口脚本（PyInstaller 用它当起点，而不是直接拿 editor.py）。

职责有三块：

1. **正常启动**：`run_editor()`。
2. **兜底报错**：打包成「无控制台」的 exe 之后，启动阶段抛异常是**静默**的 ——
   没有控制台可打印、窗口也还没建起来，用户体验就是「双击了没反应」。
   所以出异常要弹框（tkinter 还能用就弹）并往 exe 旁边写 `启动错误.log`。
3. **自检**：`笛洞工坊.exe --selfcheck` 不建主窗口，把打包产物真正该有的能力跑一遍
   （tcl/tk 能不能画、模块齐不齐、能不能渲染 SVG、自动保存落没落到 exe 旁边、
   能不能调 Edge 导 PNG），结果写成 JSON 报告供 `build_exe.py` 自动核对。

   为什么非要自检：`--exclude-module` 排错东西**打包阶段不报错**，只会在运行时才炸；
   剪 tcl/tk 数据也一样。不真跑一遍，就只能等用户点开才发现是坏的。
"""

from __future__ import annotations

import os
import sys
import traceback

SELFCHECK_ARG = "--selfcheck"
SELFCHECK_REPORT = "自检报告.json"


def _log_path() -> str:
    try:
        from tinwhistle import apppaths
        return os.path.join(apppaths.app_root(), "启动错误.log")
    except Exception:
        # apppaths 都导入不了时的兜底：至少别再抛一个异常出来
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                            "启动错误.log")


def _write_log(detail: str) -> str | None:
    try:
        import datetime
        path = _log_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} 启动失败 =====\n")
            f.write(detail)
        return path
    except Exception:
        return None


def _show_dialog(message: str) -> None:
    """尽量把错误弹出来；tkinter 本身坏掉就算了，不能因此再崩一次。"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("笛洞工坊启动失败", message)
        root.destroy()
    except Exception:
        pass


def report_failure(exc: BaseException) -> None:
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log = _write_log(detail)
    text = f"{type(exc).__name__}: {exc}"
    if log:
        text += f"\n\n完整日志已写入：\n{log}"
    _show_dialog(text)
    try:
        if sys.__stderr__ is not None:      # exe 无控制台时它可能是 None
            sys.__stderr__.write(detail)
            sys.__stderr__.flush()
    except Exception:
        pass


# ---------------------------------------------------------------- 自检
def selfcheck() -> int:
    """把打包产物该有的能力真跑一遍，报告写到 exe 旁边的 自检报告.json。"""
    import json
    import time

    checks = []

    def check(name: str, fn):
        t0 = time.perf_counter()
        try:
            detail = fn()
            checks.append({"name": name, "ok": True,
                           "detail": str(detail) if detail is not None else "",
                           "ms": int((time.perf_counter() - t0) * 1000)})
        except Exception as exc:
            checks.append({"name": name, "ok": False,
                           "detail": f"{type(exc).__name__}: {exc}",
                           "ms": int((time.perf_counter() - t0) * 1000)})

    from tinwhistle import apppaths

    info = {
        "frozen": apppaths.is_frozen(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "app_root": apppaths.app_root(),
        "project_dir": apppaths.sub_dir("projects"),
        "output_dir": apppaths.sub_dir("output"),
    }

    # 1) tcl/tk 是否完好 —— 剪过 tcl/tk 数据，这条是重点
    def tk_roundtrip():
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        cv = tk.Canvas(root, width=200, height=100)
        cv.create_text(100, 50, text="哨笛 12345")
        cv.create_line(0, 0, 200, 100, fill="#3d6b8e")
        root.update_idletasks()
        coords = cv.coords(1)          # 能取到坐标说明 canvas 真的在画
        bbox = cv.bbox(1)
        root.destroy()
        if not coords or not bbox:
            raise RuntimeError("canvas 没画出东西")
        return f"Tk {tk.TkVersion}，canvas 元素 bbox={bbox}"

    # 2) 全部业务模块能不能导入
    def imports():
        import editor                                  # noqa: F401
        from tinwhistle import (apppaths, beaming, fingering, procutil,  # noqa: F401
                                imageout, jianpu, project, render)
        return "editor / tinwhistle 全部模块导入 OK"

    # 3) 渲染一段真谱面（走编谱器的工程导出链路）
    def render_svg():
        from tinwhistle import project as pj
        proj = pj.new_project("自检", "G", "D", "4/4", True)
        proj["notes"] = [d for d in (pj.token_to_doc(t)
                                     for t in "5 3 2 1 6. 5 0".split()) if d]
        paths = pj.export_svg_pages(proj, apppaths.resolve_out_dir("output"),
                                    row_measures=3)
        with open(paths[0], encoding="utf-8") as f:
            svg = f.read()
        for token in ("<svg", "</svg>", "自检"):
            if token not in svg:
                raise RuntimeError(f"SVG 里缺少 {token!r}")
        return (f"{len(proj['notes'])} 音 / {len(paths)} 页 → "
                f"{os.path.basename(paths[0])}")

    # 4) 自动保存必须落在 **exe 旁边**，不能落进 _internal
    def autosave_path():
        from tinwhistle import project as pj
        path = os.path.join(apppaths.sub_dir("projects"), "自检-autosave.json")
        pj.save({"title": "自检", "notes": [{"pitch": "5"}]}, path)
        if not os.path.isfile(path):
            raise RuntimeError("自动保存没落盘")
        root = os.path.abspath(apppaths.app_root())
        if os.path.commonpath([root, os.path.abspath(path)]) != root:
            raise RuntimeError("自动保存跑到程序目录外面去了")
        if "_internal" in os.path.abspath(path).split(os.sep):
            raise RuntimeError("自动保存落进了 _internal（打包后 __file__ 的坑又回来了）")
        os.remove(path)
        return path

    # 5) 能不能调起 Edge/Chrome 导 PNG（找不到浏览器不算失败，标记为跳过）
    def export_png():
        from tinwhistle import imageout, project as pj
        browser = imageout.find_browser()
        if not browser:
            return "跳过：没装 Edge/Chrome"
        proj = pj.new_project("自检图", "G", "D", "4/4", True)
        proj["notes"] = [d for d in (pj.token_to_doc(t)
                                     for t in "5 3 2 1".split()) if d]
        path = pj.export_png(proj, apppaths.resolve_out_dir("output"), scale=1)[0]
        size = os.path.getsize(path)
        if size < 1000:
            raise RuntimeError(f"PNG 太小（{size} 字节），可能是空白图")
        return f"{os.path.basename(browser)} → {os.path.basename(path)}（{size} 字节）"

    check("tcl/tk 画布可用", tk_roundtrip)
    check("业务模块导入", imports)
    check("渲染 SVG", render_svg)
    check("自动保存路径", autosave_path)
    check("导出 PNG（Edge/Chrome）", export_png)

    ok = all(c["ok"] for c in checks)
    payload = {"ok": ok, "info": info, "checks": checks}
    out = os.path.join(apppaths.app_root(), SELFCHECK_REPORT)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    try:
        if sys.__stderr__ is not None:
            for c in checks:
                sys.__stderr__.write(
                    f"  [{'OK' if c['ok'] else '!!'}] {c['name']}: {c['detail']}\n")
    except Exception:
        pass
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if SELFCHECK_ARG in argv:
        return selfcheck()
    try:
        from editor import run_editor
        run_editor()
    except SystemExit:
        raise
    except BaseException as exc:          # noqa: BLE001 —— 就是要逮住所有想得到的意外
        report_failure(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
