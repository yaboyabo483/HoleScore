# -*- coding: utf-8 -*-
"""打包相关契约测试：apppaths / procutil 的无窗标志 / build_exe 的打包参数。

需用带 tkinter 的 Python 运行：G:\\Conda\\python.exe tests/qa_packaging.py

为什么值得单独测：

  * `--exclude-module` 排错模块、剪 tcl/tk 数据，**打包阶段都不报错**，只在运行时才炸。
    所以这里直接算出编谱器「真正导入」的模块集合（干净子进程里 before/after 求差集），
    再断言它跟排除清单没有交集 —— 排到一个真用到的模块就会失败。
    （不要用「导入后看 sys.modules 里有没有」那套 —— 解释器启动时就会顺带导入一堆
    模块，跟冻结后运行时需不需要没关系，结论会被带偏。）
  * 打包后 `__file__` 指向解包目录，工程/输出会写错地方 —— 这是会**丢用户数据**的
    bug（自动保存写进临时目录，一关就没了）。apppaths 的 frozen 行为在这里钉死。
  * 无控制台的 exe 调外部命令会闪黑框，靠 procutil 统一补 CREATE_NO_WINDOW。
"""

import inspect
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

fails = []


def check(name, cond, detail=""):
    tag = "OK " if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import build_exe                                          # noqa: E402
from tinwhistle import apppaths, procutil                 # noqa: E402

# ---------------------------------------------------------------- apppaths
print("— apppaths：程序根目录解析 —")

check("源码运行时 is_frozen 为假", apppaths.is_frozen() is False)
check("源码运行时 app_root 就是项目根", apppaths.app_root() == ROOT, apppaths.app_root())
check("sub_dir 拼在 app_root 下",
      apppaths.sub_dir("output") == os.path.join(ROOT, "output"))
_tmp_dir = apppaths.sub_dir("_qa_tmp_dir", create=True)
check("sub_dir(create=True) 会建目录", os.path.isdir(_tmp_dir), _tmp_dir)
shutil.rmtree(_tmp_dir, ignore_errors=True)
check("相对输出目录按 app_root 解析",
      apppaths.resolve_out_dir("output") == os.path.join(ROOT, "output"))
check("绝对输出目录原样保留",
      apppaths.resolve_out_dir(r"D:\谱\myout") == os.path.abspath(r"D:\谱\myout"))

# 模拟「打包后运行」：app_root 必须跟 sys.executable 走，而不是 __file__
_real_frozen, _real_exe = getattr(sys, "frozen", None), sys.executable
try:
    sys.frozen = True
    sys.executable = r"C:\some\where\编谱器\编谱器.exe"
    check("打包后 is_frozen 为真", apppaths.is_frozen() is True)
    check("打包后 app_root = exe 所在目录",
          apppaths.app_root() == os.path.abspath(r"C:\some\where\编谱器"),
          apppaths.app_root())
    check("打包后 projects 落在 exe 旁边（不是 _internal 里）",
          apppaths.sub_dir("projects") == os.path.abspath(r"C:\some\where\编谱器\projects"))
    check("打包后相对输出目录也按 exe 旁解析",
          apppaths.resolve_out_dir("output") == os.path.abspath(r"C:\some\where\编谱器\output"))
finally:
    if _real_frozen is None:
        del sys.frozen
    else:
        sys.frozen = _real_frozen
    sys.executable = _real_exe

# editor.py 是真正的使用者：拿它的模块级常量验收，避免「改了 apppaths 忘了改调用方」
print("— editor：工程/输出目录常量 —")
import editor                                             # noqa: E402

check("editor.PROJECT_DIR 在程序目录下",
      os.path.dirname(editor.PROJECT_DIR) == apppaths.app_root(), editor.PROJECT_DIR)
check("editor.OUTPUT_DIR 在程序目录下",
      os.path.dirname(editor.OUTPUT_DIR) == apppaths.app_root(), editor.OUTPUT_DIR)
check("autosave 跟着 PROJECT_DIR 走",
      os.path.dirname(editor.AUTOSAVE_PATH) == editor.PROJECT_DIR)
