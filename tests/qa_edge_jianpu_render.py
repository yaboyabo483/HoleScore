# -*- coding: utf-8 -*-
"""QA 独立边界用例：jianpu.parse + render（非 selftest 复用）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xml.dom.minidom as minidom

from tinwhistle import beaming, jianpu, fingering, render

fails = []
def check(name, cond, detail=""):
    tag = "OK " if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)

# ---------- jianpu.parse ----------
# 1. 时值后缀 5/ 5//
s = jianpu.parse("5/ 5// 3")
durs = [e.duration for e in s.notes]
check("时值 5/=0.5 5//=0.25 3=1.0", durs == [0.5, 0.25, 1.0], str(durs))

# 2. 调号头 "1=bB"
s = jianpu.parse("1=bB 1 2 3")
check("1=bB 调号", s.key == "bB" and s.key_source == "text", f"{s.key}/{s.key_source}")
check("1=bB 的 1 不被当音符（应3音）", len(s.notes) == 3, str(len(s.notes)))

# 3. 全角 "1＝G"
s = jianpu.parse("1＝G 5 6")
check("全角等号 1＝G", s.key == "G" and s.key_source == "text", f"{s.key}/{s.key_source}")
check("全角等号后音符数=2", len(s.notes) == 2, str(len(s.notes)))

# 4. 显式 key 覆盖谱内调号
s = jianpu.parse("1=G 1 2 3", key="C")
check("显式 C 覆盖谱内 G", s.key == "C" and s.key_source == "param", f"{s.key}/{s.key_source}")
check("覆盖后音符数=3", len(s.notes) == 3, str(len(s.notes)))

# 5. 非法记号混入
s = jianpu.parse("两只老虎 1 2 跑得快 3")
check("非法记号被忽略", len(s.notes) == 3 and len(s.ignored) > 0, str(s.ignored))

# 6. 空文本
s = jianpu.parse("")
check("空文本", s.notes == [] and s.key == "D" and s.key_source == "default")

s = jianpu.parse("   \n  ")
check("纯空白文本", s.notes == [])

# 7. "1=G" 出现在文本中间
s = jianpu.parse("3 4 1=G 5")
check("调号头在中间也剔除", len(s.notes) == 3 and s.key == "G", f"{len(s.notes)}/{s.key}")

# 8. rest 时值
s = jianpu.parse("0/ 0// 0")
durs = [e.duration for e in s.events if e.kind == "rest"]
check("休止符时值 0/ 0// 0", durs == [0.5, 0.25, 1.0], str(durs))

# 9. 连续无空格记号串
s = jianpu.parse("1235")
check("连续无空格 1235 -> 4音", len(s.notes) == 4, str(len(s.notes)))
s = jianpu.parse("5/3//1")
ds = [e.duration for e in s.notes]
check("连续带时值 5/3//1", ds == [0.5, 0.25, 1.0], str(ds))

# 10. 八度组合
s = jianpu.parse("6. 1' 6.. 1''")
octs = [e.octave for e in s.notes]
check("八度 6.=-1 1'=+1 6..=-2 1''=+2", octs == [-1, 1, -2, 2], str(octs))

# 11. 升降号
s = jianpu.parse("#4 b7")
accs = [(e.accidental, e.semitone) for e in s.notes]
check("#4=+1 b7=-1", accs == [(1, 6), (-1, 10)], str(accs))

# 12. 延音与小节线
s = jianpu.parse("5 - 5 | 3")
kinds = [e.kind for e in s.events]
check("延音/小节线 kinds", kinds == ["note", "hold", "note", "bar", "note"], str(kinds))

# 13. normalize_key 边界
check("normalize_key('g')", jianpu.normalize_key("g") == "G")
check("normalize_key('Bb')", jianpu.normalize_key("Bb") == "bB")
check("normalize_key('♭E')", jianpu.normalize_key("♭E") == "bE")
check("normalize_key('H')", jianpu.normalize_key("H") is None)
check("normalize_key(None)", jianpu.normalize_key(None) is None)

# 14. 非法调抛 ValueError
try:
    jianpu.parse("1 2 3", key="H")
    check("非法调 H 抛错", False)
except ValueError:
    check("非法调 H 抛错", True)

# 15. OCR 常见误识别归一化：O->0, l->1
s = jianpu.parse("l 2 O")
check("O/l 归一化 (1 2 0)", len(s.notes) == 2 and len([e for e in s.events if e.kind=="rest"]) == 1,
      str([(e.kind, e.token) for e in s.events]))

# ---------- render ----------
def make_svg(text, key=None):
    score = jianpu.parse(text, key=key)
    results, warnings = fingering.map_score(score.events, score.tonic, "D")
    svg = render.render_svg(score, results, title="QA", key=score.key,
                            whistle_key="D", warnings=warnings,
                            key_source=score.key_source)
    return svg, score

# R1. 十六分+低八度组合 SVG 合法
svg, score = make_svg("6.// 5.// 1'// 2'/ 3")
try:
    minidom.parseString(svg)
    check("十六分+低八度 SVG XML 合法", True)
except Exception as e:
    check("十六分+低八度 SVG XML 合法", False, str(e))

# R2. 每个音符都有简谱 label：音符数 == 粗体数字 text 数
import re as _re
note_count = len(score.notes)
digit_texts = _re.findall(r'font-size="26" font-weight="bold"[^>]*>(\d)</text>', svg)
check("每个音符带简谱 label", len(digit_texts) == note_count,
      f"labels={len(digit_texts)} notes={note_count}")

# R3. 减时线连尾（新规范）：同一拍内的十六分/八分共用一条**连续**横线
#     6.// 5.// 1'// 2'/ 同属第一拍 => 第一条线贯穿 0..3；第二条线只盖三个十六分 0..2
beams = beaming.beam_segments(score.events, "4/4")
check("同拍短音符连尾成组", beams[:2] == [(0, 3, 0), (0, 2, 1)], str(beams))
_b_y = render.HEADER_H + render.LABEL_DY + render.BEAM_DY
_b_x0 = render.MARGIN + render.CELL_W / 2 - render.UNDERLINE_W / 2
_b_x1 = render.MARGIN + 3 * render.CELL_W + render.CELL_W / 2 + render.UNDERLINE_W / 2
check("连尾横线贯穿整组（一条连续线）",
      f'<line x1="{_b_x0}" y1="{_b_y}" x2="{_b_x1}" y2="{_b_y}"' in svg,
      f"期望 x1={_b_x0} x2={_b_x1} y={_b_y}")
_b2_y = _b_y + render.UNDERLINE_DY
_b2_x1 = render.MARGIN + 2 * render.CELL_W + render.CELL_W / 2 + render.UNDERLINE_W / 2
check("十六分第二条线只盖十六分音符",
      f'<line x1="{_b_x0}" y1="{_b2_y}" x2="{_b2_x1}" y2="{_b2_y}"' in svg,
      f"期望 x1={_b_x0} x2={_b2_x1} y={_b2_y}")
# 四分音符（最后一个 3）不带减时线
check("四分音符不带减时线", all(not (i0 == 4 and i1 == 4) for i0, i1, _lv in beams), str(beams))

# R4. 调号来源标注
svg2, _ = make_svg("1=G 1 2 3")
check("谱内调号标注 (谱内标注)", "1 = G（谱内标注）" in svg2)
svg3, _ = make_svg("1 2 3", key="F")
check("指定调标注 (指定)", "1 = F（指定）" in svg3)
svg4, _ = make_svg("1 2 3")
check("默认调标注 (默认)", "1 = D（默认）" in svg4)

# R5. 低八度点在时值线之下（避让）：检查 dot cy > 数字 y + 16 + n*6
# 直接检查 SVG 中低八度 dot 的 cy 相对数字 y 的偏移
# 6.// 低八度+十六分：dot cy = 行顶+LABEL_DY+19+2*UNDERLINE_DY，列心由渲染常量推导
_ROW0_TOP = render.HEADER_H
_jy = _ROW0_TOP + render.LABEL_DY
_dot_cy = _jy + 19 + 2 * render.UNDERLINE_DY
_cx = render.MARGIN + render.CELL_W / 2
m = _re.search(rf'<circle cx="{_re.escape(str(_cx))}" cy="{_re.escape(str(_dot_cy))}"', svg)
check("低八度点避让时值线", m is not None,
      f"期望 cx={_cx} cy={_dot_cy}（由 render 常量推导）")

# R6. 休止也带时值线
svg5, _ = make_svg("0/ 1")
_line_x1 = _cx - render.UNDERLINE_W / 2
rest_lines = _re.findall(rf'<line x1="{_re.escape(str(_line_x1))}" [^>]*stroke-width="2.6"',
                         svg5)
check("休止 0/ 带 1 条时值线", len(rest_lines) == 1, str(len(rest_lines)))

# R6b. 自动移八度逻辑：6.. 超下界 -> shifted 且带警告
score6b = jianpu.parse("6.. 1 2 3")
r6b, w6b = fingering.map_score(score6b.events, score6b.tonic, "D")
check("6.. 自动升八度+警告", r6b[0].playable and r6b[0].shifted == 24 and len(w6b) == 1,
      f"shifted={r6b[0].shifted} warnings={w6b}")

# R7. 超音域策略验证（实际可达路径）：移八度 + 页脚警告（音符下面**不**压小字）
# 注意：map_note 的八度搬移使 playable=False 分支不可达（idx 总能折回 [0,24]），
# 红色警示框为死代码 —— 此处验证实际用户可见的警示链路
from tinwhistle.jianpu import NoteEvent
ev = NoteEvent(kind="note", token="1'''", degree=1, octave=3, semitone=36, index=0)
sc = jianpu.ParsedScore(events=[ev], tonic=0, key="C")
r7, w7 = fingering.map_score(sc.events, sc.tonic, "D")
svg7 = render.render_svg(sc, r7, title="t", key="C", whistle_key="D",
                         warnings=w7, key_source="default")
check("超音域自动移八度+警告", r7[0].playable and r7[0].shifted != 0 and len(w7) == 1
      and "超出音域" in w7[0], f"shifted={r7[0].shifted} w={w7}")
check("移八度不再在音符下压小字（信息只在页脚警示区）",
      "(已移八度)" not in svg7 and "超出音域" in svg7,
      "音符下仍有 (已移八度)" if "(已移八度)" in svg7 else "页脚警示缺失")
try:
    minidom.parseString(svg7)
    check("超音域 SVG XML 合法", True)
except Exception as e:
    check("超音域 SVG XML 合法", False, str(e))

# R8. 筒音指法口径（**导出侧**）：全按只在第一八度；高一个 / 高两个八度的筒音都要「放开孔1」。
#     直接从导出的 SVG 读孔位圆（cy + fill），不截图、不用浏览器。
#     回归锁：这里原来只给 idx 12 写了特例，idx 24 掉回 _FIRST_OCTAVE[0] 被画成全按。
svg8, score8 = make_svg("1 1' 1''")
_circ8 = [(float(cx), float(cy), float(r), fill)
          for cx, cy, r, fill in _re.findall(
              r'<circle cx="([-\d.]+)" cy="([-\d.]+)" r="([-\d.]+)" fill="([^"]+)"', svg8)]


def _col_marks(i):
    """第 i 格主笛身的孔位（孔1→孔6，从上到下）：● 按住 / ○ 放开"""
    cx_mid = render._cell_x(i) + render._cell_w(i) / 2
    col = sorted((cy, fill) for cx, cy, r, fill in _circ8
                 if abs(cx - cx_mid) < 0.6 and abs(r - render.HOLE_R) < 0.01)
    return "".join("●" if f != "#ffffff" else "○" for _cy, f in col)


_m0, _m1, _m2 = (_col_marks(i) for i in range(3))
check("导出：筒音 1 全按", _m0 == "●●●●●●", _m0)
check("导出：高八度筒音 1' 放开孔1（其余全按）", _m1 == "○●●●●●", _m1)
check("导出：高两个八度筒音 1'' 同样放开孔1（不许退回全按）", _m2 == "○●●●●●", _m2)

print()
print("=== jianpu/render 边界用例:", "全部通过" if not fails else f"失败 {len(fails)}: {fails}")
sys.exit(1 if fails else 0)
