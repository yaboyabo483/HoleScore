"""减时线（符尾）分组算法 —— 简谱规范
# SPDX-FileCopyrightText: 2026 yaboyabo483
# SPDX-License-Identifier: CC-BY-NC-SA-4.0

规范要点：
  1. 八分音符画一条减时线、十六分画两条，横线在数字下方；
  2. **同一拍内相邻的短音符共用一条连续減时线**（连尾），不是每个音各画一小段；
  3. 十六分的第二条线只画在十六分音符下方；连续十六分则第二条线也连成一段；
  4. **短休止符和音符一样参与连尾**（`5/ 0/ 5/` 是同一条线贯穿三格）——
     因为简谱的减时线是「这一拍是几分音符」的标记，休止符也带时值，
     把它挖掉会让同一拍被切成好几截、看着像换了拍子；
     真正打断连尾的是：小节线 / 反复记号 / 四分及更长的音、休止；
  5. 单个短音符（不与同拍相邻短音符相连）仍画自己的一段短线。

拍内分组单位（beat_unit，四分音符数）：
  2/4、3/4、4/4 → 1.0（每拍）
  2/2 → 2.0；3/8 → 1.5（整小节一组）；6/8 → 1.5（附点四分拍）

输出：[(起始展示序号, 结束展示序号, 线序号)]，线序号 0=第一条（八分线），1=第二条（十六分线）。
起止序号相同表示单音符短线。
"""

from __future__ import annotations

from . import jianpu

BEAT_UNIT = {"2/4": 1.0, "3/4": 1.0, "4/4": 1.0, "2/2": 2.0, "3/8": 1.5, "6/8": 1.5}

# 参与连尾的基时值（四分音符为单位）：八分 0.5、十六分 0.25
BEAMABLE_BASE = (0.5, 0.25)

# 参与连尾的事件类型：音符与**休止符**（休止符同样带时值，见模块文档第 4 条）
BEAMABLE_KINDS = ("note", "rest")

# 会打断连尾的「分隔性」事件：小节线与反复记号（都表示段落边界）
BREAK_KINDS = ("bar", "repeat")


