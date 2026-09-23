"""编谱工程文档模型

一个「工程」= 曲名 + 曲调 + 哨笛调性 + 音符序列。
音符（NoteDoc）以纯 dict 表示，便于 JSON 序列化与撤销快照。

每个音的孔位可以：
  - holes = None  → 按简谱音高自动查指法（推荐，改哨笛调性时自动跟随）
  - holes = [6 个 0/1/2] → 用户自选指法（编谱器里手动点的孔位，导出时原样使用）
"""

from __future__ import annotations

import json
import os
import time

from . import fingering, imageout, jianpu, render

DOC_VERSION = 1

# 输出偏好（工程里会存起来）
DEFAULT_PAPER = render.DEFAULT_PAPER          # 纸张（竖版 A4/B4/A3）
DEFAULT_SCALE = imageout.DEFAULT_SCALE        # 导出图片的倍率
DEFAULT_ROW_MEASURES = render.DEFAULT_ROW_MEASURES   # 一行几个小节（0=自动，2~6 固定）
# 「谱面大小」：简谱数字 + 洞洞图 + 行高按同一比例缩，纸张与一行几个小节不变。
# 默认 65% —— A4 竖版首页 5 行（带一行歌词也是 5 行；100% 只有 3 行）。
DEFAULT_CONTENT_SCALE = render.DEFAULT_CONTENT_SCALE
PAPER_CHOICES = tuple(render.PAPERS.keys())
ROW_MEASURES_CHOICES = render.ROW_MEASURES_CHOICES   # (2, 3, 4, 5, 6)

KIND_NOTE, KIND_REST, KIND_HOLD, KIND_BAR = "note", "rest", "hold", "bar"
# 反复记号（循环符号）：段落边界，自己占一格；方向见 REPEAT_DIRS
KIND_REPEAT = "repeat"
# 成对圆括号：把一段音整段括起来（前奏 / 间奏 / 和声伴唱），不占时值
KIND_BRACKET = "bracket"
# 「第 n 结尾」框（房子记号，配合反复用）：横线 + 左端短钩 + 标号「1.」，不占时值。
# 手工指定起止：`[1` 起、`1]` 止（数字是序号，不需要两端一致）。
KIND_ENDING = "ending"
# 「框」类记号：不占时值、不是小节边界（见 jianpu.FRAME_KINDS）
FRAME_KINDS = jianpu.FRAME_KINDS

# 反复记号方向 -> 记号文本（|: 反复开始、:| 反复结束、:|: 收尾并起下一段）
REPEAT_DIRS = {"start": "|:", "end": ":|", "both": ":|:"}
REPEAT_TOKENS = {v: k for k, v in REPEAT_DIRS.items()}

# 括号方向 -> 记号文本（半角与全角都认，导出/存盘统一写全角「整段括号」的样子）
BRACKET_DIRS = {"start": "（", "end": "）"}
BRACKET_TOKENS = {"（": "start", "）": "end", "(": "start", ")": "end"}

# 不占时值的事件（排版分隔符）
NON_TIMED = (KIND_BAR, KIND_REPEAT, KIND_BRACKET, KIND_ENDING)

# 时值 -> 简谱横线条数（含附点时值），保留旧名供外部引用
DURATION_BEAMS = {1: 0, 0.5: 1, 0.25: 2, 1.5: 0, 0.75: 1, 0.375: 2}


def duration_suffix(duration: float) -> str:
    """时值 -> 记号后缀（/ 八分、// 十六分、* 附点）"""
    base = duration / jianpu.DOT_FACTOR if jianpu.is_dotted(duration) else duration
    suffix = {0.5: "/", 0.25: "//"}.get(round(base, 6), "")
    return suffix + ("*" if jianpu.is_dotted(duration) else "")


def new_note(degree: int = 1, accidental: int = 0, octave: int = 0,
             duration: float = 1.0, holes=None, short: bool = False) -> dict:
    return {"kind": KIND_NOTE, "degree": degree, "accidental": accidental,
            "octave": octave, "duration": duration, "holes": list(holes) if holes else None,
            "short": bool(short)}


