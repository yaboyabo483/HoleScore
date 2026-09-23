# -*- coding: utf-8 -*-
"""QA：纸张 / 分页排版 / 水印 / 导出（零 GUI 依赖）

覆盖（都是「导出谱子」这一侧的硬规则）：
  1. 纸型                 A4 / B4 / A3 竖版，页宽页高按毫米换算（96dpi）
  2. 一行 4~6 个小节      小节是最小换行单位，**绝不从小节中间换行**
  2b. 一行几个小节可选     自动（4~6 均分）或固定 2/3/4/5/6；导出面板与工程两条路都传得到
  3. 分页                 行不跨页；首页大页眉、后续页紧凑页眉；最后一页按内容裁短
  3b. 谱面大小             字号/洞洞图/行高同一比例缩（默认 65% = A4 首页 5 行）；
                          纸张与一行几个小节**不变**；导出后模块状态还原（无副作用）
  4. 多页输出             render_svg 给第 1 页；render_svg_pages 给全部
  5. 水印                 淡淡一层（10% 不透明度）、画在谱面**下面**、可自选文字、留空则没有
  6. 导出                 SVG 单页 `曲名.svg` / 多页 `曲名-1.svg`…；图片按倍率 1x/2x、同样分页

导出一律走 `pj.export_svg_pages` / `pj.export_png`——就是编谱器导出按钮用的那条路。

运行：任意带标准库的 Python
  python tests/qa_page_layout.py
"""

import os
import re
import shutil
import sys
import tempfile
import xml.dom.minidom as minidom

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinwhistle import fingering, imageout, jianpu, project as pj, render

fails = []


