"""开发用：量启动耗时 —— 源码运行 vs 打包后的 exe。

「启动速度」要是能被验证的，就不能凭感觉。这里量两件事：

  1. **源码运行**的导入开销（`python -c "import editor"` 的墙钟 + 其中导入耗时）；
  2. **exe** 从「进程被创建」到「窗口就绪」的耗时。窗口就绪用 .NET 的
     `Process.WaitForInputIdle()` —— 它就是「进程的消息队列空下来了」，
     对 tkinter 来说等于窗口建好、进入 mainloop，比"进程存在"有意义得多。

PowerShell 放在 Python 的 subprocess 里调用：Bash 工具直接跑 `powershell -Command`
会被本机安全策略拒，但从脚本里 subprocess 起是通的（见 ~/.workbuddy/MEMORY.md）。

运行：G:\\Conda\\python.exe tests/bench_startup.py [exe路径 ...]
不带参数只量源码运行；带上 exe 路径就一并量 exe（可给多个做对比）。
"""

import os
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = 5

# 量 exe：StartProcess 计时 -> 等窗口就绪。用 .NET Stopwatch 而不是
# Measure-Command：后者会把输出吞掉，而且不好把「等窗口」算进去。
PS_MEASURE = r"""
param([string]$Exe, [int]$TimeoutMs = 120000)
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $Exe
$psi.UseShellExecute = $true
$psi.WorkingDirectory = (Split-Path -Parent $Exe)
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$p = [System.Diagnostics.Process]::Start($psi)
$idle = $true
try { $idle = $p.WaitForInputIdle($TimeoutMs) } catch { $idle = $false }
$sw.Stop()
$ms = $sw.Elapsed.TotalMilliseconds
$alive = -not $p.HasExited
if ($alive) { $p.Kill() }
# 输出 "耗时ms|窗口就绪?"，方便 Python 侧解析
"{0}|{1}" -f [int]$ms, $idle
"""


def bench_python(body: str, runs: int = 3) -> float:
    """跑一次 python -c，返回最快一次的墙钟毫秒。"""
    code = (f"import sys,time;sys.path.insert(0,r'{ROOT}');"
            f"t=time.perf_counter();{body};"
            "print(int((time.perf_counter()-t)*1000))")
    best = None
    for _ in range(runs):
        t0 = time.perf_counter()
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        wall = (time.perf_counter() - t0) * 1000
        inner = int((proc.stdout or "0").strip().splitlines()[-1])
        if best is None or inner < best[1]:
            best = (wall, inner)
    return best


def measure_exe(exe: str, runs: int = RUNS, timeout_ms: int = 120000) -> list:
    """量 exe 启动到窗口就绪的毫秒数，返回每次的耗时列表。"""
    script = os.path.join(os.environ.get("TEMP", "."), "_tw_bench.ps1")
    with open(script, "w", encoding="utf-8") as f:
        f.write(PS_MEASURE)
    out = []
    for i in range(runs):
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", script, "-Exe", exe, "-TimeoutMs", str(timeout_ms)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
        if "|" not in line:
            raise RuntimeError(f"没量到结果：{line or (proc.stderr or '')[:300]}")
        ms, idle = line.split("|")
        if idle.strip().lower() != "true":
            raise RuntimeError(f"第 {i + 1} 次没等到窗口就绪（可能启动失败）")
        out.append(int(ms))
    return out


def main(argv) -> int:
    print(f"Python: {sys.version.split()[0]}  ({sys.executable})")
    print()
    print("— 源码运行 —")
    for label, body in (("空解释器进程", "pass"),
                        ("import tkinter", "import tkinter"),
                        ("import editor（tkinter + 本项目全部模块）", "import editor")):
        wall, inner = bench_python(body)
        print(f"  {label:<42} 墙钟 {wall:>6.0f} ms   导入 {inner:>6.0f} ms")

    exes = [a for a in argv if a]
    for exe in exes:
        if not os.path.isfile(exe):
            print(f"\n[跳过] 找不到 {exe}")
            continue
        tag = "目录版" if os.path.isdir(os.path.join(
            os.path.dirname(exe), "_internal")) else "单文件版"
        size = os.path.getsize(exe) / 1024 / 1024
        print(f"\n— {os.path.basename(exe)}（{tag}，主程序 {size:.1f} MB）—")
        times = measure_exe(exe)
        first, rest = times[0], times[1:]
        print(f"  首次运行      {first:>6} ms")
        if rest:
            print(f"  后续运行      {min(rest):>6} ms（最快） / "
                  f"{statistics.median(rest):>6.0f} ms（中位）  n={len(rest)}")
        print(f"  全部         {times}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