def new_simple(kind: str, duration: float = 1.0) -> dict:
    return {"kind": kind, "duration": duration}


def new_repeat(direction: str = "start") -> dict:
    """反复记号（循环符号）。direction: start | end | both"""
    return {"kind": KIND_REPEAT, "direction": direction if direction in REPEAT_DIRS else "start"}


def new_bracket(direction: str = "start") -> dict:
    """成对圆括号（整段括起来）。direction: start | end"""
    return {"kind": KIND_BRACKET,
            "direction": direction if direction in BRACKET_DIRS else "start"}


def new_ending(direction: str = "start", n: int = 1) -> dict:
    """「第 n 结尾」框。direction: start | end；n = 序号（1 = 第一结尾）。"""
    return {"kind": KIND_ENDING,
            "direction": direction if direction in ("start", "end") else "start",
            "n": max(1, int(n or 1))}


# ---------------- 歌词 ----------------
# 一个音可以有**多行**歌词（多段词）。存储为 doc["lyric_lines"] = ["第一行", "第二行", ...]；
# 老工程里的单行 doc["lyric"] 仍然认（读的时候兜底），写的时候也同步写一份，
# 于是「单行歌词」这个最常用场景在 JSON 里长得和以前一模一样。
def lyric_lines_of(doc: dict) -> list:
    """该音的全部歌词行（没有就是空列表）"""
    lines = doc.get("lyric_lines")
    if isinstance(lines, list) and lines:
        return [str(x).strip() for x in lines]
    one = doc.get("lyric")
    return [str(one).strip()] if one else []


def set_lyric_lines(doc: dict, lines) -> None:
    """写/清多行歌词。

    注意：这里**不吞尾部空行**。单行时代「空串就删键」是为了让工程 JSON 干净，
    但多行时代，用户点了「＋行」还没填字时，那个空行本身就是「谱面要留出这一行」
    的声明——吞掉就等于按钮没反应。整份都是空列表时才把键删干净。
    """
    clean = [str(x or "").strip() for x in (lines or [])]
    if clean:
        doc["lyric_lines"] = clean
        doc["lyric"] = clean[0]          # 兼容老字段：第一行仍写进 lyric
    else:
        doc.pop("lyric_lines", None)
        doc.pop("lyric", None)


def lyric_of(doc: dict) -> str:
    """取一个音的**第一行**歌词（没有就是空串）——单行场景下就是全部歌词"""
    lines = lyric_lines_of(doc)
    return lines[0] if lines else ""


def set_lyric(doc: dict, text: str) -> None:
    """写/清第一行歌词（其余行不动）；整份歌词都变空了就把键删干净。"""
    lines = lyric_lines_of(doc)
    if len(lines) <= 1:
        set_lyric_lines(doc, [text] if (text or "").strip() else [])
        return
    lines[0] = text
    set_lyric_lines(doc, lines if any(str(x).strip() for x in lines) else [])


def lyric_line_count(docs) -> int:
    """这批音里最多有几行歌词（排版据此决定笛身要让多宽、行要长多高）"""
    return max((len(lyric_lines_of(d)) for d in docs), default=0)


def has_lyrics(docs) -> bool:
    return lyric_line_count(docs) > 0


def new_project(title: str = "未命名", key: str = "D", whistle: str = "D",
                beats: str = "4/4", auto_bars: bool = True) -> dict:
    return {"version": DOC_VERSION, "title": title, "key": key,
            "whistle": whistle, "beats": beats, "auto_bars": auto_bars,
            # 排版/输出偏好：纸张（竖版 A4/B4/A3）、淡淡的水印文字、图片倍率、
            # 「谱面大小」（0.5~1.0，默认 0.65）、一行几个小节（0 = 自动 4~6，也可固定 2~6）
            "paper": DEFAULT_PAPER, "watermark": "", "scale": DEFAULT_SCALE,
            "content_scale": DEFAULT_CONTENT_SCALE,
            "row_measures": DEFAULT_ROW_MEASURES,
            "notes": [], "saved_at": time.time()}


