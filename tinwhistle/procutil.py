"""跑外部命令的薄封装 —— 两件事：**别按本机代码页严格解码**、**别闪黑框**
# SPDX-FileCopyrightText: 2026 yaboyabo483
# SPDX-License-Identifier: CC-BY-NC-SA-4.0

坑（这个仓库里已经在 4 处各踩过一次，所以抽到这里来）：

`subprocess.run(..., text=True)` 会按**本机代码页**（中文 Windows = GBK）**严格**解码
子进程的 stdout/stderr。而现实里这两股输出经常不是那个编码：

  * 无头浏览器（Chromium/Edge）的日志是 **UTF-8**；
  * PowerShell、tesseract 这些工具报错时可能混进非法字节序列。

一旦碰上解不开的字节，`UnicodeDecodeError` 是在 subprocess 的**读取线程**里抛的 ——
于是非常误导人：主线程这边 `subprocess.run()` **照常返回**，只是 stdout/stderr
**静默变成 None**（真正的错误详情全丢，`proc.stderr.strip()` 直接变
`'NoneType' object has no attribute 'strip'` 或者错误信息是空的），
控制台却打出一整段 `Exception in thread Thread-2 (_readerthread)` 的 traceback，
看起来像程序崩了。

所以外部命令统一走这里：`errors="replace"`，非法字节解成 U+FFFD，永不炸。
"""

from __future__ import annotations

import os
import subprocess

# 打包成 exe（PyInstaller --windowed）之后父进程**没有控制台**了，这时再起
# PowerShell / tesseract 这类控制台程序，Windows 会给它配一个新控制台 —— 表现就是
# 导出图片、抓屏、OCR 的一瞬间弹一个黑框然后消失。CREATE_NO_WINDOW 正好治这个。
# 源码运行（从命令行或 .bat 启动）时父进程本来就有控制台、子进程会继承，
# 加这个标志对我们没有区别：输出走的是管道，不依赖控制台。
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def run_capture(cmd, timeout: float = 120, encoding: str | None = None, **kwargs):
    """执行 `cmd` 抓 stdout/stderr，**宽松解码**（不会因编码问题抛异常）。

    encoding 传 `None`：用本机代码页解（适合 PowerShell 这类按系统代码页输出的工具，
    中文还能正常读出来）；传 `"utf-8"`：按 UTF-8 解（适合 Chromium 这类统一 UTF-8
    输出的工具）。两种都带 `errors="replace"`。

    默认带上 `creationflags=CREATE_NO_WINDOW`（Windows），避免打包后的无控制台程序
    每调一次外部命令就闪一下黑框；调用方自己传了 `creationflags` 就以调用方为准。

    超时/找不到可执行文件仍按 subprocess 的规矩抛 `TimeoutExpired` / `OSError`，
    由调用方决定包成什么异常。
    """
    if _NO_WINDOW:
        kwargs.setdefault("creationflags", _NO_WINDOW)
    return subprocess.run(cmd, capture_output=True, timeout=timeout,
                          text=True, encoding=encoding, errors="replace", **kwargs)
