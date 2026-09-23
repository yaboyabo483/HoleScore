# -*- coding: utf-8 -*-
"""生成 exe 图标：SVG → 无头 Edge 截图 → ICO。
# SPDX-FileCopyrightText: 2026 yaboyabo483
# SPDX-License-Identifier: CC-BY-NC-SA-4.0

    G:\\Conda\\python.exe packaging/make_icon.py

为什么要写脚本而不是塞一个二进制图标进仓库：

  * 图标可以改（改这里的 SVG 再跑一次就行），不用找设计文件；
  * 项目本来就用无头 Edge 把 SVG 栅格化（见 tinwhistle/imageout.py），
    这里复用同一条链路，不引入新依赖（本机没有 PIL）。

ICO 用的是「PNG 内嵌」写法（Vista 之后 Windows 支持）：ICONDIR + 一个 16 字节的目录项
+ 原始 PNG 数据。比手搓 BMP + AND 掩码简单得多，PyInstaller 也认。
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinwhistle import imageout          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 256
SVG_PATH = os.path.join(HERE, "icon.svg")
PNG_PATH = os.path.join(HERE, "icon.png")
ICO_PATH = os.path.join(HERE, "icon.ico")

# 图标=一枚圆角徽章，里面是竖着的哨笛 + 六个孔（前三个实心 = 全按指法的视觉语言）。
# 不用细线：小到 16px 时只有大色块才认得出。
ICON_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" \
viewBox="0 0 256 256">
  <rect x="6" y="6" width="244" height="244" rx="54" fill="#1f6f8b"/>
  <rect x="104" y="40" width="48" height="184" rx="22" fill="#f7edd7"
        stroke="#123c4c" stroke-width="7"/>
  <rect x="112" y="26" width="32" height="26" rx="9" fill="#123c4c"/>
  <circle cx="128" cy="82"  r="8.5" fill="#123c4c"/>
  <circle cx="128" cy="106" r="8.5" fill="#123c4c"/>
  <circle cx="128" cy="130" r="8.5" fill="#123c4c"/>
  <circle cx="128" cy="154" r="8.5" fill="#f7edd7" stroke="#123c4c" stroke-width="4.5"/>
  <circle cx="128" cy="178" r="8.5" fill="#f7edd7" stroke="#123c4c" stroke-width="4.5"/>
  <circle cx="128" cy="202" r="8.5" fill="#f7edd7" stroke="#123c4c" stroke-width="4.5"/>
</svg>
"""


def render_png() -> str:
    """用无头浏览器把 SVG 栅格化成 PNG（带透明背景）。"""
    browser = imageout.find_browser()
    if not browser:
        raise SystemExit("没有找到 Edge/Chrome，无法栅格化图标 SVG")
    with open(SVG_PATH, "w", encoding="utf-8") as f:
        f.write(ICON_SVG)
    if os.path.exists(PNG_PATH):
        os.remove(PNG_PATH)
    cmd = [
        browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--no-first-run", "--no-default-browser-check",
        "--default-background-color=00000000",
        "--user-data-dir=" + os.path.join(os.environ.get("TEMP", "."), "_tw_iconprofile"),
        f"--window-size={SIZE},{SIZE}",
        "--screenshot=" + PNG_PATH,
        "file:///" + SVG_PATH.replace("\\", "/"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180)
    if not imageout._wait_for_file(PNG_PATH):
        raise SystemExit(f"浏览器没输出图标 PNG：{(proc.stderr or '')[:300]}")
    return PNG_PATH


def png_to_ico(png_path: str, ico_path: str, size: int = SIZE) -> str:
    """把一张 PNG 包成单尺寸 ICO（PNG 内嵌写法）。"""
    with open(png_path, "rb") as f:
        png = f.read()
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("截图结果不是 PNG，图标生成失败")
    dim = 0 if size >= 256 else size        # ICO 里 0 表示 256
    header = struct.pack("<HHH", 0, 1, 1)   # reserved / type=icon / 数量
    entry = struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), 6 + 16)
    with open(ico_path, "wb") as f:
        f.write(header + entry + png)
    return ico_path


def main() -> int:
    png = render_png()
    ico = png_to_ico(png, ICO_PATH)
    # 读回来验一下尺寸字段，别写出一个 Windows 不认的壳
    with open(ico, "rb") as f:
        head = f.read(22)
    _res, _type, count = struct.unpack("<HHH", head[:6])
    w, h, _c, _r, _planes, _bits, nbytes, offset = struct.unpack("<BBBBHHII", head[6:22])
    print(f"SVG : {SVG_PATH}")
    print(f"PNG : {png}  ({os.path.getsize(png)} 字节)")
    print(f"ICO : {ico}  ({os.path.getsize(ico)} 字节)  条目={count} "
          f"尺寸={'256' if w == 0 else w}x{'256' if h == 0 else h} "
          f"数据={nbytes} 偏移={offset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
