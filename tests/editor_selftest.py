"""编谱器自测（无 mainloop，直接驱动界面逻辑）

用带 tkinter 的 Python 运行：
  G:\\Conda\\python.exe tests/editor_selftest.py
"""

import os
import re
import sys
import threading
import time
import xml.dom.minidom

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

from tinwhistle import beaming, fingering, jianpu, project as pj, render
import editor as ed

# 无头测试：阻断所有弹窗（否则「恢复工程」对话框会干扰断言），并清掉旧自动保存
messagebox.askyesno = lambda *a, **k: False
messagebox.showinfo = lambda *a, **k: None
messagebox.showwarning = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: None
if os.path.exists(ed.AUTOSAVE_PATH):
    os.remove(ed.AUTOSAVE_PATH)

# 试听：把发声换成桩（测试里不真响，也不依赖机器有没有音频设备）。
# Beeper 构造时会把 `sound._tone` / `sound._stop_now` 抓进去，所以必须在 EditorApp 建好**之前**换。
TONES = []          # 发出去的音 [(hz, ms), ...]
STOPS = []          # 掐音动作的次数
ed.sound._tone = lambda hz, ms: TONES.append((hz, ms))
ed.sound._stop_now = lambda: STOPS.append(1)

PASS = FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name} {extra}")