for label, p in (("PROJECT_DIR", editor.PROJECT_DIR), ("OUTPUT_DIR", editor.OUTPUT_DIR)):
    check(f"{label} 没有落进 _internal（打包后 __file__ 的坑）",
          "_internal" not in p.split(os.sep), p)

# ---------------------------------------------------------------- procutil
print("— procutil：外部命令不闪黑框 / 宽松解码 —")
src = inspect.getsource(procutil.run_capture)
check("Windows 上默认补 CREATE_NO_WINDOW", "CREATE_NO_WINDOW" in src)
check("保留了宽松解码 errors=replace", 'errors="replace"' in src)

proc = procutil.run_capture([sys.executable, "-c", "print(1)"], timeout=30,
                            encoding="utf-8")
check("调用方不传 creationflags 时能正常抓到输出",
      proc.returncode == 0 and proc.stdout.strip() == "1")
if os.name == "nt":
    proc = procutil.run_capture([sys.executable, "-c", "print(2)"], timeout=30,
                                encoding="utf-8", creationflags=0)
    check("调用方显式传 creationflags 时不覆盖它",
          proc.returncode == 0 and proc.stdout.strip() == "2")

# ---------------------------------------------------------------- build_exe
print("— build_exe：打包参数 —")
args = build_exe.pyinstaller_args(onefile=False, clean=True)
check("默认打目录版（onedir = 启动快的关键）", "--onedir" in args)
check("目录版不带 --onefile", "--onefile" not in args)
check("GUI 程序不弹控制台", "--windowed" in args)
check("不开 UPX（壳只会拖慢加载）", "--noupx" in args)
check("有 --noconfirm（覆盖旧产物不卡住）", "--noconfirm" in args)
check("带上 --clean", "--clean" in args)
check("入口是 packaging/entry_editor.py",
      args[-1].replace("\\", "/").endswith("packaging/entry_editor.py"), args[-1])
check("--no-clean 时不该有 --clean",
      "--clean" not in build_exe.pyinstaller_args(onefile=False, clean=False))

one = build_exe.pyinstaller_args(onefile=True, clean=False)
check("单文件版用 --onefile", "--onefile" in one and "--onedir" not in one)
# 名字从 build_exe.APP_NAME 派生（改名时这条不会误报），且必须与目录版不同
check("单文件版名字带后缀，不和目录版撞名",
      one[one.index("--name") + 1] == build_exe.APP_NAME + "-单文件"
      and build_exe.pyinstaller_args(onefile=False, clean=False)[
          build_exe.pyinstaller_args(onefile=False, clean=False).index("--name") + 1]
      == build_exe.APP_NAME)

check("排除清单没有重复项",
      len(set(build_exe.EXCLUDES)) == len(build_exe.EXCLUDES),
      str([m for m in build_exe.EXCLUDES if build_exe.EXCLUDES.count(m) > 1]))

# 剪 tcl/tk 数据时绝不能碰编码表 —— 那会让 tcl 起不来
for rel in build_exe.TCL_PRUNE:
    parts = rel.replace("\\", "/").lower().split("/")
    check(f"剪裁项不碰 tcl/tk 编码表或核心库：{rel}",
          not any(p in ("encoding", "encodings", "tcl8", "tk8") or
                  p.startswith("tcl8.") or p.startswith("tk8.") for p in parts), rel)

# ---------------------------------------------------------------- 排除清单的真实性
# 曾经的写法是「导入一遍，看 sys.modules 里有没有 EXCLUDES 里的模块」。**不准**：
# 解释器启动时（site / sitecustomize / 各种 .pth）就可能已经导入了 json、shutil、
# socket…，这些跟「冻结后运行时需不需要」毫无关系，结论会被带偏（本机上 bz2/lzma/
# selectors 明明只是启动时被顺带导入，却报成「排到了要用的模块」）。
#
# 现在的写法是**差集**：在干净子进程里先记下启动时就已导入的模块（before），
# 再 import editor，两边之差才是 editor 真正新拉进来的模块。启动预导入天然落在
# before 里，不会再干扰结论。断言这个差集与 EXCLUDES 无交集即可。
#
# （也曾试过装 meta_path 拦截器把 EXCLUDES 全遮住再跑一遍 —— 思路没错，但 Tk
#  子进程 destroy 后不保证退出，父进程 communicate() 会一直等管道 EOF，表现成
#  「明明跑完了却挂住」。换成这个确定性静态检查，几秒出结果。）
print("— 排除清单：程序真正导入的模块不许被排掉 —")
CLOSURE_SNIPPET = (
    "import sys, json;"
    f"sys.path.insert(0, r'{ROOT}');"
    "before = set(sys.modules);"
    "import editor;"
    "new = sorted({m.split('.')[0] for m in set(sys.modules) - before"
    " if not m.startswith('_')});"
    "print('MODULES=' + json.dumps(new))"
)
proc = subprocess.run([sys.executable, "-c", CLOSURE_SNIPPET], capture_output=True,
                      text=True, encoding="utf-8", errors="replace", timeout=120)
