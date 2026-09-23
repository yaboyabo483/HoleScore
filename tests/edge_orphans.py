# -*- coding: utf-8 -*-
"""临时：找出「哪个 python 任务挂着的无头 msedge」，好精确收掉卡住的那一棵。

只报告 + 可选收树：
  python tests/_tmp_edgewho.py          # 只有头
  python tests/_tmp_edgewho.py kill <pid>   # taskkill /T /F 掉该 pid（及其整棵进程树）

背景：这台机器的无头 Edge 有时「截完图赖着不退出」，`tests/scale_sample.py` 用的是裸
`subprocess.run(msedge)`（没有超时）→ 整个任务就永远卡在那里，还占着 Edge 不放、
把后面排队截图的任务一起拖住。这里按「父进程」把它揪出来收掉。
"""
import subprocess
import sys

QUERY = (
    "Get-CimInstance Win32_Process | "
    "Where-Object { $_.Name -eq 'msedge.exe' -or $_.Name -like 'python*' } | "
    "ForEach-Object { \"$($_.ProcessId)`t$($_.ParentProcessId)`t$($_.Name)`t$($_.CommandLine)\" }"
)


def main():
    ps = subprocess.run(["powershell", "-NoProfile", "-Command", QUERY], capture_output=True)
    out = ps.stdout.decode("gbk", "replace")
    procs = {}
    for line in out.splitlines():
        line = line.strip()
        parts = line.split("\t")
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        procs[parts[0]] = (parts[1], parts[2], parts[3])

    pythons = {pid: v for pid, v in procs.items() if v[1].lower().startswith("python")}
    edges = {pid: v for pid, v in procs.items() if v[1].lower().startswith("msedge")}
    print("python 进程 %d 个，msedge 进程 %d 个" % (len(pythons), len(edges)), flush=True)
    print("\npython 侧（含正在跑哪个脚本）：", flush=True)
    for pid, (ppid, _n, cmd) in pythons.items():
        tail = cmd.split('"')[-1] if '"' in cmd else cmd
        print("  pid=%s ppid=%s  %s" % (pid, ppid, tail[-70:]), flush=True)
    print("\n无头 msedge 主进程（--headless 且不是 --type=...）：", flush=True)
    for pid, (ppid, _n, cmd) in edges.items():
        if "--headless" in cmd and "--type=" not in cmd:
            owner = pythons.get(ppid)
            print("  pid=%s ppid=%s -> %s" % (
                pid, ppid, ("python " + owner[2][-40:]) if owner else "（父进程已不在）"),
                flush=True)

    if len(sys.argv) > 2 and sys.argv[1] == "kill":
        target = sys.argv[2]
        r = subprocess.run(["taskkill", "/PID", target, "/T", "/F"],
                           capture_output=True, encoding="utf-8", errors="replace")
        print("\n收掉 pid=%s rc=%s\n%s" % (target, r.returncode, (r.stdout or "").strip()),
              flush=True)
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
