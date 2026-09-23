"""运行目录解析：源码运行 vs 打包成 exe 后运行。
# SPDX-FileCopyrightText: 2026 yaboyabo483
# SPDX-License-Identifier: CC-BY-NC-SA-4.0

**为什么需要单独一个模块**：PyInstaller 打包后 `__file__` 指向的是**解包目录**，
不是程序目录——

  * onefile：整个程序被解到 `%TEMP%\\_MEIxxxxxx\\`，程序退出就删；
  * onedir ：模块被放在 `<exe目录>\\_internal\\` 下。

所以拿 `os.path.dirname(__file__)` 当「程序目录」会出事：
`projects/`（自动保存）和 `output/`（导出谱子）会落到临时目录或 `_internal\\` 里，
前者**一关程序工程就没了**，后者的文件用户根本找不到。踩过这个坑，所以统一走这里。

规则：**打包后一律以 exe 所在目录为程序根目录**（`sys.executable`）。
onefile 下 `sys.executable` 同样是最初那个 exe 的路径（不是临时目录），
所以这一条对两种打包方式都成立。源码运行则用项目根目录（本包的上一级）。
"""

from __future__ import annotations

import os
import sys


def is_frozen() -> bool:
    """是否运行在 PyInstaller 等打包器生成的 exe 里。"""
    return bool(getattr(sys, "frozen", False))


def app_root() -> str:
    """程序根目录：打包后 = exe 所在目录；源码运行 = 项目根目录。"""
    if is_frozen():
        # 用 sys.executable 而不是 sys._MEIPASS：_MEIPASS 是临时解包目录，
        # 而且 onefile 会在退出时删掉它。
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sub_dir(name: str, create: bool = False) -> str:
    """程序根目录下的子目录（默认不创建，交给写入方按需 makedirs）。"""
    path = os.path.join(app_root(), name)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def resolve_out_dir(path: str, create: bool = False) -> str:
    """把「输出目录」参数定下来：相对路径按**程序根目录**解析，绝对路径原样用。

    编谱器/GUI 的默认输出是 `output` 这种相对路径。双击 exe 启动时当前工作目录
    不一定等于 exe 目录（快捷方式可以改「起始位置」），按 CWD 解析会把谱子导到
    莫名其妙的地方，所以这里统一按程序根目录。
    """
    if not os.path.isabs(path):
        path = os.path.join(app_root(), path)
    path = os.path.abspath(path)
    if create:
        os.makedirs(path, exist_ok=True)
    return path
