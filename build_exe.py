# -*- coding: utf-8 -*-
"""把「笛洞工坊」（HoleScore）打包成 exe（Windows）。

名字只在下面 `APP_NAME` 一处定义；`editor.APP_NAME` 是同一个名字，改要一起改。

    G:\\Conda\\python.exe build_exe.py                  # 目录版（推荐，启动快）
    G:\\Conda\\python.exe build_exe.py --onefile         # 单文件版（方便传，但启动慢）
    G:\\Conda\\python.exe build_exe.py --no-clean        # 保留 build/ 增量重打
    G:\\Conda\\python.exe build_exe.py --no-prune        # 不剪 tcl/tk 冗余数据（见下）

产物：
    dist/笛洞工坊/笛洞工坊.exe        ← 目录版：双击即用，**整个文件夹**要一起拷
    dist/笛洞工坊-单文件.exe           ← 单文件版（--onefile）

--------------------------------------------------------------------------------
为什么默认是**目录版（onedir）**而不是单文件（onefile）—— 这是启动速度的关键
--------------------------------------------------------------------------------
onefile 的 exe 是个自解压壳：**每次启动**都要把整个程序（解释器 + 标准库 + tcl/tk，
几十 MB）解到 `%TEMP%\\_MEIxxxxxx\\`，跑完再删。文件越多、杀软拦得越勤就越慢，
冷启动常见 2~6 秒。目录版不需要解压，直接按需映射磁盘上的文件，冷启动通常一秒内。

要对外的场合可以两个都出：目录版自己用，单文件版发给别人时省事。
实测数字见 `tests/bench_startup.py`。

--------------------------------------------------------------------------------
其它几个影响启动速度 / 体积的开关
--------------------------------------------------------------------------------
* `--windowed`  编谱器是 GUI，不分配控制台窗口（顺带省掉控制台初始化）。
  注意：这样一来 `sys.stdout` 是 None，所以**整条链路上不能有 print()**
  （已确认 editor.py 与 tinwhistle 全都没有，qa_packaging.py 会把这条钉住）。
  exe 现在只含编谱器：OCR 生谱与命令行入口已经删掉了。
* `--noupx`     UPX 压缩的 exe 每次加载都要在内存里解压：换来的是「更小」而不是「更快」，
  而且压缩壳特别容易被杀软误报，不划算。
* `--exclude-module`  开发/测试/打包工具链（unittest、pydoc、setuptools…）冻结后完全用不到，
  排掉能少几百个文件 —— 启动时被扫描的文件少了，加载就快。
* 剪 tcl/tk 用不上的数据（时区库、消息翻译、demos），同样是为了少扫描。

**排除清单必须靠「真跑一遍」来验证**：`--exclude-module` 排错东西不会在打包时报错，
只会在运行时才炸。所以打完一定要按脚本末尾的提示实际操作一次导出。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
ENTRY = os.path.join(ROOT, "packaging", "entry_editor.py")
APP_NAME = "笛洞工坊"        # 与 editor.APP_NAME 同一个名字（exe / 产物文件夹都叫这个）
BUILD_DIR = os.path.join(ROOT, "build")
DIST_DIR = os.path.join(ROOT, "dist")

# 冻结后完全用不到的模块。排之前都确认过不影响运行，并且打完后会真跑一遍验证。
EXCLUDES = (
    # 开发 / 测试 / 打包工具链
    "unittest", "doctest", "pdb", "pydoc", "pydoc_data", "lib2to3",
    "distutils", "setuptools", "pip", "wheel", "pkg_resources",
    "idlelib", "turtledemo", "turtle", "test", "ctypes.test",
    # 本项目用不到的标准库（解析简谱只用 re / json / html）
    "xml", "xmlrpc", "sqlite3", "bz2", "lzma", "curses", "dbm",
    # 注意：concurrent 不能排 —— imageout 用它做多页 PNG 并行（ThreadPoolExecutor），
    # 排掉的话打包不报错，运行时才炸 ModuleNotFoundError（qa_packaging 盯着这条）。
    "multiprocessing", "asyncio", "selectors",
    "email", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib",
    "logging.config", "logging.handlers", "wsgiref", "cgi", "cgitb",
    # tkinter 里我们不用的子模块
    "tkinter.test", "tkinter.tix", "tkinter.dnd",
)

# tcl/tk 运行数据里可以安全删掉的部分（都是给 demo / 本地化 / 时区用的）
TCL_PRUNE = (
    os.path.join("_tcl_data", "tzdata"),      # 时区库
    os.path.join("_tcl_data", "msgs"),        # tcl 报错信息的翻译表
    os.path.join("_tcl_data", "opt0.4"),      # tcl option 解析包，tk 控件不用
    os.path.join("_tk_data", "msgs"),         # tk 的翻译表
    os.path.join("_tk_data", "demos"),        # 演示程序
    os.path.join("_tk_data", "images"),       # 演示用的图标
)


def _fail(msg: str) -> None:
    print(f"\n[错误] {msg}", file=sys.stderr)
    raise SystemExit(1)


def check_python() -> None:
    """打包必须用**带 tkinter** 的 Python。

    有些精简版 / 托管的 Python 运行时没编 tkinter（嵌入版、conda 最小环境等），
    用它打出来的 exe 会在启动时报 `No module named '_tkinter'` —— 而且**打包阶段不报错**，
    所以这里先拦一道。
    """
    try:
        import tkinter
    except ImportError:
        _fail(f"当前 Python 没有 tkinter，打出来的 exe 起不来：\n  {sys.executable}\n"
              "请改用带 tkinter 的解释器，例如：G:\\Conda\\python.exe build_exe.py")
    print(f"Python  : {sys.version.split()[0]}  ({sys.executable})")
    print(f"tkinter : Tk {tkinter.TkVersion}")


def pyinstaller_args(onefile: bool, clean: bool) -> list:
    out_name = f"{APP_NAME}-单文件" if onefile else APP_NAME
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir" if not onefile else "--onefile",
        "--windowed",                 # GUI：不弹控制台（顺带省掉控制台初始化）
        "--noupx",                    # UPX 壳只会拖慢加载、还容易被杀软误报
        "--name", out_name,
        "--paths", ROOT,
        "--specpath", BUILD_DIR,
        "--workpath", os.path.join(BUILD_DIR, "work"),
        "--distpath", DIST_DIR,
        "--log-level", "WARN",
    ]
    if clean:
        args.append("--clean")
    icon = os.path.join(ROOT, "packaging", "icon.ico")
    if os.path.isfile(icon):
        args += ["--icon", icon]
    for mod in EXCLUDES:
        args += ["--exclude-module", mod]
    args.append(ENTRY)
    return args


def run_build(onefile: bool, clean: bool) -> tuple:
    args = pyinstaller_args(onefile, clean)
    print(f"\n打包{'单文件' if onefile else '目录'}版 → {DIST_DIR}")
    t0 = time.perf_counter()
    proc = subprocess.run(args, cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print((proc.stdout or "")[-4000:])
        print((proc.stderr or "")[-4000:], file=sys.stderr)
        _fail("PyInstaller 构建失败（完整日志见上）")
    took = time.perf_counter() - t0
    if onefile:
        # onefile 的产物就是 dist/xxx.exe 这一个文件（**没有**同名子目录，
        # 曾经按目录版那样拼路径，结果构建成功却报「没找到 exe」）
        out_dir = DIST_DIR
        exe = os.path.join(DIST_DIR, f"{APP_NAME}-单文件.exe")
    else:
        out_dir = os.path.join(DIST_DIR, APP_NAME)
        exe = os.path.join(out_dir, f"{APP_NAME}.exe")
    if not os.path.isfile(exe):
        _fail(f"构建结束但没找到 exe：{exe}")
    return out_dir, exe, took


def _tree_size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for base, _dirs, files in os.walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(base, fn))
            except OSError:
                pass
    return total


def prune(onefile: bool, out_dir: str) -> int:
    """剪掉 tcl/tk 里用不上的数据，返回释放的字节数。

    `--no-prune` 可以跳过这一步：剪枝要批量删 tcl 的时区库（tzdata 一个目录就有几百个文件），
    有些环境（带批量删除确认的沙箱 / 受管控的企业盘）会直接拦住 —— 这时不打才是最可惜的，
    多带几 MB 冗余数据完全不影响运行。
    """
    if onefile:
        return 0                      # 单文件版的内容封在 exe 里，没法剪
    internal = os.path.join(out_dir, "_internal")
    freed = 0
    for rel in TCL_PRUNE:
        target = os.path.join(internal, rel)
        if os.path.exists(target):
            freed += _tree_size(target)
            shutil.rmtree(target, ignore_errors=True)
    return freed


def run_selfcheck(exe: str, timeout: float = 300) -> list:
    """让打包出来的 exe 自己把该有的能力跑一遍，返回检查项列表。

    为什么非做不可：`--exclude-module` 排错模块、剪 tcl/tk 数据，**打包阶段都不报错**，
    只在运行时才炸。不真跑一遍，就只能等用户点开才发现是坏的。
    """
    report = os.path.join(os.path.dirname(exe), "自检报告.json")
    if os.path.exists(report):
        os.remove(report)
    print("\n自检：在打包产物里真跑一遍 …")
    try:
        subprocess.run([exe, "--selfcheck"], cwd=os.path.dirname(exe),
                       timeout=timeout, capture_output=True)
    except subprocess.TimeoutExpired:
        _fail("自检超时（可能卡在弹窗或浏览器上）")
    if not os.path.isfile(report):
        _fail(f"自检没产出报告：{report}\n"
              "说明 exe 根本没跑起来 —— 手动双击一次，看有没有弹窗或「启动错误.log」")
    with open(report, encoding="utf-8") as f:
        payload = json.load(f)
    os.remove(report)

    checks = payload.get("checks", [])
    for c in checks:
        mark = "OK  " if c["ok"] else "失败"
        print(f"  [{mark}] {c['name']:<22} {c['detail']}  ({c['ms']} ms)")
    if not payload.get("ok"):
        failed = "、".join(c["name"] for c in checks if not c["ok"])
        _fail(f"自检没过：{failed}\n"
              "多半是 EXCLUDES 排多了模块、或 TCL_PRUNE 剪多了 tcl/tk 数据，"
              "把它们调小一点再打。")
    return checks


def report(onefile: bool, out_dir: str, exe: str, took: float, freed: int) -> None:
    kind = "单文件版" if onefile else "目录版"
    size = os.path.getsize(exe) if onefile else _tree_size(out_dir)
    count = 1 if onefile else sum(len(fs) for _b, _d, fs in os.walk(out_dir))
    print(f"\n{'=' * 62}")
    print(f"{kind} 打包完成，用时 {took:.0f}s")
    print(f"  exe    : {exe}")
    print(f"  体积   : {size / 1024 / 1024:.1f} MB"
          + (f"（另剪掉 tcl/tk 冗余数据 {freed / 1024 / 1024:.1f} MB）" if freed else ""))
    print(f"  文件数 : {count}")
    print("=" * 62)
    if not onefile:
        print(f"用法：把整个「{APP_NAME}」文件夹拷走，双击里面的 {APP_NAME}.exe")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"把「{APP_NAME}」打包成 exe")
    ap.add_argument("--onefile", action="store_true",
                    help="打成单文件（方便传给别人，但启动慢很多）")
    ap.add_argument("--no-clean", action="store_true", help="保留 build/ 增量重打")
    ap.add_argument("--no-prune", action="store_true",
                    help="不剪 tcl/tk 冗余数据（批量删除被拦住时用；只是体积大几 MB）")
    args = ap.parse_args(argv)

    check_python()
    if not os.path.isfile(ENTRY):
        _fail(f"入口脚本不存在：{ENTRY}")
    os.makedirs(BUILD_DIR, exist_ok=True)

    out_dir, exe, took = run_build(args.onefile, clean=not args.no_clean)
    freed = 0 if args.no_prune else prune(args.onefile, out_dir)
    run_selfcheck(exe)                    # 排错模块只有真跑才知道，先验再报
    report(args.onefile, out_dir, exe, took, freed)

    print("\n自检已经覆盖了：tcl/tk 画布、模块导入、渲染 SVG、自动保存路径、导 PNG。")
    print("下面这两件事脚本代替不了，交付前手动确认一次：")
    print(f"  1) 双击 {exe}，界面上加几个音、按 Ctrl+E 导出，" )
    print("     顺手看看导出图片时会不会闪一个黑色控制台窗口（不该闪）")
    print("  2) 把整个文件夹拷到别的机器/别的路径再双击一次，确认工程与输出都还在旁边")
    print("  量启动耗时：G:\\Conda\\python.exe tests/bench_startup.py <exe路径>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