# ---------------- 记号文本 ----------------
def token_of(doc: dict) -> str:
    """还原为简谱记号文本（与 jianpu.parse 的语法一致）。

    后缀：/ 八分、// 十六分、* 附点、! 切音（吐音/切分）、v 换气；
    连音线（圆滑线/延音线）是跨音符的弧线，用附加字符表达：
    起点后缀 (、终点后缀 )，相邻同音延音线用 ~ 写在第一个音上；
    反复记号（循环符号）是独立事件，见 REPEAT_DIRS；
    整段括号也是独立事件（`（` `）`），「第 n 结尾」框见 KIND_ENDING。
    """
    kind = doc.get("kind", KIND_NOTE)
    if kind == KIND_BAR:
        return "|"
    if kind == KIND_REPEAT:
        return REPEAT_DIRS.get(doc.get("direction", "start"), "|:")
    if kind == KIND_BRACKET:
        return BRACKET_DIRS.get(doc.get("direction", "start"), "（")
    if kind == KIND_ENDING:
        n = max(1, int(doc.get("n", 1) or 1))
        return f"[{n}" if doc.get("direction", "start") == "start" else f"{n}]"
    if kind == KIND_HOLD:
        return "-"
    if kind == KIND_REST:
        return "0" + duration_suffix(doc.get("duration", 1.0))
    acc = {1: "#", -1: "b"}.get(doc.get("accidental", 0), "")
    oct_mark = "." * max(0, -doc.get("octave", 0)) + "'" * max(0, doc.get("octave", 0))
    marks = duration_suffix(doc.get("duration", 1.0))
    if doc.get("short"):
        marks += "!"
    if doc.get("breath"):
        marks += "v"
    if doc.get("slur_start"):
        marks += "("
    if doc.get("slur_end"):
        marks += ")"
    if doc.get("tie"):
        marks += "~"
    return f"{acc}{doc['degree']}{oct_mark}{marks}"


def token_to_doc(token: str) -> dict | None:
    """把单个记号文本转成 NoteDoc（编谱器导入文本用）"""
    score = jianpu.parse(token)
    for e in score.events:
        if e.kind == "note":
            doc = new_note(e.degree, e.accidental, e.octave, e.duration)
            doc["short"] = bool(getattr(e, "short", False))
            if getattr(e, "breath", False):
                doc["breath"] = True
            if getattr(e, "slur_start", False):
                doc["slur_start"] = True
            if getattr(e, "slur_end", False):
                doc["slur_end"] = True
            if getattr(e, "tie", False):
                doc["tie"] = True
            return doc
        if e.kind == KIND_REPEAT:
            return new_repeat(getattr(e, "direction", "start"))
        if e.kind == KIND_BRACKET:
            return new_bracket(getattr(e, "direction", "start"))
        if e.kind == KIND_ENDING:
            return new_ending(getattr(e, "direction", "start"), getattr(e, "ending", 1))
        if e.kind in (KIND_REST, KIND_HOLD, KIND_BAR):
            return new_simple(e.kind, getattr(e, "duration", 1.0))
    return None


# ---------------- 与渲染器对接 ----------------
def to_event(doc: dict, index: int) -> jianpu.NoteEvent:
    kind = doc.get("kind", KIND_NOTE)
    if kind == KIND_NOTE:
        acc, octv = doc.get("accidental", 0), doc.get("octave", 0)
        dur = doc.get("duration", 1.0)
        lines = lyric_lines_of(doc)
        event = jianpu.NoteEvent(
            kind="note", token=token_of(doc), degree=doc["degree"], accidental=acc,
            octave=octv, semitone=jianpu.DEGREE_SEMITONES[doc["degree"]] + acc + octv * 12,
            duration=dur, index=index, short=bool(doc.get("short")),
            breath=bool(doc.get("breath")),
            slur_start=bool(doc.get("slur_start")), slur_end=bool(doc.get("slur_end")),
            tie=bool(doc.get("tie")), lyric=(lines[0] if lines else ""),
            lyric_lines=list(lines),
        )
        event.dotted = jianpu.is_dotted(dur)   # 附点标记（渲染器读它画点）
        return event
    if kind == KIND_REPEAT:
        return jianpu.NoteEvent(kind=kind, token=token_of(doc), index=index,
                                direction=doc.get("direction", "start"))
    if kind in FRAME_KINDS:
        return jianpu.NoteEvent(kind=kind, token=token_of(doc), index=index,
                                direction=doc.get("direction", "start"),
                                ending=max(1, int(doc.get("n", 1) or 1)))
    return jianpu.NoteEvent(kind=kind, token=token_of(doc),
                            duration=doc.get("duration", 1.0), index=index)


