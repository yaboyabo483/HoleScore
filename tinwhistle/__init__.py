"""哨笛洞洞谱编辑器（编谱器）
# SPDX-FileCopyrightText: 2026 yaboyabo483
# SPDX-License-Identifier: CC-BY-NC-SA-4.0

零第三方依赖（纯标准库 + tkinter）。
模块划分：
    apppaths   程序根目录定位（源码运行 / PyInstaller 打包后都能找对 output/projects）
    jianpu     简谱文本解析（音高事件序列，含时值与调号头）
    fingering  哨笛指法表与自动转调
    beaming    减时线连尾（同一拍共用一条横线）
    project    编谱工程模型（音符文档 <-> 渲染事件的转换、导出、存取）
    render     SVG 洞洞谱渲染 + HTML 批量索引
    imageout   SVG -> PNG 栅格化（调用系统 Edge/Chrome）
    procutil   子进程调用封装（统一编码，避免中文输出乱码）

入口：
    editor.py      编谱器 GUI（也是打包成 exe 的唯一入口）
"""

__version__ = "1.0.0"
