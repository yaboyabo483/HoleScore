# -*- coding: utf-8 -*-
"""开发用：把编谱器「两个八度指法表」25 格的**简谱标签 + 音名 + 主指法**整表打出来。

调指法（`tinwhistle/fingering.py`）时最有用——指法表上的标签是编谱器自己按当前
「1=X」推出来的（`EditorApp._abs_to_jianpu`），跟 `fingering_for_index` 的孔位
是不是对得上，一眼就能看出来。这里直接用**真实方法**（拿 stub 当 self，不建窗口）。
想看别的口径就改下面的 `dump()` 参数。

    D 调哨笛 · 1=G · 全按作5
     idx  简谱标签   音名(表下)   主指法(孔1..孔6)
       0  5.         D           ●●●●●●   ← 全按
      12  5          D 高         ○●●●●●          ← 筒音高一个八度：放开孔1
      24  5'         D 高         ○●●●●●          ← 筒音高两个八度：同口径

运行：G:\\Conda\\python.exe tests/fingering_table.py    （要 tkinter，所以用系统 Python）

注意口径（改指法时别踩）：
  - **全按只属于第一八度的筒音**（idx 0）；更高八度的同一个音一律 `HIGH_TONIC`
    （放开孔1、其余全按）。原来只写成 `if idx == 12` 一条特例，idx 24 就掉回全按了。
  - 标签由 `_abs_to_jianpu` 生成，那里把八度夹在 `[-1, 1]`（编谱器的键盘只有
    低/中/高三档）。所以**别的口径下** idx 24 的标签可能是「夹过」的（如 1=D 时
    本该 `1''` 却写成 `1'`）——这是标签层的老限制，与本表要看的「孔位」无关。
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import editor  # noqa: E402
from tinwhistle import fingering, jianpu  # noqa: E402


class _Var:
    """替 tk.StringVar：`_abs_to_jianpu` 只用到 .get()"""

    def __init__(self, v):
        self._v = v

    def get(self):
        return self._v


def marks(holes) -> str:
    return "".join({1: "●", 0: "○", 2: "◐"}[h] for h in holes)


def dump(key: str, whistle: str) -> None:
    stub = types.SimpleNamespace(key_var=_Var(key), whistle_var=_Var(whistle))
    tonic = fingering.WHISTLE_TONICS[whistle]
    mode = fingering.mode_label(whistle, key) or "无对应口径"
    print(f"\n=== {whistle} 调哨笛 · 1={key} · {mode} ===")
    print(" idx  简谱标签   音名(表下)   主指法(孔1..孔6)")
    for idx in range(fingering.MAX_INDEX + 1):
        token, _note = editor.EditorApp._abs_to_jianpu(stub, tonic + idx)
        label = jianpu.NOTE_NAMES_SHARP[(tonic + idx) % 12] + (" 高" if idx >= 12 else "")
        holes = fingering.fingering_for_index(idx)
        note = "   ← 全按" if holes == (1, 1, 1, 1, 1, 1) else ""
        print(f" {idx:>3}  {token:<10} {label:<10}  {marks(holes)}{note}")
    # 整表的硬约束：只有第一八度的筒音是全按
    closed = [i for i in range(fingering.MAX_INDEX + 1)
              if fingering.fingering_for_index(i) == (1, 1, 1, 1, 1, 1)]
    print(f"  [检查] 全音域里全按的格子: {closed}（应当只有 [0]）")


def main() -> int:
    dump("G", "D")          # 1=G → D 调哨笛即「全按作5」（README 示例的口径）
    dump("D", "D")          # 全按作1
    dump("D", "C")          # 无对应口径（调外）
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