def to_result(doc: dict, index: int, key: str, whistle: str) -> fingering.FingeringResult:
    """生成渲染所需的指法结果：用户自选指法优先，否则按音高自动查表"""
    holes = doc.get("holes")
    if doc.get("kind", KIND_NOTE) != KIND_NOTE:
        return fingering.FingeringResult(playable=False)
    auto = fingering.map_note(
        jianpu.DEGREE_SEMITONES[doc["degree"]] + doc.get("accidental", 0)
        + doc.get("octave", 0) * 12,
        jianpu.KEY_SEMITONES[key], whistle)
    if holes:
        name, known = fingering.describe_holes(holes, whistle)
        return fingering.FingeringResult(
            playable=True, index=auto.index if auto.playable else -1, holes=tuple(holes),
            alternates=[], second_octave=auto.second_octave, hard=False,
            shifted=0, note_name=name.replace(" 高", ""),
            reason="" if known else "自定义指法", custom=True,
        )
    return auto


# ---------------- 自动小节线 ----------------
def beats_of(beats: str) -> float:
    """拍号 -> 每小节四分音符数"""
    return jianpu.BEATS_PER_MEASURE.get(beats, 4.0)


def display_notes(project: dict) -> tuple:
    """按拍号自动插入小节线，返回 (展示用音符列表, 展示序号->文档序号 映射)。

    - 自动小节线开启时，文档里手写的小节线会被忽略（由算法统一重排）；
    - 每行按累计时值填满一小节即插线；时值溢出时在该音之后插线并把余数带入下一小节；
    - 切音的时值照常累计（谱面只是画成小窄格），所以切音正好补满一小节时，
      小节线会落在切音之后（切音是末拍，后一个音起下一小节）；
    - **反复记号（循环符号）保留**：它不占时值，而且自己就是小节线的一种——所以同一个
      位置上不会再出现普通小节线：紧邻在前的那条会被它顶掉，它出现在小节中间时前面那半
      小节就由它收尾（不补收尾小节线，免得出 `| |:`）；`:|` / `|:` 都能被选中、编辑；
    - **整段括号 / 第 n 结尾框也保留**：同样不占时值，但它们是**记号而不是小节线**——
      不改变小节累计，也不会顶掉相邻的小节线；**贴着小节边界的那一侧按记谱口径让位**：
      收尾那一侧（`）` `n]`）留在小节线之前、起点那一侧（`（` `[n`）落在小节线之后
      （见 jianpu.is_frame_close，两处口径必须一致）；
    - 末尾补一个收尾小节线（若最后一格不是小节线/反复记号）。
    映射里小节线的值为 None（不可选中）。
    """
    notes = project.get("notes", [])
    if not project.get("auto_bars", True):
        return list(notes), list(range(len(notes)))

    cap = beats_of(project.get("beats", "4/4"))
    out, index_map = [], []
    acc = 0.0
    pending = False      # 本小节已填满，但线要「让过」紧跟其后的收尾记号再落

    def add_bar():
        out.append({"kind": KIND_BAR, "auto": True})
        index_map.append(None)

    def flush_bar():
        nonlocal pending
        if pending:
            add_bar()
            pending = False

    for i, doc in enumerate(notes):
        k = doc.get("kind")
        if k == KIND_BAR:
            continue                     # 手写小节线在自动模式下重排
        if k == KIND_REPEAT:
            flush_bar()                  # 反复记号就落在小节线该在的位置上
            if out and out[-1].get("kind") == KIND_BAR:
                out.pop()                # 反复记号自己就是小节线，取代紧邻那条
                index_map.pop()
            # 反复记号本身就是小节线，它出现的地方就是小节边界：哪怕前面那半小节
            # 没填满，也由它收尾。这里绝不能补 add_bar()，否则会画出 `| |:`。
            out.append(doc)
            index_map.append(i)          # 反复记号可以选中
            acc = 0.0
            continue
        if k in FRAME_KINDS:
            # 括号 / 结尾框：不占时值，也不影响小节累计（它不改变音乐的时间线）
            if not jianpu.is_frame_close(k, doc.get("direction", "")):
                flush_bar()              # 起点那一侧：落在小节线**之后**
            out.append(doc)
            index_map.append(i)          # 可以选中、编辑
            continue
        flush_bar()
        out.append(doc)
        index_map.append(i)
        dur = 1.0 if k == KIND_HOLD else doc.get("duration", 1.0)
        acc += dur
        if acc >= cap - 1e-6:
            pending = True
            acc = max(0.0, acc - cap)
    flush_bar()
    if out and out[-1].get("kind") not in (KIND_BAR, KIND_REPEAT):
        add_bar()
    return out, index_map