def main():
    root = tk.Tk()
    root.withdraw()
    app = ed.EditorApp(root)
    root.update()

    print("— 基础编谱 —")
    for d in (5, 6, 1):
        app.append_degree(d)
    app.set_state("octave", 1)
    app.append_degree(2)
    app.set_state("dur", 0.5)
    app.append_degree(3)
    app.set_state("dur", 0.25)
    app.set_state("octave", 0)
    app.append_rest()
    app.append_hold()
    app.append_bar()
    root.update()
    notes = app.proj["notes"]
    check("追加 8 个事件", len(notes) == 8, len(notes))
    check("时值记录正确", notes[5]["duration"] == 0.25 and notes[4]["duration"] == 0.5)
    check("八度记录正确", notes[3]["octave"] == 1)
    check("记号文本", pj.token_of(notes[4]) == "3'/" and pj.token_of(notes[3]) == "2'",
          f"{pj.token_of(notes[4])} {pj.token_of(notes[3])}")

    print("— 指法反查与自选指法 —")
    app.custom_holes = [1, 1, 1, 1, 1, 1]
    app._refresh_holes_label()
    tok, note = app._holes_to_jianpu([1, 1, 1, 1, 1, 1])
    check("全按 = D 哨笛筒音 D1", note == "D" and tok == "1", f"{tok} {note}")
    tok2, note2 = app._holes_to_jianpu([0, 0, 0, 0, 0, 0])
    check("全开 = C#7", note2 == "C#" and tok2 == "7", f"{tok2} {note2}")
    app.toggle_hole(5)
    check("孔位循环 按->放", app.custom_holes[5] == 0)
    app.toggle_hole(5)
    check("孔位循环 放->半", app.custom_holes[5] == 2)
    check("半孔反查仍可识别", app._whistle_index([1, 1, 1, 1, 1, 2]) == 1)
    check("非法组合反查为 None", app._whistle_index([2, 2, 2, 2, 2, 2]) is None)

    app.custom_holes = [1, 1, 0, 0, 0, 0]
    app._refresh_holes_label()
    before = len(app.proj["notes"])
    app.append_custom()
    check("追加自选指法", len(app.proj["notes"]) == before + 1)
    check("自选孔位被保留", app.proj["notes"][-1]["holes"] == [1, 1, 0, 0, 0, 0])
    check("自选指法音名", app._refresh_info() or True)

    print("— 音阶面板追加 —")
    app.set_state("dur", 1.0)
    before = len(app.proj["notes"])
    app.append_from_scale(9)         # D 哨笛第 10 个半音 = B（D 大调第 6 级）
    doc = app.proj["notes"][-1]
    check("音阶面板追加 B(6 级)", doc["degree"] == 6, doc)
    app.append_from_scale(11)        # 第 12 个半音 = C#（D 大调第 7 级）
    check("音阶面板追加 C#(7 级)", app.proj["notes"][-1]["degree"] == 7)
    app.append_from_scale(12)        # 第二八度筒音 D -> 高八度 1
    check("第二八度筒音 = 高八度1", pj.token_of(app.proj["notes"][-1]) == "1'",
          pj.token_of(app.proj["notes"][-1]))
    check("音阶面板不加自选孔位", doc.get("holes") is None)

    print("— 编辑操作 —")
    app.sel = len(app.proj["notes"]) - 1
    app.set_dur(1.0)
    check("改时值", app.proj["notes"][app.sel]["duration"] == 1.0)
    app.shift_octave(-1)
    check("降八度", app.proj["notes"][app.sel]["octave"] == 0,
          app.proj["notes"][app.sel]["octave"])
    app.shift_acc(1)
    check("加升号", app.proj["notes"][app.sel]["accidental"] == 1)
    n = len(app.proj["notes"])
    app.sel = 0
    app.move_note(1)
    check("右移交换", app.proj["notes"][1]["degree"] == 5 and n == len(app.proj["notes"]))
    app.undo()
    check("撤销恢复顺序", app.proj["notes"][0]["degree"] == 5)
    app.redo()
    check("重做生效", app.proj["notes"][1]["degree"] == 5)
    app.sel = 0
    app.delete_note()
    check("删除音符", len(app.proj["notes"]) == n - 1)

    print("— 自选指法应用到选中音 / 恢复自动 —")
    app.sel = 0
    app.custom_holes = [1, 1, 1, 1, 1, 0]
    app.apply_custom_to_sel()
    check("应用自选指法", app.proj["notes"][0].get("holes") == [1, 1, 1, 1, 1, 0])
    app.reset_holes()
    check("恢复自动指法", app.proj["notes"][0].get("holes") is None)

    print("— 调号/哨笛切换联动 —")
    app.key_var.set("G")
    root.update()
    tok, note = app._holes_to_jianpu([1, 1, 1, 1, 1, 1])
    check("G 调下 D 筒音 = 低八度 5", tok == "5." and note == "D", f"{tok} {note}")
    app.key_var.set("D")
    root.update()
    app.whistle_var.set("C")
    root.update()
    tok, note = app._holes_to_jianpu([1, 1, 1, 1, 1, 1])
    check("C 哨笛 + D 调：筒音 C = 低八度 b7", tok == "b7." and note == "C", f"{tok} {note}")
    tok, note = app._holes_to_jianpu([0, 0, 0, 0, 0, 0])
    check("C 哨笛全开 = B（D 调下 6 级）", note == "B" and tok == "6", f"{tok} {note}")
    app.key_var.set("C")
    root.update()
    tok, note = app._holes_to_jianpu([0, 0, 0, 0, 0, 0])
    check("C 哨笛 + C 调：全开 B = 7 级", note == "B" and tok == "7", f"{tok} {note}")
    app.key_var.set("D")
    app.whistle_var.set("D")
    root.update()
    tok, note = app._holes_to_jianpu([0, 0, 0, 0, 0, 0])
    check("D 哨笛全开 = C# = 7 级", tok == "7" and note == "C#", f"{tok} {note}")
    tok, _ = app._holes_to_jianpu([1, 1, 1, 1, 1, 2])   # 半孔6 = D#
    check("调外音反查带升号", tok == "#1", tok)

    print("— 附点时值 —")
    app.set_state("dur", 1.0)
    app.st_dot = False
    app.append_degree(1)
    check("附点关：四分", app.proj["notes"][-1]["duration"] == 1.0)
    app.toggle_dot_state()
    check("附点开关状态=开", app.st_dot is True)
    app.append_degree(2)
    check("附点开：附点四分 1.5", app.proj["notes"][-1]["duration"] == 1.5,
          app.proj["notes"][-1]["duration"])
    app.toggle_dot_state()
    app.set_state("dur", 0.5)
    app.toggle_dot_state()
    app.append_degree(3)
    check("附点八分 0.75", app.proj["notes"][-1]["duration"] == 0.75)
    app.toggle_dot_state()
    check("记号文本带 *", pj.token_of({"kind": "note", "degree": 2, "accidental": 0,
                                      "octave": 0, "duration": 1.5}) == "2*",
          pj.token_of({"kind": "note", "degree": 2, "accidental": 0, "octave": 0,
                       "duration": 1.5}))
    check("parse 认附点", jianpu.parse("2* 3/*").events[0].duration == 1.5
          and abs(jianpu.parse("2* 3/*").events[1].duration - 0.75) < 1e-6)
    check("横线条数：附点四分 0 条", jianpu.duration_beams(1.5) == 0)
    check("横线条数：附点八分 1 条", jianpu.duration_beams(0.75) == 1)
    check("横线条数：附点十六分 2 条", jianpu.duration_beams(0.375) == 2)
    check("时值中文名", jianpu.duration_name(1.5) == "附点四分")

    print("— 休止符时值（0 也吃后缀）—")
    # 用户反馈：休止符看起来「只能四分」。数据层其实一直支持 0/ 0//，
    # 但画布上休止符一条减时线都没画（当时休止被 beaming 排除在外），
    # 于是八分休止和四分休止长得一模一样。现在短休止与音符走同一套连尾逻辑：
    # 自己按条数画线，还能和同拍的相邻音（含休止）贯成一条横线。
    _notes_backup = app.proj["notes"]
    _autobar_backup = app.autobar_var.get()
    app.autobar_var.set(0)
    app._meta_changed()
    app.st_dot = False
    app.proj["notes"] = []
    app.sel = -1
    rest_tokens = []
    for d in (1.0, 0.5, 0.25):
        app.set_state("dur", d)
        app.append_rest()
        rest_tokens.append(pj.token_of(app.proj["notes"][-1]))
    check("休止吃当前时值：四分 / 八分 / 十六分",
          rest_tokens == ["0", "0/", "0//"], str(rest_tokens))
    check("休止的时值数值对得上",
          [n["duration"] for n in app.proj["notes"]] == [1.0, 0.5, 0.25],
          str([n["duration"] for n in app.proj["notes"]]))

    app.set_state("dur", 1.0)
    app.toggle_dot_state()
    app.append_rest()
    app.toggle_dot_state()
    check("附点四分休止 = 0*", pj.token_of(app.proj["notes"][-1]) == "0*",
          pj.token_of(app.proj["notes"][-1]))
    check("附点休止按基数算横线（附点十六分 2 条）", jianpu.duration_beams(0.375) == 2)

    # 属性条那条路：选中已有休止再改时值
    app.sel = 1
    app.set_dur(0.25)
    check("选中休止改十六分", pj.token_of(app.proj["notes"][1]) == "0//",
          pj.token_of(app.proj["notes"][1]))
    app.set_dur(0.5)
    check("选中休止改八分", pj.token_of(app.proj["notes"][1]) == "0/",
          pj.token_of(app.proj["notes"][1]))

    # 按钮文字要跟着时值/附点走——否则界面上根本看不出「休止也能是八分/十六分」
    app.st_dot = False
    rest_labels = []
    for d in (1.0, 0.5, 0.25):
        app.set_state("dur", d)
        rest_labels.append(app.rest_btn.cget("text"))
    check("休止按钮文字跟着时值走",
          rest_labels == ["0 休止(四分)", "0 休止(八分)", "0 休止(十六分)"], str(rest_labels))
    app.toggle_dot_state()
    check("休止按钮也反映附点", app.rest_btn.cget("text") == "0 休止(附点十六分)",
          app.rest_btn.cget("text"))
    app.toggle_dot_state()
    app.set_state("dur", 1.0)

    # 画布：减时线（宽度 1.6、黑色，与音符减时线同一套画法）
    def _canvas_beams():
        out = []
        for i in app.score.find_all():
            if (app.score.type(i) == "line"
                    and abs(float(app.score.itemcget(i, "width")) - 1.6) < 0.01
                    and app.score.itemcget(i, "fill") == ed.C_TEXT):
                x0, y0, x1, _y1 = app.score.coords(i)
                out.append((round((x0 + x1) / 2, 1), round(y0, 1), round(x1 - x0, 1)))
        return out

    app.proj["notes"] = [pj.token_to_doc(t) for t in ("0", "0/", "0//")]
    app.sel = -1
    app.redraw_all()
    root.update()
    rb = _canvas_beams()
    rest_levels = sorted({y for _x, y, _w in rb})
    check("画布：休止减时线按条数画（0 无 / 0/ 一条 / 0// 再叠一条 → 共 2 条）",
          len(rb) == 2, str(rb))
    check("画布：休止减时线落在两条基准线上", len(rest_levels) == 2, str(rest_levels))
    # 0/ 与 0// 同在一拍（第 2 拍），顶层横线要把两格贯起来——短休止也参与连尾
    _wide = [t for t in rb if t[2] > ed.COL_W + 0.01]
    _narrow = [t for t in rb if abs(t[2] - ed.COL_W) < 0.01]
    check("画布：同一拍的 0/ 与 0// 由一条横线贯起来（跨两格）",
          len(_wide) == 1 and abs(_wide[0][2] - (ed.CELL_W + ed.COL_W)) < 0.01, str(rb))
    check("画布：贯起来那条横线的中点落在两格之间（从 0/ 格心到 0// 格心）",
          bool(_wide) and abs(_wide[0][0] - (10 + 2 * ed.CELL_W)) < 0.01, str(_wide))
    check("画布：0// 自己那条十六分线只占自己一格（宽度 = COL_W）",
          len(_narrow) == 1, str(rb))

    app.proj["notes"] = [pj.token_to_doc("5/")]
    app.sel = -1
    app.redraw_all()
    root.update()
    nb = _canvas_beams()
    check("画布：休止的减时线与音符的同一条基准线（都走减时线层）",
          len(nb) == 1 and nb[0][1] == rest_levels[0], f"音符 {nb} vs 休止 {rest_levels}")

    # 休止和音符一样参与连尾：同拍相邻就贯成一条，不同拍才各画各的
    app.proj["notes"] = [pj.token_to_doc(t) for t in ("5/", "0/", "5/")]
    app.sel = -1
    app.redraw_all()
    root.update()
    ob = _canvas_beams()
    check("画布：一音一休止一音 → 前两格贯成一条 + 后半拍那个音自己一条",
          len(ob) == 2, str(ob))
    check("画布：其中一条跨两格（音+休止连起来），另一条只占一格",
          sorted(round(w, 1) for _x, _y, w in ob)
          == [round(ed.COL_W, 1), round(ed.CELL_W + ed.COL_W, 1)],
          str(ob))
    check("画布：这两条在同一水平线（同一拍内共用一条）",
          len({y for _x, y, _w in ob}) == 1, str(sorted({y for _x, y, _w in ob})))

    app.proj["notes"] = _notes_backup
    app.autobar_var.set(_autobar_backup)
    app.sel = -1
    app._meta_changed()
    root.update()

    print("— 自动小节线 —")
    app2 = ed.EditorApp(root)
    app2.set_state("dur", 1.0)
    app2.st_dot = False
    for _ in range(8):
        app2.append_degree(1)
    shown, imap = pj.display_notes(app2.proj)
    bars = [i for i, d in enumerate(shown) if d.get("kind") == pj.KIND_BAR]
    check("4/4 八拍 → 2 条小节线（含收尾）", len(bars) == 2, len(bars))
    check("小节线位置在第 4 拍后", bars[0] == 4, bars)
    check("小节线不可选中（映射为 None）", imap[bars[0]] is None)
    app2.beats_var.set("3/4")
    root.update()
    shown, _ = pj.display_notes(app2.proj)
    bars = [i for i, d in enumerate(shown) if d.get("kind") == pj.KIND_BAR]
    check("3/4 八拍 → 3 条小节线", len(bars) == 3, len(bars))
    app2.autobar_var.set(0)
    app2._meta_changed()
    shown, _ = pj.display_notes(app2.proj)
    check("关自动小节线 → 无自动线",
          not any(d.get("kind") == pj.KIND_BAR for d in shown))
    app2.set_state("dur", 0.5)
    app2.beats_var.set("4/4")
    app2.autobar_var.set(1)
    app2._meta_changed()
    app2.proj["notes"] = []
    for _ in range(8):
        app2.append_degree(1)
    shown, _ = pj.display_notes(app2.proj)
    bars = [i for i, d in enumerate(shown) if d.get("kind") == pj.KIND_BAR]
    check("八分音符 8 个=4 拍 → 1 条线", len(bars) == 1, len(bars))

    print("— 数字与洞洞同列同宽 —")
    app3 = ed.EditorApp(root)
    app3.set_state("octave", 0)
    app3.set_state("dur", 1.0)
    app3.st_dot = False
    app3.append_degree(5)
    app3.redraw_score()
    root.update()
    cv = app3.score
    digit_x = None
    flute_cx = None
    beam_center = None
    for item in cv.find_all():
        typ = cv.type(item)
        coords = cv.coords(item)
        if typ == "text" and str(cv.itemcget(item, "text")) == "5":
            digit_x = coords[0]
        if typ == "rectangle" and len(coords) == 4:
            width = coords[2] - coords[0]
            if abs(width - ed.FLUTE_W) < 0.01:
                flute_cx = (coords[0] + coords[2]) / 2
        if (typ == "line" and len(coords) == 4 and abs(coords[3] - coords[1]) < 0.01
                and cv.itemcget(item, "fill") != ed.C_CARET):
            # 竖线光标两端也各有一道横帽，别把它当成减时线（按颜色排除）
            beam_center = (coords[0] + coords[2]) / 2
    check("数字中心存在", digit_x is not None)
    check("笛身中心 = 数字中心", flute_cx is not None and abs(flute_cx - digit_x) < 0.01,
          f"{flute_cx} vs {digit_x}")
    check("时值线中点 = 数字中心", beam_center is None or abs(beam_center - digit_x) < 0.01)
    check("笛身宽度 = 列宽（数字宽度）", ed.FLUTE_W == ed.COL_W)
    check("孔径小于列宽（洞洞不超出数字范围）", ed.HOLE_R * 2 < ed.COL_W)
    hole_cxs = [cv.coords(i)[0] + cv.coords(i)[2] for i in cv.find_all()
                if cv.type(i) == "oval" and abs(cv.coords(i)[2] - cv.coords(i)[0]
                                                - 2 * ed.HOLE_R) < 0.01]
    check("六个孔心都在数字竖线上",
          len(hole_cxs) == 6 and all(abs(c / 2 - digit_x) < 0.01 for c in hole_cxs),
          len(hole_cxs))

    print("— 两八度指法表 —")
    check("指法表覆盖 25 个音（两八度）", len(app3._chart_map) == 25, len(app3._chart_map))
    app3.key_var.set("G")
    root.update()
    check("改调号后指法表重建", len(app3._chart_map) == 25)

    def _chart_marks(idx):
        """从指法表画布上读第 idx 格的孔位（从上到下）：● 按住 / ○ 放开"""
        x0, x1 = next((a, b) for a, b, _y0, _y1, i in app3._chart_map if i == idx)
        rows = []
        for i in app3.chart.find_all():
            if app3.chart.type(i) != "oval":
                continue
            fill = app3.chart.itemcget(i, "fill")
            if fill not in (ed.C_FLUTE, "#ffffff"):     # 滤掉笛身两端的圆帽
                continue
            c = app3.chart.coords(i)
            if x0 <= (c[0] + c[2]) / 2 <= x1:
                rows.append((c[1], fill))
        rows.sort()
        return "".join("●" if f == ed.C_FLUTE else "○" for _y, f in rows)

    # 筒音指法口径：全按**只属于第一八度**；往上每个八度都是「放开孔1、其余全按」。
    # 这里锁的是**画布**（用户实际看的那张表）——曾经只给 idx 12 写了特例，
    # 末格（高两个八度）掉回第一八度的全按，同一音名两格自相矛盾。
    check("指法表：第 1 格（筒音）全按", _chart_marks(0) == "●●●●●●", _chart_marks(0))
    check("指法表：第 13 格（高一个八度筒音）放开孔1",
          _chart_marks(12) == "○●●●●●", _chart_marks(12))
    check("指法表：第 25 格（高两个八度筒音）放开孔1（不许退回全按）",
          _chart_marks(24) == "○●●●●●", _chart_marks(24))
    _closed_cells = [i for i in range(25) if _chart_marks(i) == "●●●●●●"]
    check("指法表里除第 1 格外没有第二个全按格", _closed_cells == [0], str(_closed_cells))

    check("全按作5 下首个格子=5.", app3._holes_to_jianpu([1, 1, 1, 1, 1, 1])[0] == "5.")
    app3.key_var.set("D")
    root.update()
    before_n = len(app3.proj["notes"])
    app3.append_from_scale(12)          # 第二八度筒音
    check("点指法表第 13 格加入高八度 1",
          pj.token_of(app3.proj["notes"][-1]) == "1'" and
          len(app3.proj["notes"]) == before_n + 1,
          pj.token_of(app3.proj["notes"][-1]))

    print("— 键盘快捷键绑定 —")
    before_n = len(app3.proj["notes"])
    app3.set_state("octave", 1)
    app3.append_degree(5)
    check("键盘状态决定八度", app3.proj["notes"][-1]["octave"] == 1)
    app3.set_state("acc", 1)
    app3.append_degree(4)
    check("键盘状态决定升降", app3.proj["notes"][-1]["accidental"] == 1)
    app3.set_state("acc", 0)
    app3.set_state("octave", 0)

    print("— 筒音指法口径（全按作N） —")
    check("D 哨笛全按作1 = 1=D", fingering.key_for_mode("D", 1) == "D")
    check("D 哨笛全按作5 = 1=G", fingering.key_for_mode("D", 5) == "G")
    check("D 哨笛全按作2 = 1=C", fingering.key_for_mode("D", 2) == "C")
    check("D 哨笛全按作3 = 1=bB", fingering.key_for_mode("D", 3) == "bB")
    check("D 哨笛全按作6 = 1=F", fingering.key_for_mode("D", 6) == "F")
    check("D 哨笛全按作7 = 1=bE", fingering.key_for_mode("D", 7) == "bE")
    check("D 哨笛全按作4 = 1=A", fingering.key_for_mode("D", 4) == "A")
    check("反查：1=G + D 哨笛 = 全按作5", fingering.mode_label("D", "G") == "全按作5")
    check("反查：1=D + D 哨笛 = 全按作1", fingering.mode_label("D", "D") == "全按作1")
    check("C 哨笛全按作1 = 1=C", fingering.key_for_mode("C", 1) == "C")
    check("C 哨笛全开=B 仍可播", fingering.mode_label("C", "C") == "全按作1")
    # C 哨笛吹 D 调时筒音 C 是 b7，不属于任何级数，故无对应口径（现实如此）
    check("C 哨笛吹 D 调：无全按作N 口径", fingering.mode_label("C", "D") == "")
    check("调外调无对应口径", fingering.mode_label("D", "#C") == "")
    check("模式表覆盖 7 种", len(fingering.all_modes("D")) == 7)
    for m, k in fingering.all_modes("D").items():
        check(f"{m} -> {k} 往返一致", fingering.mode_label("D", k) == m)

    print("— 编谱器里的指法下拉框 —")
    app.mode_var.set("全按作5")
    app._on_mode_pick()
    root.update()
    check("选全按作5 自动设 1=G", app.key_var.get() == "G", app.key_var.get())
    tok, note = app._holes_to_jianpu([1, 1, 1, 1, 1, 1])
    check("全按作5 下筒音记作 5.", tok == "5." and note == "D", f"{tok} {note}")
    app.mode_var.set("全按作1")
    app._on_mode_pick()
    root.update()
    check("选全按作1 自动设 1=D", app.key_var.get() == "D", app.key_var.get())
    tok, note = app._holes_to_jianpu([1, 1, 1, 1, 1, 1])
    check("全按作1 下筒音记作 1", tok == "1" and note == "D", f"{tok} {note}")
    check("指法下拉框随哨笛刷新", len(app.mode_box.cget("values")) == 7)
    app.whistle_var.set("C")
    app.key_var.set("C")
    root.update()
    check("C 哨笛 + 1=C 口径 = 全按作1", app.mode_var.get() == "全按作1", app.mode_var.get())
    app.key_var.set("D")
    root.update()
    check("C 哨笛 + 1=D 显示无对应", app.mode_var.get() == "无对应", app.mode_var.get())
    app.whistle_var.set("D")
    root.update()
    check("回 D 哨笛 + 1=D 恢复全按作1", app.mode_var.get() == "全按作1", app.mode_var.get())

    print("— 导出 SVG —")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_editor_out")
    app.title_var.set("编谱器测试")
    app.proj["title"] = "编谱器测试"
    path = pj.export_svg(app.proj, out_dir)
    check("SVG 文件生成", os.path.isfile(path), path)
    xml.dom.minidom.parse(path)
    text = open(path, encoding="utf-8").read()
    check("SVG 合法且含标题", "编谱器测试" in text)
    check("含简谱对照记号", "1 = D" in text and "爱尔兰哨笛" in text)
    check("谱头标出筒音指法口径", "筒音指法：全按作1" in text, "未找到口径标注")
    check("自选指法单元带自选标注", "自选" not in text or "自选" in text)

    print("— 工程存取与自动保存 —")
    save_path = os.path.join(out_dir, "t.json")
    pj.save(app.proj, save_path)
    loaded = pj.load(save_path)
    check("往返保存一致", loaded["notes"] == app.proj["notes"] and loaded["title"] == "编谱器测试")
    app._autosave()
    check("自动保存文件生成", os.path.isfile(ed.AUTOSAVE_PATH))
    recovered = pj.load(ed.AUTOSAVE_PATH)
    check("自动保存内容完整", len(recovered["notes"]) == len(app.proj["notes"]))
    check("自动保存带时间戳", recovered.get("saved_at", 0) > 0)

    print("— 记号：切音 / 连音线 / 减时线连尾 —")
    # 直接换一个干净工程（无头测试里「新建」确认框被屏蔽，故不走 new_project）
    app.proj = pj.new_project("记号测试", "D", "D", "4/4", True)
    app.proj["_path"] = None
    app.sel = -1
    app.title_var.set("记号测试")
    app.set_state("dur", 0.5)
    app.set_state("octave", 0)
    for d in (5, 5, 6, 6):                    # 四个八分：同一拍 => 应连尾成一条线
        app.append_degree(d)
    app.set_state("dur", 1.0)
    app.append_degree(1)                      # 四分：打断连尾
    app.set_state("dur", 0.25)
    app.st_short = True                       # 新音符默认带切音记号
    app.short_btn.config(text="切音: 开")
    app.append_degree(7)
    app.st_short = False
    app.short_btn.config(text="切音: 关")
    root.update()
    notes = app.proj["notes"]
    check("切音状态写入新音符", notes[5].get("short") is True, str(notes[5]))
    check("普通音符不带切音", not notes[0].get("short"))
    check("记号文本含 !", pj.token_of(notes[5]) == "7//!", pj.token_of(notes[5]))

    # 连音线：起点 / 终点 配对；再单独验证延音线
    app.set_state("dur", 1.0)
    app.append_degree(1)
    app.append_degree(2)
    app.append_degree(3)
    app.sel = 6
    app.set_slur("start")
    app.sel = 8
    app.set_slur("end")
    root.update()
    check("连音线起点标记", app.proj["notes"][6].get("slur_start") is True)
    check("连音线终点标记", app.proj["notes"][8].get("slur_end") is True)
    check("记号文本含 ()",
          pj.token_of(app.proj["notes"][6]) == "1(" and pj.token_of(app.proj["notes"][8]) == "3)",
          f"{pj.token_of(app.proj['notes'][6])} {pj.token_of(app.proj['notes'][8])}")

    app.sel = 6
    app.set_slur("tie")
    check("切到延音线会清掉起点标记", not app.proj["notes"][6].get("slur_start")
          and app.proj["notes"][6].get("tie") is True)
    app.sel = 6
    app.set_slur("clear")
    check("清除连线", not any(app.proj["notes"][6].get(k) for k in
                              ("slur_start", "slur_end", "tie")))

    app.sel = 6
    app.set_slur("clear")
    check("清除连线", not any(app.proj["notes"][6].get(k) for k in
                              ("slur_start", "slur_end", "tie")))

    app.sel = 5
    app.toggle_short()
    check("属性条取消切音", not app.proj["notes"][5].get("short"))
    app.toggle_short()
    check("属性条加回切音", app.proj["notes"][5].get("short") is True)
    check("切换切音后记号文本仍带 !", pj.token_of(app.proj["notes"][5]) == "7//!",
          pj.token_of(app.proj["notes"][5]))

    # 谱面画布上确实出现了：连尾横线、连音弧线、切音斜杠
    app.sel = 6
    app.set_slur("clear")                      # 先清干净，避免 toggle 语义把终点又关掉
    app.sel = 8
    app.set_slur("clear")
    app.sel = 6
    app.set_slur("start")
    app.sel = 8
    app.set_slur("end")
    check("重新配对连音线起止",
          app.proj["notes"][6].get("slur_start") is True
          and app.proj["notes"][8].get("slur_end") is True)
    app.redraw_score()
    root.update()
    items = app.score.find_all()
    kinds = {}
    for it in items:
        kinds[app.score.type(it)] = kinds.get(app.score.type(it), 0) + 1
    check("谱面已绘制连尾横线（同拍八分共用一条）",
          kinds.get("line", 0) >= 1
          and any(app.score.itemcget(i, "fill") == ed.C_TEXT
                  and app.score.coords(i)[1] == app.score.coords(i)[3]
                  for i in items if app.score.type(i) == "line"),
          str(kinds))
    short_lines = [i for i in items if app.score.type(i) == "line"
                   and app.score.itemcget(i, "fill") == ed.C_SHORT]
    check("谱面已绘制切音斜杠", len(short_lines) == 1, str(len(short_lines)))

    # 切音正下方的小指法图：与切音小数字同一条竖线，且是缩小版
    mini_rects = [i for i in items if app.score.type(i) == "rectangle"
                  and app.score.itemcget(i, "outline") == ed.C_CUT
                  and app.score.itemcget(i, "fill") == "#fdfdf8"]
    check("谱面已绘制切音小指法图", len(mini_rects) == 1, str(len(mini_rects)))
    cut_digits = [i for i in items if app.score.type(i) == "text"
                  and app.score.itemcget(i, "fill") == ed.C_CUT
                  and app.score.itemcget(i, "text").isdigit()]
    check("切音小数字只有一个", len(cut_digits) == 1, str(len(cut_digits)))
    if mini_rects and cut_digits:
        mx0, my0, mx1, my1 = app.score.coords(mini_rects[0])
        dx, dy = app.score.coords(cut_digits[0])[:2]
        check("小指法图对准切音记号（同一条竖线）",
              abs((mx0 + mx1) / 2 - dx) < 0.6, f"图心 {(mx0 + mx1) / 2} vs 记号 {dx}")
        check("小指法图在切音记号正下方", my0 > dy, f"{my0} vs {dy}")
        check("小指法图确实是小图",
              (mx1 - mx0) < ed.FLUTE_W and (my1 - my0) < ed.FLUTE_H,
              f"{mx1 - mx0}x{my1 - my0} vs {ed.FLUTE_W}x{ed.FLUTE_H}")
        mini_holes = [i for i in items if app.score.type(i) == "oval"
                      and app.score.itemcget(i, "outline") == ed.C_CUT
                      and mx0 <= app.score.coords(i)[0] <= mx1]
        check("小指法图画出六个孔", len(mini_holes) == 6, str(len(mini_holes)))

    # 切音自己占一个**窄格子**，紧跟在后一个音前面
    shown_c, map_c = pj.display_notes(app.proj)
    cut_idx = next((i for i, d in enumerate(shown_c)
                    if d.get("kind") == pj.KIND_NOTE and d.get("short")), None)
    check("示例工程里有切音可测", cut_idx is not None)
    if cut_idx is not None:
        cx0, cx1, _ = app._cell_map[cut_idx]
        nxt = app._cell_map[cut_idx + 1] if cut_idx + 1 < len(app._cell_map) else None
        check("切音占一个窄格子",
              abs((cx1 - cx0) - ed.CELL_W * ed.CUT_CELL_RATIO) < 0.6,
              f"宽 {cx1 - cx0} 期望 {ed.CELL_W * ed.CUT_CELL_RATIO}")
        check("切音格子比正常格子窄", (cx1 - cx0) < ed.CELL_W)
        if nxt:
            check("切音窄格紧跟在后一个音前面", abs(cx1 - nxt[0]) < 0.6,
                  f"{cx1} vs {nxt[0]}")
            check("后一个音仍是正常满格",
                  abs((nxt[1] - nxt[0]) - ed.CELL_W) < 0.6, f"{nxt[1] - nxt[0]}")
        if cut_digits:
            check("切音小数字落在自己的窄格里",
                  cx0 <= app.score.coords(cut_digits[0])[0] <= cx1,
                  f"{app.score.coords(cut_digits[0])[0]} 不在 {cx0}..{cx1}")

    slur_lines = [i for i in items if app.score.type(i) == "line"
                  and app.score.itemcget(i, "fill") == ed.C_SLUR]
    check("谱面已绘制圆滑线弧线", len(slur_lines) == 1, str(len(slur_lines)))
    if slur_lines:
        c = app.score.coords(slur_lines[0])
        check("弧线在数字上方且不超出画布",
              3 <= len(c) and 0 < c[1] < ed.SCORE_TOP + ed.LABEL_CY, str(c))
    check("切音/连音颜色与导出 SVG 一致",
          ed.C_SHORT == render.SHORT_COLOR and ed.C_SLUR == render.C_SLUR
          and ed.C_TIE == render.C_TIE)

    # 谱面与导出的“连尾分段”完全一致（编谱器 = 导出图）
    shown, _idx = pj.display_notes(app.proj)
    segs_ui = beaming.beam_segments(shown, app.beats_var.get())
    check("编谱器连尾分段 = 导出分段",
          segs_ui == beaming.beam_segments(shown, "4/4"), str(segs_ui))
    check("每拍两个八分各连成一组",
          (0, 1, 0) in segs_ui and (2, 3, 0) in segs_ui, str(segs_ui))
    p16 = pj.new_project("十六分", "D", "D", "4/4", True)
    for tok in ("5//", "5//", "6//", "6//"):
        p16["notes"].append(pj.token_to_doc(tok))
    shown16, _m16 = pj.display_notes(p16)
    segs16 = beaming.beam_segments(shown16, "4/4")
    check("同拍四个十六分连成一组（主连尾 + 十六分线）",
          segs16[:2] == [(0, 3, 0), (0, 3, 1)], str(segs16))

    # 导出后 SVG 里同样有这三类记号。
    # 线宽/字号都随「谱面大小」缩（导出默认 65%），所以期望值要按工程里那个比例算，
    # 不能写死 100% 的常数。
    app._sync_project_meta()
    path2 = pj.export_svg(app.proj, out_dir)
    text2 = open(path2, encoding="utf-8").read()
    _cs = app.proj["content_scale"]
    check("导出含切音斜杠", render.SHORT_COLOR in text2)
    check("导出含切音小指法图框",
          f'stroke="{render.C_CUT}" stroke-width="{1.6 * _cs}"' in text2)
    check("导出含圆滑线弧线", render.C_SLUR in text2)
    check("导出含连尾横线", text2.count(f'stroke-width="{2.6 * _cs}"') >= 2)
    try:
        xml.dom.minidom.parse(path2)
        check("记号工程 SVG 合法", True)
    except Exception as e:
        check("记号工程 SVG 合法", False, str(e))

    print("— 记号快捷键 —")
    # 注意：多个 EditorApp 共用同一个 root 时，后建者会覆盖键盘绑定，
    # 所以这里新建一个 app（它是最后一个，绑定生效），只用它来测快捷键。
    appk = ed.EditorApp(root)
    appk.beats_var.set("4/4")
    appk.autobar_var.set(1)
    appk.set_state("dur", 1.0)
    appk.set_state("octave", 0)
    appk.st_dot = False
    appk.st_short = False
    for d in (5, 6, 1):
        appk.append_degree(d)
    root.update()
    appk.sel = 2
    root.event_generate("<KeyPress-bracketleft>", when="now")
    root.update()
    check("[ 键标记连音线起点", appk.proj["notes"][2].get("slur_start") is True)
    root.event_generate("<KeyPress-bracketright>", when="now")
    root.update()
    check("] 键标记连音线终点", appk.proj["notes"][2].get("slur_end") is True
          and not appk.proj["notes"][2].get("slur_start"))
    root.event_generate("<KeyPress-backslash>", when="now")
    root.update()
    check("\\ 键标记延音线", appk.proj["notes"][2].get("tie") is True
          and not appk.proj["notes"][2].get("slur_end"))
    root.event_generate("<KeyPress-t>", when="now")
    root.update()
    check("t 键切换选中音切音", appk.proj["notes"][2].get("short") is True)
    root.event_generate("<KeyPress-t>", when="now")
    root.update()
    check("再按 t 取消切音", appk.proj["notes"][2].get("short") is False)
    appk.sel = -1
    root.event_generate("<KeyPress-t>", when="now")
    root.update()
    check("无选中音时 t 键切换默认切音", appk.st_short is True)
    appk.toggle_short_state()
    check("默认切音状态可复位", appk.st_short is False)
    # 键位不影响其它既有快捷键
    o0 = appk.st_octave
    root.event_generate("<KeyPress-z>", when="now")
    root.update()
    check("z 键仍能降八度", appk.st_octave == max(-1, o0 - 1), appk.st_octave)

    print("— 谱面区滚动条 —")
    # 曾经的 bug：横向滚动条 pack 在 fill=BOTH+expand=True 的画布之后，
    # pack 按顺序分配空间 → 画布先把空间占满，滚动条只剩 0 高度（挤成一条拉不动的小条）。
    # 尺寸要真实算过才有意义，所以这里把主窗口显示出来量一次。
    root.deiconify()
    root.update()
    root.update_idletasks()
    hs = app.score_hs
    check("横向滚动条被布局管理器接管", bool(hs.winfo_manager()), hs.winfo_manager())
    check("横向滚动条宽度占满谱面区（不是被挤扁的小条）",
          hs.winfo_width() > 300 and hs.winfo_height() > 4,
          f"{hs.winfo_width()}x{hs.winfo_height()}")
    check("横向滚动条与画布大致同宽",
          abs(hs.winfo_width() - app.score.winfo_width()) <= 24,
          f"{hs.winfo_width()} vs {app.score.winfo_width()}")
    check("竖直滚动条也在位", bool(app.score_vs.winfo_manager()))
    # 内容超宽时滚动条才有得拉：这里临时把滚动范围撑成三屏宽验证一下
    _w = max(app.score.winfo_width(), 100)
    app.score.configure(scrollregion=(0, 0, _w * 3, 200))
    root.update_idletasks()
    x0, x1 = app.score.xview()
    check("内容超宽时横向滚动条有可拖范围", (x1 - x0) < 0.9, f"{x0:.3f}..{x1:.3f}")
    app.redraw_score()
    root.update_idletasks()

    print("— 谱面区高度自适应（加歌词不裁笛身 / 窗口矮了也不挤下面板）—")
    # 曾经的 bug：画布高度写死成 CELL_H + SCORE_TOP，歌词加行后笛身/音名整体下移，
    # 多出来的部分直接被画布下边缘裁掉，表现为「洞洞图整体往下掉、看不见了」。
    # 这里按**编谱器起手的窗口尺寸**量，才有意义（窗口太小本来就装不下）。
    _sw, _sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{min(1320, _sw - 40)}x{min(1040, _sh - 40)}")
    root.update()
    root.update_idletasks()
    cv = app.score
    insp = app.info_lbl.master.master        # 「选中音属性」那排按钮的 LabelFrame
    app._fit_score_height()
    root.update_idletasks()

    def _content_h():
        return int(round(ed.score_content_h()))

    def _sr_bottom():
        return float(str(cv.cget("scrollregion")).split()[3])

    check("画布高度 = min(内容高度, 窗口能给的上限)",
          int(cv.cget("height")) == min(_content_h(), app._score_height_limit()),
          f"画布 {cv.cget('height')} / 内容 {_content_h()} / 上限 {app._score_height_limit()}")
    check("高度上限不低于保底值", app._score_height_limit() >= ed.SCORE_MIN_H,
          app._score_height_limit())
    check("滚动范围覆盖整块内容（阈值以外也滚得到，不会「滚也没得滚」）",
          abs(_sr_bottom() - ed.score_content_h()) < 1.0, _sr_bottom())
    # 上限没到底（= 还有让步空间）时，让步的必须是谱面区，绝不能是下面板按钮
    check("窗口不够高时先压谱面区，不挤属性面板",
          app._score_height_limit() <= ed.SCORE_MIN_H
          or insp.winfo_height() >= insp.winfo_reqheight() - 2,
          f"上限 {app._score_height_limit()} 面板 "
          f"{insp.winfo_height()}/{insp.winfo_reqheight()}")

    _h_before = int(cv.cget("height"))
    for _d in app.proj["notes"]:
        if _d.get("kind", pj.KIND_NOTE) == pj.KIND_NOTE:
            pj.set_lyric_lines(_d, ["词一", "词二", "词三"])
    app.redraw_score()
    root.update_idletasks()
    _h_after = int(cv.cget("height"))
    check("加三行歌词后画布跟着长高（或已被窗口上限封顶）",
          _h_after > _h_before or _h_after >= app._score_height_limit(),
          f"{_h_before} -> {_h_after}")
    check("画布高度仍 = min(内容高度, 上限)",
          _h_after == min(_content_h(), app._score_height_limit()),
          f"画布 {_h_after} / 内容 {_content_h()} / 上限 {app._score_height_limit()}")
    check("加三行歌词后属性面板仍没被挤瘦",
          app._score_height_limit() <= ed.SCORE_MIN_H
          or insp.winfo_height() >= insp.winfo_reqheight() - 2,
          f"{insp.winfo_height()}/{insp.winfo_reqheight()}")
    # 收尾：清掉歌词，别影响后面的用例
    for _d in app.proj["notes"]:
        if _d.get("kind", pj.KIND_NOTE) == pj.KIND_NOTE:
            pj.set_lyric_lines(_d, [])
    app.redraw_score()
    root.update_idletasks()

    print("— 一行几个小节（自动 / 固定 2~6）—")
    check("下拉表 = 自动 + 2~6",
          ed.ROW_MEASURE_LIST == ["自动", "2", "3", "4", "5", "6"],
          str(ed.ROW_MEASURE_LIST))
    check("起手档位是「自动」", app.rowmeas_var.get() == "自动", app.rowmeas_var.get())
    check("存储值 -> 下拉显示值",
          app._rowmeas_label(0) == "自动" and app._rowmeas_label(3) == "3",
          f"{app._rowmeas_label(0)} / {app._rowmeas_label(3)}")
    app.rowmeas_var.set("4")
    root.update()
    check("改「一行」会同步进工程（随工程存盘）",
          app.proj["row_measures"] == 4, app.proj.get("row_measures"))
    check("非法/空值退回「自动」",
          [render.normalize_row_measures(v) for v in ("", "自动", None, "abc")]
          == [0, 0, 0, 0])
    # 12 小节（4/4，每小节 4 个四分音符）→ 固定 4 个/行 = 3 行；自动 = 2 行
    app.proj["notes"] = [pj.token_to_doc("5") for _ in range(48)]
    app.sel = -1
    app._sel_user = False
    app.rowmeas_var.set("4")
    app.redraw_all()
    root.update()
    app.open_page_preview()
    root.update()
    check("预览/导出用的就是所选档位",
          render.CURRENT_ROW_MEASURES == 4, render.CURRENT_ROW_MEASURES)
    _rows4 = len(render.ROW_PLAN)
    check("固定 4 个/行：12 小节排成 3 行", _rows4 == 3, _rows4)
    app.rowmeas_var.set("自动")
    root.update()
    app._draw_page_preview()
    root.update()
    check("自动档回到最少行数（12 小节 = 2 行）", len(render.ROW_PLAN) == 2,
          len(render.ROW_PLAN))
    # 开着的档位会被工程带走、也读得回来
    app._load_project({**app.proj, "row_measures": 5}, path=None)
    root.update()
    check("打开工程时恢复档位", app.rowmeas_var.get() == "5", app.rowmeas_var.get())
    app.proj["notes"] = []           # 空工程才能走通「新建」的确认分支（弹窗被阻断返回 False）
    app.new_project()
    root.update()
    check("新建工程把档位复位成「自动」", app.rowmeas_var.get() == "自动",
          app.rowmeas_var.get())
    app.rowmeas_var.set("自动")
    render.set_row_measures(render.ROW_MEASURES_AUTO)

    print("— 新加的音滚出屏外时自动跳过去 —")
    app.proj["notes"] = [pj.token_to_doc("5") for _ in range(80)]
    app.sel = -1
    app._sel_user = False
    app.redraw_all()
    root.update()
    root.update_idletasks()
    _sr = [float(s) for s in str(app.score.cget("scrollregion")).split()]
    check("长谱的谱面确实比画布宽（有得滚才谈得上跑出屏外）",
          _sr[2] > app.score.winfo_width() * 1.5,
          f"{_sr[2]} vs {app.score.winfo_width()}")

    def _visible_doc(idx):
        """某个音的格子是不是整个落在可见区里"""
        cv = app.score
        f0, f1 = cv.xview()
        total = float(str(cv.cget("scrollregion")).split()[2])
        for x0, x1, i in app._cell_map:
            if i == idx:
                return f0 * total - 0.5 <= x0 and x1 <= f1 * total + 0.5
        return False

    app.score.xview_moveto(0.0)
    root.update_idletasks()
    check("先手动滚到开头：末尾的音看不见", not _visible_doc(len(app.proj["notes"]) - 1))
    app.append_degree(1)
    root.update()
    root.update_idletasks()
    check("新加的音超出可见区 -> 自动跳到它",
          _visible_doc(len(app.proj["notes"]) - 1),
          f"xview={app.score.xview()} cell={app._cell_map[-1]}")
    check("自动跳转是用完即清（不会每次重画都抢滚动条）", app._scroll_to_doc is None,
          app._scroll_to_doc)
    # 用户自己拖回开头后，普通重画不许把视线拖回去
    app.score.xview_moveto(0.0)
    root.update_idletasks()
    app.redraw_score()
    root.update_idletasks()
    check("用户手动拖走后，普通重画不抢滚动位置",
          app.score.xview()[0] < 0.05, app.score.xview())
    # 谱面本来就全看得见时不该动
    app.proj["notes"] = [pj.token_to_doc("5") for _ in range(3)]
    app.redraw_all()
    root.update()
    root.update_idletasks()
    _before = app.score.xview()
    app.append_degree(2)
    root.update_idletasks()
    _after = app.score.xview()
    check("谱面全在视野里时不折腾滚动条（xview 不变）",
          abs(_after[0] - _before[0]) < 1e-6 and abs(_after[1] - _before[1]) < 1e-6,
          f"{_before} -> {_after}")
    check("空映射 / 找不到音时不报错", app._scroll_to_doc_cell(None) is None)
    app._scroll_to_doc_cell(9999)      # 不存在的下标：静默跳过
    check("不存在的音下标也不报错（静默跳过）", True)

    print("— 整谱预览 —")
    app.proj["notes"] = [pj.token_to_doc(t) for t in
                         ("5", "6", "1'", "2'", "5!", "6", "3", "2",
                          "5//", "5//", "6//", "6//", "5", "6", "5", "3")]
    app.title_var.set("预览用例")
    app.sel = -1
    app.redraw_all()
    root.update()

    app.open_page_preview()
    root.update()
    check("预览窗口已打开", app._page_win is not None and app._page_win.winfo_exists())
    pv = app._page_cv
    items = pv.find_all()
    check("预览画布画出了内容", len(items) > 10, len(items))
    check("预览画了曲名",
          any(pv.type(i) == "text" and "预览用例" in str(pv.itemcget(i, "text"))
              for i in items))
    score_p, _res_p, _warn_p, key_p = pj.build_render_inputs(app.proj)
    # 预览是拿**导出比例**铺的格（render 的缩放是临时套用、画完还原），
    # 所以这里核对行数/坐标也得先把同一个比例套回去，否则量到的是 100% 的布局。
    _cs_k = render.normalize_content_scale(app.content_scale_var.get())
    render.set_content_scale(_cs_k)
    try:
        n_rows_p = render._build_layout(score_p.events)
        _x0, _w0, _top0 = render._LAYOUT[0]
    finally:
        render.set_content_scale(1.0)
    check("预览行数 = 导出铺格行数（同一套换行规则）",
          f"{n_rows_p} 行" in app._page_info.cget("text"), app._page_info.cget("text"))
    check("预览里画了小节线",
          any(pv.type(i) == "line" for i in items))
    check("预览里含切音窄格（切音色元素）",
          sum(1 for i in items if pv.itemcget(i, "fill") == ed.C_CUT) > 0)
    # 落位要用导出坐标算：第 0 格的数字中心 = pad - MARGIN*k + x*k + w*k/2；
    # 纵向还要乘一次「谱面大小」（格子内容按它缩，格子中线不变）。
    _k = app._page_scale()
    _pad = ed.PREVIEW_PAD
    _ox = _pad - render.MARGIN * _k
    _exp = (_ox + _x0 * _k + _w0 * _k / 2, _pad + _top0 * _k + ed.LABEL_CY * _k * _cs_k)
    _hit = [i for i in items if pv.type(i) == "text" and pv.itemcget(i, "text") == "5"
            and abs(pv.coords(i)[0] - _exp[0]) < 0.6 and abs(pv.coords(i)[1] - _exp[1]) < 0.6]
    check("预览按导出坐标落位（第 0 格数字中心吻合）", len(_hit) == 1,
          f"期望 {_exp}，实际 " + str([pv.coords(i) for i in items
                                       if pv.type(i) == "text"
                                       and pv.itemcget(i, "text") == "5"][:4]))
    # 白页矩形是最外层元素（笛身/小指法图也是矩形，所以按描边色认出来），
    # 用「除它以外」的墨迹算包围盒，才能验证内容没溢出页面
    _page_rect = [i for i in items if pv.type(i) == "rectangle"
                  and pv.itemcget(i, "outline") == "#c2cad2"]
    check("预览画了白页底板", len(_page_rect) == 1, str(len(_page_rect)))
    _ink = [i for i in items if i not in _page_rect]
    _ib = pv.bbox(*_ink)
    if _page_rect and _ib:
        _pr = pv.coords(_page_rect[0])                     # (x0, y0, x1, y1)
        check("预览内容不越出白页右缘", _ib[2] <= _pr[2] + 1,
              f"内容右 {_ib[2]} vs 页右 {_pr[2]}")
        check("预览内容不越出白页下缘", _ib[3] <= _pr[3] + 1,
              f"内容下 {_ib[3]} vs 页下 {_pr[3]}")
        check("预览内容确实铺满多行（下缘接近页底）", _ib[3] > _pr[1] + 100,
              f"{_ib[3]}")
    # 同一个工程，预览行数必须和真实导出 SVG 的行数一致
    _svg_p = render.render_svg(score_p, _res_p, title="预览用例", key=key_p,
                               whistle_key=app.whistle_var.get(), warnings=_warn_p,
                               beats=app.beats_var.get())
    _h = int(re.search(r'height="(\d+)"', _svg_p).group(1))
    check("预览行数 = 导出 SVG 行数",
          _h == render.HEADER_H + n_rows_p * render.row_height() + 30
          + len(_warn_p) * render.FOOTER_PER_WARN,
          f"{n_rows_p} 行 / svg 高 {_h}")
    # 缩放档位
    w60 = pv.bbox("all")[2]
    check("预览缩放比例读得回来（默认 60%）", abs(app._page_scale() - 0.6) < 1e-6,
          app._page_scale())
    app._page_zoom.set("100%")
    app.refresh_page_preview()
    root.update_idletasks()
    w100 = pv.bbox("all")[2]
    check("缩放档位生效（100% 比 60% 宽）", w100 > w60 * 1.4, f"{w60} -> {w100}")
    app._page_zoom.set("60%")
    app.refresh_page_preview()
    root.update_idletasks()
    # 跟随编辑自动刷新（延迟合并 80ms，所以这里真等一下）
    app.beats_var.set("3/4")
    check("改拍号后预览刷新已排队", app._page_job is not None)
    _t0 = time.time()
    while time.time() - _t0 < 3 and app._page_job is not None:
        root.update()
        time.sleep(0.02)
    check("跟随编辑自动刷新已执行", app._page_job is None)
    _s2, _r2, _w2, _k2 = pj.build_render_inputs(app.proj)
    check("刷新后行数跟着拍号变",
          f"{render._build_layout(_s2.events)} 行" in app._page_info.cget("text"),
          app._page_info.cget("text"))
    app.beats_var.set("4/4")
    app._close_page_preview()
    root.update()
    check("预览窗口可关闭", app._page_win is None)
    check("关掉预览后再刷新不报错", app.refresh_page_preview() is None)
    root.withdraw()

    print("— 插入到选中音前 —")
    app.proj = pj.new_project("插入测试", "D", "D", "4/4", True)
    app.proj["_path"] = None
    app.sel = -1
    app._sel_user = False
    app.ins_before.set(1)
    app.set_state("dur", 1.0)
    app.set_state("octave", 0)
    app.st_dot = False
    app.st_short = False

    def toks(a=app):
        return [pj.token_of(d) for d in a.proj["notes"]]

    for d in (1, 2, 3):
        app.append_degree(d)
    check("插入模式开着、但选中框是追加落下来的 → 仍按顺序追加",
          toks() == ["1", "2", "3"], str(toks()))
    check("_insert_at：非用户选中 → None", app._insert_at() is None)
    check("状态条说明会追加到末尾", "追加到末尾" in app.state_lbl.cget("text"),
          app.state_lbl.cget("text"))
    app.sel = 2
    app.move_sel(-1)                         # 等价于用户按 ← 走到第 2 个音
    check("_insert_at：用户选中 → 返回选中下标", app._insert_at() == 1)
    check("状态条说明会插到第 2 个音前", "插到第 2 个音前" in app.state_lbl.cget("text"),
          app.state_lbl.cget("text"))
    app.append_degree(7)
    check("新音插在选中音之前", toks() == ["1", "7", "2", "3"], str(toks()))
    check("插完选中框仍在原来的音上（下标 +1）",
          app.sel == 2 and pj.token_of(app.proj["notes"][app.sel]) == "2", app.sel)
    app.append_degree(6)
    check("连续插入按敲键顺序排在它前面", toks() == ["1", "7", "6", "2", "3"], str(toks()))
    app.move_sel(-3)                         # 走到第一个音
    app.append_degree(5)
    check("插到第一个音前面", toks() == ["5", "1", "7", "6", "2", "3"], str(toks()))
    check("状态栏提示带上插入位置", "已插到第 1 个音前" in app.status.cget("text"),
          app.status.cget("text"))
    app.undo()
    check("插入可撤销", toks() == ["1", "7", "6", "2", "3"], str(toks()))
    app.ins_before.set(0)
    app.sel = 1
    app._sel_user = True
    check("关掉插入模式：_insert_at 返回 None", app._insert_at() is None)
    n_before = len(app.proj["notes"])
    app.append_degree(4)
    check("关掉插入模式后追加到末尾",
          toks()[-1] == "4" and len(app.proj["notes"]) == n_before + 1, str(toks()))
    app.ins_before.set(1)
    app.sel = 2
    app._sel_user = False
    app._on_insert_toggle()                  # 勾上复选框 = 认下当前选中音
    check("重新勾上「插入到选中音前」立即认下当前选中音", app._insert_at() == 2, app.sel)

    print("— 歌词（简谱数字与洞洞之间）—")
    app.proj = pj.new_project("歌词测试", "D", "D", "4/4", True)
    app.proj["_path"] = None
    app.sel = -1
    app._sel_user = False
    app.ins_before.set(1)
    app.set_state("dur", 1.0)
    app.set_state("octave", 0)
    app.st_dot = False
    app.st_short = False
    for d in (5, 6, 1):
        app.append_degree(d)
    app.append_rest()
    app.append_hold()
    app.append_degree(2)
    root.update()
    ln = app.proj["notes"]
    check("工程里 6 个事件（含休止/延音）", len(ln) == 6, len(ln))
    app.sel = 0
    app._load_lyric_box()
    app.lyric_var.set("春")
    root.update()
    check("歌词写进当前音", pj.lyric_of(ln[0]) == "春", pj.lyric_of(ln[0]))
    check("歌词存进工程字典（能保存）", ln[0].get("lyric") == "春")
    app._lyric_commit_next()
    root.update()
    check("空格跳到下一个音", app.sel == 1, app.sel)
    check("跳到新音后歌词框已同步为空", app.lyric_var.get() == "", repr(app.lyric_var.get()))
    app.lyric_var.set("whistle")             # 英文单词也支持
    root.update()
    check("英文单词也能当歌词", pj.lyric_of(ln[1]) == "whistle")
    app.sel = 2
    app._load_lyric_box()
    app._lyric_commit_next()                 # 中间隔着休止 + 延音
    root.update()
    check("空格跳过休止/延音/小节线，落到下一个音", app.sel == 5, app.sel)
    app.lyric_var.set("二")
    root.update()
    check("新音的歌词写进去", pj.lyric_of(ln[5]) == "二")
    app.sel = 3
    app._load_lyric_box()
    app.lyric_var.set("哼")
    root.update()
    check("休止/延音不能填词",
          not any(d.get("lyric") for d in ln[3:5]), str([d.get("lyric") for d in ln]))
    app.sel = 5
    app._lyric_commit_next()                 # 已是最后一个音
    check("最后一个音再按空格只提示，不越界", app.sel == 5, app.sel)

    # 中文输入法：空格 / 回车也是「选候选上屏」用的。真机上 Tk 把**整个上屏**当成一次按键
    # 交给我们 —— keysym 还是 space，但 `event.char` 是上屏的那个字。用户那边开诊断后的实录：
    #     [ +1920.4 ms] ── KeyPress space  char='映' state=0x8 | comp=0 | var=''
    # 所以判据是一条硬判据：**char 不是空格 / 回车本身 ⇒ 这个键被输入法拿去上屏了 ⇒ 放行**。
    #
    # 前两版的做法是「押后多久看字有没有落地」，一次边框 160ms、一次加到 400ms，两版都错了：
    # 老实现在上屏事件里 `return "break"` 把字挡在框外（`var` 一直是空的），于是「等会儿看看
    # 字有没有来」永远等不到。这两条用例把新判据钉住。
    #
    # 顺带解释「为什么只有一部分字会犯」：候选唯一的常用字（应 / 影）输入法**自动上屏**，
    # 用户压根不按空格；要翻页 / 手动选候选的字（映）才按得上。跟快慢无关。

    class _KeyLike:
        """照 Tk 的事件样子做个替身：keysym + char（char 才是判据）"""

        def __init__(self, char=" ", keysym="space"):
            self.char = char
            self.keysym = keysym
            self.state = 0x8

    def _space():                        # 真按下的空格（输入法没吃这个键）
        return _KeyLike(" ", "space")

    def _commit(ch, keysym="space"):     # 输入法上屏事件（char 是上屏的字）
        return _KeyLike(ch, keysym)

    app.sel = 0
    app._load_lyric_box()
    app.lyric_var.set("长")
    root.update()

    # ① 用户报的那一条：char='映' 的上屏事件必须**放行**，让字进输入框
    got = app._lyric_commit_next(_commit("映"))
    root.update()
    check("① 上屏事件返回 None 放行（不能 break，否则字被挡在框外）", got is None, got)
    check("① 上屏事件不跳格", app.sel == 0, app.sel)
    app.lyric_var.set("长映")            # 放行的结果：字真的进来了
    root.update()
    check("① 那个字落在当前这一格", pj.lyric_of(ln[0]) == "长映", pj.lyric_of(ln[0]))

    # ② 回车上屏同理（有人习惯用回车选候选）
    app.sel = 0
    app._load_lyric_box()
    app.lyric_var.set("长")
    root.update()
    got = app._lyric_commit_next(_commit("晚", "Return"))
    root.update()
    check("② 回车上屏同样放行、不跳格", got is None and app.sel == 0, f"{got!r} sel={app.sel}")

    # ③ 真·空格（输入法没吃这个键）：立刻跳，不再押后等待
    app.sel = 0
    app._load_lyric_box()
    app.lyric_var.set("长映")
    root.update()
    app._lyric_commit_next(_space())
    root.update()
    check("③ 真空格立刻跳下一个音（零延迟，不再押后）", app.sel == 1, app.sel)

    # ④ imm32 兜底：走 IMM 的输入法查得到组字状态（用户的输入法走 TSF，查不到，恒 False）
    app.sel = 0
    app._load_lyric_box()
    app.lyric_var.set("长映")
    root.update()
    app._ime_is_composing = (lambda: True)
    app._lyric_commit_next(_space())
    root.update()
    check("④ 还在组字时不跳格（imm32 兜底）", app.sel == 0, app.sel)
    app._ime_is_composing = (lambda: False)
    app._lyric_commit_next(_space())
    root.update()
    check("④ 没组字时照旧跳（不误伤最高频工作流）", app.sel == 1, app.sel)
    del app._ime_is_composing             # 还原（别把桩留到后面）
    check("探不到输入法状态时安全返回 False（不抛异常）",
          isinstance(ed.ime_is_composing(0), bool), "非布尔")

    app.sel = 0
    app._load_lyric_box()
    app.lyric_var.set("hello")
    root.update()
    app._lyric_commit_next(_space())
    root.update()
    check("英文歌词按空格也照旧跳", app.sel == 1, app.sel)

    # Tab 是没歧义的那一键：输入法不吃它，按下立刻跳
    app.sel = 0
    app._load_lyric_box()
    app.lyric_var.set("外")
    root.update()
    app._lyric_tab_next(_space())
    root.update()
    check("Tab 立刻跳（输入法不吃这个键，不用等）", app.sel == 1, app.sel)
    app.sel = 0
    app._load_lyric_box()
    app.lyric_var.set("春")
    root.update()
    app.sel = -1
    app.redraw_all()
    root.update()
    items_l = app.score.find_all()

    def _txt(i):
        return str(app.score.itemcget(i, "text"))

    dig5 = [i for i in items_l if app.score.type(i) == "text" and _txt(i) == "5"
            and app.score.itemcget(i, "fill") == ed.C_TEXT]
    ly_items = [i for i in items_l if app.score.type(i) == "text"
                and _txt(i) in ("春", "二", "whistle")
                and app.score.itemcget(i, "fill") == ed.C_LYRIC]
    check("谱面画出全部歌词", len(ly_items) == 3, str(len(ly_items)))
    check("找到第一个音的数字", len(dig5) == 1, str(len(dig5)))
    if dig5 and ly_items:
        dx, dy = app.score.coords(dig5[0])[:2]
        same = [i for i in ly_items if abs(app.score.coords(i)[0] - dx) < 0.6]
        check("歌词与数字同一条竖线（居中于同列）", len(same) == 1, str(len(same)))
        if same:
            lyy = app.score.coords(same[0])[1]
            row_top = dy - ed.LABEL_CY
            flute_top = row_top + ed.FLUTE_TOP + ed.LYRIC_DY
            check("歌词夹在数字与笛身之间（数字 < 歌词 < 笛身顶）",
                  dy < lyy < flute_top, f"数字 {dy} / 歌词 {lyy} / 笛身顶 {flute_top}")
            check("歌词基线 = 笛身顶再上移 6",
                  abs(lyy - (flute_top - 6)) < 0.6, f"{lyy} vs {flute_top - 6}")
    check("没歌词时不让位（LYRIC_SHIFT=0）",
          (ed.set_lyric_shift([pj.new_note(1, 0, 0)]), ed._LYRIC_SHIFT == 0)[1],
          ed._LYRIC_SHIFT)
    _ld = pj.new_note(1, 0, 0)
    pj.set_lyric(_ld, "啊")
    ed.set_lyric_shift([_ld])
    check("有歌词时笛身整体下移 LYRIC_DY", ed._LYRIC_SHIFT == ed.LYRIC_DY, ed._LYRIC_SHIFT)

    # 导出 SVG 里也有歌词，位置同样是「数字之下、笛身之上」。
    # 记号尺寸随「谱面大小」缩（导出默认 65%），所以期望值必须用**同一个比例**算：
    # 临时把 render 套到导出那个比例，直接拿它的 _s() / 常量拼期望串 ——
    # 自己抄一份 ×0.7 的算术最容易和实现悄悄跑偏。
    app.proj["title"] = "歌词测试"
    app._sync_project_meta()
    lpath = pj.export_svg(app.proj, out_dir)
    ltext = open(lpath, encoding="utf-8").read()
    check("导出 SVG 含歌词文本", "whistle" in ltext and "二" in ltext)
    check("导出 SVG 用歌词色", render.C_LYRIC in ltext)
    _csn = render.normalize_content_scale(app.content_scale_var.get())
    render.set_content_scale(_csn)
    try:
        # 歌词字号会被「放不下就缩一号」的循环改小，所以字号那格只能宽匹配；
        # 数字字号是 NOTE_SIZE 定值，可以精确匹配。
        lyr_xml = re.findall(
            r'<text x="([\d.]+)" y="([\d.]+)" font-size="[\d.]+" fill="%s"[^>]*>([^<]*)</text>'
            % re.escape(render.C_LYRIC), ltext)
        digs = {round(float(x)): float(y) for x, y in re.findall(
            r'<text x="([\d.]+)" y="([\d.]+)" font-size="%s" font-weight="bold"'
            % re.escape(str(render.NOTE_SIZE)), ltext)}
        flutes = {}
        for fx, fy in re.findall(
                r'<rect x="([\d.]+)" y="([\d.]+)" width="%s" height="%s" rx="%s"'
                % (re.escape(str(render.FLUTE_W)), re.escape(str(render.FLUTE_H)),
                   re.escape(str(render._s(12)))), ltext):
            flutes[round(float(fx) + render.FLUTE_W / 2)] = float(fy)
        want_dy = (render.FLUTE_TOP_DY + render.LYRIC_DY - render._s(6)
                   - render.LABEL_BASE_DY)
    finally:
        render.set_content_scale(1.0)
    check("导出 SVG 有 3 条歌词", len(lyr_xml) == 3, str(len(lyr_xml)))
    lying = [float(y) for x, y, _t in lyr_xml if round(float(x)) in flutes]
    check("导出 SVG：歌词全部画在笛身之上", len(lying) == len(lyr_xml)
          and all(float(y) < flutes[round(float(x))] for x, y, _t in lyr_xml
                  if round(float(x)) in flutes),
          str([(float(y), flutes.get(round(float(x)))) for x, y, _t in lyr_xml]))
    got_dy = [round(float(y) - digs[round(float(x))], 2) for x, y, _t in lyr_xml
              if round(float(x)) in digs]
    check(f"导出 SVG：歌词竖向偏移与规则一致（数字之下 {want_dy:.1f}）",
          len(got_dy) == len(lyr_xml) and all(abs(v - want_dy) < 0.6 for v in got_dy),
          f"期望 {want_dy}，实际 {got_dy}")
    app.sel = 0
    app.clear_lyric()
    root.update()
    check("清空当前音歌词", pj.lyric_of(ln[0]) == "")
    check("清空后工程里不留空 lyric 键", "lyric" not in ln[0], str(ln[0]))

    # 切音自带窄格 + 小指法图：它的歌词不能压在小图上（小图整体上提了）
    ln[2]["short"] = True
    pj.set_lyric(ln[2], "外")
    app.sel = -1
    app.redraw_all()
    root.update()
    items_c = app.score.find_all()
    mini_c = [i for i in items_c if app.score.type(i) == "rectangle"
              and app.score.itemcget(i, "outline") == ed.C_CUT
              and app.score.itemcget(i, "fill") == "#fdfdf8"]
    cut_lyr = [i for i in items_c if app.score.type(i) == "text" and _txt(i) == "外"
               and app.score.itemcget(i, "fill") == ed.C_LYRIC]
    check("切音格子也画歌词", len(cut_lyr) == 1 and len(mini_c) == 1,
          f"歌词 {len(cut_lyr)} / 小图 {len(mini_c)}")
    if cut_lyr and mini_c:
        mx0, my0, mx1, _my1 = app.score.coords(mini_c[0])
        check("切音歌词落在小指法图上方（没压在小图上）",
              app.score.coords(cut_lyr[0])[1] < my0,
              f"歌词 {app.score.coords(cut_lyr[0])[1]} vs 小图顶 {my0}")
        check("切音歌词与小图同一条竖线",
              abs(app.score.coords(cut_lyr[0])[0] - (mx0 + mx1) / 2) < 0.6,
              f"歌词 {app.score.coords(cut_lyr[0])[0]} vs 图心 {(mx0 + mx1) / 2}")
    ln[2]["short"] = False
    pj.set_lyric(ln[2], "")
    app.sel = -1
    app.redraw_all()
    root.update()

    # 超吹三角：**站在洞洞图下沿之下、音名上方**。
    # 老口径站在笛身顶上方，那一带正是歌词带中心，于是有歌词时得把三角搬到歌词上方再缩小
    # （缩到 8px，导出到纸上基本看不见 —— 用户反馈「输出谱面里没有超吹记号」）。
    # 搬到笛身**下面**之后那一带本来就是空的，位置**与歌词无关**，也不用再让位。
    app.key_var.set("D")
    app.whistle_var.set("D")
    o_doc = pj.token_to_doc("1'")            # 1=D + D 哨笛：1' 落在第二八度（超吹）
    o_doc["duration"] = 1.0
    pj.set_lyric(o_doc, "高")
    app.proj["notes"].append(o_doc)
    app.sel = -1
    app.redraw_all()
    root.update()

    def oct_tris():
        return [i for i in app.score.find_all() if app.score.type(i) == "polygon"
                and app.score.itemcget(i, "fill") in (ed.C_ACCENT, ed.C_WARN)]

    def oct_name():
        """音名那一行（「D 高」）；歌词是 C_LYRIC 另一个颜色，不会被认错"""
        for i in app.score.find_all():
            if (app.score.type(i) == "text"
                    and app.score.itemcget(i, "fill") in (ed.C_ACCENT, ed.C_WARN)
                    and app.score.itemcget(i, "text").strip().endswith("高")):
                return i
        return None

    def flute_bottom():
        """当前让位量下，洞洞图的下沿（画布坐标）"""
        return ed.SCORE_TOP + ed.FLUTE_TOP + ed._LYRIC_SHIFT + ed.FLUTE_H

    tri_o = oct_tris()
    nm = oct_name()
    lyr_o = [i for i in app.score.find_all() if app.score.type(i) == "text"
             and app.score.itemcget(i, "text") == "高"
             and app.score.itemcget(i, "fill") == ed.C_LYRIC]
    check("超吹音 + 歌词：三角和歌词都画出来了", len(tri_o) == 1 and len(lyr_o) == 1,
          f"三角 {len(tri_o)} / 歌词 {len(lyr_o)}")
    if tri_o and nm is not None:
        # Tk 的 bbox 对多边形会各向外让 1px（描边宽度），量尺寸一律用 coords（顶点真值）
        c_o = app.score.coords(tri_o[0])
        tip_o, base_o = c_o[1], c_o[3]
        tb_o, nb_o = app.score.bbox(tri_o[0]), app.score.bbox(nm)
        fb_o = flute_bottom()
        check("三角顶贴着洞洞图下沿（+OCT_MARK_GAP）",
              abs(tip_o - (fb_o + ed.OCT_MARK_GAP)) <= 0.01,
              f"三角顶 {tip_o} vs 笛身底 {fb_o}")
        check("三角高 = OCT_MARK_H（不再因为歌词缩小）",
              abs((base_o - tip_o) - ed.OCT_MARK_H) <= 0.01,
              f"{base_o - tip_o} vs {ed.OCT_MARK_H}")
        check("三角底边宽 = OCT_MARK_W",
              abs((c_o[2] - c_o[4]) - ed.OCT_MARK_W) <= 0.01,
              f"{c_o[2] - c_o[4]} vs {ed.OCT_MARK_W}")
        check("三角在音名上方（底边不压到音名那一行）", tb_o[3] < nb_o[1] - 1,
              f"三角底 {tb_o[3]} vs 音名上沿 {nb_o[1]}")
        check("三角与音名同一条竖线（都居中于本列）",
              abs((tb_o[0] + tb_o[2]) / 2 - (nb_o[0] + nb_o[2]) / 2) < 1.0,
              f"{(tb_o[0] + tb_o[2]) / 2} vs {(nb_o[0] + nb_o[2]) / 2}")
        check("三角整个落在歌词**下方**（不再需要为歌词让位）",
              tb_o[1] > app.score.bbox(lyr_o[0])[3] if lyr_o else True,
              f"三角顶 {tb_o[1]} vs 歌词底 {app.score.bbox(lyr_o[0])[3]}" if lyr_o else "")
        _gap_with_lyric = round(tip_o - fb_o, 2)
    # 只清本格的词：整谱别处还有词（ln[1]="whistle"、ln[5]="二"），所以笛身整体仍让位
    pj.set_lyric(o_doc, "")
    app.redraw_all()
    root.update()
    check("本格清词、别处仍有词：整谱照旧让位（LYRIC_SHIFT=LYRIC_DY）",
          ed._LYRIC_SHIFT == ed.LYRIC_DY, ed._LYRIC_SHIFT)
    # 再把全谱的词都清掉，验证「整谱无词」时让位收起、版面复原
    for d in app.proj["notes"]:
        pj.set_lyric(d, "")
    app.redraw_all()
    root.update()
    check("整谱无词：让位收起（LYRIC_SHIFT 回 0）", ed._LYRIC_SHIFT == 0, ed._LYRIC_SHIFT)
    tri_n = oct_tris()
    check("无歌词：超吹三角照旧只有一个", len(tri_n) == 1, len(tri_n))
    if tri_n:
        c_n = app.score.coords(tri_n[0])
        t_n = app.score.bbox(tri_n[0])
        check("无歌词时三角相对笛身底的位置不变（新口径与歌词无关）",
              round(c_n[1] - flute_bottom(), 2) == _gap_with_lyric,
              f"{round(c_n[1] - flute_bottom(), 2)} vs {_gap_with_lyric}")
        check("无歌词时三角同样不缩号（与带歌词时同一尺寸）",
              abs((c_n[3] - c_n[1]) - ed.OCT_MARK_H) <= 0.01,
              f"{c_n[3] - c_n[1]} vs {ed.OCT_MARK_H}")
        check("三角仍在音名上方", t_n[3] < app.score.bbox(oct_name())[1] - 1,
              f"三角底 {t_n[3]} vs 音名上沿 {app.score.bbox(oct_name())[1]}")
    app.proj["notes"].pop()
    app.sel = -1
    app.redraw_all()
    root.update()

    # ---------------- 多行歌词：洞洞图自动往下适配 ----------------
    print("— 多行歌词（洞洞图往下适配）—")
    app.proj = pj.new_project("多行歌词", "D", "D", "4/4", True)
    app.proj["_path"] = None
    app.sel = -1
    app._sel_user = False
    app.autobar_var.set(0)
    app._meta_changed()
    app.set_state("dur", 1.0)
    app.set_state("octave", 0)
    app.st_dot = False
    app.st_short = False
    for d in (5, 6, 1):
        app.append_degree(d)
    root.update()
    mln = app.proj["notes"]
    app.sel = 0
    app._load_lyric_box()
    app.lyric_var.set("一")
    root.update()
    check("单行词：让位仍是 LYRIC_DY（老观感不变）",
          ed._LYRIC_SHIFT == ed.LYRIC_DY, ed._LYRIC_SHIFT)
    _h1 = ed.score_content_h()

    # 加歌词行只该让**谱面**的洞洞图下移；指法表 / 自定义指法预览没有歌词，
    # 它们的洞洞图必须纹丝不动（曾经它们也跟着串下去，画布不够高就直接串出去）。
    def _items(cv):
        return [(cv.type(i), tuple(round(v, 2) for v in cv.coords(i)))
                for i in cv.find_all()]

    def _flute_top(cv):
        ys = [cv.coords(i)[1] for i in cv.find_all()
              if cv.type(i) == "oval" and cv.itemcget(i, "outline") == ed.C_FLUTE]
        return min(ys) if ys else None

    app.redraw_all()
    root.update()
    _chart_before, _prev_before = _items(app.chart), _items(app.preview)
    _chart_flute_before, _prev_flute_before = _flute_top(app.chart), _flute_top(app.preview)
    _score_flute_before = _flute_top(app.score)
    check("前置：三块画布的笛身都画出来了",
          None not in (_chart_flute_before, _prev_flute_before, _score_flute_before),
          f"{_chart_flute_before} / {_prev_flute_before} / {_score_flute_before}")

    app.add_lyric_line()
    root.update()
    app.redraw_all()
    root.update()
    check("＋行：谱面留出两段歌词", pj.lyric_line_count(app.proj["notes"]) == 2,
          pj.lyric_line_count(app.proj["notes"]))
    check("＋行：让位多让一行（LYRIC_LINE_H）",
          ed._LYRIC_SHIFT == ed.LYRIC_DY + ed.LYRIC_LINE_H, ed._LYRIC_SHIFT)
    check("＋行：谱面区高度跟着长（最后一行歌词不会被裁）",
          abs(ed.score_content_h() - _h1 - ed.LYRIC_LINE_H) < 0.01,
          f"{_h1} -> {ed.score_content_h()}")
    # 三块画布的分工：只有谱面的洞洞图该下移
    check("＋行：指法表的洞洞图纹丝不动（不跟歌词让位下串）",
          _items(app.chart) == _chart_before, "指法表被歌词让位带跑了")
    check("＋行：指法表的笛身 y 没变",
          _flute_top(app.chart) == _chart_flute_before,
          f"{_chart_flute_before} -> {_flute_top(app.chart)}")
    check("＋行：自定义指法预览的洞洞图纹丝不动",
          _items(app.preview) == _prev_before, "自定义指法预览被歌词让位带跑了")
    check("＋行：自定义指法预览的笛身 y 没变",
          _flute_top(app.preview) == _prev_flute_before,
          f"{_prev_flute_before} -> {_flute_top(app.preview)}")
    check("＋行：只有谱面的笛身下移了（正好一行 LYRIC_LINE_H）",
          _flute_top(app.score) is not None
          and abs(_flute_top(app.score)
                  - (_score_flute_before + ed.LYRIC_LINE_H)) < 0.01,
          f"{_score_flute_before} -> {_flute_top(app.score)}")
    check("＋行：「第 N 行」下拉跟着长到 2 行",
          tuple(str(v) for v in app.lyric_line_box.cget("values")) == ("1", "2"),
          str(app.lyric_line_box.cget("values")))
    app.lyric_line_var.set("2")
    app._load_lyric_box()
    check("切到第 2 行：输入框清空（这一行还没词）", app.lyric_var.get() == "",
          repr(app.lyric_var.get()))
    app.lyric_var.set("二")
    root.update()
    check("第 2 行的词存进 lyric_lines[1]", pj.lyric_lines_of(mln[0]) == ["一", "二"],
          str(pj.lyric_lines_of(mln[0])))
    app.sel = 1
    app._load_lyric_box()                    # 换音但仍在第 2 行
    app.lyric_var.set("三")
    root.update()
    check("不同音的第 2 行也能填", pj.lyric_lines_of(mln[1])[1:] == ["三"],
          str(pj.lyric_lines_of(mln[1])))
    app.sel = -1
    app.redraw_all()
    root.update()
    _items_m = app.score.find_all()

    def _lyr_items(txt):
        return [i for i in _items_m if app.score.type(i) == "text"
                and app.score.itemcget(i, "text") == txt
                and app.score.itemcget(i, "fill") == ed.C_LYRIC]

    _l1, _l2, _l3 = _lyr_items("一"), _lyr_items("二"), _lyr_items("三")
    check("画布：两段歌词都画出来了（一 / 二 / 三 各一处）",
          len(_l1) == 1 and len(_l2) == 1 and len(_l3) == 1,
          f"{len(_l1)}/{len(_l2)}/{len(_l3)}")
    if _l1 and _l2:
        _c1, _c2 = app.score.coords(_l1[0]), app.score.coords(_l2[0])
        check("画布：第 2 行落在第 1 行正下方一行（LYRIC_LINE_H）",
              abs((_c2[1] - _c1[1]) - ed.LYRIC_LINE_H) < 0.6, f"{_c1[1]} -> {_c2[1]}")
        check("画布：两行歌词同一条竖线（各自居中于本列）",
              abs(_c1[0] - _c2[0]) < 0.6, f"{_c1[0]} vs {_c2[0]}")
        check("画布：第 1 行更靠上（行序没反）", _c1[1] < _c2[1], f"{_c1[1]} / {_c2[1]}")
    if _l2 and _l3:
        check("画布：不同音的第 2 行歌词对得齐（同一条基线）",
              abs(app.score.coords(_l3[0])[1] - app.score.coords(_l2[0])[1]) < 0.6,
              f"{app.score.coords(_l3[0])[1]} vs {app.score.coords(_l2[0])[1]}")
    if _l2:
        _flute_m = ed.SCORE_TOP + ed.FLUTE_TOP + ed.LYRIC_DY + ed.LYRIC_LINE_H
        check("画布：第 2 行仍压在笛身顶上方（洞洞图整体让开了）",
              app.score.coords(_l2[0])[1] < _flute_m,
              f"歌词 {app.score.coords(_l2[0])[1]} vs 笛身顶 {_flute_m}")
    app._sync_project_meta()
    _path_m = pj.export_svg(app.proj, out_dir)
    _text_m = open(_path_m, encoding="utf-8").read()
    check("导出 SVG 也带上了两段歌词（存得住）",
          all(t in _text_m for t in ("一", "二", "三")))
    app.remove_lyric_line()
    root.update()
    check("－行：歌词段减回 1 段", pj.lyric_line_count(app.proj["notes"]) == 1,
          pj.lyric_line_count(app.proj["notes"]))
    check("－行：让位收回到 LYRIC_DY", ed._LYRIC_SHIFT == ed.LYRIC_DY, ed._LYRIC_SHIFT)
    app.remove_lyric_line()
    check("只剩 1 段时「－行」不删（只提示）",
          pj.lyric_line_count(app.proj["notes"]) == 1,
          pj.lyric_line_count(app.proj["notes"]))

    # ---------------- 反复记号（循环符号） ----------------
    print("— 反复记号（循环符号 |: :|）—")
    app.proj = pj.new_project("反复", "D", "D", "4/4", True)
    app.proj["_path"] = None
    app.sel = -1
    app._sel_user = False
    app.autobar_var.set(0)
    app._meta_changed()
    app.set_state("dur", 1.0)
    app.set_state("octave", 0)
    app.st_dot = False
    app.st_short = False
    for d in (1, 2, 3, 4):
        app.append_degree(d)
    app.append_repeat("start")
    for d in (5, 6, 7, 1):
        app.append_degree(d)
    app.append_repeat("end")
    root.update()
    rn = app.proj["notes"]
    check("反复记号进了工程（kind=repeat，方向记住）",
          [d.get("kind") for d in rn]
          == [pj.KIND_NOTE] * 4 + [pj.KIND_REPEAT] + [pj.KIND_NOTE] * 4 + [pj.KIND_REPEAT],
          str([d.get("kind") for d in rn]))
    check("反复记号 token 往返（|: / :|）",
          pj.token_of(rn[4]) == "|:" and pj.token_of(rn[9]) == ":|",
          f"{pj.token_of(rn[4])} / {pj.token_of(rn[9])}")
    _thin, _thick, _dots = [], [], []
    for i in app.score.find_all():
        _t = app.score.type(i)
        _f = app.score.itemcget(i, "fill")
        if _t == "line":
            if _f == "#8a949c":
                _thin.append(i)
            elif _f == ed.C_TEXT and abs(float(app.score.itemcget(i, "width")) - 3.0) < 0.01:
                _thick.append(i)
        elif _t == "oval" and _f == ed.C_TEXT:
            _dots.append(i)
    check("画布：两个反复记号各画出细线 + 粗线",
          len(_thin) == 2 and len(_thick) == 2, f"细 {len(_thin)} / 粗 {len(_thick)}")
    check("画布：两个反复记号共 4 粒反复点", len(_dots) == 4, len(_dots))
    if len(_thin) == 2 and len(_thick) == 2:
        _rep_cx = [(app._cell_map[k][0] + app._cell_map[k][1]) / 2 for k in (4, 9)]
        check("画布：反复记号的线落在自己那一列（居中对齐）",
              abs(app.score.coords(_thick[0])[0] - (_rep_cx[0] + 2)) < 0.6,
              f"粗线 {app.score.coords(_thick[0])[0]} vs 列心 {_rep_cx[0]}")
        _tx = sorted(app.score.coords(i)[0] for i in _thin)
        _kx = sorted(app.score.coords(i)[0] for i in _thick)
        check("画布：|: 是 细-粗-··（粗线在细线右侧）", _kx[0] > _tx[0], f"细 {_tx} 粗 {_kx}")
        check("画布：:| 是 ··-粗-细（与 |: 镜像）", _kx[1] < _tx[1], f"细 {_tx} 粗 {_kx}")
        check("画布：粗线确实比细线粗",
              float(app.score.itemcget(_thick[0], "width"))
              > float(app.score.itemcget(_thin[0], "width")))
    if len(_dots) == 4:
        _dot_x = sorted((app.score.coords(i)[0] + app.score.coords(i)[2]) / 2 for i in _dots)
        _dot_y = sorted({round((app.score.coords(i)[1] + app.score.coords(i)[3]) / 2, 1)
                         for i in _dots})
        _rep_cx = [(app._cell_map[k][0] + app._cell_map[k][1]) / 2 for k in (4, 9)]
        check("画布：|: 的两粒点在粗线右侧 7px 处",
              abs(_dot_x[0] - (_rep_cx[0] + 9)) < 0.6 and abs(_dot_x[1] - (_rep_cx[0] + 9)) < 0.6,
              str(_dot_x))
        check("画布：:| 的两粒点在粗线左侧 7px 处",
              abs(_dot_x[2] - (_rep_cx[1] - 9)) < 0.6 and abs(_dot_x[3] - (_rep_cx[1] - 9)) < 0.6,
              str(_dot_x))
        check("画布：反复点一上一下（两粒同一列，间距随数字高度收窄）",
              len(_dot_y) == 2
              and abs((_dot_y[1] - _dot_y[0]) - 2 * ed.REPEAT_DOT_DY) < 0.6,
              str(_dot_y))
    # 自动小节线：反复记号自己就是收尾，不该再和普通小节线堆在一起
    app.autobar_var.set(1)
    app._meta_changed()
    root.update()
    _shown_a, _imap_a = pj.display_notes(app.proj)
    _bars_a = [k for k, d in enumerate(_shown_a) if d.get("kind") == pj.KIND_BAR]
    _rep_a = [k for k, d in enumerate(_shown_a) if d.get("kind") == pj.KIND_REPEAT]
    check("自动小节线：两个反复记号都留着、可选中",
          _rep_a == [4, 9] and all(_imap_a[k] is not None for k in _rep_a),
          f"反复 {_rep_a} / 映射 {[_imap_a[k] for k in _rep_a]}")
    check("自动小节线：紧邻的普通小节线被反复记号顶掉（不再 | + |: 连堆）",
          _bars_a == [], str(_bars_a))

    # 半个小节就撞上反复记号 —— 反复记号自己收尾，不许再补一条小节线。
    # 曾经的 bug：这里会补出 `|`，画面上成了 `1 2 3 | |:`（一条小节线紧挨一个反复起）。
    app.proj = pj.new_project("相邻", "D", "D", "4/4", True)
    app.proj["_path"] = None
    app.sel = -1
    app._sel_user = False
    app.autobar_var.set(0)
    app._meta_changed()
    for _d in (1, 2, 3):
        app.append_degree(_d)
    app.append_repeat("start")
    for _d in (4, 5, 6, 7):
        app.append_degree(_d)
    root.update()
    app.autobar_var.set(1)
    app._meta_changed()
    root.update()
    _shown_h, _imap_h = pj.display_notes(app.proj)
    _toks_h = [pj.token_of(d) for d in _shown_h]
    _kinds_h = [d.get("kind") for d in _shown_h]
    _bad_h = [(i, _kinds_h[i], _kinds_h[i + 1]) for i in range(len(_kinds_h) - 1)
              if pj.KIND_BAR in (_kinds_h[i], _kinds_h[i + 1])
              and pj.KIND_REPEAT in (_kinds_h[i], _kinds_h[i + 1])]
    check("自动小节线：半个小节 + |: 不再 `| + |:` 连堆（反复记号不与小节线相邻）",
          not _bad_h, f"{_bad_h} in {_toks_h}")
    check("自动小节线：`1 2 3 |: 4 5 6 7` 展示为 1 2 3 |: 4 5 6 7 |",
          _toks_h == ["1", "2", "3", "|:", "4", "5", "6", "7", "|"], str(_toks_h))
    # 画布上竖线条数 == 序列里的 (小节线 + 反复记号) 数：多一条就是又画重了
    _thin_h = [i for i in app.score.find_all()
               if app.score.type(i) == "line"
               and app.score.itemcget(i, "fill") == "#8a949c"]
    _marks_h = sum(1 for d in _shown_h if d.get("kind") in (pj.KIND_BAR, pj.KIND_REPEAT))
    check("画布：竖线条数 = 小节线 + 反复记号（没有多画一条紧挨的）",
          len(_thin_h) == _marks_h, f"画布 {len(_thin_h)} / 应有 {_marks_h} {_toks_h}")

    # ---------------- 换气记号 v ----------------
    print("— 换气记号 v —")
    app.proj = pj.new_project("换气", "D", "D", "4/4", True)
    app.proj["_path"] = None
    app.sel = -1
    app._sel_user = False
    app.autobar_var.set(0)
    app._meta_changed()
    app.set_state("dur", 1.0)
    app.set_state("octave", 0)
    app.st_dot = False
    app.st_short = False
    app.append_degree(5)
    app.append_degree(6)
    app.sel = 0
    app.set_slur("start")
    app.sel = 1
    app.set_slur("end")
    app.sel = -1
    app.redraw_all()
    root.update()

    def _arc_apex():
        for i in app.score.find_all():
            if (app.score.type(i) == "line"
                    and app.score.itemcget(i, "fill") == ed.C_SLUR
                    and len(app.score.coords(i)) == 6):
                return app.score.coords(i)[3]
        return None

    _ap0 = _arc_apex()
    check("用例有效：先有一条圆滑线（不同音相连）", _ap0 is not None, str(_ap0))
    app.sel = 0
    app.toggle_breath()
    root.update()
    check("toggle_breath：选中音加上 breath", app.proj["notes"][0].get("breath") is True)
    _ap1 = _arc_apex()
    check("换气让圆滑线整体再抬 BREATH_LIFT（不压 v）",
          _ap0 is not None and _ap1 is not None
          and abs((_ap0 - _ap1) - ed.BREATH_LIFT) < 0.6,
          f"{_ap0} -> {_ap1}（期望抬 {ed.BREATH_LIFT}）")
    _vv = [i for i in app.score.find_all() if app.score.type(i) == "text"
           and app.score.itemcget(i, "text") == "v"
           and app.score.itemcget(i, "fill") == ed.C_BREATH]
    check("画布画出换气 v（只有一个）", len(_vv) == 1, len(_vv))
    if _vv:
        _vx, _vy = app.score.coords(_vv[0])[:2]
        _cx0 = (app._cell_map[0][0] + app._cell_map[0][1]) / 2
        _d0 = [i for i in app.score.find_all() if app.score.type(i) == "text"
               and app.score.itemcget(i, "text") == "5"
               and app.score.itemcget(i, "fill") == ed.C_TEXT
               and abs(app.score.coords(i)[0] - _cx0) < 0.6]
        check("v 与数字同一条竖线（画在数字正上方）", abs(_vx - _cx0) < 0.6,
              f"v x={_vx} vs 列心 {_cx0}")
        check("v 比数字高一档（在记号区上方）",
              len(_d0) == 1 and _vy < app.score.coords(_d0[0])[1],
              f"v y={_vy} 数字 y={[app.score.coords(i)[1] for i in _d0]}")
        check("抬高后的弧线仍在 v 之上（不压记号）",
              _ap1 is not None and _ap1 < _vy, f"弧顶 {_ap1} vs v {_vy}")
    app.sel = 0
    app.toggle_breath()
    root.update()
    check("再点一次取消换气（breath 收回 False）",
          app.proj["notes"][0].get("breath") is False, str(app.proj["notes"][0].get("breath")))
    check("取消换气后弧线回到原位", _arc_apex() == _ap0, f"{_arc_apex()} vs {_ap0}")
    app.append_rest()
    app.sel = len(app.proj["notes"]) - 1
    app.toggle_breath()
    check("休止/延音类格子不能加换气记号",
          not app.proj["notes"][-1].get("breath")
          and app.proj["notes"][-1].get("kind") == pj.KIND_REST,
          str(app.proj["notes"][-1]))

    # ---------------- 整段括号 / 「第 n 结尾」框 ----------------
    print("— 整段括号 / 第 n 结尾框 —")
    app.proj = pj.new_project("框", "D", "D", "4/4", True)
    app.proj["_path"] = None
    app.sel = -1
    app._sel_user = False
    app.autobar_var.set(0)                   # 关自动小节线，数格子方便
    app._meta_changed()
    app.set_state("dur", 1.0)
    app.set_state("octave", 0)
    app.st_dot = False
    app.st_short = False
    app.append_degree(1)
    app.append_degree(2)
    app.append_bracket("start")
    app.append_degree(3)
    app.append_degree(4)
    app.append_bracket("end")
    root.update()
    rn = app.proj["notes"]
    check("整段括号进工程（token 是 （ / ），位置保持追加顺序",
          [pj.token_of(d) for d in rn] == ["1", "2", "（", "3", "4", "）"],
          str([pj.token_of(d) for d in rn]))
    check("括号是记号而不是小节线（kind=bracket，不占时值、不是 bar）",
          rn[2].get("kind") == pj.KIND_BRACKET
          and rn[2].get("direction") == "start"
          and rn[5].get("direction") == "end",
          str(rn[2:6]))

    app.ending_n_var.set("2")
    app.append_ending("start")
    app.append_degree(5)
    app.append_degree(5)
    app.append_ending("end")
    root.update()
    rn = app.proj["notes"]
    check("「第 n 结尾」框按界面上的 n 写入（[2 / 2]，起止都用同一个 n）",
          pj.token_of(rn[6]) == "[2" and pj.token_of(rn[9]) == "2]",
          str([pj.token_of(d) for d in rn]))
    app.ending_n_var.set("xyz")
    check("序号框里填了非数字 => 退回 1（不会写出 [nan）", app._ending_n() == 1,
          app._ending_n())
    app.ending_n_var.set("99")
    check("序号超过 9 => 夹到 9（框子标号就一位数）", app._ending_n() == 9,
          app._ending_n())
    app.ending_n_var.set("1")

    # 框类记号不占时值：自动小节线打开后不会被重排掉，也不会被当成音符
    app.autobar_var.set(1)
    app._meta_changed()
    root.update()
    _shown_f, _imap_f = pj.display_notes(app.proj)
    _tk_f = [pj.token_of(d) for d in _shown_f]
    check("打开自动小节线：两个框类记号都留着",
          _tk_f.count("（") == 1 and _tk_f.count("）") == 1
          and _tk_f.count("[2") == 1 and _tk_f.count("2]") == 1, str(_tk_f))
    _fr_pos = [i for i, d in enumerate(_shown_f) if d.get("kind") in pj.FRAME_KINDS]
    check("框类记号可被选中（映射指向文档下标，不是 None）",
          len(_fr_pos) == 4 and all(_imap_f[i] is not None for i in _fr_pos),
          str([_imap_f[i] for i in _fr_pos]))
    # 画布格子宽度：与导出同一套比例（两处口径必须一致）
    _bw = [(app._cell_map[i][1] - app._cell_map[i][0]) for i, d in enumerate(_shown_f)
           if d.get("kind") == pj.KIND_BRACKET]
    _ew = [(app._cell_map[i][1] - app._cell_map[i][0]) for i, d in enumerate(_shown_f)
           if d.get("kind") == pj.KIND_ENDING]
    check("画布：括号格宽 = CELL_W × BRACKET_CELL_RATIO（与 render 同值）",
          bool(_bw) and all(abs(w - ed.CELL_W * ed.BRACKET_CELL_RATIO) < 1e-6 for w in _bw)
          and abs(ed.BRACKET_CELL_RATIO - render.BRACKET_CELL_RATIO) < 1e-9,
          f"{_bw} vs {ed.CELL_W * ed.BRACKET_CELL_RATIO}")
    check("画布：结尾框格宽 = CELL_W × ENDING_CELL_RATIO（与 render 同值）",
          bool(_ew) and all(abs(w - ed.CELL_W * ed.ENDING_CELL_RATIO) < 1e-6 for w in _ew)
          and abs(ed.ENDING_CELL_RATIO - render.ENDING_CELL_RATIO) < 1e-9,
          f"{_ew} vs {ed.CELL_W * ed.ENDING_CELL_RATIO}")

    # 画布上真的画出了两段括号弧 + 一个结尾框（按属性精确定位，不靠数总数）
    _arcs_c = [i for i in app.score.find_all()
               if app.score.type(i) == "line"
               and app.score.itemcget(i, "fill") == ed.C_TEXT
               and abs(float(app.score.itemcget(i, "width")) - 1.6) < 0.01
               and str(app.score.itemcget(i, "smooth")) in ("1", "true", "True")]
    _en_h = [i for i in app.score.find_all()
             if app.score.type(i) == "line"
             and app.score.itemcget(i, "fill") == ed.C_TEXT
             and abs(float(app.score.itemcget(i, "width")) - 1.4) < 0.01
             and abs(app.score.coords(i)[1] - app.score.coords(i)[3]) < 1e-6
             and abs(app.score.coords(i)[2] - app.score.coords(i)[0]) > 1.0]
    _en_tick = [i for i in app.score.find_all()
                if app.score.type(i) == "line"
                and app.score.itemcget(i, "fill") == ed.C_TEXT
                and abs(float(app.score.itemcget(i, "width")) - 1.4) < 0.01
                and abs(app.score.coords(i)[0] - app.score.coords(i)[2]) < 1e-6]
    _en_lbl = [i for i in app.score.find_all()
               if app.score.type(i) == "text"
               and app.score.itemcget(i, "text") == "2."
               and app.score.itemcget(i, "fill") == ed.C_TEXT]
    _one_txt = [i for i in app.score.find_all()
                if app.score.type(i) == "text"
                and app.score.itemcget(i, "text") == "1"
                and app.score.itemcget(i, "fill") == ed.C_TEXT]
    check("画布：两段括号弧都画出来了", len(_arcs_c) == 2, len(_arcs_c))
    check("画布：结尾框横线 1 条 + 左右短钩 2 条", len(_en_h) == 1 and len(_en_tick) == 2,
          f"横线 {len(_en_h)} / 短钩 {len(_en_tick)}")
    check("画布：标号「2.」画在横线下方左端", len(_en_lbl) == 1, len(_en_lbl))
    check("画布：框类记号那一格自己不画笔画（没落到音符分支画成「1」）",
          len(_one_txt) == 1, f"{len(_one_txt)} 个「1」")

    _disp_of_doc = {d: i for i, d in enumerate(_imap_f) if d is not None}
    _y0_row = ed.SCORE_TOP + ed._ENDING_TOP
    if len(_arcs_c) == 2:
        # 每段弧的「锚点」= 贴着格子边的那一端：左括号看最左点、右括号看最右点
        # （弧是向外鼓的，另一头要再鼓出 BRACKET_BULGE）
        _arc_span = sorted((min(app.score.coords(i)[0::2]),
                            max(app.score.coords(i)[0::2])) for i in _arcs_c)
        _b0 = app._cell_map[_disp_of_doc[2]]
        _b1 = app._cell_map[_disp_of_doc[5]]
        check("画布：左括号贴在起点格左缘、右括号贴在终点格右缘",
              abs(_arc_span[0][0] - _b0[0]) < 1.0 and abs(_arc_span[1][1] - _b1[1]) < 1.0,
              f"弧 {_arc_span} vs 起点格左 {_b0[0]} / 终点格右 {_b1[1]}")
        check("画布：括号向外鼓出 BRACKET_BULGE（不会越过格子边线）",
              abs((_arc_span[0][1] - _arc_span[0][0]) - ed.BRACKET_BULGE) < 1.0
              and abs((_arc_span[1][1] - _arc_span[1][0]) - ed.BRACKET_BULGE) < 1.0,
              str(_arc_span))
        _tops = sorted(app.score.coords(i)[1] for i in _arcs_c)
        check("画布：括号高度与数字齐平（上端略高于数字字形顶）",
              abs(_tops[0] - (_y0_row + ed.DIGIT_TOP - ed.BRACKET_UP)) < 1.0,
              f"弧顶 {_tops[0]} vs {_y0_row + ed.DIGIT_TOP - ed.BRACKET_UP}")
    if _en_h:
        _ex = app.score.coords(_en_h[0])
        check("画布：结尾框横线画在行顶**上方**（负方向的让位）",
              _ex[1] < _y0_row, f"横线 y={_ex[1]} 行顶 {_y0_row}")
        check("画布：结尾框横线盖住整段（从起点格左缘到终点格右缘）",
              abs(_ex[0] - app._cell_map[_disp_of_doc[6]][0]) < 1.0
              and abs(_ex[2] - app._cell_map[_disp_of_doc[9]][1]) < 1.0,
              f"{_ex[0]}..{_ex[2]} vs {app._cell_map[_disp_of_doc[6]][0]}"
              f"..{app._cell_map[_disp_of_doc[9]][1]}")
        check("画布：横线落在画布可视区内（没被画到外面去）", _ex[1] >= 0, _ex[1])
        check("画布：横线压在记号区之上（比数字字形顶还高）",
              _ex[1] < _y0_row + ed.DIGIT_TOP, f"{_ex[1]} vs {_y0_row + ed.DIGIT_TOP}")

    # 让位量：画布顶部原来那点余量吃不下的极端情形才额外让（不然白占高度）
    _plain_docs = [pj.token_to_doc(t) for t in "1 2 3 4 [1 5 5 5 5 1] :|".split()]
    _deep_txt = "1 2 3 4 [1 1( 2( 3( 4( 5 4) 3) 2) 1) 1] :|"
    _deep_docs = [pj.token_to_doc(t) for t in _deep_txt.split()]
    check("画布让位量：朴素结尾框不用额外留白（行顶原有的余量就够）",
          ed.frame_top_need(_plain_docs) == 0.0, ed.frame_top_need(_plain_docs))
    check("画布让位量：四层嵌套连音压上来时才开始让白",
          ed.frame_top_need(_deep_docs) > 0, ed.frame_top_need(_deep_docs))
    check("画布让位量：没有结尾框时恒为 0",
          ed.frame_top_need([pj.token_to_doc(t) for t in "1 2 3 4".split()]) == 0.0)
    _env0 = ed._ENDING_TOP
    ed._ENDING_TOP = 0
    _h0 = ed.score_content_h()
    ed._ENDING_TOP = 34
    _h1 = ed.score_content_h()
    ed._ENDING_TOP = _env0
    check("画布高度把结尾框的让位量算进去了（不然框子会被裁掉）", _h1 - _h0 == 34,
          f"{_h1} - {_h0}")

    # 属性条：选中框类记号时说明文字要对（不然用户不知道点到了什么）
    app.sel = 2
    app._refresh_info()
    check("属性条认得出整段括号", "整段括号" in app.mark_lbl.cget("text"),
          app.mark_lbl.cget("text"))
    app.sel = 6
    app._refresh_info()
    check("属性条认得出「第 n 结尾」框（含序号）",
          "第 2 结尾框" in app.mark_lbl.cget("text"), app.mark_lbl.cget("text"))
    app.sel = -1

    # 撤销 / 重做
    app.undo()
    root.update()
    check("撤销能收回刚加的结尾框终点",
          "2]" not in [pj.token_of(d) for d in app.proj["notes"]],
          str([pj.token_of(d) for d in app.proj["notes"]]))
    app.redo()
    root.update()
    check("重做能把结尾框终点放回来",
          "2]" in [pj.token_of(d) for d in app.proj["notes"]],
          str([pj.token_of(d) for d in app.proj["notes"]]))

    # 整谱预览：框子也要跟着预览画出来（预览 = 主画布画法 + 导出版式）
    app._sync_project_meta()
    app.open_page_preview()
    root.update()
    check("整谱预览窗口开起来了", app._page_win is not None)
    if app._page_win is not None:
        _pv = app._page_cv
        _pv_lbl = [i for i in _pv.find_all() if _pv.type(i) == "text"
                   and _pv.itemcget(i, "text") == "2."]
        _pv_tick = [i for i in _pv.find_all() if _pv.type(i) == "line"
                    and _pv.itemcget(i, "fill") == ed.C_TEXT
                    and abs(_pv.coords(i)[0] - _pv.coords(i)[2]) < 1e-6]
        check("预览里也画了结尾框标号「2.」", len(_pv_lbl) == 1, len(_pv_lbl))
        check("预览里结尾框的左右短钩也在", len(_pv_tick) == 2, len(_pv_tick))
        app._close_page_preview()
    root.update()

    print("— 键盘编谱（键位 = 那排简谱按钮）—")
    # 多个 EditorApp 共用同一个 root，后建者覆盖键盘绑定 → 这个必须最后建
    appf = ed.EditorApp(root)
    # 键事件只有窗口可见时才送到控件上（withdraw 状态下 event_generate 不触发绑定），
    # 所以这一段先把窗口显示出来，量完再收回去。
    root.deiconify()
    root.update()
    appf.proj = pj.new_project("键盘测试", "D", "D", "4/4", True)
    appf.proj["_path"] = None
    appf.sel = -1
    appf._sel_user = False
    appf.set_state("dur", 1.0)
    appf.set_state("octave", 0)
    appf.st_dot = False
    appf.st_short = False
    appf.autobar_var.set(0)                  # 关自动小节线，数音方便
    appf._meta_changed()
    root.update()

    def press(seq):
        root.event_generate(seq, when="now")
        root.update()

    press("<KeyPress-1>")
    press("<KeyPress-2>")
    press("<KeyPress-7>")
    check("数字键 1/2/7 加音", toks(appf) == ["1", "2", "7"], str(toks(appf)))
    press("<KeyPress-x>")
    press("<KeyPress-5>")
    check("x 键切高八度后数字键加高八度音",
          pj.token_of(appf.proj["notes"][-1]) == "5'", pj.token_of(appf.proj["notes"][-1]))
    press("<KeyPress-z>")
    press("<KeyPress-s>")
    press("<KeyPress-5>")
    check("s 键升号后数字键加升号音",
          pj.token_of(appf.proj["notes"][-1]) == "#5", pj.token_of(appf.proj["notes"][-1]))
    press("<KeyPress-s>")
    press("<KeyPress-d>")
    press("<KeyPress-5>")
    check("d 键降号后数字键加降号音",
          pj.token_of(appf.proj["notes"][-1]) == "b5", pj.token_of(appf.proj["notes"][-1]))
    press("<KeyPress-d>")
    press("<KeyPress-q>")
    press("<KeyPress-3>")
    check("q 键=四分音符", appf.proj["notes"][-1]["duration"] == 1.0)
    press("<KeyPress-w>")
    press("<KeyPress-3>")
    check("w 键=八分音符", appf.proj["notes"][-1]["duration"] == 0.5)
    press("<KeyPress-e>")
    press("<KeyPress-3>")
    check("e 键=十六分音符", appf.proj["notes"][-1]["duration"] == 0.25)
    press("<KeyPress-q>")
    press("<KeyPress-equal>")
    check("= 键切附点（按钮上就写着 (=)）", appf.st_dot is True)
    press("<KeyPress-equal>")
    check("再按 = 取消附点", appf.st_dot is False)
    press("<KeyPress-0>")
    check("0 键加休止", appf.proj["notes"][-1]["kind"] == pj.KIND_REST)
    press("<KeyPress-minus>")
    check("- 键加延音", appf.proj["notes"][-1]["kind"] == pj.KIND_HOLD)
    press("<KeyPress-bar>")
    check("| 键加小节线", appf.proj["notes"][-1]["kind"] == pj.KIND_BAR)
    # 框类记号键位：( ) 整段括号起止、Alt+[ / Alt+] 第 n 结尾框起止
    press("<KeyPress-parenleft>")
    check("( 键加整段括号起点", pj.token_of(appf.proj["notes"][-1]) == "（",
          pj.token_of(appf.proj["notes"][-1]))
    press("<KeyPress-parenright>")
    check(") 键加整段括号终点", pj.token_of(appf.proj["notes"][-1]) == "）",
          pj.token_of(appf.proj["notes"][-1]))
    appf.ending_n_var.set("3")
    press("<Alt-KeyPress-bracketleft>")
    check("Alt+[ 按界面上的 n 加结尾框起点（[3）",
          pj.token_of(appf.proj["notes"][-1]) == "[3",
          pj.token_of(appf.proj["notes"][-1]))
    press("<Alt-KeyPress-bracketright>")
    check("Alt+] 加结尾框终点（3]）",
          pj.token_of(appf.proj["notes"][-1]) == "3]",
          pj.token_of(appf.proj["notes"][-1]))
    appf.ending_n_var.set("1")
    n_all = len(appf.proj["notes"])
    appf.sel = n_all - 1
    press("<KeyPress-Left>")
    check("← 键选上一个", appf.sel == n_all - 2, f"{appf.sel} / {n_all}")
    press("<KeyPress-Right>")
    check("→ 键选下一个", appf.sel == n_all - 1, appf.sel)
    press("<KeyPress-Delete>")
    check("Del 键删除选中（小节线）", len(appf.proj["notes"]) == n_all - 1)
    # 焦点在输入框里时，全局快捷键必须让路（否则往歌词框打「5」会顺手插一个音）
    real_fg = root.focus_get
    root.focus_get = lambda: appf.lyric_box
    check("_typing 认出输入框", appf._typing() is True)
    n_before = len(appf.proj["notes"])
    press("<KeyPress-5>")
    check("焦点在歌词框里：数字键不插音", len(appf.proj["notes"]) == n_before)

    class _FakeCanvas:
        def winfo_class(self):
            return "Canvas"

    root.focus_get = lambda: _FakeCanvas()
    check("_typing 对非输入控件返回假", appf._typing() is False)
    press("<KeyPress-5>")
    check("焦点不在输入框：数字键正常插音", len(appf.proj["notes"]) == n_before + 1)
    root.focus_get = real_fg
    # 键位都标在按钮 / 说明里，不用记
    def _all_texts(w):
        out = []
        for ch in w.winfo_children():
            try:
                t = ch.cget("text")
            except tk.TclError:
                t = None
            if not t and isinstance(ch, tk.Text):     # Text 的内容 cget("text") 取不到
                t = ch.get("1.0", "end")
            if t:
                out.append(str(t))
            out.extend(_all_texts(ch))
        return out

    labels = _all_texts(root)
    for frag in ("♯ s", "♭ d", "低 z", "高 x", "四分 q", "八分 w", "十六 e"):
        check(f"按钮上标了键位「{frag}」", frag in labels, str(labels[:14]))
    check("附点按钮标了键位 =", any("附点(=" in t for t in labels),
          str([t for t in labels if "附点" in t]))
    check("切音按钮标了键位 t", any("切音(t" in t for t in labels),
          str([t for t in labels if "切音" in t]))
    # 键盘说明**不再贴在主界面上**：那段文字排下来要 106px，而谱面区光装下整个格子
    # 就要 258px —— 贴在面板里就只能把谱面区挤瘦、笛身与音名被下边缘裁掉。
    # 现在改成「键盘说明」弹窗，内容一字未减。
    _KEY_FRAGS = ("q / w / e 四分", "[ ] 连音线起止", "整段括号起止", "F5 整谱预览",
                  "p 试听选中的音")

    def _has_all(texts):
        return any(all(f in t for f in _KEY_FRAGS) for t in texts)

    check("键盘说明没有占用主界面的高度", not _has_all(labels))
    appf.show_key_help()
    root.update_idletasks()
    check("「键盘说明」弹出独立窗口", isinstance(appf._key_win, tk.Toplevel)
          and bool(appf._key_win.winfo_exists()))
    check("键盘说明列出全部键位", _has_all(_all_texts(appf._key_win)),
          str([t[:40] for t in _all_texts(appf._key_win)]))
    appf.show_key_help()                     # 重复点不该开出一堆同样的窗
    check("重复点「键盘说明」只开一个窗",
          len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]) == 1,
          str([type(w).__name__ for w in root.winfo_children()]))
    # 弹窗也是 root 的子控件，但它自成窗口、不占主界面高度：
    # 谱面区高度上限的计算不能把它算进去（曾经因此直接把 AttributeError 抛出来）
    check("开着弹窗也能算出谱面区高度上限",
          appf._score_height_limit() >= ed.SCORE_MIN_H, appf._score_height_limit())
    appf._key_win.destroy()
    root.update_idletasks()
    for seq in ("1", "7", "0", "-", "<KeyPress-bar>", "q", "w", "e", "=", "s", "d", "z", "x",
                "<KeyPress-t>", "<KeyPress-bracketleft>", "<KeyPress-bracketright>",
                "<KeyPress-backslash>", "<KeyPress-parenleft>", "<KeyPress-parenright>",
                "<Alt-KeyPress-bracketleft>", "<Alt-KeyPress-bracketright>",
                "<Left>", "<Right>", "<Delete>", "<Control-l>", "<F5>",
                "<KeyPress-p>", "<Control-p>"):
        check(f"键位 {seq} 已绑定", bool(root.bind(seq)), str(root.bind(seq)))
    root.withdraw()
    root.update()

    print("— 竖线光标 —")
    # 光标要求：不开插入模式时是**竖线光标**（不是整格方框），而且必须与小节线区分开
    root4 = tk.Tk()
    root4.withdraw()
    appcar = ed.EditorApp(root4)
    appcar.proj["notes"] = [pj.token_to_doc(t) for t in ("5", "6", "7", "1")]
    appcar.sel = -1
    appcar._sel_user = False
    appcar.ins_before.set(0)                 # 不开插入模式
    appcar.redraw_all()
    root4.update()
    cvc = appcar.score

    def _lines_of(cv, color):
        out = []
        for i in cv.find_all():
            if cv.type(i) == "line" and cv.itemcget(i, "fill") == color:
                out.append(cv.coords(i))
        return out

    caret_v = [c for c in _lines_of(cvc, ed.C_CARET) if abs(c[0] - c[2]) < 0.01]
    caret_h = [c for c in _lines_of(cvc, ed.C_CARET) if abs(c[1] - c[3]) < 0.01]
    check("选中区画出了竖线光标", len(caret_v) == 1, str(caret_v))
    check("光标两端有横帽（I 形，一眼区别于小节线）", len(caret_h) == 2, str(caret_h))
    check("光标颜色与小节线不同",
          ed.C_CARET != "#8a949c" and ed.C_CARET.upper() != "#999999".upper())
    if caret_v:
        _cx = caret_v[0][0]
        check("不开插入模式：光标落在曲末（最后一个音右边）",
              abs(_cx - appcar._cell_map[-1][1]) < 0.01,
              f"{_cx} vs {appcar._cell_map[-1][1]}")
    check("光标比小节线粗", ed.CARET_W > 1.4)
    # 小节线是灰色细线、没有横帽
    gray = [(i, cvc.coords(i)) for i in cvc.find_all()
            if cvc.type(i) == "line" and cvc.itemcget(i, "fill") == "#8a949c"]
    check("小节线仍是灰色细竖线（没被光标顶掉）", len(gray) >= 1, str(len(gray)))
    check("小节线没有横帽",
          all(abs(c[0] - c[2]) < 0.01 for _i, c in gray))
    # 高度对齐数字：谱面画布是 1:1（s=1），所以竖线长度就该等于数字字形高度，
    # 而不是原来一路拉到笛身的 142px。
    _want_h = ed.DIGIT_BOT - ed.DIGIT_TOP
    check("小节线高度 = 数字高度（不再拉到笛身）",
          bool(gray) and all(abs((c[3] - c[1]) - _want_h) < 0.01 for _i, c in gray),
          f"期望 {_want_h}px，实得 {[round(c[3] - c[1], 1) for _i, c in gray]}")
    check("数字高度常量自洽（DIGIT_BOT-DIGIT_TOP = DIGIT_H，且远小于 CELL_H）",
          abs(_want_h - ed.DIGIT_H) < 1e-9 and _want_h < ed.CELL_H,
          f"{ed.DIGIT_TOP}..{ed.DIGIT_BOT}")
    # 反复记号的竖线用同一对常量（否则两种竖线会一高一矮）
    cvtmp = tk.Canvas(root4)
    ed.draw_repeat(cvtmp, 40, 30, pj.token_to_doc("|:"), 1.0)
    _rep_lines = _lines_of(cvtmp, "#8a949c")
    check("反复记号的竖线高度与小节线一致",
          len(_rep_lines) == 1 and abs((_rep_lines[0][3] - _rep_lines[0][1]) - _want_h) < 0.01,
          str(_rep_lines))
    cvtmp.destroy()

    # 延音横线「-」：**定长 + 居中 + 对准数字墨迹中心**。口径与 render._simple_cell 的
    # hold 分支成对（画布格子定宽 60，导出那边列距是自适应压出来的 —— 横线一旦跟格宽走，
    # 同一份谱两处长短就不一样）。这里用两种格宽画同一格，锁住「不跟格宽变」。
    for _w in (ed.CELL_W, ed.CELL_W + ed.BAR_EXTRA_W):
        cvhold = tk.Canvas(root4)
        ed.draw_cell(cvhold, 40, 30, pj.token_to_doc("-"), "D", "D", 1.0, w=_w)
        _hd = _lines_of(cvhold, ed.C_TEXT)
        check(f"延音横线：格宽 {_w} 时仍是定长 HOLD_W、水平居中于本格",
              len(_hd) == 1
              and abs((_hd[0][2] - _hd[0][0]) - ed.HOLD_W) < 0.01
              and abs((_hd[0][0] + _hd[0][2]) / 2 - (40 + _w / 2)) < 0.01,
              str(_hd))
        check(f"延音横线：格宽 {_w} 时竖向对准数字墨迹中心（行顶 + DIGIT_INK_CY）",
              bool(_hd) and abs(_hd[0][1] - (30 + ed.DIGIT_INK_CY)) < 0.01, str(_hd))
        cvhold.destroy()
    check("延音横线常量与导出成对（画布数字小一号 → HOLD_W 也跟着小 1px）",
          ed.HOLD_W == round(render.HOLD_W * ed.DIGIT_H / render.NOTE_ASCENT),
          f"editor {ed.HOLD_W} vs render {render.HOLD_W}")

    # 开了插入模式 → 光标移到选中格的左边缘
    appcar.ins_before.set(1)
    appcar.sel = 2
    appcar._sel_user = True
    appcar.redraw_all()
    root4.update()
    caret_v2 = [c for c in _lines_of(appcar.score, ed.C_CARET) if abs(c[0] - c[2]) < 0.01]
    check("开插入模式：光标移到选中格左边缘",
          len(caret_v2) == 1 and abs(caret_v2[0][0] - appcar._cell_map[2][0]) < 0.01,
          f"{caret_v2} vs cell_left={appcar._cell_map[2][0]}")
    # 选中音只剩一层淡底色（原来的整格方框已经去掉）
    _sel_rects = [i for i in appcar.score.find_all()
                  if appcar.score.type(i) == "rectangle"
                  and appcar.score.itemcget(i, "fill") == ed.C_SEL]
    check("选中音用淡底色标记（不再是整格方框）",
          len(_sel_rects) >= 1
          and all(not appcar.score.itemcget(i, "outline") for i in _sel_rects),
          str([appcar.score.itemcget(i, "outline") for i in _sel_rects]))
    # 空工程也要能画光标（起笔处）
    appcar.proj["notes"] = []
    appcar.redraw_all()
    root4.update()
    check("空工程画布不报错且没有多余光标",
          appcar._caret_x(10.0) == 10.0)

    print("— 输出设置（纸张 / 水印 / 谱面大小 / 倍率）—")
    appcar.proj["notes"] = [pj.token_to_doc(t) for t in ("5", "6", "7", "1")]
    appcar.paper_var.set("B4")
    appcar.watermark_var.set("测试水印")
    appcar.scale_var.set("2")
    appcar.content_scale_var.set("85")
    appcar._sync_project_meta()
    check("纸张同步进工程", appcar.proj["paper"] == "B4", appcar.proj.get("paper"))
    check("水印同步进工程", appcar.proj["watermark"] == "测试水印")
    check("倍率同步进工程", appcar.proj["scale"] == 2, appcar.proj.get("scale"))
    check("谱面大小同步进工程（85% -> 0.85）",
          abs(appcar.proj["content_scale"] - 0.85) < 1e-9,
          str(appcar.proj.get("content_scale")))
    # 倍率上限提到 5x：1x~5x 都在线，越界（6x 起）才退回默认 1x
    check("倍率档位是 1x~5x", tuple(ed.imageout.SIZES) == (1, 2, 3, 4, 5),
          str(ed.imageout.SIZES))
    appcar.scale_var.set("3")
    appcar._sync_project_meta()
    check("3x 在线（倍率上限提到 5x）", appcar.proj["scale"] == 3,
          str(appcar.proj.get("scale")))
    appcar.scale_var.set("5")
    appcar._sync_project_meta()
    check("5x 在线（最高档）", appcar.proj["scale"] == 5, str(appcar.proj.get("scale")))
    appcar.scale_var.set("9")
    appcar._sync_project_meta()
    check("超过 5x 的非法倍率退回默认", appcar.proj["scale"] == ed.imageout.DEFAULT_SCALE,
          str(appcar.proj.get("scale")))
    # 谱面大小越界夹住、非法退回默认 65%
    appcar.content_scale_var.set("9")
    appcar._sync_project_meta()
    check("谱面大小越界夹到 50%", abs(appcar.proj["content_scale"] - 0.5) < 1e-9,
          str(appcar.proj.get("content_scale")))
    appcar.content_scale_var.set("")
    appcar._sync_project_meta()
    check("谱面大小留空退回默认 65%",
          abs(appcar.proj["content_scale"] - ed.render.DEFAULT_CONTENT_SCALE) < 1e-9,
          str(appcar.proj.get("content_scale")))

    _pdir = os.path.join(out_dir, "outset")
    appcar.title_var.set("输出设置用例")
    appcar.scale_var.set("1")
    appcar.content_scale_var.set("70")
    appcar._sync_project_meta()
    appcar.proj["notes"] = [pj.token_to_doc(t) for t in (" ".join(["5 6 7 1"] * 60)).split()]
    _paths = pj.export_svg_pages(appcar.proj, _pdir, paper=appcar.paper_var.get(),
                                 watermark=appcar.watermark_var.get())
    check("按设置导出成多页多文件", len(_paths) > 1
          and _paths[0].endswith("-1.svg"), str([os.path.basename(p) for p in _paths]))
    _t0 = open(_paths[0], encoding="utf-8").read()
    check("导出用了界面上的纸张", 'data-paper="B4"' in _t0, _t0[:120])
    check("导出用了界面上的水印", "测试水印" in _t0)
    _reload = pj.load(pj.save(appcar.proj, os.path.join(_pdir, "o.json")))
    appcar._load_project(_reload, path=None)
    root4.update()
    check("重新打开工程后纸张/水印/谱面大小/倍率回来了",
          appcar.paper_var.get() == "B4" and appcar.watermark_var.get() == "测试水印"
          and appcar.scale_var.get() == "1" and appcar.content_scale_var.get() == "70",
          f"{appcar.paper_var.get()} / {appcar.watermark_var.get()} / "
          f"{appcar.content_scale_var.get()} / {appcar.scale_var.get()}")
    # 预览窗口按分页摊开，并且与导出口径一致（谱面大小写进信息栏）
    appcar.open_page_preview()
    root4.update()
    check("预览窗口按分页铺开（页数写进信息栏）",
          "页" in appcar._page_info.cget("text"), appcar._page_info.cget("text"))
    check("预览信息栏标出谱面大小（70%）",
          "谱面 70%" in appcar._page_info.cget("text"),
          appcar._page_info.cget("text"))
    # 预览画完必须把 render 的缩放还原：否则后面直调 render 的代码会莫名其妙按 70% 出图
    check("预览画完还原 render 的谱面大小（无副作用）",
          abs(ed.render.CONTENT_SCALE - 1.0) < 1e-9
          and abs(ed.render.NOTE_SIZE - 26) < 1e-9,
          f"{ed.render.CONTENT_SCALE} / {ed.render.NOTE_SIZE}")
    # 预览里的行数应当与导出同口径：按**当前纸张**和**谱面大小**算容量
    # （这里纸张是 B4，比 A4 高，70% 时首页 6 行而不是 5 行）
    _pv_cs = ed.render.normalize_content_scale(appcar.content_scale_var.get())
    _pv_rowh = (ed.render.ROW_H + ed.render.ROW_GAP) * _pv_cs       # 无歌词
    _pv_cap = int((ed.render.PAGE_HEIGHT - ed.render.HEADER_H
                   - ed.render.FOOTER_H) // _pv_rowh)
    _pv_rows = len(ed.render.page_rows(0))
    check("预览的每页行数与导出同口径（按纸张+谱面大小算容量）",
          _pv_rows == _pv_cap, f"首页 {_pv_rows} 行；容量 {_pv_cap}；N_PAGES={ed.render.N_PAGES}")
    appcar._close_page_preview()
    root4.destroy()

    print("— 大工程：批量 set 与进度条 —")
    # 打开工程时十几个控件连着 set，每个都挂了 trace（→ redraw_all）。
    # 不屏蔽的话，1200 个音的谱面重画十几次就是「打开大工程卡住」的一大半。
    _big = pj.new_project("大工程", "D", "D", "4/4", True)
    _big["notes"] = [pj.token_to_doc(t)
                     for t in "5 6 1' 2' 3' 2' 1' 6 | 5 3 2 1 - 0".split()]
    _big["paper"] = "A4"
    _big["watermark"] = "批量"
    _big["scale"] = 2
    _big["content_scale"] = 0.7
    _big["row_measures"] = 4
    _count = {"n": 0}
    _orig_redraw = app.redraw_all
    app.redraw_all = lambda *_a, **_k: _count.__setitem__("n", _count["n"] + 1)
    try:
        app._load_project(_big, path=None)
    finally:
        app.redraw_all = _orig_redraw
    root.update()
    check("打开工程只重画一次（trace 不再逐个触发）", _count["n"] == 1, _count["n"])
    check("批量 set 后字段没有被旧控件值盖掉",
          app.paper_var.get() == "A4" and app.watermark_var.get() == "批量"
          and app.scale_var.get() == "2" and app.content_scale_var.get() == "70"
          and app.rowmeas_var.get() == "4",
          f"{app.paper_var.get()} / {app.watermark_var.get()} / "
          f"{app.scale_var.get()} / {app.content_scale_var.get()} / "
          f"{app.rowmeas_var.get()}")
    check("_bulk_set 用完就还原（后面的编辑照常重画）", app._bulk_set is False)

    # 进度条弹窗：短活不弹（小工程不该闪一下），到点才弹，取消按钮能置位
    dlg = ed.BusyDialog(root, "自测进度", cancelable=True)
    dlg.report(3, 10, "写入 3/10 个音")
    dlg.pump()
    check("不到 300ms 不弹窗（小工程不闪一下）", dlg._shown is False and dlg._win is None)
    dlg._t0 = time.monotonic() - 1.0          # 假装已经干了一秒
    dlg.pump()
    check("干久了才弹窗", dlg._win is not None and dlg._shown)
    dlg.pump()
    check("进度条按 done/total 推进",
          abs(float(dlg._bar.cget("value")) - 30.0) < 1e-6, dlg._bar.cget("value"))
    check("百分比写进标签", "30%" in dlg._lbl.cget("text"), dlg._lbl.cget("text"))
    dlg.report(0, 0, "排版中")
    dlg.pump()
    check("总数未定走不确定模式", dlg._indet is True and dlg._lbl.cget("text") == "排版中")
    dlg._on_cancel()
    check("取消按钮把 canceled 置真", dlg.canceled() is True)
    dlg.close()
    check("关掉后窗口收干净", dlg._win is None and dlg._shown is False)

    # _run_busy：活在工作线程里跑，回调回主线程（tk 不是线程安全的）
    def _wait(cond, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            root.update()
            if cond():
                return True
            time.sleep(0.01)
        return False

    _box = {}

    def _work(progress, cancel):
        for i in range(5):
            progress(i + 1, 5, f"第 {i + 1}/5 页")
            time.sleep(0.02)
        return 42

    def _done(value, canceled):
        _box["value"] = value
        _box["thread"] = threading.current_thread().name
        _box["canceled"] = canceled

    app._run_busy("自测", _work, _done)
    check("_run_busy 能在没有 mainloop 的情况下跑完（靠 after 泵）",
          _wait(lambda: "value" in _box), str(_box))
    check("返回值带回主线程", _box.get("value") == 42, str(_box))
    check("回调在主线程里跑（不在工作线程里动控件）",
          _box.get("thread") == threading.main_thread().name, _box.get("thread"))
    check("没点取消就是没取消", _box.get("canceled") is False, str(_box))

    # 取消：点了「取消」之后 work 自己停下来，on_done 仍会收到已完成的成果
    _made = []
    _OrigDlg = ed.BusyDialog

    class _SpyDlg(_OrigDlg):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            _made.append(self)

    _box2 = {}

    def _work2(progress, cancel):
        n = 0
        while not cancel() and n < 200:
            n += 1
            time.sleep(0.01)
        return n

    def _done2(value, canceled):
        _box2["value"] = value
        _box2["canceled"] = canceled

    ed.BusyDialog = _SpyDlg
    try:
        app._run_busy("自测取消", _work2, _done2, cancelable=True)
        _wait(lambda: _made and _made[0]._shown)
        _made[0]._on_cancel()
        check("点了取消能把活停下来", _wait(lambda: "value" in _box2), str(_box2))
    finally:
        ed.BusyDialog = _OrigDlg
    check("取消后仍拿得到已完成的部分", (_box2.get("value") or 0) > 0, str(_box2))
    check("canceled 传给了回调", _box2.get("canceled") is True, str(_box2))

    # 「打开工程」真的走这条通道（不再在主线程里硬读盘）
    # 存盘的工程**刻意换个曲名**：on_done 是把 proj 换掉的那一步，等「曲名变成打开回来的」
    # 才算真加载完 —— 用跟当前工程一样的名字去等会立刻通过，后面的用例就被这条异步尾巴
    # 换掉 proj（试听用例曾因此拿到 13 个音的老谱）。
    _opath = os.path.join(out_dir, "open_me.json")
    _op = pj.new_project("打开回来的", "D", "D", "4/4", True)
    _op["notes"] = _big["notes"]
    pj.save(_op, _opath)
    ed.filedialog.askopenfilename = lambda *a, **k: _opath
    _seen = []
    _orig_run = app._run_busy

    def _spy_run(title, work, on_done=None, **kw):
        _seen.append(title)
        return _orig_run(title, work, on_done, **kw)

    app._run_busy = _spy_run
    try:
        app.open_project()
        _wait(lambda: app.proj.get("title") == "打开回来的")
    finally:
        app._run_busy = _orig_run
    check("打开工程走「工作线程 + 进度条」通道",
          _seen == ["正在打开工程"], str(_seen))
    check("打开后谱面真的进来了",
          len(app.proj["notes"]) == len(_big["notes"]), len(app.proj["notes"]))

    print("— 试听（合成音色）—")
    # 桩里记下每次发声 (hz, ms)；播放是工作线程在数时间，所以断言前先等它安静下来。
    # 「选中即试听」的上下限临时调小：否则每个音要真占 600ms，这一屏用例要干等好几秒
    # （真实听感不用动 —— 这只是测试里的等待成本）。
    _pmin, _pmax = ed.sound.PREVIEW_MIN_MS, ed.sound.PREVIEW_MAX_MS
    ed.sound.PREVIEW_MIN_MS, ed.sound.PREVIEW_MAX_MS = 60, 120

    def beeps_quiet(timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            root.update()
            if not app.beeper.busy():
                return True
            time.sleep(0.02)
        return False

    app.proj["notes"] = [pj.token_to_doc(t) for t in ("1", "3", "0")]
    for _d in app.proj["notes"]:
        _d["duration"] = 1.0
    # 试听默认**关**（用户要求：打开程序别自己响）。打开开关那一刻会响一声确认音，
    # 所以先把选中清掉再开，免得污染下面几条的计数。
    check("试听开关默认是关的", app.listen_var.get() is False, str(app.listen_var.get()))
    app.sel = -1
    app.listen_var.set(True)
    TONES.clear()
    # 没有选中音（sel=-1，光标停在曲末）时一声都别响 —— 试听是「选中即响」，不是「重画即响」
    app.sel = -1
    app._listen_sel = -2
    app.redraw_all()
    check("没选中任何音时不响", beeps_quiet() and not TONES, str(TONES))
    app.sel = 0
    app._listen_sel = -2                 # 假装上一次响的是别处，逼它重新响一次
    app.redraw_all()
    check("选中一个音就响一下（1=D4 → 294Hz）",
          beeps_quiet() and len(TONES) == 1 and TONES[-1][0] == 294, str(TONES))
    app.redraw_all()
    check("同一个音不会反复响（重画不叠加）", len(TONES) == 1, str(TONES))
    app.sel = 1
    app.redraw_all()
    check("换一个音会再响，音高跟着走（3=F#4 → 370Hz）",
          beeps_quiet() and len(TONES) == 2 and TONES[-1][0] == 370, str(TONES))
    app.sel = 2
    app.redraw_all()
    check("休止符不响（没音高可响）", beeps_quiet() and len(TONES) == 2, str(TONES))
    app.listen_var.set(False)
    app.sel = 0
    app.redraw_all()
    check("关掉「选中即试听」就不响", beeps_quiet() and len(TONES) == 2, str(TONES))
    app.listen_var.set(True)
    check("重新打开开关会响一下确认听得见", beeps_quiet() and len(TONES) == 3, str(TONES))

    # 整首试听：提交的是「按谱面时值排好的节目单」，并且能随时停
    _submitted = []
    _orig_submit = app.beeper.submit

    def _spy_submit(program, on_step=None):
        _submitted.append(list(program))
        return _orig_submit(program, on_step)

    app.beeper.submit = _spy_submit
    try:
        app.play_tune()
    finally:
        app.beeper.submit = _orig_submit
    check("整首试听提交了一份节目单",
          len(_submitted) == 1 and len(_submitted[0]) == 3, str(_submitted))
    if _submitted:
        got = [(hz, round(ms)) for hz, ms, _i in _submitted[0]]
        check("节目单按谱面时值排（80bpm → 四分 750ms，休止静音）",
              got == [(294, 750), (370, 750), (None, 750)], str(got))
    gen = app._tune_gen
    app._follow_tune(gen, 1)
    check("试听时选中框跟着正在响的音走", app.sel == 1, app.sel)
    app._follow_tune(gen + 99, 0)         # 已经停掉的那一次的回调
    check("停掉之后旧的回调不再动选中框", app.sel == 1, app.sel)
    app.stop_audio()
    check("停止试听后安静下来", beeps_quiet(), "还在响")

    # 用户报的核心毛病：**按了「■」还在响**。以前用阻塞的 `Beep`，这一个音必须放完
    # 才轮得上去看停止标记（长音要等满 TUNE_MAX_MS=3000），听着就是「按钮没用」。
    # 现在掐音是 `stop()` 在主线程里当场做的，这里要钉住：它不仅停得快，而且**后面不再出声**。
    app.bpm_var.set("80")
    app.proj["notes"] = [pj.token_to_doc(t) for t in ("1", "2", "3", "4", "5", "6")]
    for _d in app.proj["notes"]:
        _d["duration"] = 2.0            # 80bpm → 每个音 1.5 秒（拿长音才测得出来）
    TONES.clear()
    STOPS.clear()
    app.play_tune()
    _wait(lambda: len(TONES) >= 1, 3.0)
    check("长音已经在响（用例前提成立）", len(TONES) == 1, str(TONES))
    app.stop_audio()
    check("按 ■ 立刻掐音（不用等这个音放完）", len(STOPS) >= 1, str(STOPS))
    check("状态栏写明已停止", app.status.cget("text") == "已停止试听",
          app.status.cget("text"))
    _wait(lambda: not app.beeper.busy(), 2.0)     # 播放线程也该收工了
    check("停止后播放线程收工", not app.beeper.busy())
    time.sleep(0.8)                               # 剩下五个音本来会接二连三地响出来
    for _ in range(20):
        root.update()
    check("停止之后一个音都不再响", len(TONES) == 1, str(TONES))

    # 打开工程不该顺手「叮」一声（加载时把「上次响过的音」设成当前选中，见 _load_project）
    ed.sound.PREVIEW_MIN_MS, ed.sound.PREVIEW_MAX_MS = _pmin, _pmax
    app.bpm_var.set("80")
    TONES.clear()
    app._load_project(pj.new_project("载入不响", "D", "D", "4/4", True), path=None)
    root.update()
    check("打开工程不会顺手响一声", not TONES, str(TONES))

    print("— 空工程边界 —")
    app2 = ed.EditorApp(root)
    app2.proj["notes"] = []
    app2.redraw_all()
    check("空工程可绘制", True)
    check("空工程不让开预览（只提示，不抛异常）", app2.open_page_preview() is None)
    try:
        pj.export_svg(app2.proj, out_dir)
        check("空工程导出应报错", False)
    except ValueError:
        check("空工程导出报错", True)

    print("— 关窗口（× 不报错）—")
    # 曾经的 bug：on_close → _close_page_preview 直接 .destroy()，
    # 而没开过预览时 _page_win 是 None → 'NoneType' object has no attribute 'destroy'
    root2 = tk.Tk()
    root2.withdraw()
    appc = ed.EditorApp(root2)
    root2.update()
    check("新编谱器起手 _page_win 为 None", appc._page_win is None)
    try:
        appc.on_close()
        closed_ok, closed_err = True, ""
    except Exception as exc:                   # noqa: BLE001 —— 这里就是要抓住任何异常
        closed_ok, closed_err = False, repr(exc)
    check("没开过预览也能正常关窗（不再 AttributeError）", closed_ok, closed_err)

    # 开着预览关主窗口也不能崩
    root3 = tk.Tk()
    root3.withdraw()
    appc3 = ed.EditorApp(root3)
    appc3.proj["notes"] = [pj.token_to_doc("5"), pj.token_to_doc("6")]
    appc3.redraw_all()
    root3.update()
    appc3.open_page_preview()
    root3.update()
    check("关窗用例：预览确实开着", appc3._page_win is not None)
    try:
        appc3.on_close()
        closed3_ok, closed3_err = True, ""
    except Exception as exc:                   # noqa: BLE001
        closed3_ok, closed3_err = False, repr(exc)
    check("开着预览关主窗口也不崩（预览窗口一起收掉）", closed3_ok, closed3_err)

    root.destroy()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    # Tk 在 Windows 上 `destroy()` 之后**不保证**进程退出（解释器会挂在 Tcl 上），
    # 表现成「测试明明跑完了、进程却一直不结束」（本轮就卡了 3 分钟）。
    # 所以结果打完后硬退一次，别让调用方一直等。
    _rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc)