_closure = set()
for _line in (proc.stdout or "").splitlines():
    if _line.startswith("MODULES="):
        try:
            _closure = set(json.loads(_line[len("MODULES="):]))
        except ValueError:
            _closure = set()
check("能拿到 editor 的真实导入闭包（子进程导入成功）",
      proc.returncode == 0 and bool(_closure),
      ((proc.stderr or "")[-500:] or "闭包为空"))
_collide = sorted(_closure & set(build_exe.EXCLUDES))
check("EXCLUDES 一个都没排到程序真正用到的模块", not _collide,
      f"排多了：{_collide} ｜ editor 实际用到：{sorted(_closure)}")

# 反过来说，tkinter 和渲染链路依赖的几个必须留着 —— 防止有人手滑加进排除表
# concurrent 是给多页 PNG 并行用的（imageout.pages_to_png 的线程池），
# winsound 是试听那条链路（tinwhistle/sound.py）—— 排掉的话打包阶段不报错、
# 运行时才炸，所以正反两面都钉住。
for must in ("tkinter", "re", "json", "html", "shutil", "subprocess", "tempfile",
             "concurrent", "winsound"):
    check(f"必备模块 {must} 不在排除清单里", must not in build_exe.EXCLUDES)

# 只保留编谱器：OCR / CLI 那条链路的模块不该再留在项目里
print("— 只保留编谱器：已删模块不许再回来 —")
for gone in ("ocr", "imaging", "pipeline", "main", "gui"):
    check(f"已删除的模块 {gone} 不在项目里",
          not os.path.exists(os.path.join(ROOT, f"{gone}.py"))
          and not os.path.exists(os.path.join(ROOT, "tinwhistle", f"{gone}.py")))
check("tinwhistle 包内只剩编谱器需要的模块",
      sorted(m[:-3] for m in os.listdir(os.path.join(ROOT, "tinwhistle"))
             if m.endswith(".py")) ==
      ["__init__", "apppaths", "beaming", "fingering", "imageout", "jianpu",
       "procutil", "project", "render", "sound"],
      str(sorted(m for m in os.listdir(os.path.join(ROOT, "tinwhistle"))
                 if m.endswith(".py"))))

# ---------------------------------------------------------------- 入口脚本
print("— 打包入口 —")
entry = os.path.join(ROOT, "packaging", "entry_editor.py")
check("入口脚本存在", os.path.isfile(entry), entry)
with open(entry, encoding="utf-8") as f:
    entry_src = f.read()
check("入口支持 --selfcheck 自检", "--selfcheck" in entry_src)
check("入口会写启动错误日志（无控制台时唯一的线索）", "启动错误.log" in entry_src)
check("入口在打包链路上没有 print()（--windowed 下 stdout 是 None）",
      "print(" not in entry_src)
check("图标文件已生成", os.path.isfile(os.path.join(ROOT, "packaging", "icon.ico")))

# 无控制台的 exe 里 sys.stdout 是 None，编谱器这条链路一句 print 都不能有
with open(os.path.join(ROOT, "editor.py"), encoding="utf-8") as f:
    check("editor.py 没有 print（打包后 stdout 为 None 会炸）", "print(" not in f.read())

print()
print("=== 打包契约:", "全部通过" if not fails else f"失败 {len(fails)}: {fails}")
sys.exit(1 if fails else 0)