def build_render_inputs(project: dict):
    """返回 (ParsedScore, results, warnings, key)"""
    key = project.get("key", "D")
    whistle = project.get("whistle", "D")
    shown, _ = display_notes(project)
    events = [to_event(d, i) for i, d in enumerate(shown)]
    results, warnings = {}, []
    for e in events:
        if e.kind != "note":
            continue
        r = to_result(shown[e.index], e.index, key, whistle)
        results[e.index] = r
        if not r.playable:
            warnings.append(f"第 {e.index + 1} 个音 {e.token}：{r.reason or '无法演奏'}")
    # 括号 / 结尾框只有一侧的：画不出框来，只能提醒补上另一半
    for kind, label in ((KIND_BRACKET, "整段括号"), (KIND_ENDING, "结尾框")):
        _pairs, unpaired = jianpu.pair_frames(events, kind)
        for i, direction, _n in unpaired:
            which = "起点" if direction == "start" else "终点"
            warnings.append(f"第 {i + 1} 格的{label}只有{which} {token_of(shown[i])}，"
                            f"缺另一半，谱面上画不出来")
    score = jianpu.ParsedScore(events=events)
    score.tonic = jianpu.KEY_SEMITONES[key]
    score.key = key
    score.key_source = "param"
    return score, results, warnings, key


def safe_name(name: str) -> str:
    """曲名 → 安全的文件名（去掉 Windows 不允许的字符）。"""
    raw = str(name or "")
    out = "".join(ch for ch in raw if ch not in '\\/:*?"<>|').strip()
    return out or "未命名"


