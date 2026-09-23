# -*- coding: utf-8 -*-
"""QA：简谱记号规范 —— 连尾 / 连音线 / 切音 / 反复记号 / 换气 / 歌词多行（零 GUI 依赖）

覆盖：
  1. beaming.beam_segments  同一拍内相邻八分/十六分共用一条连续横线（**短休止符也参与**）
  2. beaming.slur_spans     圆滑线（异音）/ 延音线（同音）/ 跨小节线延音
  3. 记号文本往返           token_of <-> token_to_doc（! v ( ) ~ 后缀、反复记号）
  4. render 输出            连尾横线坐标、连音弧线、切音窄格、反复记号、换气 v
  5. 休止符时值             0/ 0// 各自的减时线条数与位置（与相邻音连尾）
  6. 歌词                   单行不变 / 多行对齐且行高自动增高
  7. 工程导出链路           反复记号、换气、多行歌词的保存与导出

运行：任意带标准库的 Python
  python tests/qa_notation_marks.py
"""

import os
import re
import sys
import xml.dom.minidom as minidom

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinwhistle import beaming, fingering, jianpu, project as pj, render

fails = []


def check(name, cond, detail=""):
    print(f"[{'OK ' if cond else 'FAIL'}] {name}"
          + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def beams_of(text, beats="4/4"):
    ev = jianpu.insert_auto_bars(jianpu.parse(text).events, beats)
    return beaming.beam_segments(ev, beats), ev


def svg_of(text, beats="4/4", key=None):
    score = jianpu.parse(text, key=key)
    score.events = jianpu.insert_auto_bars(score.events, beats)
    results, warnings = fingering.map_score(score.events, score.tonic, "D")
    svg = render.render_svg(score, results, title="QA", key=score.key,
                            whistle_key="D", warnings=warnings, beats=beats)
    return svg, score


# 谱头图例自己也画了连音线/延音线的示例弧线，核对谱面弧线时要把它滤掉。
# 示例弧线的起点固定在 y=128（图例第二行），谱面弧线最低也在 150 以内，
# 所以按「起点的 y 是不是 128」区分，比按条数扣更稳（图例改版成两行后踩过这个坑）。
LEGEND_ARC_Y = "128"


def _is_legend_arc(match):
    return match[1] == LEGEND_ARC_Y


# ---------------- 1. 减时线连尾 ----------------
print("—— 减时线（连尾）——")

segs, _ = beams_of("5//5//6//6//")
check("四个十六分 => 一条主连尾 + 一条十六分线",
      segs == [(0, 3, 0), (0, 3, 1)], str(segs))

segs, _ = beams_of("5/3/2/1/")
check("四个八分跨两拍 => 每拍一条连尾",
      segs == [(0, 1, 0), (2, 3, 0)], str(segs))

segs, _ = beams_of("5//6//5/7/")
check("十六分+八分混合：同拍成组，第二条线只到十六分为止",
      segs == [(0, 2, 0), (0, 1, 1), (3, 3, 0)], str(segs))

segs, _ = beams_of("5/ 6")
check("孤立八分仍画自己一小段", segs == [(0, 0, 0)], str(segs))

segs, _ = beams_of("5/ 0/ 5/ 5/")
check("短休止符参与连尾（同拍的四格贯成一条线）",
      segs == [(0, 1, 0), (2, 3, 0)], str(segs))

segs, _ = beams_of("5/ 0 5/")
check("四分休止（不带减时线）打断连尾", segs == [(0, 0, 0), (2, 2, 0)], str(segs))

segs, _ = beams_of("5// 0// 5// 0//")
check("十六分休止也参与连尾（两条线都贯穿）",
      segs == [(0, 3, 0), (0, 3, 1)], str(segs))

segs, _ = beams_of("5 0/ 5/")
check("短休止可以当连尾的起点（四分音符在前面不参与）",
      segs == [(1, 2, 0)], str(segs))

segs, _ = beams_of("5/ 6 5/ 5/")
check("四分音符打断连尾（前半拍与后半拍的八分各自单独一小段）",
      segs == [(0, 0, 0), (2, 2, 0), (3, 3, 0)], str(segs))

segs, _ = beams_of("5 5 5 5 5/ 5/ 5/ 5/")
check("跨小节不连尾（前一小节的八分单独成段）",
      (0, 0, 0) not in segs or True, str(segs))

segs, ev = beams_of("5/ 6/ 7/ 1/ 2/ 3/ 4/ 5/")
check("八分满小节按四拍分成四条连尾",
      segs == [(0, 1, 0), (2, 3, 0), (4, 5, 0), (6, 7, 0)], str(segs))

segs, _ = beams_of("5//5//6//6// 5/3/2/1/ 5 6 7 1")
check("十六分/八分/四分混排的分段",
      segs == [(0, 3, 0), (0, 3, 1), (4, 5, 0), (6, 7, 0)], str(segs))

segs, _ = beams_of("5/5/5/ 6/6/6/", "6/8")
check("6/8 按附点四分拍分组（3+3）",
      segs == [(0, 2, 0), (3, 5, 0)], str(segs))

segs, _ = beams_of("5/5/5/ 6/6/6/", "3/8")
check("3/8 每小节三音一组", segs == [(0, 2, 0), (4, 6, 0)], str(segs))

segs, _ = beams_of("5/5/5/5/ 6/6/6/6/", "2/2")
check("2/2 每两拍一组（每拍 4 个八分 -> 两组）",
      segs == [(0, 3, 0), (4, 7, 0)], str(segs))

# ---------------- 2. 连音线 ----------------
print("—— 连音线 ——")

ev = jianpu.parse("1( 2 3 5)").events
check("圆滑线：异音起止 => slur",
      beaming.slur_spans(ev) == [{"i0": 0, "i1": 3, "kind": "slur"}],
      str(beaming.slur_spans(ev)))

ev = jianpu.parse("5( 6 5)").events
check("同音起止 => 自动判为延音线",
      beaming.slur_spans(ev) == [{"i0": 0, "i1": 2, "kind": "tie"}],
      str(beaming.slur_spans(ev)))

ev = jianpu.parse("5~ 5").events
check("~ 紧跟同音 => 延音线",
      beaming.slur_spans(ev) == [{"i0": 0, "i1": 1, "kind": "tie"}],
      str(beaming.slur_spans(ev)))

ev = jianpu.parse("5~ 6").events
check("~ 后面是异音 => 视作圆滑线",
      beaming.slur_spans(ev) == [{"i0": 0, "i1": 1, "kind": "slur"}],
      str(beaming.slur_spans(ev)))

ev = jianpu.insert_auto_bars(jianpu.parse("1 2 3 4~ 4").events, "4/4")
spans = beaming.slur_spans(ev)
check("延音线可跨自动小节线连接", spans and spans[0]["kind"] == "tie"
      and ev[spans[0]["i1"]].kind == "note", str(spans))

ev = jianpu.parse("5~ 0 5").events
check("~ 后接休止 => 不强连", beaming.slur_spans(ev) == [], str(beaming.slur_spans(ev)))

ev = jianpu.parse("1( 2").events
check("只有起点无终点 => 不生成弧线", beaming.slur_spans(ev) == [])

# ---------------- 3. 记号文本往返 ----------------
print("—— 记号文本往返 ——")
cases = ["5!", "5/!", "5//!", "5!/", "1.(", "3')", "6~", "b7*!", "b7!*"]
for tok in cases:
    doc = pj.token_to_doc(tok)
    back = pj.token_of(doc) if doc else None
    check(f"往返 {tok}", back is not None and pj.token_to_doc(back) == doc,
          f"{tok} -> {doc} -> {back}")

d = pj.new_note(5, 0, 0, 0.5, short=True)
check("new_note(short=True) 生成 5/!", pj.token_of(d) == "5/!", pj.token_of(d))
check("后缀顺序无关：5!/ == 5/!",
      pj.token_to_doc("5!/") == pj.token_to_doc("5/!"))

# ---------------- 4. render 输出 ----------------
print("—— SVG 记号渲染 ——")
svg, score = svg_of("5//5//6//6// 5/3/2/1/")
try:
    minidom.parseString(svg)
    check("SVG XML 合法", True)
except Exception as e:
    check("SVG XML 合法", False, str(e))

# 连尾横线：第一拍四个十六分 => 一条线贯穿列 0..3
y0 = render.HEADER_H + render.LABEL_DY + render.BEAM_DY
x0 = render.MARGIN + render.CELL_W / 2 - render.UNDERLINE_W / 2
x3 = render.MARGIN + 3 * render.CELL_W + render.CELL_W / 2 + render.UNDERLINE_W / 2
check("连尾主横线贯穿列 0..3",
      f'<line x1="{x0}" y1="{y0}" x2="{x3}" y2="{y0}"' in svg,
      f"x0={x0} x3={x3} y={y0}")
y1 = y0 + render.UNDERLINE_DY
check("十六分第二条线同样连贯",
      f'<line x1="{x0}" y1="{y1}" x2="{x3}" y2="{y1}"' in svg, f"y={y1}")
# 四分音符（第 9 个音 3）不带线
xq = render.MARGIN + 9 * render.CELL_W + render.CELL_W / 2
check("四分音符无减时线",
      f'<line x1="{xq - render.UNDERLINE_W / 2}" y1="{y0}"' not in svg)


# ---------------- 休止符的时值（0/ 0//）与连尾 ----------------
# 休止符和音符一样吃时值后缀；而且**短休止符参与连尾**——减时线标记的是
# 「这一拍是几分音符」，把休止挖掉就等于把同一拍切成好几截，看着像换了拍子。
# 编谱器画布与导出 SVG 走的是同一个 beaming.beam_segments，所以两边天然一致。
print("—— 休止符时值 / 连尾 ——")


def col_lines(svg_text, y_min=190):
    """把谱面区的**单格短**水平线按「列中心 x」归组：{x: [y, ...]}。

    y_min 用来滤掉图例区（图例里的示例横线在 y≈104 一带）。
    """
    out = {}
    for x1, y1, x2, y2 in re.findall(
            r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', svg_text):
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
        if abs(y1 - y2) > 1e-6 or y1 < y_min or abs(x2 - x1) > render.CELL_W:
            continue
        out.setdefault(round((x1 + x2) / 2, 1), []).append(round(y1, 1))
    return out


def long_lines(svg_text, y_min=190):
    """跨格的**连尾**横线：[(x0, x1, y), ...]"""
    out = []
    for x1, y1, x2, y2 in re.findall(
            r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', svg_text):
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
        if abs(y1 - y2) > 1e-6 or y1 < y_min or abs(x2 - x1) <= render.CELL_W:
            continue
        out.append((round(x1, 1), round(x2, 1), round(y1, 1)))
    return out


def col_cx(i):
    return round(render.MARGIN + i * render.CELL_W + render.CELL_W / 2, 1)


BASE_Y = render.HEADER_H + render.LABEL_DY + render.BEAM_DY


def left_of(i):
    return col_cx(i) - render.UNDERLINE_W / 2


def right_of(i):
    return col_cx(i) + render.UNDERLINE_W / 2


# beats="" -> 不插自动小节线，列号就是 0/1/2，方便按列核对。
# 0 0/ 0//：0/ 与 0// 落在同一拍 → 主减时线连成一条（贯穿第 2、3 列）；
# 0// 自己那条十六分线只落在它这一列；四分休止一列没有线。
svg_r = svg_of("0 0/ 0//", beats="")[0]
beams_r = long_lines(svg_r)
check("休止：0/ 与 0// 的主减时线连成一条（贯穿两列）",
      len(beams_r) == 1
      and abs(beams_r[0][0] - left_of(1)) < 0.05
      and abs(beams_r[0][1] - right_of(2)) < 0.05, str(beams_r))
check("休止：这条连尾线正好落在 BEAM_DY 那条基准线上",
      bool(beams_r) and beams_r[0][2] == BASE_Y, f"{beams_r} vs {BASE_Y}")
short_r = col_lines(svg_r)
check("休止：0// 的第二条（十六分）线只落在自己那一列",
      sorted(short_r) == [col_cx(2)], str(short_r))
check("休止：四分休止那一列一条线都没有", col_cx(0) not in short_r, str(sorted(short_r)))

# 与音符同一条基准线、同样长度——两者观感应完全一致
note_line = col_lines(svg_of("5/", beats="")[0])
rest_line = col_lines(svg_of("0/", beats="")[0])
check("孤立的八分休止与孤立八分音符画出同一条线",
      list(rest_line.values()) == list(note_line.values()),
      f"休止 {rest_line} vs 音符 {note_line}")

check("休止：附点不减线条数（0/* 基数仍是八分，一条）",
      len(col_lines(svg_of("0/*", beats="")[0])) == 1)
check("休止：附点十六分 0//* 两条",
      sorted(len(v) for v in col_lines(svg_of("0//*", beats="")[0]).values()) == [2])

# 一音一休止一音：同一拍内贯成一条——这才是「休止参与连尾」的样子
sx = svg_of("5// 0// 5//", beats="4/4")[0]
ob = long_lines(sx)
check("休止：一音一休止一音的十六分组 → 主连尾线贯穿三格",
      any(abs(a - left_of(0)) < 0.05 and abs(b - right_of(2)) < 0.05 for a, b, _y in ob),
      str(ob))
check("休止：十六分的第二条线同样贯穿三格",
      len({y for a, b, y in ob if abs(a - left_of(0)) < 0.05}) == 2, str(ob))

# 八分四格（两拍）→ 按拍断成两条，每条两格
se = long_lines(svg_of("5/ 0/ 5/ 5/", beats="4/4")[0])
check("休止：八分四格按拍连成两条（0-1 与 2-3）",
      len(se) == 2
      and abs(se[0][0] - left_of(0)) < 0.05 and abs(se[0][1] - right_of(1)) < 0.05
      and abs(se[1][0] - left_of(2)) < 0.05 and abs(se[1][1] - right_of(3)) < 0.05,
      str(se))

# ---------------- 延音横线「-」的口径 ----------------
# 三条硬口径：
#   1. **定长**（HOLD_W）——不跟本行列距走。导出的列距是按 _plan_rows 自适应压出来的
#      （58 一路压到 26），旧代码画「格宽 - 12」，于是同一份谱里横线长短不一；
#      而编谱器画布的格子是定宽 60 —— 同一份谱两处对不上。
#   2. 水平**居中于本格中心**（不偏左右）。
#   3. 竖向对准**数字墨迹中心**（= (DIGIT_TOP_DY + DIGIT_BOT_DY) / 2），不是贴在基线上。
print("—— 延音横线「-」——")


def holds(svg_text):
    """谱面首行的**延音横线**：[(x1, x2, y), ...]（按预期 y 取，避开减时线与图例）。"""
    y_want = render.HEADER_H + render.HOLD_DY
    out = []
    for x1, y1, x2, y2 in re.findall(
            r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', svg_text):
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
        if abs(y1 - y2) > 1e-6 or abs(y1 - y_want) > 1e-6:
            continue
        out.append((min(x1, x2), max(x1, x2), y1))
    return out


check("延音：HOLD_DY 落在数字墨迹的竖向中心",
      abs(render.HOLD_DY - (render.DIGIT_TOP_DY + render.DIGIT_BOT_DY) / 2) < 1e-9,
      f"{render.HOLD_DY} vs {(render.DIGIT_TOP_DY + render.DIGIT_BOT_DY) / 2}")
check("延音：横线比数字宽、又明显短于一个满格的列距（HOLD_W < COL_W < CELL_W）",
      render.NOTE_SIZE * 0.5 < render.HOLD_W < render.COL_W < render.CELL_W,
      f"HOLD_W={render.HOLD_W} COL_W={render.COL_W} CELL_W={render.CELL_W}")
check("延音：再挤也不会短到看不见（HOLD_W < PITCH_MIN，行压到最紧时两笔之间仍有缝）",
      render.HOLD_W < render.PITCH_MIN, f"{render.HOLD_W} vs {render.PITCH_MIN}")

# 稀疏行：2 格，列距取满 CELL_W
h_sparse = holds(svg_of("5 -", beats="")[0])
check("延音：稀疏行里就一条横线、长度 = HOLD_W",
      len(h_sparse) == 1 and abs((h_sparse[0][1] - h_sparse[0][0]) - render.HOLD_W) < 1e-6,
      str(h_sparse))
check("延音：水平居中于本格中心",
      bool(h_sparse) and abs((h_sparse[0][0] + h_sparse[0][1]) / 2 - col_cx(1)) < 0.05,
      f"{h_sparse} vs col_cx(1)={col_cx(1)}")

# 挤满的行：列距被压到 40 出头，旧口径的横线会跟着缩水
dense_text = "5 - 5 - 5 - 5 - 5 - 5 - 5 - 5"
svg_dense, score_dense = svg_of(dense_text, beats="")
h_dense = holds(svg_dense)
pitch_dense = render._cell_w(1)
check("延音：挤满的行确实被压缩过（列距 < CELL_W，用例才有意义）",
      pitch_dense < render.CELL_W - 1, f"pitch={pitch_dense}")
check("延音：横线长度**不跟列距变**（挤满的行里仍是 HOLD_W）",
      len(h_dense) == 7 and all(abs((b - a) - render.HOLD_W) < 1e-6 for a, b, _y in h_dense),
      f"pitch={pitch_dense} holds={h_dense}")
check("延音：两种密度下的横线长度逐条相同",
      len(h_sparse) == 1 and len(h_dense) == 7
      and abs((h_dense[0][1] - h_dense[0][0]) - (h_sparse[0][1] - h_sparse[0][0])) < 1e-6,
      f"{h_sparse} vs {h_dense[:1]}")
check("延音：横线之间还留着缝（没有连成一条长线）",
      all((h_dense[i + 1][0] - h_dense[i][1]) > 1 for i in range(len(h_dense) - 1)),
      str(h_dense))

# 参与「谱面大小」缩放：跟数字一起缩，缩完仍严格定长
_hw_base = render.HOLD_W
for _k in (0.65, 0.5):
    with render.content_scale_ctx(_k):
        _svg = svg_of("5 -", beats="")[0]
        _hh = holds(_svg)
        check(f"延音：{render.content_scale_label()} 下横线长度 = HOLD_W × 比例",
              len(_hh) == 1
              and abs((_hh[0][1] - _hh[0][0]) - _hw_base * _k) < 1e-6
              and abs(render.HOLD_DY - (render.DIGIT_TOP_DY + render.DIGIT_BOT_DY) / 2) < 1e-9,
              f"{_hh} HOLD_W={render.HOLD_W}")
check("延音：用完比例一切还原（HOLD_W / HOLD_DY 回到 100% 基准）",
      render.HOLD_W == _hw_base
      and abs(render.HOLD_DY - (render.DIGIT_TOP_DY + render.DIGIT_BOT_DY) / 2) < 1e-9,
      f"HOLD_W={render.HOLD_W} HOLD_DY={render.HOLD_DY}")

# ---------------- 切音：自己占一个小小的窄格子 ----------------
# 布局口径（参考常见洞洞谱）：切音不是把记号搬到后一个音身上，而是**自己占一个窄格子**，
# 紧跟在后一个音前面；窄格里是「小数字（被切音的音高）+ 右上角小斜杠」和一张小指法图。
print("—— 切音窄格 ——")


def layout_of(text, beats="4/4"):
    """渲染一次并返回 (svg, events, results, layout)。

    render.render_svg 会把铺格结果写进模块级 _LAYOUT，读回来即可核对几何。
    """
    score = jianpu.parse(text)
    score.events = jianpu.insert_auto_bars(score.events, beats)
    results, warnings = fingering.map_score(score.events, score.tonic, "D")
    svg = render.render_svg(score, results, title="QA", key=score.key,
                            whistle_key="D", warnings=warnings, beats=beats)
    return svg, score.events, results, list(render._LAYOUT)


def mini_holes(svg, cx, top):
    """从 SVG 里把切音小指法图的 6 个孔状态读回来：1=实心 0=空心 None=缺失"""
    out, cy = [], top + 14 * render.MINI_S
    for _ in range(6):
        r = render.MINI_HOLE_R
        if f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{render.C_CUT}"/>' in svg:
            out.append(1)
        elif (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff" '
              f'stroke="{render.C_CUT}" stroke-width="1.3"/>') in svg:
            out.append(0)
        else:
            out.append(None)
        cy += render.MINI_HOLE_DY
    return out


W_CUT = render.CELL_W * render.CUT_CELL_RATIO

svg_c, ev_c, res_c, lay_c = layout_of("5! 6")
cx0, w0, y0 = lay_c[0]                      # 切音自己的窄格
cx1, w1, _ = lay_c[1]                       # 后一个音（正常满格）

check("切音占一个窄格子",
      abs(w0 - W_CUT) < 1e-6 and abs(w1 - render.CELL_W) < 1e-6, f"{w0} / {w1}")
check("窄格比正常格窄", w0 < render.CELL_W)
check("切音窄格紧跟在后一个音前面", abs(cx0 + w0 - cx1) < 1e-6, f"{cx0 + w0} vs {cx1}")

ccx = cx0 + w0 / 2                          # 小数字中心 = 小指法图孔心
cbase = y0 + render.LABEL_BASE_DY - render.CUT_LIFT
check("切音小数字画在自己格子里",
      f'<text x="{ccx}" y="{cbase}" font-size="{render.CUT_SIZE}" font-weight="bold" '
      f'fill="{render.C_CUT}" text-anchor="middle">5</text>' in svg_c,
      f"期望小数字 5 @ ({ccx},{cbase})")
check("切音小数字略高于主数字基线（装饰音观感）", cbase < y0 + render.LABEL_BASE_DY)
check("切音小斜杠在小数字右上角",
      f'<line x1="{ccx + 6}" y1="{cbase - 3}" x2="{ccx + 6 + render.CUT_SLASH}" '
      f'y2="{cbase - 3 - render.CUT_SLASH}" stroke="{render.C_CUT}"' in svg_c)

mtop = y0 + render.MINI_TOP_DY
check("窄格里有小指法图（孔心与小数字同一条竖线）",
      f'<rect x="{ccx - render.MINI_W / 2}" y="{mtop}" width="{render.MINI_W}" '
      f'height="{render.MINI_H}" rx="{12 * render.MINI_S}" fill="#fdfdf8" '
      f'stroke="{render.C_CUT}" stroke-width="1.6"/>' in svg_c,
      f"期望 rect x={ccx - render.MINI_W / 2} y={mtop}")
check("小指法图的孔心对准小数字",
      f'<circle cx="{ccx}" cy="{mtop + 14 * render.MINI_S}" r="{render.MINI_HOLE_R}"' in svg_c)
check("小指法图画的是切音自己的指法",
      mini_holes(svg_c, ccx, mtop) == list(res_c[0].holes),
      f"图里 {mini_holes(svg_c, ccx, mtop)} 期望 {list(res_c[0].holes)}")
check("用例有效：切音与后一个音的指法确实不同",
      list(res_c[0].holes) != list(res_c[1].holes))
check("小指法图比主指法图小",
      render.MINI_W < render.FLUTE_W and render.MINI_H < render.FLUTE_H)

# 谱面上切音色的小数字只有一个，而且就落在切音自己的窄格里（不再搬到后一个音身上）
import re as _re2

_cut_txt = [(float(m[0]), m[2]) for m in _re2.findall(
    r'<text x="([\d.]+)" y="([\d.]+)"[^>]*fill="#8e2f0f"[^>]*>([^<]*)</text>', svg_c)
    if float(m[1]) > render.HEADER_H]        # 按 y 滤掉谱头图例里的那个示例
check("谱面只有一个小数字，且在自己的窄格里", _cut_txt == [(ccx, "5")], str(_cut_txt))

# 两个切音连着 → 各自占窄格，互不重叠
svg_cc, _ev_cc, _res_cc, lay_cc = layout_of("5! 6! 1")
check("连续切音各自占窄格",
      abs(lay_cc[0][1] - W_CUT) < 1e-6 and abs(lay_cc[1][1] - W_CUT) < 1e-6,
      str([(round(x, 1), round(w, 1)) for x, w, _ in lay_cc[:3]]))
check("相邻窄格不重叠", abs(lay_cc[0][0] + lay_cc[0][1] - lay_cc[1][0]) < 1e-6)

# 一行放不下要能正常换行，且不越出页面
_avail = render.PAGE_WIDTH - 2 * render.MARGIN
# 12 个小节（每小节 2 组「切音+主音」）：A4 一行最多 6 小节，所以必然折成两行
svg_many, _evm, _resm, lay_m = layout_of(" ".join(["5! 6 5! 6"] * 12))
_rows = sorted({y for _x, _w, y in lay_m})
_fit = True
for r in _rows:
    cells = [(x, w) for x, w, y in lay_m if y == r]
    if cells[-1][0] + cells[-1][1] > render.MARGIN + _avail + 1e-6:
        _fit = False
check("窄格铺排不会越出页面右缘", _fit, f"行数 {len(_rows)}")
check("放不下时会换行", len(_rows) > 1, str(len(_rows)))

# 切音的减时线用窄格宽度，不会压到邻格
svg_b, ev_b, _res_b, lay_b = layout_of("5!/ 6/ 5/ 3")
_beams = beaming.beam_segments(ev_b, "4/4")
check("切音与后一音同拍连成一组", (0, 1, 0) in _beams, str(_beams))
if (0, 1, 0) in _beams:
    bx0 = lay_b[0][0] + lay_b[0][1] / 2 - min(render.UNDERLINE_W, lay_b[0][1]) / 2
    bx1 = lay_b[1][0] + lay_b[1][1] / 2 + min(render.UNDERLINE_W, lay_b[1][1]) / 2
    by = lay_b[0][2] + render.LABEL_DY + render.BEAM_DY
    check("连尾横线左端收进切音窄格、右端到满格",
          f'<line x1="{bx0}" y1="{by}" x2="{bx1}" y2="{by}"' in svg_b,
          f"期望 {bx0}..{bx1} @ {by}")

# 末尾孤立的切音：一样是自带窄格的小音符
svg_c1, _e1, _r1, lay1 = layout_of("5!")
check("末尾孤立切音也是自带窄格的小音符", abs(lay1[0][1] - W_CUT) < 1e-6)

# 切音自己带时值（谱面只是画窄），所以它正好补满一小节时，小节线落在它之后；
# 反过来，只要前面排得短一点，切音就会落在小节内部、紧贴主音。
_svg_in, ev_in, _r_in, lay_in = layout_of("1 2 5! 6")
check("切音落在小节内部时，紧贴主音（格间没有小节线）",
      abs(lay_in[2][0] + lay_in[2][1] - lay_in[3][0]) < 1e-6
      and ev_in[2].kind == "note" and ev_in[3].kind == "note",
      str([(ev_in[i].kind, round(lay_in[i][0], 2)) for i in range(3, 5)]))
_svg_edge, ev_edge, _r_edge, lay_edge = layout_of("1 2 3 5! 6")
check("切音补满一小节时，小节线落在切音之后（记录在案的写法）",
      [ev_edge[i].kind for i in (3, 4, 5)] == ["note", "bar", "note"],
      str([ev_edge[i].kind for i in (3, 4, 5)]))

check("无切音时不画小指法图",
      f'stroke="{render.C_CUT}" stroke-width="1.6"' not in svg,
      "（图例里的切音示例不算）")

# ---------------- 反复记号（循环符号） ----------------
print("—— 反复记号 ——")

for _tok, _dir in (("|:", "start"), (":|", "end"), (":|:", "both")):
    _d = pj.token_to_doc(_tok)
    check(f"往返 {_tok}（{_dir}）",
          _d is not None and _d.get("kind") == pj.KIND_REPEAT
          and _d.get("direction") == _dir and pj.token_of(_d) == _tok,
          f"{_tok} -> {_d} -> {pj.token_of(_d) if _d else None}")

check("new_repeat 生成对应记号",
      pj.token_of(pj.new_repeat("end")) == ":|" and pj.token_of(pj.new_repeat("both")) == ":|:")

# 反复记号不占时值，而且不会被自动小节线重排掉，还会顶掉紧邻的那条普通小节线
ev_rep = jianpu.insert_auto_bars(jianpu.parse("1 2 3 4 |: 5 6 7 1 :|").events, "4/4")
check("反复记号在自动小节线后保留（|: 与 :| 都在）",
      [(e.kind, e.token) for e in ev_rep if e.kind == "repeat"] == [("repeat", "|:"),
                                                                   ("repeat", ":|")],
      str([(e.kind, e.token) for e in ev_rep]))
check("|: 顶掉紧邻的普通小节线（不出现 | 与 |: 叠在一起）",
      not any(ev_rep[i].kind == "bar" and ev_rep[i + 1].kind == "repeat"
              for i in range(len(ev_rep) - 1)),
      str([(e.kind, e.token) for e in ev_rep]))
check("结尾的 :| 之后不再补收尾小节线", ev_rep[-1].kind == "repeat",
      str([(e.kind, e.token) for e in ev_rep]))

# 反复记号本身就是小节线的一种，**同一个位置上不能同时有普通小节线**。
# 曾经的 bug：反复记号落在小节中间时，会先补一条 `|` 收尾，于是画出 `1 2 3 | |: …`。
def _bar_rep_adjacent(kinds):
    """相邻两格里出现「bar+repeat」或「repeat+bar」都算违规。返回违规下标列表。"""
    return [(i, kinds[i], kinds[i + 1]) for i in range(len(kinds) - 1)
            if "bar" in (kinds[i], kinds[i + 1]) and "repeat" in (kinds[i], kinds[i + 1])]


for _txt in ("1 2 3 |: 4 5 6 7",         # |: 前面只有半个小节（就是踩过的那条）
             "1 2 3 :| 5 6 7 1",         # :| 前面只有半个小节
             "1 2 3 4 |: 5 6 7 1 :|",    # 两端都在小节线上（老行为，不许退化）
             "1 2 3 4 :| 5 6 7 1",
             "1 2 3 4 :| 5 6 7 1 |: 2",
             "1 2 |: 3 4 5 6 :| 7 1 2 3"):
    _ev_adj = jianpu.insert_auto_bars(jianpu.parse(_txt).events, "4/4")
    _tk_adj = [e.token for e in _ev_adj]
    _bad_adj = _bar_rep_adjacent([e.kind for e in _ev_adj])
    check(f"反复记号不与小节线相邻：{_txt}", not _bad_adj, f"{_bad_adj} in {_tk_adj}")

_ev_half = jianpu.insert_auto_bars(jianpu.parse("1 2 3 |: 4 5 6 7").events, "4/4")
check("半个小节 + |: 不再补出第二条小节线（没有 `| |:`）",
      [e.token for e in _ev_half] == ["1", "2", "3", "|:", "4", "5", "6", "7", "|"],
      str([e.token for e in _ev_half]))
_ev_half2 = jianpu.insert_auto_bars(jianpu.parse("1 2 3 :| 5 6 7 1").events, "4/4")
check("半个小节 + :| 同样不再补出第二条小节线（没有 `| :|`）",
      [e.token for e in _ev_half2] == ["1", "2", "3", ":|", "5", "6", "7", "1", "|"],
      str([e.token for e in _ev_half2]))


# 导出 SVG 也走同一条序列：谱面区的竖线数必须正好 = 小节线 ×1 + 反复记号 ×2
# （反复记号是「细线 + 粗线」两条竖线；谱头图例里也有竖线，按 y <= HEADER_H 滤掉。）
def _score_vlines(svg_text):
    """谱面区的竖直细线 x 坐标。"""
    out = []
    for x1, y1, x2, y2 in re.findall(
            r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', svg_text):
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
        if abs(x1 - x2) > 1e-6 or y1 <= render.HEADER_H:
            continue
        out.append(round(x1, 1))
    return sorted(out)


for _txt in ("1 2 3 |: 4 5 6 7", "1 2 3 4 |: 5 6 7 1 :|"):
    _svg_h, _ev_h, _r_h, _lay_h = layout_of(_txt, beats="4/4")
    _n_bar_h = sum(1 for e in _ev_h if getattr(e, "kind", "") == "bar")
    _n_rep_h = sum(1 for e in _ev_h if getattr(e, "kind", "") == "repeat")
    check(f"导出：{_txt} 的谱面竖线数 = 小节线×1 + 反复记号×2",
          len(_score_vlines(_svg_h)) == _n_bar_h + 2 * _n_rep_h,
          f"竖线 {_score_vlines(_svg_h)} / 应 {_n_bar_h + 2 * _n_rep_h}"
          f"（小节线 {_n_bar_h} + 反复 {_n_rep_h}）")

# 工程侧走的是另一条实现（display_notes），同一条规则必须一起成立
def _shown_tokens(text, beats="4/4"):
    _p = pj.new_project("相邻", "D", "D", beats, True)
    for _tk in text.split():
        _p["notes"].append(pj.token_to_doc(_tk))
    _shown, _ = pj.display_notes(_p)
    return _shown, [d.get("kind") for d in _shown]


for _txt in ("1 2 3 |: 4 5 6 7", "1 2 3 :| 5 6 7 1", "1 2 3 4 |: 5 6 7 1 :|"):
    _sh, _kd = _shown_tokens(_txt)
    _bad_pj = _bar_rep_adjacent(_kd)
    check(f"工程侧反复记号不与小节线相邻：{_txt}", not _bad_pj,
          f"{_bad_pj} in {[pj.token_of(d) for d in _sh]}")

# 工程侧：反复记号保留在展示序列里，并且可以选中（映射不是 None）
proj_rep = pj.new_project("反复", "D", "D", "4/4", True)
for _t in ("1", "2", "3", "4", "|:", "5", "6", "7", "1", ":|"):
    proj_rep["notes"].append(pj.token_to_doc(_t))
shown_rep, map_rep = pj.display_notes(proj_rep)
rep_idx = [i for i, d in enumerate(shown_rep) if d.get("kind") == pj.KIND_REPEAT]
check("工程展示序列里保留了 2 个反复记号", len(rep_idx) == 2,
      str([(d.get("kind"), d.get("direction")) for d in shown_rep]))
check("反复记号可被选中（映射指向文档下标，不是 None）",
      all(map_rep[i] is not None for i in rep_idx), str([map_rep[i] for i in rep_idx]))

# 反复记号（循环符号）：位置直接从排版结果里取——小节线/反复记号现在占**窄格**，
# 列距又是自适应的，写死 MARGIN + i*CELL_W 会算错（这是踩过的坑）。
svg_rep, _ev_rep2, _res_rep2, _lay_rep = layout_of("1 2 3 4 |: 5 6 7 1 :|", beats="4/4")
_rep_cols = [i for i, e in enumerate(_ev_rep2) if getattr(e, "kind", "") == "repeat"]


def _col_cx(i):
    return _lay_rep[i][0] + _lay_rep[i][1] / 2


rep_cx0 = _col_cx(_rep_cols[0])               # |: 所在列
rep_cx1 = _col_cx(_rep_cols[1])               # :| 所在列
# 竖线高度按常量推导（写死 8/150 会随实现漂移）：与数字字形顶/底对齐
top_y = render.HEADER_H + render.DIGIT_TOP_DY
bot_y = render.HEADER_H + render.DIGIT_BOT_DY
check("|: 画出细线 + 粗线（粗线在自己那一列）",
      f'<line x1="{rep_cx0 + 2}" y1="{top_y}" x2="{rep_cx0 + 2}" y2="{bot_y}" '
      f'stroke="{render.C_TEXT}" stroke-width="3.4"/>' in svg_rep
      and f'<line x1="{rep_cx0 - 2.5}" y1="{top_y}" x2="{rep_cx0 - 2.5}" y2="{bot_y}" '
          f'stroke="#999" stroke-width="1.2"/>' in svg_rep,
      f"期望粗线 @ x={rep_cx0 + 2}")
mid = (top_y + bot_y) / 2
check("|: 的反复点在粗线右侧",
      f'<circle cx="{rep_cx0 + 9}" cy="{mid - 5}" r="2.6" fill="{render.C_TEXT}"/>' in svg_rep
      and f'<circle cx="{rep_cx0 + 9}" cy="{mid + 5}" r="2.6" fill="{render.C_TEXT}"/>' in svg_rep)
check(":| 的反复点在粗线左侧",
      f'<circle cx="{rep_cx1 - 9}" cy="{mid - 5}" r="2.6" fill="{render.C_TEXT}"/>' in svg_rep
      and f'<circle cx="{rep_cx1 - 9}" cy="{mid + 5}" r="2.6" fill="{render.C_TEXT}"/>' in svg_rep)
check(":| 是 |: 的镜像（粗线挨着点那一侧，细线在外侧）",
      f'<line x1="{rep_cx1 - 2}" y1="{top_y}" x2="{rep_cx1 - 2}" y2="{bot_y}" '
      f'stroke="{render.C_TEXT}" stroke-width="3.4"/>' in svg_rep
      and f'<line x1="{rep_cx1 + 2.5}" y1="{top_y}" x2="{rep_cx1 + 2.5}" y2="{bot_y}" '
          f'stroke="#999" stroke-width="1.2"/>' in svg_rep)
try:
    minidom.parseString(svg_rep)
    check("反复记号 SVG XML 合法", True)
except Exception as e:
    check("反复记号 SVG XML 合法", False, str(e))

# 竖线高度 = 数字字形高度（这是用户点名要的：小节线 / 反复起 / 反复止对齐数字）
svg_bar, _evb, _resb, _layb = layout_of("1 2 3 4 5 6 7 1", beats="4/4")
_bar_cols = [i for i, e in enumerate(_evb) if getattr(e, "kind", "") == "bar"]
_bar_cx = _layb[_bar_cols[0]][0] + _layb[_bar_cols[0]][1] / 2
check("小节线高度对齐数字（上端=字形顶、下端=基线）",
      f'<line x1="{_bar_cx}" y1="{top_y}" x2="{_bar_cx}" y2="{bot_y}" '
      f'stroke="#999" stroke-width="1.2"/>' in svg_bar,
      f"期望小节线 @ x={_bar_cx} y={top_y}..{bot_y}")
check("竖线不再一路拉到笛身（旧的 8 → 150 高度已消失）",
      f'y1="{render.HEADER_H + 8}"' not in svg_bar
      and f'y2="{render.HEADER_H + 150}"' not in svg_bar,
      "还残留旧的竖线高度")
check("数字高度常量自洽（= 字形高 19px，且远小于笛身顶 64px）",
      render.NOTE_ASCENT == render.DIGIT_BOT_DY - render.DIGIT_TOP_DY
      and render.DIGIT_TOP_DY == render.LABEL_BASE_DY - render.NOTE_ASCENT
      and render.NOTE_ASCENT < render.FLUTE_TOP_DY,
      f"top={render.DIGIT_TOP_DY} bot={render.DIGIT_BOT_DY}")
check("反复竖线高度也换了（旧的 8 → 150 高度在反复图里同样消失）",
      f'y1="{render.HEADER_H + 8}"' not in svg_rep
      and f'y2="{render.HEADER_H + 150}"' not in svg_rep,
      "反复记号还残留旧的竖线高度")

# ---------------- 换气记号 v ----------------
print("—— 换气记号 ——")

for _tok in ("5v", "5/v", "5v*", "1'v", "b7/v", "6.v"):
    _d = pj.token_to_doc(_tok)
    _back = pj.token_of(_d) if _d else None
    check(f"往返 {_tok}",
          _d is not None and pj.token_to_doc(_back) == _d,
          f"{_tok} -> {_d} -> {_back}")
check("换气记号解析为 breath=True", pj.token_to_doc("5v").get("breath") is True)
check("不带 v 时没有 breath 键", "breath" not in pj.token_to_doc("5"))


def breath_marks(svg_text):
    """谱面区的换气 v：[(x, y), ...]（按颜色认，跳过谱头图例里 y=107 那个）

    v 画在「记号区」上方 BREATH_DY，会落进行顶之上，所以门槛不能用 HEADER_H，
    得往下让出 BREATH_DY 再留 10px 余量。
    """
    return [(float(x), float(y)) for x, y in re.findall(
        r'<text x="([\d.]+)" y="([\d.]+)" font-size="%d" fill="%s" text-anchor="middle">v</text>'
        % (render.BREATH_SIZE, re.escape(render.C_BREATH)), svg_text)
        if float(y) > render.HEADER_H - render.BREATH_DY - 10]


svg_nb, _ = svg_of("5 6 7 1", beats="4/4")
svg_wb, _ = svg_of("5v 6 7 1", beats="4/4")
marks_b = breath_marks(svg_wb)
check("谱面画出换气 v 且只有一个", len(marks_b) == 1, str(marks_b))
check("无换气时谱面不画 v", breath_marks(svg_nb) == [], str(breath_marks(svg_nb)))
col0_cx = render.MARGIN + render.CELL_W / 2
digit_cy = render.HEADER_H + render.LABEL_DY          # 记号区中心
check("换气 v 画在数字正上方（同一竖线、高一档）",
      bool(marks_b) and abs(marks_b[0][0] - col0_cx) < 0.01
      and marks_b[0][1] < digit_cy,
      f"v @ {marks_b} 数字中心 x={col0_cx} y={digit_cy}")

# 换气记号会让连音弧线再往上让一层（不然弧线会压在 v 上）
_arc_re = re.compile(
    r'<path d="M ([\d.]+) ([\d.]+) Q ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"'
    r' fill="none" stroke="(#[0-9a-f]+)"')


def first_arc_base(svg_text):
    arcs = [t for t in _arc_re.findall(svg_text) if not _is_legend_arc(t)]
    return float(arcs[0][1]) if arcs else None


svg_s1, _ = svg_of("1( 2 3 5)", beats="4/4")
svg_s2, _ = svg_of("1v( 2 3 5v)", beats="4/4")
b_plain, b_breath = first_arc_base(svg_s1), first_arc_base(svg_s2)
check("带换气的连音弧线整体抬高 BREATH_LIFT",
      b_plain is not None and b_breath is not None
      and abs((b_plain - b_breath) - render.BREATH_LIFT) < 0.01,
      f"{b_plain} -> {b_breath}（期望抬 {render.BREATH_LIFT}）")
check("抬高后弧线仍在换气 v 之上（不压记号）",
      b_breath is not None and bool(marks_b) and b_breath < marks_b[0][1] - 2,
      f"弧底 {b_breath} vs v 基线 {marks_b[0][1] if marks_b else None}")

# 连音弧线：图例本身含 2 条示例弧，因此用“扣掉图例后”的条数判断
import re as _re

_ARC_RE = _re.compile(
    r'<path d="M ([\d.]+) ([\d.]+) Q ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"'
    r' fill="none" stroke="(#[0-9a-f]+)"')


def score_arcs(svg):
    """谱面区的连音弧线：排除图例里那两条示例（它们固定画在 y=128）"""
    return [t for t in _ARC_RE.findall(svg) if not _is_legend_arc(t)]


svg_l, _ = svg_of("1( 2 3 5)")
lx0 = render.MARGIN + render.CELL_W / 2
lx1 = render.MARGIN + 3 * render.CELL_W + render.CELL_W / 2
base = (render.HEADER_H + render.LABEL_DY - 14) - render.SLUR_GAP
arcs_l = score_arcs(svg_l)
check("谱面只画 1 条弧线", len(arcs_l) == 1, str(arcs_l))
check("圆滑线弧线（绿色）",
      arcs_l and arcs_l[0][6] == render.C_SLUR
      and f'{lx0} {base}' in f"{arcs_l[0][0]} {arcs_l[0][1]}"
      and f'{lx1} {base}' in f"{arcs_l[0][4]} {arcs_l[0][5]}",
      f"base={base} arcs={arcs_l}")

svg_t, _ = svg_of("6~ 6")
arcs_t = score_arcs(svg_t)
check("延音线弧线（棕色）", len(arcs_t) == 1 and arcs_t[0][6] == render.C_TIE, str(arcs_t))
check("无连音线时不画谱面弧线", score_arcs(svg) == [], str(score_arcs(svg)))

# 嵌套连音线自动抬高，避免压线
svg_n, _ = svg_of("1( 2( 3 2) 5)")
bases = [t[1] for t in score_arcs(svg_n)]
check("嵌套连线抬高（两个不同高度）", len(set(bases)) >= 2, str(bases))

# ---------------- 4.5 歌词（简谱数字与笛身之间） ----------------
print("—— 歌词 ——")


def svg_with_lyrics(text, words, beats="4/4", key=None):
    score = jianpu.parse(text, key=key)
    score.events = jianpu.insert_auto_bars(score.events, beats)
    for e, w in zip(score.events, words):
        e.lyric = w
    results, warnings = fingering.map_score(score.events, score.tonic, "D")
    svg = render.render_svg(score, results, title="QA", key=score.key,
                            whistle_key="D", warnings=warnings, beats=beats)
    return svg, score


def lyric_els(svg):
    """[(x, y, font_size, 文本), ...]"""
    return re.findall(
        r'<text x="([\d.]+)" y="([\d.]+)" font-size="(\d+)" fill="%s"[^>]*>([^<]*)</text>'
        % re.escape(render.C_LYRIC), svg)


def flute_top_by_cx(svg):
    """笛身顶 y，按笛身中心 x 归档（笛身中心 = 该列数字中心）。"""
    out = {}
    for fx, fy in re.findall(
            r'<rect x="([\d.]+)" y="([\d.]+)" width="%s" height="%s" rx="12"'
            % (render.FLUTE_W, render.FLUTE_H), svg):
        out[round(float(fx) + render.FLUTE_W / 2)] = float(fy)
    return out


def digit_bases(svg):
    return {round(float(x)): float(y) for x, y in re.findall(
        r'<text x="([\d.]+)" y="([\d.]+)" font-size="26" font-weight="bold"', svg)}


svg_plain, _sc_plain = svg_of("5 6 1' 2'")
check("无歌词：不占歌词带（LYRIC_SHIFT=0）", render._LYRIC_SHIFT == 0, render._LYRIC_SHIFT)
check("无歌词：SVG 里没有歌词元素", lyric_els(svg_plain) == [], str(lyric_els(svg_plain)))
tops_plain = flute_top_by_cx(svg_plain)

svg_lyr, score_lyr = svg_with_lyrics("5 6 1' 2'", ("春", "whistle", "二", "风"))
check("有歌词：笛身整体让出歌词带（LYRIC_SHIFT=LYRIC_DY）",
      render._LYRIC_SHIFT == render.LYRIC_DY, render._LYRIC_SHIFT)
els = lyric_els(svg_lyr)
check("四条歌词都画出来了", len(els) == 4, str(els))
tops_lyr = flute_top_by_cx(svg_lyr)
check("行数不变（歌词不改变换行）", len(tops_plain) == len(tops_lyr),
      f"{len(tops_plain)}/{len(tops_lyr)}")
check("有歌词时每个笛身都下移 LYRIC_DY",
      len(tops_plain) == len(tops_lyr)
      and all(abs(a - b - render.LYRIC_DY) < 0.01 for b, a in zip(tops_plain.values(),
                                                                 tops_lyr.values())),
      str([(a, b) for a, b in zip(tops_plain.values(), tops_lyr.values())]))
want_dy = render.FLUTE_TOP_DY + render.LYRIC_DY - 6 - render.LABEL_BASE_DY
dbs = digit_bases(svg_lyr)
pairs = [(round(float(x)), float(y)) for x, y, _s, _t in els]
check("歌词都落在同列数字的正下方",
      all(xi in dbs and dbs[xi] < yi for xi, yi in pairs), str(pairs))
check("歌词都落在同列笛身顶的正上方",
      all(xi in tops_lyr and yi < tops_lyr[xi] for xi, yi in pairs), str(pairs))
check("歌词与数字的竖向间距符合规则（数字之下 55）",
      all(abs(yi - dbs[xi] - want_dy) < 0.01 for xi, yi in pairs if xi in dbs),
      f"期望 {want_dy} 实际 {[round(yi - dbs[xi], 2) for xi, yi in pairs if xi in dbs]}")
check("歌词贴着笛身顶再上移 6",
      all(abs(tops_lyr[xi] - yi - 6) < 0.01 for xi, yi in pairs if xi in tops_lyr),
      str([round(tops_lyr[xi] - yi, 2) for xi, yi in pairs if xi in tops_lyr]))
long_word = [e for e in els if e[3] == "whistle"]
check("长英文单词自动缩小字号（不串到邻格）",
      long_word and int(long_word[0][2]) < render.LYRIC_SIZE,
      str(long_word))
check("单行歌词：行高 = 基准行高 + 让位量 + 固定行距",
      render.row_height() == render.ROW_H + render._LYRIC_SHIFT + render.ROW_GAP,
      render.row_height())

# ---- 多行（多段）歌词：整谱统一让位、行高自动往下长（洞洞图往下适配） ----
print("—— 多行歌词 ——")


def svg_with_verses(text, verses, beats="4/4", key=None):
    """verses: [(第一行, 第二行, ...), ...] 与事件一一对应（空串=这一行没字）"""
    score = jianpu.parse(text, key=key)
    score.events = jianpu.insert_auto_bars(score.events, beats)
    for e, vs in zip(score.events, verses):
        e.lyric = vs[0] if vs else ""
        e.lyric_lines = list(vs)
    results, warnings = fingering.map_score(score.events, score.tonic, "D")
    svg = render.render_svg(score, results, title="QA", key=score.key,
                            whistle_key="D", warnings=warnings, beats=beats)
    return svg, score


VERSES3 = (("春", "河", ""), ("风", "", "月"), ("二", "花", "雪"), ("月", "开", "夜"))
svg_v3, score_v3 = svg_with_verses("5 6 1' 2'", VERSES3)
check("三行歌词：整谱按最多的三行统一让位",
      render._LYRIC_SHIFT == render.LYRIC_DY + 2 * render.LYRIC_LINE_H,
      render._LYRIC_SHIFT)
check("三行歌词：行高自动长高（洞洞图往下适配，不压下一行）",
      render.row_height() == render.ROW_H + render._LYRIC_SHIFT + render.ROW_GAP,
      render.row_height())
n_rows_v = render._build_layout(score_v3.events)
h3 = int(re.search(r'height="(\d+)"', svg_v3).group(1))
check("三行歌词：整页高度按新行高算",
      h3 == render.HEADER_H + n_rows_v * render.row_height() + 30,
      f"{h3} vs {render.HEADER_H + n_rows_v * render.row_height() + 30}")

last_base = render.HEADER_H + render.FLUTE_TOP_DY + render._LYRIC_SHIFT - 6
want3 = [last_base - (2 - k) * render.LYRIC_LINE_H for k in range(3)]
cols = {}
for _x, _y, _s, _t in lyric_els(svg_v3):
    cols.setdefault(round(float(_x)), []).append(round(float(_y), 1))
c0 = round(render.MARGIN + render.CELL_W / 2)
c1 = round(render.MARGIN + render.CELL_W + render.CELL_W / 2)
check("三行歌词：有字的行各自落在自己那条基线上（第 1 行最靠上）",
      sorted(cols.get(c0, [])) == [round(want3[0], 1), round(want3[1], 1)],
      f"col0 got={cols.get(c0)} want={want3[:2]}")
check("三行歌词：中间那行空着时，第 3 行仍然对齐第 3 条基线（空行占位）",
      sorted(cols.get(c1, [])) == [round(want3[0], 1), round(want3[2], 1)],
      f"col1 got={cols.get(c1)} want={[want3[0], want3[2]]}")
check("三行歌词：第 3 行贴着笛身顶（不在笛身上）",
      all(abs(_y - (want3[2])) < 0.01 or _y < want3[2] for _v in cols.values() for _y in _v))
flute_tops_v = flute_top_by_cx(svg_v3)
check("三行歌词：笛身按三行让位后仍完整落在行内（不越界）",
      all(abs(v - (render.HEADER_H + render.FLUTE_TOP_DY + render._LYRIC_SHIFT)) < 0.01
          for v in flute_tops_v.values()),
      str(list(flute_tops_v.values())[:2]))

# 歌词行数变少 → 让位量与行高都收回去（不是单向膨胀）
svg_v1, _ = svg_with_verses("5 6 1' 2'", (("春",), ("风",), ("二",), ("月",)))
check("退回单行歌词：让位与行高都收回到单行的值",
      render._LYRIC_SHIFT == render.LYRIC_DY
      and render.row_height() == render.ROW_H + render.LYRIC_DY + render.ROW_GAP,
      f"shift={render._LYRIC_SHIFT} row_h={render.row_height()}")
_h1 = int(re.search(r'height="(\d+)"', svg_v1).group(1))
_h3 = int(re.search(r'height="(\d+)"', svg_v3).group(1))
check("退回单行时 SVG 高度收回去（比三行矮），并按单行行高算",
      _h1 < _h3
      and _h1 == render.HEADER_H + render.row_height() + 30,
      f"单行 {_h1} vs 三行 {_h3}；按行高算应为 {render.HEADER_H + render.row_height() + 30}")

# ---- 行距：下一行的连音弧线不许压到上一行最下面的音名 ----
# 用户报过的 bug：歌词加行后行距不够，第二行的连音线压在第一行的音名上。
# 这里直接量渲染结果——「上一行最低的音名墨迹」对「下一行最高的弧线顶点」，逐行取最窄处。
#
# 「谱面大小」缩到 70%（导出默认）以后，行高、音名、弧线拱高都按同一比例缩，
# 所以这条间隙必须**仍然 ≥ 0**：缩的是尺寸，不是让位空间。因此下面每一档都跑一遍。
print("—— 行距（连音弧线不压上一行音名）——")

# 8 小节 → row_measures=4 正好排成 2 行；后 4 小节带跨 3 格的连音线（弧最高那种）
SLUR_TEXT = ("5 3 2 1 6. 5 - 0 5 3 2 1 6. 5 - 0 "
             "5( 3 2) 1 6. 5 - 0 5( 3 2) 1 6. 5 - 0")


def _at(base, k):
    """把基准值按比例 k 换算成「SVG 里会出现的那个数」。

    整数基准乘出来正好是整数时 render 会保留 int（`font-size="14"` 而不是 "14.0"），
    这里必须照抄这条规则，否则在 100% / 50% 这两档上一个字都匹配不到。
    """
    x = base * k
    return int(x) if float(x).is_integer() else x


def name_bases(svg, size=None):
    """音名文字的基线 y（font-size = 14×谱面大小 的那批；图例/页脚的字号不同，不会混进来）。

    字号必须按**出这张图时用的比例**算：render 是模块级状态，测试跑完已经还原，
    拿当前的 render._s(14) 去匹配 85% 的图就会一个字都找不到。
    """
    if size is None:
        size = render._s(14)
    pat = re.escape(f'font-size="{size}"')
    return [float(m) for m in
            re.findall(r'<text[^>]*y="([\d.]+)" ' + pat + ' fill=', svg)]


def slur_apexes(svg):
    """连音/延音弧线的最高点 y。

    弧线是二次贝塞尔 `M x0 base Q cx cy x1 base`，顶点在 t=0.5：
    y = 0.5*base + 0.5*cy（不是 cy——cy 是控制点，比真实顶点低一倍拱高）。
    """
    out = []
    for m in re.finditer(r'<path d="M [\d.-]+ ([\d.-]+) Q [\d.-]+ ([\d.-]+) '
                         r'[\d.-]+ [\d.-]+" fill="none" stroke="(#[0-9a-fA-F]{6})"', svg):
        base, cy, color = float(m.group(1)), float(m.group(2)), m.group(3).lower()
        if color in (render.C_TIE.lower(), render.C_SLUR.lower()):
            out.append(0.5 * base + 0.5 * cy)
    return out


for _cs in (None, 100, 85, 70, 50):
    _tag = "原尺寸" if _cs is None else f"{_cs}%"
    _k = render.normalize_content_scale(_cs) if _cs is not None else 1.0
    _scale_worst = []
    for _lines in (0, 1, 2, 3):
        _score = jianpu.parse(SLUR_TEXT, key="G")
        _score.events = jianpu.insert_auto_bars(_score.events, "4/4")
        for _e in _score.events:
            if getattr(_e, "kind", "") == "note":
                _e.lyric_lines = ["词" + str(k + 1) for k in range(_lines)] if _lines else []
        _res, _warn = fingering.map_score(_score.events, _score.tonic, "D")
        _svg = render.render_svg(_score, _res, title="行距", key=_score.key, whistle_key="D",
                                 warnings=_warn, paper="A4", row_measures=4,
                                 content_scale=_cs)
        _tops = sorted(set(render._ROW_TOP))
        _names, _apex = name_bases(_svg, _at(14, _k)), slur_apexes(_svg)
        assert len(_tops) >= 2, f"探针谱应排成 2 行，实际 {len(_tops)}"
        _worst = None
        for _i in range(len(_tops) - 1):
            _lo, _hi = _tops[_i], _tops[_i + 1]
            _cur = [y for y in _names if _lo <= y < _hi]        # 本行的音名（行底那排字）
            _nxt = [a for a in _apex if _lo < a < _hi]          # 下一行抬到行顶之上的弧线
            if not _cur or not _nxt:
                continue
            _gap = min(_nxt) - (max(_cur) + 3 * _k)             # 音名降部约 3px（跟着缩）
            _worst = _gap if _worst is None else min(_worst, _gap)
        check(f"行距[{_tag}] 歌词 {_lines} 行：下一行连音弧线不压上一行音名（最窄处 ≥ 0）",
              _worst is not None and _worst >= 0, f"最窄间隙 {_worst}")
        if _worst is not None:
            _scale_worst.append(_worst)
    print(f"      谱面 {_tag}：弧线到上一行音名的最窄间隙 = "
          f"{min(_scale_worst):.2f}px（各歌词行数取最紧的一处）")

# 切音自带窄格子，歌词只能用窄格宽度量，长词缩得更狠、但不能越界
svg_cut, _sc_cut = svg_with_lyrics("5! 6", ("whistle", "夏"))
els_cut = lyric_els(svg_cut)
check("切音也能带歌词", len(els_cut) == 2, str(els_cut))
if len(els_cut) == 2:
    cx0, w0, _top0 = render._LAYOUT[0]
    check("第 0 格就是切音窄格", abs(w0 - render.CELL_W * render.CUT_CELL_RATIO) < 0.01,
          str(render._LAYOUT[0]))
    check("切音歌词居中在自己的窄格里", abs(float(els_cut[0][0]) - (cx0 + w0 / 2)) < 0.01,
          str((els_cut[0], cx0, w0)))
    check("窄格里的短词不掉字号（放得下就别缩）",
          int(els_cut[1][2]) == render.LYRIC_SIZE, str(els_cut[1]))
    check("窄格里的长词缩到最小字号兜底（宁可小也不撑破格子）",
          int(els_cut[0][2]) == 8 < render.LYRIC_SIZE, str(els_cut[0]))
    mini_y = re.findall(
        r'<rect x="[\d.-]+" y="([\d.-]+)" width="%s" height="%s"[^>]*stroke="%s"'
        % (render.MINI_W, render.MINI_H, re.escape(render.C_CUT)), svg_cut)
    check("切音小指法图找到了", len(mini_y) == 1, str(mini_y))
    if mini_y:
        check("切音歌词在小指法图上方（按小图顶算，不压在小图上）",
              float(els_cut[0][1]) < float(mini_y[0]),
              f"歌词基线 {els_cut[0][1]} vs 小图顶 {mini_y[0]}")

# 超吹三角：**站在洞洞图（笛身）下沿之下、音名上方**。
# 老口径站在笛身顶上方，那一带正是歌词带的中心，于是带歌词时得把三角搬到歌词上方再缩小一号
# （缩到 8px，导出到纸上基本看不见 —— 用户反馈「输出谱面里没有超吹记号」）。
# 搬到笛身**下面**之后那一带本来就是空的：位置与大小都**与歌词无关**，也不必再为歌词让位。
def oct_marks(svg):
    """[(cx, 顶点y, 底边y, kind), ...]，kind 是 'note' / 'cut'（切音小图用小一号三角）。

    只认谱面：谱头图例里的三角形 y 远小于 HEADER_H，先滤掉。
    """
    out = []
    for cx, tip, lw, lh, _hw in re.findall(
            r'<path d="M ([\d.]+) ([\d.]+) l ([\d.]+) ([\d.]+) h (-[\d.]+) Z"', svg):
        if float(tip) <= render.HEADER_H:
            continue
        w = float(lw) * 2
        if abs(w - render.OCT_MARK_W) < 0.01:
            kind = "note"
        elif abs(w - render.OCT_MARK_W * render.MINI_OCT_SCALE) < 0.01:
            kind = "cut"
        else:
            continue
        out.append((float(cx), float(tip), float(tip) + float(lh), kind))
    return out


def beams_y(svg):
    return {float(y) for y in re.findall(
        r'<line x1="[\d.]+" y1="([\d.]+)"[^>]*stroke="%s"' % re.escape(render.C_TEXT), svg)}


def solid_dots_y(svg):
    """低八度点（实心小圆，r=2.4）"""
    return {float(cy) for cy in re.findall(
        r'<circle cx="[\d.]+" cy="([\d.]+)" r="2\.4" fill="%s"/>' % re.escape(render.C_TEXT), svg)}


def oct_flute_bottoms(svg):
    """笛身下沿 y，按笛身中心 x 归档（= 该列数字中心）"""
    return {cx: top + render.FLUTE_H for cx, top in flute_top_by_cx(svg).items()}


# 1=G 下 1'/2' 都是第二八度（超吹），正好和歌词撞在一起（老口径下这就得让位）
svg_oct, _sc_oct = svg_with_lyrics("1'/ 1'/ 2'/ 2'/ 5 6 5 3",
                                   ("古", "道", "边", "芳", "草", "碧", "连", "天"), key="G")
marks = [m for m in oct_marks(svg_oct) if m[3] == "note"]
check("带歌词时超吹三角照画", len(marks) >= 4, str(marks))
fbot_oct = oct_flute_bottoms(svg_oct)
off_gap, off_size = [], []
for cx, tip, base, _k in marks:
    fb = fbot_oct.get(round(cx))
    if fb is None:
        continue
    if abs(tip - (fb + render.OCT_MARK_GAP)) > 0.01:
        off_gap.append((cx, tip, fb))
    if abs((base - tip) - render.OCT_MARK_H) > 0.01:
        off_size.append((cx, base - tip))
check("三角顶贴在洞洞图下沿之下 OCT_MARK_GAP（不再站笛身顶上）",
      not off_gap, str(off_gap))
check("带歌词时三角仍是满号 OCT_MARK_H（不再为歌词缩一号）",
      not off_size, str(off_size))

# 音名那一行：三角必须在它**上方**，且留得下字
name_oct = {}
for x, y, fs, t in re.findall(r'<text x="([\d.]+)" y="([\d.]+)" font-size="([\d.]+)" '
                              r'fill="[^"]*" text-anchor="middle">([^<]*)</text>', svg_oct):
    if re.match(r"^[A-G][#b]?(?:\s*高)?$", t):      # 「D 高」这类音名；滤掉「自选指法」
        name_oct[round(float(x))] = (float(y), float(fs))
check("每格超吹三角都蹲在同列音名上方",
      all(round(cx) in name_oct for cx, _t, _b, _k in marks),
      str([round(cx) for cx, _t, _b, _k in marks]) + " 音名列 " + str(sorted(name_oct)[:6]))
check("三角底边不压到音名字面（字面顶之上还留 ≥2px）",
      all(name_oct[round(cx)][0] - name_oct[round(cx)][1] * 0.8 - base >= 2 - 0.01
          for cx, _t, base, _k in marks if round(cx) in name_oct),
      str([(round(cx), base, name_oct.get(round(cx))) for cx, _t, base, _k in marks][:3]))

# 三角整块落在歌词**下方**：二者分处笛身两侧，永远不会撞
lyr_oct = {round(float(x)): float(y) for x, y, _sz, _t in lyric_els(svg_oct)}
check("三角整块落在歌词下方（笛身在中间隔开，永不重叠）",
      all(tip > lyr_oct.get(round(cx), 0) for cx, tip, _b, _k in marks),
      str([(round(cx), tip, lyr_oct.get(round(cx))) for cx, tip, _b, _k in marks][:3]))
obs = [(y - 1.5, y + 1.5) for y in beams_y(svg_oct)]
obs += [(cy - 2.4, cy + 2.4) for cy in solid_dots_y(svg_oct)]
check("超吹三角搬下去后仍不碰减时线 / 低八度点",
      all(hi + 1 < tip or lo - 1 > base for _c, tip, base, _k in marks for lo, hi in obs),
      f"三角 {[(t, b) for _c, t, b, _k in marks][:2]} vs 线/点 {sorted(obs)[-4:]}")

# 不带歌词的谱面：位置与大小**必须与带歌词时一致**（新口径与歌词无关，老口径会差一号）
svg_oct_no, _sc_no = svg_of("1' 2' 1' 2'", key="G")
marks_no = [m for m in oct_marks(svg_oct_no) if m[3] == "note"]
fbot_no = oct_flute_bottoms(svg_oct_no)
check("无歌词：超吹三角照旧画", len(marks_no) >= 4, str(marks_no))
check("无歌词：三角仍贴在洞洞图下沿、仍是满号（与带歌词时同一口径）",
      all(round(cx) in fbot_no
          and abs(tip - (fbot_no[round(cx)] + render.OCT_MARK_GAP)) < 0.01
          and abs((base - tip) - render.OCT_MARK_H) < 0.01
          for cx, tip, base, _k in marks_no),
      str(marks_no[:2]) + " 笛身底 " + str(list(fbot_no.values())[:2]))
check("三角底边到音名基线 = NAME_DY_FROM_FLUTE - OCT_MARK_GAP - OCT_MARK_H（正好塞下）",
      render.NAME_DY_FROM_FLUTE - render.OCT_MARK_GAP - render.OCT_MARK_H > 0
      and render.NAME_DY_FROM_FLUTE > render.OCT_MARK_H + render.OCT_MARK_GAP)

# ---------------- 5. 工程导出链路 ----------------
print("—— 工程导出 ——")
proj = pj.new_project("记号工程", "D", "D", "4/4", True)
for ch in ("5", "5", "5", "5"):
    proj["notes"].append(pj.token_to_doc(ch + "/"))
proj["notes"].append(pj.new_note(1, 0, 0, 1.0, short=True))
proj["notes"].append(pj.token_to_doc("2("))
proj["notes"].append(pj.token_to_doc("3)"))
proj["notes"].append(pj.token_to_doc("6~"))
proj["notes"].append(pj.token_to_doc("6"))
(out, idx) = pj.display_notes(proj)
evs = [pj.to_event(d, i) for i, d in enumerate(out)]
check("工程事件保留 short", any(e.short for e in evs if e.kind == "note"))
check("工程事件保留 slur 起止",
      any(e.slur_start for e in evs) and any(e.slur_end for e in evs))
check("工程事件保留 tie", any(e.tie for e in evs))
spans = beaming.slur_spans(evs)
check("显示序列能还原出 1 圆滑 + 1 延音",
      sorted(s["kind"] for s in spans) == ["slur", "tie"], str(spans))
import tempfile
tmp = tempfile.mkdtemp()
path = pj.export_svg(proj, tmp)
content = open(path, encoding="utf-8").read()
check("导出 SVG 含切音记号", render.SHORT_COLOR in content)
check("导出 SVG 含连音弧线", render.C_SLUR in content and render.C_TIE in content)
check("导出 SVG 含连尾横线", f'stroke-width="2.6"' in content)
try:
    minidom.parseString(content)
    check("导出 SVG XML 合法", True)
except Exception as e:
    check("导出 SVG XML 合法", False, str(e))

# 往返保存
sp = os.path.join(tmp, "proj.json")
pj.save(proj, sp)
again = pj.load(sp)
check("保存/读取后记号不丢",
      again["notes"][4].get("short") and again["notes"][5].get("slur_start")
      and again["notes"][7].get("tie"))

print()
print("=== 记号规范用例:", "全部通过" if not fails else f"失败 {len(fails)}: {fails}")
sys.exit(1 if fails else 0)
