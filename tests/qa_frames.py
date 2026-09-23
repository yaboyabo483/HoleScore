# -*- coding: utf-8 -*-
"""QA：整段括号（前奏/间奏/和声伴唱）与「第 n 结尾」框（房子记号）—— 零 GUI 依赖

覆盖：
  1. 解析         （ ） ( )  -> bracket 起止；[n / n] -> ending 起止（`1]` 的 1 不被音符吃掉）
  2. 框类语义      不占时值、不是小节边界、不顶掉相邻小节线；贴着小节边界的那一侧
                  按记谱口径让位（起在小节线后、止在小节线前）
  3. 配对         pair_frames 配对 / 嵌套 / 缺一半的检测
  4. 记号往返      token_of <-> token_to_doc（（ ） [1 1] ）
  5. 工程侧        display_notes 保留 + 可选中；缺一半时 build_render_inputs 出提示
  6. 两条实现一致   display_notes（编谱器）与 insert_auto_bars（导出）给出同一串记号
  7. 渲染几何      括号两侧贴在起止格边缘、高度与数字齐平；结尾框横线/短钩/标号位置
  8. 不重叠       结尾框横线压在这一段最深处连音弧线之上（按实际内容算），
                 行顶留白够（不压上一行音名）、页眉留白够（不压图例）
  9. 谱面大小      100/85/70/50% 各档下这些不变量仍成立

运行：任意带标准库的 Python
  python tests/qa_frames.py
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


def parse_ev(text, beats="4/4"):
    return jianpu.insert_auto_bars(jianpu.parse(text).events, beats)


def tokens(events):
    return [e.token for e in events]


def parse_plain(text):
    """不插自动小节线（列号就是记号顺序，方便按列核对几何）"""
    return jianpu.parse(text).events


def num(v):
    """照抄 render 的整数友好规则：整数基准乘出来是整数就写成 int。

    render 的坐标是直接 format 出来的（`y="171"` 而不是 `y="171.0"`），
    测试拿 float 反推期望字符串时必须同样收一下，否则一个字都匹配不到。
    """
    return int(v) if float(v).is_integer() else v


def render_of(text, beats="4/4", scale=None, **kw):
    """渲染一次并返回 (svg, events, layout)

    scale=None 表示「用 render 当前的谱面大小」（放在 content_scale_ctx 里跑时就用它）；
    给了数就临时套一下（画完自动还原）。
    """
    score = jianpu.parse(text)
    score.events = jianpu.insert_auto_bars(score.events, beats)
    results, warnings = fingering.map_score(score.events, score.tonic, "D")
    if scale is not None:
        kw["content_scale"] = scale
    svg = render.render_svg(score, results, title="QA", key=score.key, whistle_key="D",
                            warnings=warnings, beats=beats, **kw)
    return svg, score.events, list(render._LAYOUT)


# ---------------- 1. 解析 ----------------
print("—— 解析 ——")

ev = parse_plain("1 2 （ 3 4 ） 5")
check("全角括号解析成 bracket 起止",
      [(i, e.kind, getattr(e, "direction", None)) for i, e in enumerate(ev)
       if e.kind == "bracket"] == [(2, "bracket", "start"), (5, "bracket", "end")],
      str([(i, e.kind, getattr(e, "direction", None)) for i, e in enumerate(ev)]))

ev = parse_plain("1 2 ( 3 4 ) 5")
check("半角括号同样认（人工输入常用半角）",
      [e.kind for e in ev] == ["note", "note", "bracket", "note", "note", "bracket", "note"],
      str([e.kind for e in ev]))

check("紧跟数字的括号仍是连音线后缀（`1(` 不是整段括号）",
      [(e.kind, bool(getattr(e, "slur_start", False))) for e in parse_plain("1( 2")]
      == [("note", True), ("note", False)],
      str([(e.kind, bool(getattr(e, "slur_start", False))) for e in parse_plain("1( 2")]))

ev = parse_plain("[1 3 3 3 3 1]")
check("[1 / 1] 解析成 ending 起止，序号都读到了",
      [(e.kind, e.direction, e.ending) for e in ev
       if e.kind == "ending"] == [("ending", "start", 1), ("ending", "end", 1)],
      str([(e.kind, getattr(e, "direction", None), getattr(e, "ending", None))
           for e in ev]))

ev = parse_plain("2] [3")
check("序号写在终点上也认（2] / [3）",
      [(e.direction, e.ending) for e in ev if e.kind == "ending"]
      == [("end", 2), ("start", 3)],
      str([(e.direction, getattr(e, "ending", None)) for e in ev]))

# 这是踩过的坑：`1]` 必须排在音符分支**之前**，否则 1 被当成音符吃掉、只剩下一个 ]
ev = parse_plain("1]")
check("`1]` 里的数字不被音符分支吃掉（只剩一个孤零零的 ]）",
      len(ev) == 1 and ev[0].kind == "ending" and ev[0].direction == "end",
      str([(e.kind, e.token) for e in ev]))
check("`1]` 的 token 是 `1]`（不是 `1` + `]`）", tokens(ev) == ["1]"], str(tokens(ev)))
ev = parse_plain("[1")
check("`[1` 单独出现也是 ending 起点", tokens(ev) == ["[1"] and ev[0].ending == 1,
      str([(e.kind, e.token) for e in ev]))

# ---------------- 2. 框类语义（不占时值 / 不是小节边界） ----------------
print("—— 框类语义 ——")

ev = parse_ev("1 2 （ 3 4")
check("括号落在一小节中间，不会把小节切成两段",
      tokens(ev) == ["1", "2", "（", "3", "4", "|"], str(tokens(ev)))

ev = parse_ev("1 2 3 4 （ 5 6 7 1 ）")
check("括号不顶掉相邻的小节线，且贴边界的那一侧按记谱口径让位（起在小节线后、止在小节线前）",
      tokens(ev) == ["1", "2", "3", "4", "|", "（", "5", "6", "7", "1", "）", "|"],
      str(tokens(ev)))

ev = parse_ev("[1 3 3 3 3 1]")
check("结尾框不占时值：4 个音仍按 4/4 各占一小节，收尾 `1]` 留在小节线之前",
      tokens(ev) == ["[1", "3", "3", "3", "3", "1]", "|"], str(tokens(ev)))

# 贴着小节边界的那一侧要让位（记谱口径）：**起在小节线后、止在小节线前**
ev = parse_ev("（ 5 6 5 3 ） 1 2 3 4 1 2 3 4")
check("括号起落在小节线之后、括号止落在小节线之前",
      tokens(ev) == ["（", "5", "6", "5", "3", "）", "|", "1", "2", "3", "4", "|",
                     "1", "2", "3", "4", "|"],
      str(tokens(ev)))

ev = parse_ev("（ 5 6 5 3 ） （ 1 2 3 4 ）")
check("两个括号背靠背时也各归各位（前一个的止在前、后一个的起在后）",
      tokens(ev) == ["（", "5", "6", "5", "3", "）", "|",
                     "（", "1", "2", "3", "4", "）", "|"],
      str(tokens(ev)))

ev = parse_ev("|: 5 5 6 5 [1 1 2 3 4 1] :|")
check("结尾框同样：`[n` 落在小节线之后、`n]` 落在小节线之前",
      tokens(ev) == ["|:", "5", "5", "6", "5", "|",
                     "[1", "1", "2", "3", "4", "1]", ":|"],
      str(tokens(ev)))

check("让位只是挪记号位置，小节线的条数不多不少",
      tokens(parse_ev("（ 5 6 5 3 ） 1 2 3 4")).count("|") == 2,
      str(tokens(parse_ev("（ 5 6 5 3 ） 1 2 3 4"))))

check("is_frame_close 只认收尾那一侧（`）` `n]`）",
      [jianpu.is_frame_close(*a) for a in
       (("bracket", "end"), ("bracket", "start"), ("ending", "end"),
        ("ending", "start"), ("note", "end"), ("note", ""))]
      == [True, False, True, False, False, False],
      "bracket/ending 的 end 才算收尾")

ev = parse_ev("|: 1 2 3 4 [1 5 5 5 5 1] :| [2 6 6 6 6 2] |")
check("结尾框 + 反复记号能一起用（反复边界照旧，框子只是记号）",
      [e.token for e in ev if e.kind in ("repeat", "ending")]
      == ["|:", "[1", "1]", ":|", "[2", "2]"],
      str(tokens(ev)))

che = parse_ev("1 2 3 |: 4 5 6 7 [1 1 1 1 1 1] :|")
check("结尾框不会造成「小节线 + 反复记号」相邻（旧的相邻 bug 没被它带回来）",
      not any("bar" in (che[i].kind, che[i + 1].kind)
              and "repeat" in (che[i].kind, che[i + 1].kind)
              for i in range(len(che) - 1)),
      str(tokens(che)))

check("FRAME_KINDS 口径统一（jianpu 与 project 是同一个元组）",
      jianpu.FRAME_KINDS == pj.FRAME_KINDS == ("bracket", "ending"),
      f"{jianpu.FRAME_KINDS} / {pj.FRAME_KINDS}")

# ---------------- 3. 配对 ----------------
print("—— 配对 ——")

ev = parse_plain("（ 1 2 ） （ 3 4 ）")
check("两组括号各自配对",
      jianpu.pair_frames(ev, "bracket")[0] == [(0, 3, 0), (4, 7, 0)],
      str(jianpu.pair_frames(ev, "bracket")))

ev = parse_plain("[1 1 1 [2 2 2 2] 1]")
pairs, unpaired = jianpu.pair_frames(ev, "ending")
check("结尾框按栈配对，嵌套也能各归各的",
      pairs == [(3, 6, 2), (0, 7, 1)] and not unpaired, f"{pairs} / {unpaired}")

ev = parse_plain("[1 1 1 1] [2 2 2 2]")
check("先 1 后 2 的常见写法配对正确",
      jianpu.pair_frames(ev, "ending")[0] == [(0, 3, 1), (4, 7, 2)],
      str(jianpu.pair_frames(ev, "ending")))

ev = parse_plain("1 2 [1 3 4")
pairs, unpaired = jianpu.pair_frames(ev, "ending")
check("只写了起点 => 配不上对，进 unpaired",
      pairs == [] and unpaired == [(2, "start", 1)], f"{pairs} / {unpaired}")
ev = parse_plain("1 2 3] 4")
pairs, unpaired = jianpu.pair_frames(ev, "ending")
check("只写了终点 => 同样进 unpaired",
      pairs == [] and unpaired == [(2, "end", 3)], f"{pairs} / {unpaired}")

check("配对了的一种记号不会跑到另一种里去",
      jianpu.pair_frames(parse_plain("（ [1 1] ）"), "bracket")[0] == [(0, 3, 0)],
      str(jianpu.pair_frames(parse_plain("（ [1 1] ）"), "bracket")))

# ---------------- 4. 记号往返 ----------------
print("—— 记号往返 ——")

for _tok in ("（", "）", "[1", "1]", "[2", "2]"):
    _d = pj.token_to_doc(_tok)
    _back = pj.token_of(_d) if _d else None
    check(f"往返 {_tok}",
          _d is not None and pj.token_to_doc(_back) == _d,
          f"{_tok} -> {_d} -> {_back}")
    check(f"往返 {_tok}：文本逐字不变", _back == _tok, f"{_tok} -> {_back}")

check("半角括号归一成全角存盘",
      pj.token_of(pj.token_to_doc("(")) == "（"
      and pj.token_of(pj.token_to_doc(")")) == "）")
check("new_bracket / new_ending 生成对应记号",
      pj.token_of(pj.new_bracket("end")) == "）"
      and pj.token_of(pj.new_ending("start", 3)) == "[3"
      and pj.token_of(pj.new_ending("end", 3)) == "3]")
check("new_ending 序号越界时夹回 1（不会写出 [0）",
      pj.token_of(pj.new_ending("start", 0)) == "[1",
      pj.token_of(pj.new_ending("start", 0)))
check("框类记号都在 NON_TIMED 里（排版分隔符口径统一）",
      all(k in pj.NON_TIMED for k in jianpu.FRAME_KINDS), str(pj.NON_TIMED))

# ---------------- 5. 工程侧 ----------------
print("—— 工程侧 ——")


def proj_of(text, beats="4/4", auto=True):
    p = pj.new_project("框", "D", "D", beats, auto)
    for tk_ in text.split():
        p["notes"].append(pj.token_to_doc(tk_))
    return p


p_br = proj_of("1 2 （ 3 4 ） 5 6 7 1")
shown, imap = pj.display_notes(p_br)
check("工程展示序列保留括号（两条实现都保留）",
      [pj.token_of(d) for d in shown if d.get("kind") == pj.KIND_BRACKET] == ["（", "）"],
      str([pj.token_of(d) for d in shown]))
br_idx = [i for i, d in enumerate(shown) if d.get("kind") == pj.KIND_BRACKET]
check("括号可被选中（映射指向文档下标，不是 None）",
      all(imap[i] is not None for i in br_idx), str([imap[i] for i in br_idx]))

p_en = proj_of("|: 1 2 3 4 [1 5 5 5 5 1] :| [2 6 6 6 6 2] |")
shown_e, imap_e = pj.display_notes(p_en)
check("工程展示序列保留结尾框（含序号）",
      [pj.token_of(d) for d in shown_e if d.get("kind") == pj.KIND_ENDING]
      == ["[1", "1]", "[2", "2]"],
      str([pj.token_of(d) for d in shown_e]))
en_idx = [i for i, d in enumerate(shown_e) if d.get("kind") == pj.KIND_ENDING]
check("结尾框可被选中", all(imap_e[i] is not None for i in en_idx),
      str([imap_e[i] for i in en_idx]))

_score, _res, warns, _key = pj.build_render_inputs(proj_of("1 2 （ 3 4"))
check("缺右括号 => 导出前给出提示（画不出框来，只能提醒补另一半）",
      len(warns) == 1 and "括号" in warns[0] and "缺另一半" in warns[0], str(warns))
_score, _res, warns, _key = pj.build_render_inputs(proj_of("1 2 [1 3 4"))
check("结尾框缺终点 => 同样有提示",
      len(warns) == 1 and "结尾框" in warns[0] and "缺另一半" in warns[0], str(warns))
_score, _res, warns, _key = pj.build_render_inputs(proj_of("1 2 （ 3 4 ）"))
check("括号成对 => 不再报「缺一半」",
      not any("括号" in w for w in warns), str(warns))

# 存盘往返
import tempfile
_tmp = tempfile.mkdtemp()
_sp = os.path.join(_tmp, "frames.json")
pj.save(p_en, _sp)
_again = pj.load(_sp)
check("保存/读取后框类记号不丢（含序号）",
      [pj.token_of(d) for d in _again["notes"] if d.get("kind") == pj.KIND_ENDING]
      == ["[1", "1]", "[2", "2]"],
      str([pj.token_of(d) for d in _again["notes"]]))

# ---------------- 6. 两条实现一致 ----------------
print("—— 两条实现一致（编谱器 display_notes / 导出 insert_auto_bars）——")

for _txt in ("1 2 （ 3 4 ） 5 6 7 1",
             "|: 1 2 3 4 [1 5 5 5 5 1] :| [2 6 6 6 6 2] |",
             "1 2 3 |: 4 5 6 7 [1 1 1 1 1 1] :|",
             "[1 1 1 [2 2 2 2] 1]",
             "（ 5 6 5 3 ） 1 2 3 4 1 2 3 4",
             "（ 5 6 5 3 ） （ 1 2 3 4 ）",
             "|: 5 5 6 5 [1 1 2 3 4 1] :|"):
    _a = tokens(parse_ev(_txt))
    _b = [pj.token_of(d) for d in pj.display_notes(proj_of(_txt))[0]]
    check(f"两条实现给出同一串记号：{_txt}", _a == _b, f"导出 {_a} / 编谱器 {_b}")

# ---------------- 7. 渲染几何 ----------------
print("—— 渲染几何：整段括号 ——")

svg_br, ev_br, lay_br = render_of("1 2 （ 3 4 ） 5 6 7 1", beats="")
_br_cols = [i for i, e in enumerate(ev_br) if e.kind == "bracket"]
check("用例有效：谱里有两个 bracket", len(_br_cols) == 2, str(_br_cols))

top_dy = render.DIGIT_TOP_DY - render.BRACKET_UP
bot_dy = render.DIGIT_BOT_DY + render.BRACKET_DOWN
b = render.BRACKET_BULGE
for _i, _side in zip(_br_cols, ("start", "end")):
    _x, _w, _top = lay_br[_i]
    _y0, _y1 = _top + top_dy, _top + bot_dy
    _ym = (_y0 + _y1) / 2
    if _side == "start":
        _want = (f'M {_x + b} {_y0} Q {_x} {_ym} {_x + b} {_y1}')
    else:
        _want = (f'M {_x + _w - b} {_y0} Q {_x + _w} {_ym} {_x + _w - b} {_y1}')
    check(f"左/右括号画在{'起点那格左缘' if _side == 'start' else '终点那格右缘'}"
          f"（{_side}）",
          f'<path d="{_want}" fill="none" stroke="{render.C_TEXT}"' in svg_br,
          f"期望 {_want}")
check("括号高度与简谱数字齐平（不拉到笛身、不进歌词带）",
      bot_dy - top_dy < render.FLUTE_TOP_DY - render.DIGIT_TOP_DY,
      f"括号 {top_dy}..{bot_dy} 笛身顶 {render.FLUTE_TOP_DY}")

# 贴边界的让位落到几何上就是：**右括号在紧跟其后的小节线左边、左括号在前一条线右边**
# （小节线画在自己那格的**中间**，见 render 的 `<line x1="{cx}" …`）
svg_bo, ev_bo, lay_bo = render_of("（ 5 6 5 3 ） 1 2 3 4 （ 1 2 3 4 ）")
_bar_kinds = ("bar", "repeat")


def _cx(k):
    return lay_bo[k][0] + lay_bo[k][1] / 2


_bad, _seen = [], set()
for _i, _e in enumerate(ev_bo):
    if _e.kind != "bracket":
        continue
    if _e.direction == "end":
        _x = lay_bo[_i][0] + lay_bo[_i][1]                 # 右括号＝自己那格的右缘
        if _i + 1 < len(ev_bo) and ev_bo[_i + 1].kind in _bar_kinds:
            _seen.add("end")
            if not _x < _cx(_i + 1):
                _bad.append(("end", _i, round(_x, 1), round(_cx(_i + 1), 1)))
    else:
        _x = lay_bo[_i][0]                                 # 左括号＝自己那格的左缘
        if _i > 0 and ev_bo[_i - 1].kind in _bar_kinds:
            _seen.add("start")
            if not _x > _cx(_i - 1):
                _bad.append(("start", _i, round(_x, 1), round(_cx(_i - 1), 1)))
check("用例有效：起止两侧都真的贴着小节线（让位才看得出来）",
      _seen == {"start", "end"}, str(_seen))
check("几何上右括号在小节线左边、左括号在小节线右边（贴边界的让位真落到了坐标上）",
      not _bad, f"不合位的 {_bad}")
check("括号上端比数字字形顶再高一点、下端低于数字基线（盖住低八度点）",
      top_dy < render.DIGIT_TOP_DY and bot_dy > render.DIGIT_BOT_DY)
check("括号格比正常格窄（就一道弧，不占满格）",
      all(abs(lay_br[i][1] - render.CELL_W * render.BRACKET_CELL_RATIO) < 1e-6
          for i in _br_cols),
      str([lay_br[i][1] for i in _br_cols]))
check("括号两侧各自自足：各自画在自己那一格，不依赖配对",
      not jianpu.pair_frames(parse_plain("（ 1 2"), "bracket")[0]      # 只有一侧
      and f'M {lay_br[_br_cols[0]][0] + b} ' in svg_br)               # 照样画出来了

print("—— 渲染几何：第 n 结尾框 ——")

svg_en, ev_en, lay_en = render_of("1 2 3 4 [1 5 5 5 5 1] :| [2 6 6 6 6 2] |", beats="4/4")
_line_re = re.compile(
    r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)" '
    r'stroke="%s" stroke-width="%s"/>'
    % (re.escape(render.C_TEXT), re.escape(str(render._s(1.4)))))
_hlines = [(float(a), float(bb), float(c), float(dd)) for a, bb, c, dd in _line_re.findall(svg_en)
           if abs(float(bb) - float(dd)) < 1e-6 and abs(float(c) - float(a)) > 1.0]
_en_pairs = jianpu.pair_frames(ev_en, "ending")[0]
check("用例有效：谱里有两个结尾框", len(_en_pairs) == 2, str(_en_pairs))
check("每个结尾框都画出一条横线（不多不少）", len(_hlines) == len(_en_pairs),
      f"横线 {_hlines} / 框 {_en_pairs}")

for (i0, i1, n), (x0, y, x1, _y) in zip(_en_pairs, _hlines):
    _x0 = lay_en[i0][0]
    _x1 = lay_en[i1][0] + lay_en[i1][1]
    _y = lay_en[i0][2] + render.ending_top_offset(ev_en, i0, i1)
    check(f"第 {n} 结尾框：横线从起点格左缘到终点格右缘",
          abs(x0 - _x0) < 1e-6 and abs(x1 - _x1) < 1e-6, f"{x0}..{x1} 期望 {_x0}..{_x1}")
    check(f"第 {n} 结尾框：横线高度 = 行顶 + ending_top_offset（按内容算）",
          abs(y - _y) < 1e-6, f"{y} 期望 {_y}")
    check(f"第 {n} 结尾框：横线落在行顶**上方**",
          y < lay_en[i0][2], f"横线 {y} 行顶 {lay_en[i0][2]}")
    check(f"第 {n} 结尾框：左端有向下的短钩",
          f'<line x1="{num(_x0)}" y1="{num(_y)}" x2="{num(_x0)}" '
          f'y2="{num(_y + render.ENDING_TICK)}" '
          f'stroke="{render.C_TEXT}"' in svg_en,
          f"期望短钩 y {num(_y)}..{num(_y + render.ENDING_TICK)}")
    check(f"第 {n} 结尾框：右端也有向下的短钩",
          f'<line x1="{num(_x1)}" y1="{num(_y)}" x2="{num(_x1)}" '
          f'y2="{num(_y + render.ENDING_TICK)}" '
          f'stroke="{render.C_TEXT}"' in svg_en,
          f"期望短钩 @ x={num(_x1)}")
    check(f"第 {n} 结尾框：标号「{n}.」贴在横线下方左端",
          f'<text x="{num(_x0 + render.ENDING_INSET)}" '
          f'y="{num(_y + render.ENDING_TEXT_SIZE)}" '
          f'font-size="{num(render.ENDING_TEXT_SIZE)}" font-weight="bold" '
          f'fill="{render.C_TEXT}">{n}.</text>' in svg_en,
          f"期望标号 @ x={num(_x0 + render.ENDING_INSET)} y={num(_y + render.ENDING_TEXT_SIZE)}")

try:
    minidom.parseString(svg_en)
    check("结尾框 SVG XML 合法", True)
except Exception as e:
    check("结尾框 SVG XML 合法", False, str(e))
check("结尾框记号格比括号格更窄（框子画在上方，这一格只是让它有个位置）",
      render.ENDING_CELL_RATIO < render.BRACKET_CELL_RATIO)
check("数字上方不画「1」：结尾框那一格自己不画任何笔画",
      all(_hlines) and render._simple_cell(
          [e for e in ev_en if e.kind == "ending"][0], 0, 0) == "")

# ---------------- 8. 不重叠（按实际内容算） ----------------
print("—— 结尾框不压记号 / 不压上一行 / 不压图例 ——")

# 这一段里最难摆的几种：换气 v、高八度点、落在这段里的连音弧线（嵌套三层）
CASES = {
    "朴素": "1 2 3 4 [1 5 5 5 5 1] :|",
    "换气+高八度": "1 2 3 4 [1 5'v 5'v 5'v 5'v 1] :|",
    "嵌套连音": "1 2 3 4 [1 1( 2( 3( 4 3) 2) 1) 1] :|",
}
for _tag, _txt in CASES.items():
    _svg, _ev, _lay = render_of(_txt, beats="4/4")
    _pairs = jianpu.pair_frames(_ev, "ending")[0]
    _spans = beaming.slur_spans(_ev)
    for i0, i1, _n in _pairs:
        _off = render.ending_top_offset(_ev, i0, i1)
        _labels = [render._label_top(_ev[i], 0.0) for i in range(i0, i1 + 1)]
        _inside = [sp for sp in _spans if i0 <= sp["i0"] and sp["i1"] <= i1]
        if _inside:
            _depth = max(min(3, beaming.span_depth(_spans, sp)) for sp in _inside)
            _apex = (min(_labels) - render.SLUR_GAP
                     - _depth * render.SLUR_NEST - render.SLUR_H)
            check(f"[{_tag}] 横线压在最深连音弧线之上（净空 ≥ ENDING_GAP）",
                  _off <= _apex - render.ENDING_GAP + 1e-6,
                  f"框 {_off} vs 弧顶 {_apex}（净空 {_apex - _off:.2f}）")
        else:
            check(f"[{_tag}] 横线压在本段最靠上的记号之上（净空 ≥ ENDING_GAP）",
                  _off <= min(_labels) - render.ENDING_GAP + 1e-6,
                  f"框 {_off} vs 记号区顶 {min(_labels)}")
    # 行顶留白：加进 row_height 的 _ENDING_SHIFT 要够（不压上一行的音名）
    check(f"[{_tag}] 行顶留白够（base_row_slack + _ENDING_SHIFT ≥ 需要量）",
          render.base_row_slack() + render._ENDING_SHIFT + 0.999
          >= render.ending_top_need(_ev) + render.ENDING_MARGIN - 1e-6,
          f"余量 {render.base_row_slack()} + 让位 {render._ENDING_SHIFT} "
          f"vs 需要 {render.ending_top_need(_ev)} + {render.ENDING_MARGIN}")
    # 页眉留白：首页标题区 / 后续页紧凑页眉都不能被框子压到
    _min_off = min(render.ending_top_offset(_ev, a, c)
                   for a, c, _x in jianpu.pair_frames(_ev, "ending")[0])
    for _first, _ink in ((True, render.HEADER_INK_BOTTOM),
                         (False, render.COMPACT_HEADER_INK_BOTTOM)):
        check(f"[{_tag}] {'首页' if _first else '后续页'}页眉留白够（框子不压图例）",
              render.header_h(_first) + _min_off >= _ink,
              f"页眉 {render.header_h(_first)} + 框 {_min_off} vs 墨迹下沿 {_ink}")

# 朴素结尾框本来就不该多留头顶空间（别白占行高）
_svg_p, _ev_p, _ = render_of("1 2 3 4 [1 5 5 5 5 1] :|", beats="4/4")
check("朴素结尾框不需要额外行高（行顶原本的余量就够吃）",
      render._ENDING_SHIFT == 0, render._ENDING_SHIFT)
_svg_d, _ev_d, _ = render_of(CASES["嵌套连音"], beats="4/4")
check("嵌套连音压上来时，行高才跟着长",
      render._ENDING_SHIFT > 0, render._ENDING_SHIFT)
check("行高确实把让位量加进去了（row_height = 基准 + 歌词 + 让位）",
      render.row_height() == (render.ROW_H + render._LYRIC_SHIFT + render.ROW_GAP
                              + render._ENDING_SHIFT),
      render.row_height())
check("没有结尾框的谱子：一点头顶空间都不多留",
      render.ending_top_need(parse_ev("1 2 3 4 5 6 7 1")) == 0.0)

# ---------------- 9. 谱面大小各档 ----------------
print("—— 谱面大小各档（不变量仍成立）——")

# 注意：render 的模块状态就是「当前谱面大小」，所以整套量测都要放在 ctx 里做
# —— 出了 ctx 再问 ending_top_offset / header_h 拿到的是 100% 的数，两边对不上。
for _cs in (100, 85, 70, 50):
    with render.content_scale_ctx(_cs):
        _txt = CASES["嵌套连音"]
        _svg, _ev, _lay = render_of(_txt, beats="4/4")      # 用当前状态 = _cs
        _pairs = jianpu.pair_frames(_ev, "ending")[0]
        _spans = beaming.slur_spans(_ev)
        _ok_arc, _ok_row, _ok_head = True, True, True
        for i0, i1, _n in _pairs:
            _off = render.ending_top_offset(_ev, i0, i1)
            _labels = [render._label_top(_ev[i], 0.0) for i in range(i0, i1 + 1)]
            _inside = [sp for sp in _spans if i0 <= sp["i0"] and sp["i1"] <= i1]
            _apex = min(_labels) - render.SLUR_GAP
            if _inside:
                _apex -= (max(min(3, beaming.span_depth(_spans, sp)) for sp in _inside)
                          * render.SLUR_NEST + render.SLUR_H)
            if not (_off <= _apex - render.ENDING_GAP + 1e-6):
                _ok_arc = False
        if not (render.base_row_slack() + render._ENDING_SHIFT + 0.999
                >= render.ending_top_need(_ev) + render.ENDING_MARGIN - 1e-6):
            _ok_row = False
        _min_off = min(render.ending_top_offset(_ev, a, c) for a, c, _x in _pairs)
        _heads = []
        for _first, _ink in ((True, render.HEADER_INK_BOTTOM),
                             (False, render.COMPACT_HEADER_INK_BOTTOM)):
            _h = render.header_h(_first)
            _heads.append(f"{'首页' if _first else '后续'} {_h}+{_min_off}"
                          f"={_h + _min_off} vs {_ink}")
            if not (_h + _min_off >= _ink):
                _ok_head = False
        check(f"谱面 {_cs}%：框子仍压在连音弧线之上", _ok_arc,
              f"shift={render._ENDING_SHIFT} need={render.ending_top_need(_ev)}")
        check(f"谱面 {_cs}%：行顶留白仍够（不压上一行音名）", _ok_row,
              f"slack={render.base_row_slack()} shift={render._ENDING_SHIFT}")
        check(f"谱面 {_cs}%：页眉留白仍够（不压图例）", _ok_head, "; ".join(_heads))
        try:
            minidom.parseString(_svg)
            check(f"谱面 {_cs}%：SVG XML 合法", True)
        except Exception as e:
            check(f"谱面 {_cs}%：SVG XML 合法", False, str(e))

# 切音窄格 + 括号混排：不越出页面右缘（跨格记号也能跟着窄格铺排）
svg_mix, ev_mix, lay_mix = render_of(
    " ".join(["5! 6 （ 5! 6 ）"] * 10), beats="4/4", row_measures=4)
_rows = sorted({y for _x, _w, y in lay_mix})
_fit = True
for _r in _rows:
    _cells = [(x, w) for x, w, y in lay_mix if y == _r]
    if _cells and _cells[-1][0] + _cells[-1][1] > render.MARGIN + (render.PAGE_WIDTH
                                                                  - 2 * render.MARGIN) + 1e-6:
        _fit = False
check("切音窄格 + 括号混排不越出页面右缘", _fit, f"行数 {len(_rows)}")
check("混排时会正常换行", len(_rows) > 1, str(len(_rows)))

print()
print("=== 框类记号用例:", "全部通过" if not fails else f"失败 {len(fails)}: {fails}")
sys.exit(1 if fails else 0)