def export_svg_pages(project: dict, out_dir: str, paper: str = "",
                     watermark: str = "", row_measures=None,
                     content_scale=None, progress=None) -> list:
    """把工程导出为与自动生成完全一致的 SVG 洞洞谱（**一页一个文件**）。

    分页规则见 render._build_layout：一行几个小节由 row_measures 决定
    （0/空 = 自动 4~6 个，也可固定 2~6）、绝不从小节中间换行、行不跨页。
    单页 = `曲名.svg`；多页 = `曲名-1.svg` / `曲名-2.svg` …（序号即页码）。
    纸张 paper 与淡淡的水印文字 watermark 不传时用工程里存的值。
    content_scale = 「谱面大小」（0.5~1.0 或 70 这样的百分数），不传用工程里存的值
    （新工程默认 0.65 —— A4 首页 5 行）；它只缩记号与行高，纸张和一行几个小节不变。
    返回所有生成的文件路径。
    """
    score, results, warnings, key = build_render_inputs(project)
    if not score.events:
        raise ValueError("工程里还没有音符")
    paper = paper or project.get("paper", "") or render.DEFAULT_PAPER
    watermark = watermark if watermark else project.get("watermark", "")
    if row_measures is None:
        row_measures = project.get("row_measures", DEFAULT_ROW_MEASURES)
    if content_scale is None:
        content_scale = project.get("content_scale", DEFAULT_CONTENT_SCALE)
    pages = render.render_svg_pages(score, results, title=project.get("title", "未命名"),
                                    key=key, whistle_key=project.get("whistle", "D"),
                                    warnings=warnings, beats=project.get("beats", ""),
                                    paper=paper, watermark=watermark,
                                    row_measures=row_measures,
                                    content_scale=content_scale)
    os.makedirs(out_dir, exist_ok=True)
    base = safe_name(project.get("title", "未命名"))
    paths = []
    for i, svg in enumerate(pages):
        path = os.path.join(out_dir, imageout.page_name(base, i, len(pages), ".svg"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        paths.append(path)
        if progress:
            progress(i + 1, len(pages), f"第 {i + 1}/{len(pages)} 页")
    return paths


def export_svg(project: dict, out_dir: str, paper: str = "",
               watermark: str = "", row_measures=None, content_scale=None) -> str:
    """导出 SVG，返回**第一个文件**的路径（多页谱请用 export_svg_pages 取全部）。"""
    return export_svg_pages(project, out_dir, paper=paper, watermark=watermark,
                            row_measures=row_measures,
                            content_scale=content_scale)[0]


def export_png(project: dict, out_dir: str, paper: str = "", watermark: str = "",
               scale: int | None = None, row_measures=None, progress=None,
               content_scale=None, cancel=None) -> list:
    """把工程导出成 PNG 图片：按纸张分页、逐页一个文件，倍率 1x~5x。

    单个页面 = `曲名.png`；多页 = `曲名-1.png` / `曲名-2.png` …。
    需要系统里有 Edge/Chrome（用来把矢量谱面栅格化成图片）。
    content_scale 同 export_svg_pages（不传用工程里存的值）。

    progress(done, total, label) 会先报一次「排版」再逐页报；cancel() 见
    imageout.pages_to_png（返回 True 就不再开新的页）。
    """
    score, results, warnings, key = build_render_inputs(project)
    if not score.events:
        raise ValueError("工程里还没有音符")
    paper = paper or project.get("paper", "") or render.DEFAULT_PAPER
    watermark = watermark if watermark else project.get("watermark", "")
    if scale is None:
        scale = project.get("scale", imageout.DEFAULT_SCALE)
    if row_measures is None:
        row_measures = project.get("row_measures", DEFAULT_ROW_MEASURES)
    if content_scale is None:
        content_scale = project.get("content_scale", DEFAULT_CONTENT_SCALE)
    pages = render.render_svg_pages(score, results, title=project.get("title", "未命名"),
                                    key=key, whistle_key=project.get("whistle", "D"),
                                    warnings=warnings, beats=project.get("beats", ""),
                                    paper=paper, watermark=watermark,
                                    row_measures=row_measures,
                                    content_scale=content_scale)
    if progress:
        progress(0, len(pages), f"排版完成，共 {len(pages)} 页")
    return imageout.pages_to_png(pages, out_dir, safe_name(project.get("title", "未命名")),
                                 scale=scale, progress=progress, cancel=cancel)


# ---------------- 工程存取 ----------------
# 存盘的 JSON 是**手改友好**的（`indent=1`），也常被直接看 diff，所以分块写必须
# 与 `json.dump(project, indent=1)` **逐字节一致**（有测试钉住，见 tests/selftest.py）。
# 规则：`json.dumps(v, indent=1)` 出来的是「第 0 列 `{`、成员 1 空格」，而它在完整文档里
# 的位置决定了要整体右移几格 —— 顶层字段的值：除首行外每行 +1；`notes` 里的元素：每行 +2。
def _reindent(text: str, pad: int, skip_first: bool = True) -> str:
    """每行前面补 pad 个空格（json.dump 的缩进规则）。

    skip_first=True：第一行不补——它是跟在 `"key": ` 后面的。
    skip_first=False：整块都要右移（notes 里的元素是另起一行的）。
    """
    if pad <= 0:
        return text
    out = []
    for i, ln in enumerate(text.split("\n")):
        out.append(ln if (i == 0 and skip_first) or not ln else " " * pad + ln)
    return "\n".join(out)


def iter_save_pieces(project: dict):
    """分块产出 (文本片段, 已写到第几个音)，拼起来正是 json.dump(indent=1) 的结果。

    音符多的时候 notes 占掉绝大多数内容，所以**每写完一个音产出一段**——保存的进度条
    就能按「第 N/M 个音」推进，而不是整块黑箱。第二个数是给调用方报进度用的。
    """
    project = dict(project)
    project["version"] = DOC_VERSION
    project["saved_at"] = time.time()
    keys = list(project.keys())
    notes = project.get("notes", []) or []
    # 第二个返回值必须**单调不减**：notes 后面还有别的字段（watermark / scale …），
    # 那些片段要带着「当前已写到第几个音」一起交出去；写成 0 的话进度条会在收尾时
    # 从 200/200 一下跳回 0（保存进度不回头的回归见 tests/selftest.py）。
    done = 0
    yield "{\n", done
    for n, key in enumerate(keys):
        tail = ",\n" if n < len(keys) - 1 else "\n"
        if key == "notes" and isinstance(notes, list) and notes:
            yield ' "notes": [\n', done
            last = len(notes) - 1
            for i, doc in enumerate(notes):
                body = _reindent(json.dumps(doc, ensure_ascii=False, indent=1), 2,
                                 skip_first=False)
                done = i + 1
                yield body + (",\n" if i < last else "\n"), done
            yield " ]" + tail, done
            continue
        val = json.dumps(project[key], ensure_ascii=False, indent=1)
        yield " " + json.dumps(key, ensure_ascii=False) + ": " + _reindent(val, 1) + tail, done
    yield "}", done


def save(project: dict, path: str, progress=None) -> str:
    """写工程文件。progress(done, total, label)：按「已写第几个音」推进。

    仍然先写 .tmp 再原子替换（自动保存不会写坏工程文件）。
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    total = len(project.get("notes", []) or [])
    tmp = path + ".tmp"
    done = 0
    with open(tmp, "w", encoding="utf-8") as f:
        for piece, n in iter_save_pieces(project):
            f.write(piece)
            if n != done:                    # 音符数变了才报一次（避免每条都回调）
                done = n
                if progress:
                    progress(done, total, f"写入 {done}/{total} 个音")
    os.replace(tmp, path)   # 原子替换，避免自动保存写坏工程文件
    if progress:
        progress(max(total, 1), max(total, 1), f"已写 {total} 个音")
    return path


def load(path: str, progress=None) -> dict:
    """读工程文件。progress(done, total, label)：按阶段推进（读文件 → 解析 → 整理）。

    进度按**百分比**报（total 恒为 100）：读盘占 0~60（按字节数推进，这是唯一能
    真实分块的一段），解析 60~85，整理字段 85~100。解析只能整块做（json.loads），
    对几 MB 的 JSON 也就零点几秒，所以不值得为它造假进度。
    """
    def _pct(value: float, label: str):
        if progress:
            progress(int(value), 100, label)

    size = os.path.getsize(path) if os.path.isfile(path) else 0
    chunks = []
    read = 0
    with open(path, "rb") as f:
        while True:
            blk = f.read(1 << 20)                     # 1 MB 一块
            if not blk:
                break
            chunks.append(blk)
            read += len(blk)
            _pct(60 * min(read / max(size, 1), 1.0), f"读取 {read // 1024} KB")
    raw = b"".join(chunks).decode("utf-8")
    _pct(65, "解析工程")
    data = json.loads(raw)
    _pct(88, "整理字段")
    base = new_project(data.get("title", "未命名"), data.get("key", "D"),
                       data.get("whistle", "D"), data.get("beats", "4/4"),
                       data.get("auto_bars", True))
    base["notes"] = data.get("notes", [])
    # 输出偏好（老工程里没有这几个字段时退回默认）
    base["paper"] = data.get("paper", DEFAULT_PAPER)
    base["watermark"] = data.get("watermark", "")
    base["scale"] = data.get("scale", DEFAULT_SCALE)
    base["content_scale"] = render.normalize_content_scale(
        data.get("content_scale", DEFAULT_CONTENT_SCALE))
    base["row_measures"] = render.normalize_row_measures(
        data.get("row_measures", DEFAULT_ROW_MEASURES))
    base["saved_at"] = data.get("saved_at", time.time())
    base["_path"] = path
    _pct(100, f"共 {len(base['notes'])} 个单元")
    return base