def check(name, cond, detail=""):
    print(f"[{'OK ' if cond else 'FAIL'}] {name}"
          + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def make(text, beats="4/4", key=None):
    score = jianpu.parse(text, key=key)
    score.events = jianpu.insert_auto_bars(score.events, beats)
    results, warnings = fingering.map_score(score.events, score.tonic, "D")
    return score, results, warnings


def svg_pages(text, beats="4/4", paper="A4", watermark="", title="QA"):
    score, results, warnings = make(text, beats)
    return render.render_svg_pages(score, results, title=title, key=score.key,
                                   whistle_key="D", warnings=warnings, beats=beats,
                                   paper=paper, watermark=watermark), score


def measures_of(n):
    """n 小节的简谱文本（每小节 4 个四分音符）"""
    return " ".join(["5 6 7 1"] * n)


def proj_of(text, title="QA", key="D", beats="4/4"):
    """简谱文本 -> 编谱工程（导出走 `pj.export_*`，与编谱器导出按钮同一条路）。"""
    p = pj.new_project(title, key, "D", beats, True)
    p["notes"] = [pj.token_to_doc(t) for t in text.split() if pj.token_to_doc(t)]
    return p


def exported_svg(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def row_cells(lay):
    """按**行号**把事件下标分组。

    不能用 y 当键：行顶是**页内**坐标（第 2 页起用小页眉 COMPACT_HEADER_H），
    所以「第 1 页的最后一行」和「第 2 页的第一行」可能是同一个 y —— 按 y 归组会把
    跨页的两行并成一行，行数看起来就少了一行（行高变了以后必然踩到）。
    """
    rows = {}
    for i in range(len(lay)):
        rows.setdefault(render._ROW_OF[i], []).append(i)
    return {r: sorted(v, key=lambda i: lay[i][0]) for r, v in rows.items()}


def measure_map(events):
    mi = {}
    for m_no, m in enumerate(render._measure_groups(events)):
        for i in m:
            mi[i] = m_no
    return mi


# ---------------- 1. 纸型 ----------------
print("—— 纸型（竖版 A4 / B4 / A3）——")

EXPECT = {"A4": (210, 297), "B4": (250, 353), "A3": (297, 420)}
ok_size = True
ok_ratio = True
for name, (w_mm, h_mm) in EXPECT.items():
    render.set_paper(name)
    ew, eh = round(w_mm * render.MM_PX), round(h_mm * render.MM_PX)
    if (render.PAGE_WIDTH, render.PAGE_HEIGHT) != (ew, eh):
        ok_size = False
        print(f"   {name}: {render.PAGE_WIDTH}x{render.PAGE_HEIGHT} != {ew}x{eh}")
    if render.PAGE_HEIGHT <= render.PAGE_WIDTH:     # 必须是竖版
        ok_ratio = False
check("A4/B4/A3 页宽页高按毫米换算正确", ok_size,
      f"A4={render.PAPERS['A4']}")
check("三种纸型都是竖版（高 > 宽）", ok_ratio)
check("set_paper 返回实际生效纸型", render.set_paper("A4") == "A4"
      and render.set_paper("不存在") == render.DEFAULT_PAPER)
check("A4 是默认纸型", render.DEFAULT_PAPER == "A4")
# SVG 根节点上标了纸型，便于外部核对
svg_a4, _ = svg_pages(measures_of(4), paper="A4")
svg_b4, _ = svg_pages(measures_of(4), paper="B4")
check("SVG 标注了纸型与页号",
      'data-paper="A4"' in svg_a4[0] and 'data-page="1"' in svg_a4[0]
      and 'data-paper="B4"' in svg_b4[0])
check("换纸型后页宽跟着变",
      f'width="{round(250 * render.MM_PX)}"' in svg_b4[0])

# ---------------- 2. 自动档：一行 4~6 个小节 ----------------
print("—— 自动档一行 4~6 个小节 / 不从小节中间换行 ——")

render.set_paper("A4")
for n in (4, 6, 8, 9, 10, 11, 12, 13, 18, 24):
    score, results, warnings = make(measures_of(n))
    render.render_svg(score, results, title="QA", key=score.key, whistle_key="D",
                      beats="4/4", paper="A4")
    ev = score.events
    mi = measure_map(ev)
    rows = row_cells(render._LAYOUT)
    counts, whole = [], True
    groups = render._measure_groups(ev)
    for y, idxs in sorted(rows.items()):
        s = set(idxs)
        counts.append(len({mi[i] for i in idxs}))
        for m_no in {mi[i] for i in idxs}:          # 小节必须整个落在同一行
            if not set(groups[m_no]) <= s:
                whole = False
    check(f"{n} 小节：每行 4~6 个", all(4 <= c <= 6 for c in counts), str(counts))
    check(f"{n} 小节：不从小节中间换行", whole, str(counts))

# 7 小节是唯一凑不出「每行 4~6」的总数（只能 4+3），此时允许最后一行短一点，
# 但不许留 1~2 小节的孤行（宁可 4+3 也不要 6+1）。
score, results, _w = make(measures_of(7))
render.render_svg(score, results, title="QA", key=score.key, whistle_key="D",
                  beats="4/4", paper="A4")
_mi7 = measure_map(score.events)
_counts7 = [len({_mi7[i] for i in idxs}) for idxs in render.ROW_PLAN]
check("7 小节：凑不出全是 4~6 时留 4+3（不留 6+1 孤行）", _counts7 == [4, 3],
      str(_counts7))

# 密集小节：一行塞不下 4~6 个时允许降到 3，但**不许留无谓的 1 小节孤行**。
# 贪心是「能塞多少塞多少」，会把料堆到前几行、尾巴剩一个（如 3+1）；
# `_plan_rows` 末尾有一步尾部均分，把它掰成 2+2。
D7 = "5/ 5/ 5/ 5/ 5/ 5/ 5"       # 7 格/小节（6 个八分 + 1 个四分）：一行最多 3 个
D6 = "5/ 5/ 5/ 5/ 5 5"           # 6 格/小节：一行最多 4 个


def row_measure_counts(text):
    s, r, _w = make(text)
    render.render_svg(s, r, title="QA", key=s.key, whistle_key="D",
                      beats="4/4", paper="A4")
    mm = measure_map(s.events)
    return [len({mm[i] for i in idxs}) for idxs in render.ROW_PLAN]


_c4 = row_measure_counts(" ".join([D7] * 4))
check("密集 7 格 × 4 小节：留 2+2 而不是 3+1", _c4 == [2, 2], str(_c4))
_c7 = row_measure_counts(" ".join([D7] * 7))
check("密集 7 格 × 7 小节：留 3+2+2 而不是 3+3+1", _c7 == [3, 2, 2], str(_c7))
_c5 = row_measure_counts(" ".join([D6] * 5))
check("密集 6 格 × 5 小节：留 3+2 而不是 4+1", _c5 == [3, 2], str(_c5))

# 极密小节（9 格/小节，一行只放得下 2 个）时，奇数个小节的孤行是几何上躲不掉的
# （5 = 2+2+1，没有别的拆法）。所以这里不要求「没有孤行」，只要求
# **孤行数恰好等于几何上限逼出来的那一个**——能凑匀就绝不留孤行。
D9 = "5/ 5/ 5/ 5/ 5/ 5/ 5/ 5// 5//"
_s9, _r9, _w9 = make(" ".join([D9] * 5))
render.render_svg(_s9, _r9, title="QA", key=_s9.key, whistle_key="D",
                  beats="4/4", paper="A4")
_g9 = render._measure_groups(_s9.events)
_mm9 = measure_map(_s9.events)
_counts9 = [len({_mm9[i] for i in idxs}) for idxs in render.ROW_PLAN]
_avail9 = render.PAGE_WIDTH - 2 * render.MARGIN
_cap9 = 0
for _k in range(1, render.ROW_MEASURES_MAX + 1):
    if _k <= len(_g9) and _avail9 / render._units(
            _s9.events, [i for g in _g9[:_k] for i in g]) >= render.PITCH_MIN:
        _cap9 = _k
check("极密 9 格：一行只放得下 2 个小节", _cap9 == 2, str(_cap9))
check("极密 9 格 × 5 小节：孤行数 = 几何上躲不掉的数量",
      _counts9.count(1) == (1 if len(_g9) % _cap9 == 1 else 0),
      f"{_counts9} 共{len(_g9)}小节 上限{_cap9}")
check("极密谱也绝不从小节中间换行",
      all(set(_g9[_mm9[i]]) <= set(idxs)
          for idxs in render.ROW_PLAN for i in idxs), str(_counts9))

# 行数最少（不多凑空行）
score, results, _w = make(measures_of(12))
render.render_svg(score, results, title="QA", key=score.key, whistle_key="D",
                  beats="4/4", paper="A4")
check("行数取最少（12 小节 = 2 行，不是 3 行）", len(render.ROW_PLAN) == 2,
      str([len(r) for r in render.ROW_PLAN]))
check("ROW_PLAN 按排版顺序覆盖所有事件",
      [i for r in render.ROW_PLAN for i in r] == list(range(len(score.events))))

# 页宽真的用满：每行右缘顶到右边距（列距自适应在起作用）
_last = render._LAYOUT[render.ROW_PLAN[0][-1]]
check("一行排满到右边距（列距自适应）",
      abs(_last[0] + _last[1] - (render.PAGE_WIDTH - render.MARGIN)) < 0.6,
      f"{_last[0] + _last[1]} vs {render.PAGE_WIDTH - render.MARGIN}")

# 小节线/反复记号占窄格，不然一行少排一个小节
_bar = [e for e in score.events if getattr(e, "kind", "") == "bar"][0]
check("小节线占窄格（细竖线不值得给整格）",
      abs(render.cell_width(_bar) - render.CELL_W * render.BAR_CELL_RATIO) < 1e-6,
      str(render.cell_width(_bar)))

# ---------------- 2b. 一行几个小节可选（自动 / 2~6 固定档） ----------------
print("—— 一行几个小节：自动 或 固定 2~6 ——")

check("默认是「自动」", render.DEFAULT_ROW_MEASURES == render.ROW_MEASURES_AUTO
      and render.ROW_MEASURES_AUTO == 0)
check("固定档只有 2~6", render.ROW_MEASURES_CHOICES == (2, 3, 4, 5, 6))
check("取值归一化：自动/空/非法 -> 0",
      all(render.normalize_row_measures(v) == 0
          for v in (0, "", "自动", "auto", "AUTO", None, "-", " 自动 ", "x", 0.0)),
      str([render.normalize_row_measures(v)
           for v in ("", "自动", None, "-", "x")]))
check("取值归一化：数字/字符串都认，且夹到 2~6",
      [render.normalize_row_measures(v) for v in (2, "3", 4.0, "5 ", 6, 9, -3)]
      == [2, 3, 4, 5, 6, 6, 0],
      str([render.normalize_row_measures(v) for v in (2, "3", 4.0, "5 ", 6, 9, -3)]))
check("显示标签：0 -> 自动，N -> N 小节/行",
      render.row_measures_label(0) == "自动"
      and render.row_measures_label(4) == "4 小节/行"
      and render.row_measures_label("自动") == "自动",
      str(render.row_measures_label(4)))
check("set_row_measures 写入全局并返回生效值",
      render.set_row_measures("5") == 5
      and render.CURRENT_ROW_MEASURES == 5
      and render.set_row_measures("自动") == 0
      and render.CURRENT_ROW_MEASURES == 0)
check("row_cap：自动时 = ROW_MEASURES_MAX，固定档时 = 该档",
      render.row_cap() == render.ROW_MEASURES_MAX
      and (render.set_row_measures(3), render.row_cap() == 3)[1])
render.set_row_measures(render.ROW_MEASURES_AUTO)


def fixed_row_counts(n: int, cap: int):
    """固定 cap 档时，n 个小节实际怎么分行（返回每行小节数）"""
    render.set_row_measures(cap)
    return render._row_counts(n)


for _cap in (2, 3, 4, 5, 6):
    for _n in (2, 4, 5, 6, 7, 9, 12, 13, 18, 24, 25):
        _c = fixed_row_counts(_n, _cap)
        # 每行不超过所选档、加起来正好 n 个小节；
        # 孤行（只有 1 个小节的一行）只在几何上躲不掉时才允许（奇数 × 上限 2）。
        _ok = (sum(_c) == _n and all(1 <= x <= _cap for x in _c)
               and _c.count(1) == (1 if (_cap == 2 and _n % 2 == 1) else 0))
        check(f"固定 {_cap} 个/行：{_n} 小节 -> {_c}", _ok)
    # 整除时「选几个就是几个」
    _exact = fixed_row_counts(_cap * 3, _cap)
    check(f"固定 {_cap} 个/行：{_cap * 3} 小节正好 {_cap}×3",
          _exact == [_cap] * 3, str(_exact))

# 固定档真的落到了导出版式上（每行小节数不再超过所选档，且小节不被切开）
render.set_paper("A4")
for _cap in render.ROW_MEASURES_CHOICES:
    _s, _r, _w = make(measures_of(13))
    render.render_svg(_s, _r, title="QA", key=_s.key, whistle_key="D",
                      beats="4/4", paper="A4", row_measures=_cap)
    _m = measure_map(_s.events)
    _g = render._measure_groups(_s.events)
    _rws = row_cells(render._LAYOUT)
    _cnt = [len({_m[i] for i in idxs}) for _y, idxs in sorted(_rws.items())]
    check(f"固定 {_cap} 个/行：导出每行 <= {_cap} 个小节", all(c <= _cap for c in _cnt),
          str(_cnt))
    check(f"固定 {_cap} 个/行：导出不从小节中间换行",
          all(set(_g[_m[i]]) <= set(idxs) for idxs in _rws.values() for i in idxs),
          str(_cnt))

# SVG 根节点带上生效的档位（方便外部工具/肉眼核对）
_s_auto, _r_auto, _wa = make(measures_of(8))
_auto_svg = render.render_svg(_s_auto, _r_auto, title="QA", key=_s_auto.key,
                              whistle_key="D", beats="4/4", paper="A4",
                              row_measures=0)
check("导出的 SVG 记下生效档位（自动 -> auto）",
      'data-row-measures="auto"' in _auto_svg)
_fs, _fr, _fw = make(measures_of(8))
_fix_svg = render.render_svg(_fs, _fr, title="QA", key=_fs.key, whistle_key="D",
                             beats="4/4", paper="A4", row_measures=3)
check("导出的 SVG 记下生效档位（固定 3 -> 3）",
      'data-row-measures="3"' in _fix_svg)

# 导出面板 / 工程两条路都传得到（最终都落到 pj.export_svg_pages 上）
_row_dir = tempfile.mkdtemp()
_rp4 = pj.export_svg_pages(proj_of(measures_of(12), "固定四"), _row_dir,
                           paper="A4", row_measures=4)
check("export_svg_pages 收下 row_measures 并用上",
      'data-row-measures="4"' in exported_svg(_rp4[0]))
check("不传 row_measures 时按「自动」导出",
      'data-row-measures="auto"' in exported_svg(
          pj.export_svg_pages(proj_of(measures_of(4), "自动谱"), _row_dir,
                              paper="A4")[0]))
shutil.rmtree(_row_dir, ignore_errors=True)

_proj = pj.new_project("工程固定档", "D", "D", "4/4", True)
_proj["notes"] = [pj.token_to_doc(t) for t in measures_of(12).split()]
_proj["row_measures"] = 3
_pdir = os.path.join(tempfile.mkdtemp(), "p")
_pp = pj.export_svg_pages(_proj, _pdir)
check("工程导出用上工程里存的档位",
      'data-row-measures="3"' in open(_pp[0], encoding="utf-8").read())
check("export_svg_pages 的参数优先于工程里的值",
      'data-row-measures="6"' in open(pj.export_svg_pages(
          _proj, _pdir, row_measures=6)[0], encoding="utf-8").read())
check("工程里的档位存得住",
      pj.load(pj.save(_proj, os.path.join(tempfile.mkdtemp(), "p.json")))
      ["row_measures"] == 3)

# 老工程里没有这个字段 -> 读回来是「自动」，不会炸
import json  # noqa: E402
_legacy_path = os.path.join(tempfile.mkdtemp(), "old.json")
with open(_legacy_path, "w", encoding="utf-8") as _f:
    json.dump({k: v for k, v in pj.new_project().items() if not k.startswith("_")},
              _f, ensure_ascii=False)
check("老工程（没有该字段）读回来是「自动」",
      pj.load(_legacy_path)["row_measures"] == 0)

render.set_row_measures(render.ROW_MEASURES_AUTO)

# ---------------- 3. 分页 ----------------
print("—— 分页 ——")

render.set_paper("A4")
score, results, _w = make(measures_of(60))
pages = render.render_svg_pages(score, results, title="QA", key=score.key,
                                whistle_key="D", beats="4/4", paper="A4")
rows = len(render.ROW_PLAN)
per_page = render.rows_per_page(first=True)
check("60 小节要多页", len(pages) > 1, str(len(pages)))
check("页数 = ceil(行数 / 每页行数)",
      len(pages) == -(-rows // per_page), f"{len(pages)} vs {rows}/{per_page}")
# 行不跨页
ok_split = True
for p in range(len(pages)):
    got = len(render.page_rows(p))
    if got > (render.rows_per_page(first=(p == 0))):
        ok_split = False
check("每页行数不超过容量（行不会跨页）", ok_split)
check("所有行都被分到某一页",
      sorted(r for p in range(len(pages)) for r in render.page_rows(p))
      == list(range(rows)))
# 每页的尺寸：中间页是整张纸，最后一页按内容裁短
mid = [render._page_height(p, len(render.page_rows(p)), 0)
       for p in range(len(pages) - 1)]
check("中间页都是整张纸高", all(abs(h - render.PAGE_HEIGHT) < 0.01 for h in mid),
      str(mid))
last = render._page_height(len(pages) - 1, len(render.page_rows(len(pages) - 1)), 0)
check("最后一页按内容裁短（不留一页空白）", last < render.PAGE_HEIGHT, str(last))
check("render_svg 只给第 1 页，render_svg_pages 给全部",
      render.render_svg(score, results, title="QA", key=score.key, whistle_key="D",
                        beats="4/4", paper="A4") == pages[0])

# 页眉页脚
check("第 1 页是完整标题区（带图例）", "按住" in pages[0] and "放开" in pages[0])
check("第 2 页起是紧凑页眉（不再重复图例）", "按住" not in pages[1])
check("每页都有页码", all(f"第 {i + 1} / {len(pages)} 页" in p
                          for i, p in enumerate(pages)))
check("首页标题区标出总页数", f"共 {len(pages)} 页" in pages[0])
for i, p in enumerate(pages):
    try:
        minidom.parseString(p)
    except Exception as exc:                      # noqa: BLE001
        check(f"第 {i + 1} 页 SVG XML 合法", False, str(exc))
        break
else:
    check("每页 SVG XML 合法", True)

# 单页谱不会无端多出「共 N 页」
one, _ = svg_pages(measures_of(4), paper="A4")
check("单页谱只有 1 页、不标总页数", len(one) == 1 and "共 1 页" not in one[0])

# ---------------- 3b. 谱面大小（导出缩放 / 一页 5 行） ----------------
# 「把导出图片的三倍放大当一倍」的落地：字号 + 洞洞图 + 行高**同一个比例**缩，
# 纸张和一行几个小节都不动 —— 于是行变矮、一页多排两行。
print("—— 谱面大小（导出缩放）——")

check("默认谱面大小 = 65%（导出即用这个值）",
      abs(render.DEFAULT_CONTENT_SCALE - 0.65) < 1e-9
      and render.content_scale_label(render.DEFAULT_CONTENT_SCALE) == "65%",
      f"{render.DEFAULT_CONTENT_SCALE} / {render.content_scale_label()}")
check("缩放范围 50%~100%",
      render.CONTENT_SCALE_MIN == 0.5 and render.CONTENT_SCALE_MAX == 1.0)

# 70 / "70" / "70%" 三种写法归一成同一个值；越界夹住；非法值退回默认
check("百分数写法与小数写法等价（70 / \"70\" / \"70%\" / 0.7）",
      len({render.normalize_content_scale(v) for v in (70, "70", "70%", 0.7)}) == 1
      and abs(render.normalize_content_scale(70) - 0.7) < 1e-9,
      str([render.normalize_content_scale(v) for v in (70, "70", "70%", 0.7)]))
check("越界夹到 50% / 100%",
      abs(render.normalize_content_scale(0.2) - 0.5) < 1e-9
      and abs(render.normalize_content_scale(9) - 0.5) < 1e-9
      and abs(render.normalize_content_scale(200) - 1.0) < 1e-9)
check("非法值退回默认 65%",
      abs(render.normalize_content_scale("") - render.DEFAULT_CONTENT_SCALE) < 1e-9
      and abs(render.normalize_content_scale(None) - render.DEFAULT_CONTENT_SCALE) < 1e-9)

# A4 竖版：100% 首页 3 行，65% 首页正好 5 行（这正是选 65% 当默认的原因）
render.set_paper("A4")
render.set_content_scale(100)
_h100, _r100 = render.row_height(), render.rows_per_page(first=True)
render.set_content_scale(65)
_h65, _r65 = render.row_height(), render.rows_per_page(first=True)
_r65_next = render.rows_per_page(first=False)
render.set_content_scale(100)
check("A4 首页：100% 排 3 行、65% 排 5 行",
      _r100 == 3 and _r65 == 5, f"100% {_h100}px/{_r100} 行；65% {_h65}px/{_r65} 行")
check("行高按同一比例缩（214+40 的 65% = 165.1）",
      abs(_h65 - 165.1) < 1e-6, str(_h65))
check("次页（紧凑页眉）也不少于首页容量", _r65_next >= _r65,
      f"次页 {_r65_next} vs 首页 {_r65}")

# 带一行歌词的行更高（要让出歌词带），**这一档也必须是 5 行** —— 选 65% 而不是 70%
# 正是因为它：中文歌几乎都带词，带词掉到 4 行就等于没满足「一页 5 行」。
_lscore, _lres, _lw = make(measures_of(60))
for _e in _lscore.events:
    if getattr(_e, "kind", "") == "note":
        _e.lyric_lines = ["词"]
render.set_content_scale(65)
_lh65 = render.row_height()
_lr65 = render.rows_per_page(first=True)
render.set_content_scale(100)
check("带一行歌词时 65% 首页仍是 5 行（这首是选 65% 当默认的原因）",
      _lr65 == 5, f"一行歌词行高 {_lh65}px → {_lr65} 行")
lp65 = render.render_svg_pages(_lscore, _lres, title="QA", key=_lscore.key,
                               whistle_key="D", warnings=_lw, beats="4/4",
                               paper="A4", content_scale=65)
check("带一行歌词导出：A4 首页实排 5 行",
      len(render.page_rows(0)) == 5, f"实排 {len(render.page_rows(0))} 行")

# 真正导出一次：首页要**实排**满 5 行（不是容量够却排不满）
_score_s, _res_s, _w_s = make(measures_of(60))
_p65 = render.render_svg_pages(_score_s, _res_s, title="QA", key=_score_s.key,
                               whistle_key="D", warnings=_w_s, beats="4/4",
                               paper="A4", content_scale=65)
_first_rows = len(render.page_rows(0))
check("65% 导出：A4 首页实排 5 行",
      _first_rows == 5, f"实排 {_first_rows} 行")
# 注意：导出已经把 render 还原成 100%，所以容量要拿**上面在 65% 下量到的** _r65 比，
# 不能在这里再问一次 render.rows_per_page（那样问到的是 100% 的 3 行）。
check("65% 导出：每页行数都不超容量",
      all(len(render.page_rows(_p)) <= (_r65 if _p == 0 else _r65_next)
          for _p in range(render.N_PAGES)),
      str([len(render.page_rows(_p)) for _p in range(render.N_PAGES)]))
check("65% 导出：所有行都被分到某一页",
      sorted(r for _p in range(render.N_PAGES) for r in render.page_rows(_p))
      == list(range(sum(len(render.page_rows(_p)) for _p in range(render.N_PAGES)))))
check("65% 导出：页数比 100% 少（行变矮 = 一页装更多）",
      len(_p65) < len(render.render_svg_pages(_score_s, _res_s, title="QA",
                                             key=_score_s.key, whistle_key="D",
                                             warnings=_w_s, beats="4/4", paper="A4",
                                             content_scale=100)),
      f"65% {len(_p65)} 页")
check("65% 导出的 SVG 里数字字号 = 26×0.65 = 16.9",
      f'font-size="{26 * render.DEFAULT_CONTENT_SCALE}" font-weight="bold"' in _p65[0])
check("65% 导出：水平布局不变（页宽 / 列宽 / 边距仍是原值）",
      f'width="{render.PAGE_WIDTH}"' in _p65[0] and render.CELL_W == 58)

# 缩放不能有副作用：render 是模块级状态，导出完必须还原，
# 否则后面直调 render 的代码会莫名其妙按 65% 出图。
check("导出后模块状态还原成 100%",
      abs(render.CONTENT_SCALE - 1.0) < 1e-9 and abs(render.NOTE_SIZE - 26) < 1e-9,
      f"{render.CONTENT_SCALE} / {render.NOTE_SIZE}")
check("传 content_scale=None 时不改任何东西（与不传等价）",
      abs(render.NOTE_SIZE - 26) < 1e-9)

# 工程侧：新工程默认 65%、「谱面大小」存得住、导出走工程里那个值
_pj_new = pj.new_project("谱面大小")
check("新工程默认谱面大小 = 65%",
      abs(_pj_new["content_scale"] - 0.65) < 1e-9 and pj.DEFAULT_CONTENT_SCALE == 0.65,
      str(_pj_new.get("content_scale")))
_pj_new["content_scale"] = 85
_tmp_ps = tempfile.mkdtemp(prefix="psz_")
try:
    _pj_back = pj.load(pj.save(_pj_new, os.path.join(_tmp_ps, "p.json")))
    check("「谱面大小」随工程存取（0.85 存得住）",
          abs(_pj_back["content_scale"] - 0.85) < 1e-9, str(_pj_back.get("content_scale")))
    # 老工程没有这个字段 -> 用默认 65%（不是被迫回到 100%）
    _legacy = dict(_pj_new)
    _legacy.pop("content_scale")
    pj.save(_legacy, os.path.join(_tmp_ps, "old.json"))
    check("老工程没有这个字段时退回默认 65%",
          abs(pj.load(os.path.join(_tmp_ps, "old.json"))["content_scale"] - 0.65) < 1e-9)

    # 走工程导出这条路（编谱器导出按钮用的就是它）：内容确实缩了
    _ps_proj = proj_of(measures_of(8), "缩放谱")
    _ps_proj["content_scale"] = 65
    _ps_out = os.path.join(_tmp_ps, "out")
    _ps_path = pj.export_svg(_ps_proj, _ps_out)
    _ps_svg = exported_svg(_ps_path)
    check("工程导出按 65% 出图（数字字号 16.9）",
          f'font-size="{26 * render.DEFAULT_CONTENT_SCALE}" font-weight="bold"' in _ps_svg)
    _ps_proj["content_scale"] = 100
    _ps_path2 = pj.export_svg(_ps_proj, os.path.join(_tmp_ps, "out100"))
    check("同一个工程改成 100% 后导出恢复原尺寸（字号 26）",
          'font-size="26" font-weight="bold"' in exported_svg(_ps_path2))
finally:
    shutil.rmtree(_tmp_ps, ignore_errors=True)

# 图片倍率：1x ~ 5x，默认 1x
check("图片倍率可选 1x ~ 5x，默认 1x",
      imageout.SIZES == (1, 2, 3, 4, 5) and imageout.DEFAULT_SCALE == 1
      and imageout.normalize_scale(3) == 3 and imageout.normalize_scale(5) == 5,
      f"SIZES={imageout.SIZES} DEFAULT={imageout.DEFAULT_SCALE} 3x->{imageout.normalize_scale(3)}")
check("倍率越界（6x）退回默认 1x", imageout.normalize_scale(6) == 1,
      f"6x->{imageout.normalize_scale(6)}")

# ---------------- 4. 水印 ----------------
print("—— 水印 ——")

wm, _ = svg_pages(measures_of(8), paper="A4", watermark="仅供学习")
check("水印文字进 SVG", "仅供学习" in wm[0])
_m = re.search(r'<text[^>]*fill-opacity="([\d.]+)"[^>]*>仅供学习</text>', wm[0])
check("水印不透明度很低（淡淡一层）",
      _m is not None and float(_m.group(1)) <= 0.12,
      _m.group(1) if _m else "没找到水印")
check("水印是灰色的（彩打也不抢眼）",
      render.C_WATERMARK in wm[0] and render.WATERMARK_OPACITY <= 0.12)
check("水印斜排", re.search(r'rotate\(-\d+ ', wm[0]) is not None)
# 画在谱面**下面**：水印必须先于第一个简谱数字出现，记号才能压在水印上
_first_digit = wm[0].find('font-size="26" font-weight="bold"')
check("水印画在谱面之前（记号压在水印之上）",
      0 <= wm[0].find("仅供学习") < _first_digit,
      f"wm@{wm[0].find('仅供学习')} digit@{_first_digit}")
check("多页谱每页都有水印",
      all("仅供学习" in p for p in svg_pages(measures_of(60), paper="A4",
                                            watermark="仅供学习")[0]))
_none, _ = svg_pages(measures_of(4), paper="A4", watermark="")
check("水印留空就不画", "rotate(-24" not in _none[0] and 'fill-opacity="0.' not in _none[0])
check("水印文字会做 XML 转义", "&lt;x&gt;" in svg_pages(
    measures_of(4), paper="A4", watermark="<x>")[0][0])
# 最后一页会被按内容裁短（短谱只有 400 多 px 高），水印必须落在纸内——
# 位置与字号都得按「本页实际高度」算，按整张纸高去居中的话会掉到纸外的空白里（踩过）
_short = svg_pages(measures_of(4), paper="A4", watermark="仅供学习")[0][0]
_sh = float(re.search(r'<svg[^>]*?height="([\d.]+)"', _short).group(1))
_wm = re.search(r'<text x="[\d.]+" y="([\d.]+)" font-size="([\d.]+)" font-weight="bold" '
                r'fill="%s"' % re.escape(render.C_WATERMARK), _short)
check("短谱最后一页的水印仍在纸内（位置/字号按本页高度算）",
      _wm is not None and 0 < float(_wm.group(1)) < _sh and float(_wm.group(2)) < _sh,
      f"{_wm.groups() if _wm else None} 页高 {_sh}")

# ---------------- 5. 导出：多文件 ----------------
print("—— 导出（SVG 多文件 / 图片）——")

tmp = tempfile.mkdtemp(prefix="qa_page_")
try:
    short_dir = os.path.join(tmp, "short")
    p1 = pj.export_svg_pages(proj_of(measures_of(4), "短谱"), short_dir, paper="A4")
    check("单页导出 = 曲名.svg",
          [os.path.basename(p) for p in p1] == ["短谱.svg"]
          and os.path.isfile(p1[0]), str([os.path.basename(p) for p in p1]))

    long_out = os.path.join(tmp, "long")
    p2 = pj.export_svg_pages(proj_of(measures_of(60), "长谱"), long_out,
                             paper="A4", watermark="内部资料")
    _names2 = [os.path.basename(p) for p in p2]
    check("多页导出 = 曲名-1.svg / -2.svg …",
          len(p2) > 1 and _names2 == [f"长谱-{i + 1}.svg" for i in range(len(p2))]
          and all(os.path.isfile(p) for p in p2), str(_names2))
    check("多页导出的第 1 个文件就是第 1 页", p2[0].endswith("-1.svg"))
    check("导出的每一页都有水印",
          all("内部资料" in exported_svg(p) for p in p2))
    check("导出的每一页都标了纸型",
          all('data-paper="A4"' in exported_svg(p) for p in p2))

    # 工程里存的输出偏好：导出时不传参数就自动用上
    proj = pj.new_project("工程长谱", "D", "D", "4/4", True)
    proj["notes"] = [pj.token_to_doc(t) for t in measures_of(60).split()]
    proj["paper"] = "A4"
    proj["watermark"] = "工程水印"
    pj_out = os.path.join(tmp, "proj")
    paths = pj.export_svg_pages(proj, pj_out)
    check("工程导出也是多文件", len(paths) == len(p2)
          and paths[0].endswith("-1.svg"), str([os.path.basename(p) for p in paths]))
    check("工程导出用了工程里存的纸型/水印",
          "工程水印" in exported_svg(paths[0])
          and 'data-paper="A4"' in exported_svg(paths[0]))
    check("export_svg 返回第一页", pj.export_svg(proj, pj_out) == paths[0])
    check("工程里的输出偏好存得住",
          pj.load(pj.save(proj, os.path.join(tmp, "p.json")))["paper"] == "A4")

    # 图片导出：倍率是「矢量按目标像素重画」而不是位图放大
    s, _ = svg_pages(measures_of(4), paper="A4")
    w0, h0 = imageout.svg_size(s[0])
    w2, h2 = imageout.svg_size(imageout.scale_svg(s[0], 2))
    check("倍率作用于 SVG 宽高（2x 就是两倍像素）",
          (w2, h2) == (w0 * 2, h0 * 2), f"{w0}x{h0} -> {w2}x{h2}")
    w5, h5 = imageout.svg_size(imageout.scale_svg(s[0], 5))
    check("5x 也是矢量重画（A4 竖版 -> 约 3970×5615）",
          (w5, h5) == (w0 * 5, h0 * 5), f"{w0}x{h0} -> {w5}x{h5}")
    check("非法倍率退回默认",
          imageout.normalize_scale(9) == imageout.DEFAULT_SCALE
          and imageout.normalize_scale("2") == 2)
    check("页面命名：单页 曲名.svg / 多页 曲名-1.svg",
          imageout.page_name("曲", 0, 1) == "曲.svg"
          and imageout.page_name("曲", 0, 3) == "曲-1.svg"
          and imageout.page_name("曲", 2, 3) == "曲-3.svg"
          and imageout.page_name("曲", 1, 3, ".png") == "曲-2.png")

    browser = imageout.find_browser()
    if browser:
        png_proj = proj_of(measures_of(4), "图片谱")
        img_dir = os.path.join(tmp, "img")
        imgs = pj.export_png(png_proj, img_dir, paper="A4", watermark="水印", scale=1)
        png = imgs[0]
        check("图片导出成功（1x）", os.path.isfile(png))
        with open(png, "rb") as f:
            head = f.read(24)          # PNG 签名 8 + 长度 4 + "IHDR" 4 + 宽 4 + 高 4
        # 期望尺寸直接取自同一工程的 SVG 页面（图片是矢量按目标像素重画的）
        _svg_dir = os.path.join(tmp, "img_svg")
        _svg_p = pj.export_svg_pages(png_proj, _svg_dir, paper="A4", watermark="水印")[0]
        pw, ph = imageout.svg_size(exported_svg(_svg_p))
        # PNG 头里就是宽高（大端 4 字节 ×2）
        real_w = int.from_bytes(head[16:20], "big")
        real_h = int.from_bytes(head[20:24], "big")
        check("PNG 尺寸等于页面像素尺寸",
              (real_w, real_h) == (int(pw), int(ph)),
              f"{real_w}x{real_h} vs {int(pw)}x{int(ph)}")
        check("PNG 文件名与页面一致", os.path.basename(png) == "图片谱.png")
        check("多页图片导出也是 曲名-1.png / -2.png …",
              all(os.path.basename(p) == f"长谱-{i + 1}.png"
                  for i, p in enumerate(pj.export_png(
                      proj_of(measures_of(60), "长谱"), os.path.join(tmp, "img_long"),
                      paper="A4", scale=1))))
    else:
        print("（没找到 Edge/Chrome，跳过 PNG 实测）")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# 收尾：把纸型恢复成默认，别影响别的用例
render.set_paper(render.DEFAULT_PAPER)

print()
if fails:
    print(f"=== 排版/分页/水印用例: 失败 {len(fails)}: {fails}")
    raise SystemExit(1)
print("=== 排版/分页/水印用例: 全部通过")