def _f(obj, key, default=None):
    """统一取值：兼容 dict（工程/编辑器的 NoteDoc）与对象（渲染器的 NoteEvent）"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def base_duration(duration: float) -> float:
    """去掉附点后的基时值"""
    return duration / jianpu.DOT_FACTOR if jianpu.is_dotted(duration) else duration


def beam_lines_of(duration: float) -> int:
    """该时值需要几条减时线（附点不影响条数）"""
    return jianpu.duration_beams(duration)


def _positions(notes, beats: str):
    """算出每个音符在小节内的位置（四分音符为单位），返回列表（与 notes 等长，非音符为 None）"""
    unit_cap = jianpu.BEATS_PER_MEASURE.get(beats, 4.0)
    pos_list, pos, measure = [], 0.0, 0
    for doc in notes:
        kind = _f(doc, "kind")
        if kind in BREAK_KINDS:          # 小节线 / 反复记号：都是段落边界，位置归零
            pos_list.append(None)
            pos, measure = 0.0, measure + 1
            continue
        dur = 1.0 if kind == "hold" else _f(doc, "duration", 1.0)
        pos_list.append((measure, pos))
        pos += dur
        if pos >= unit_cap - 1e-6:
            pos = 0.0
            measure += 1
    return pos_list


def beam_segments(notes, beats: str = "4/4") -> list:
    """计算减时线段落。

    notes: 展示顺序的事件列表（每条含 kind / duration）
    返回 [(i0, i1, level), ...]

    休止符与音符一视同仁（都是 BEAMABLE_KINDS）：`5/ 0/ 5/` 得到一段贯穿三格的线。
    四分及更长的音 / 休止、小节线、反复记号会打断连尾。
    """
    unit = BEAT_UNIT.get(beats, 1.0)
    pos_list = _positions(notes, beats)
    segments = []

    def beamable(i) -> bool:
        doc = notes[i]
        if _f(doc, "kind") not in BEAMABLE_KINDS:
            return False
        return round(base_duration(_f(doc, "duration", 1.0)), 6) in BEAMABLE_BASE

    def group_key(i):
        measure, pos = pos_list[i]
        return (measure, int(pos // unit + 1e-9))

    i = 0
    n = len(notes)
    while i < n:
        if not beamable(i):
            i += 1
            continue
        key = group_key(i)
        j = i
        while j + 1 < n and beamable(j + 1) and group_key(j + 1) == key:
            j += 1
        # 第一条线：整组一段（单音符也返回，画自己的短线）
        segments.append((i, j, 0))
        # 第二条线：组内连续十六分（基时值 0.25）各自成段
        k = i
        while k <= j:
            if round(base_duration(_f(notes[k], "duration", 1.0)), 6) == 0.25:
                m = k
                while (m + 1 <= j
                       and round(base_duration(_f(notes[m + 1], "duration", 1.0)), 6) == 0.25):
                    m += 1
                segments.append((k, m, 1))
                k = m + 1
            else:
                k += 1
        i = j + 1
    return segments


# ---------------- 连音线 / 圆滑线 ----------------
def next_sounding(notes, i: int):
    """从 i 往后找下一个“发声”事件（跳过小节线/反复记号），返回其下标；找不到返回 None"""
    j = i + 1
    while j < len(notes) and _f(notes[j], "kind") in BREAK_KINDS:
        j += 1
    if j < len(notes) and _f(notes[j], "kind") == "note":
        return j
    return None


def slur_spans(notes) -> list:
    """解析连音线区间。

    规则：
      - doc["slur_start"] 标记起点（可嵌套：用栈记录未闭合的起点，后开先闭）；
      - 遇到 doc["slur_end"] 时与最近的未闭合起点配对；
      - 同音高 → kind="tie"（延音线，唱奏成一个长音）；
      - 不同音高 → kind="slur"（圆滑线，连奏）;
      - doc["tie"] 为 True 时，与紧随其后的下一个音相连（自动小节线可穿过其中）；
      - 跨小节线的连音线属于正常写法，因此查找时会跳过 bar 事件。
    返回 [{"i0", "i1", "kind"}, ...]
    """
    spans, pending = [], []
    for i, doc in enumerate(notes):
        if _f(doc, "kind") != "note":
            continue
        if _f(doc, "tie"):
            nxt = next_sounding(notes, i)
            if nxt is not None:
                spans.append({"i0": i, "i1": nxt,
                              "kind": "tie" if same_pitch(doc, notes[nxt]) else "slur"})
        if _f(doc, "slur_start"):
            pending.append(i)
        if _f(doc, "slur_end") and pending:
            j = pending.pop()                 # 后开先闭，支持嵌套
            if i > j:
                spans.append({"i0": j, "i1": i,
                              "kind": "tie" if same_pitch(notes[j], doc) else "slur"})
    return spans


def span_depth(spans, sp) -> int:
    """该连音线被多少条其它连音线包含（用于把嵌套弧线逐层抬高，避免压线）"""
    return sum(1 for o in spans
               if o is not sp and o["i0"] <= sp["i0"] and sp["i1"] <= o["i1"]
               and (o["i0"], o["i1"]) != (sp["i0"], sp["i1"]))


# ---------------- 切音 ----------------
def is_cut(doc) -> bool:
    """该事件是不是「切音」：一个自带窄格子的小音符（见 render.cell_width）。

    布局层面由渲染器/编谱器自己处理——切音不再把记号搬到后一个音身上，
    而是**自己占一个小小的窄格子**紧跟在后一个音前面。
    """
    return _f(doc, "kind", "note") == "note" and bool(_f(doc, "short", False))


def same_pitch(a, b) -> bool:
    return (_f(a, "degree") == _f(b, "degree")
            and _f(a, "accidental", 0) == _f(b, "accidental", 0)
            and _f(a, "octave", 0) == _f(b, "octave", 0))
