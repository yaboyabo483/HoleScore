"""简谱文本解析器

输入约定（校对框里的人工可读格式，OCR 结果也归一化到该格式）：
    音高      0-7            0=休止, 1-7=do..si
    升降号    # / b 前缀      #4  b7
    低八度    数字后加 .      6.  (两个点 6.. 表示低两个八度)
    高八度    数字后加 '      1'  (两个撇 1'' 表示高两个八度)
    时值      数字后加 /      5/ 八分音符, 5// 十六分音符（无后缀=四分音符）
    附点      数字后加 *      5* 附点四分, 5/* 附点八分
    切音      后缀里的 !     5! 切音（吐音/切分）；谱面里切音**自己占一个小小的窄格子**，
              紧跟在该音前面，窄格内是「小数字（该音音高）+ 右上角小斜杠」+ 小指法图
    换气      后缀里的 v     5v 换气记号（吹奏到这歇一口气），画成数字上方一个小 v
    连音线    后缀 ( ) ~    5( 起点、3) 终点（同音=延音线，异音=圆滑线）；5~ 与下一音相连
              以上后缀顺序无关：5/! 与 5!/ 等价
    延音      -              延长前一个音，不产生新指法
    小节线    |              仅用于排版分组
    反复记号  |:  :|  :|:    循环符号：|: 反复开始、:| 反复结束、:|: 一段收尾并起下一段
    整段括号  （  ）  (  )   成对圆括号把一段音整段括起来（前奏/间奏/和声伴唱）；
                            独立出现才算（紧跟数字的 `1(` 仍是连音线起点）。
                            左右两侧各自画在自己那一格边缘，跨行也不丢
    第 n 结尾  [n  n]        房子记号，配合反复用：`[1` 起、`1]` 止，序号写在任一侧都认。
                            横线压在这一段所有记号（高八度点/换气 v/连音弧线）之上。
                            **`n]` 里的 n 是标号（与 `[n` 呼应），不是音符**；
                            要在收尾这一格放音就多写一格（`1 1]`）。这么定是因为
                            「收尾」经常落在延音/休止上（`-]` 解析不出记号），
                            标号必须自带，所以收尾这一支只能读作标号。
    调号头    文本中任意位置的 "1=G" 样式会被识别并从正文中剔除；
              未显式传 key 时以文本调号为准。
    其他字符   忽略（歌词、标题等；但全/半角圆括号与 `[n`/`n]` 已被上面两条收走）

解析结果：NoteEvent 列表，包含绝对音高索引（相对哨笛调性）之前的
“调内音高”（tonic_semitone + degree_offset + octave*12），
具体映射到哨笛指法由 fingering.py 完成。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 大调音阶各级的半音偏移
DEGREE_SEMITONES = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}

# 调名 -> 半音值（C=0）
KEY_SEMITONES = {
    "C": 0, "#C": 1, "bD": 1, "D": 2, "#D": 3, "bE": 3,
    "E": 4, "F": 5, "#F": 6, "bG": 6, "G": 7, "#G": 8,
    "bA": 8, "A": 9, "#A": 10, "bB": 10, "B": 11,
}

NOTE_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# 单个简谱记号：可选升降号 + 数字 + 后缀（八度点/撇、时值斜线、附点 *、切音 !、换气 v、连音 ( ) ~）
# 后缀内部**顺序无关**：5/!、5!/、5!、5*! 等价，便于人工输入与 OCR 纠错。
#
# 顺序有几个不能动的约束：
#   * 反复记号（循环符号）排在 | 前面，否则 :| 会被拆成「垃圾 + 小节线」；
#   * `[1` / `1]`（第 n 结尾框的起止）**必须排在音符那条之前**：正则按左到右挑第一个
#     能匹配的分支，而 `1]` 里的 `1` 会被音符分支先吃掉（`]` 不在后缀字符集里，
#     于是留下一个孤零零的 `]`）。排在前面才抢得到。
#   * 成对括号 `（` `）` 排在最后：它们在音符后缀里也有，但那只在**紧跟数字**时成立
#     （`1(` 是连音线起点）；独立出现的括号才落到这两条分支上。全角括号永远走这里。
_TOKEN_RE = re.compile(
    r"(?P<ending_start>\[(?P<ending_s_n>\d+))"
    r"|(?P<ending_end>(?P<ending_e_n>\d+)\])"
    r"|(?P<acc>[#b]?)(?P<num>[0-7])(?P<suffix>[.'*/!()~v]*)"
    r"|(?P<repeat_both>:\|:)"
    r"|(?P<repeat_start>\|:)"
    r"|(?P<repeat_end>:\|)"
    r"|(?P<dash>-+)"
    r"|(?P<bar>\|)"
    r"|(?P<lbracket>[（(])"
    r"|(?P<rbracket>[）)])"
)

# 调号头：1=G / 1 = bB / 1＝#F / 1=F# 等（升降号前后写法都接受）
_KEY_HEADER_RE = re.compile(r"1\s*[=＝]\s*([#bB]?[A-Ga-g][#bB]?)")

_KEY_NAME_RE = re.compile(r"([#bB]?)([A-Ga-g])([#bB]?)")

# OCR 常见误识别与全角字符归一化表
_NORMALIZE_MAP = str.maketrans({
    "＃": "#", "♯": "#", "ｂ": "b", "♭": "b",
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7",
    "．": ".", "。": ".", "·": ".", "•": ".",
    "＇": "'", "’": "'", "‘": "'", "`": "'",
    "－": "-", "—": "-", "–": "-", "一": "-",  # OCR 常把延音线看成“一”
    "｜": "|", "丨": "|",
    "／": "/",
    "O": "0", "o": "0", "l": "1", "I": "1",
})

# 时值后缀 -> 拍值（四分音符为 1）
# 时值：基数（无横线=四分, / = 八分, // = 十六分），后缀 * 表示附点（×1.5）
# 注：解析已改为按后缀字符计数（见 _TOKEN_RE），此表保留供外部/历史引用。
_DURATION_MAP = {None: 1.0, "/": 0.5, "//": 0.25}
DOT_FACTOR = 1.5

# 拍号 -> 每小节占多少个四分音符
BEATS_PER_MEASURE = {
    "2/4": 2.0, "3/4": 3.0, "4/4": 4.0,
    "3/8": 1.5, "6/8": 3.0, "2/2": 4.0,
}

# 「框」类记号：不占时值、不是小节边界，只在谱面上画出来
#   bracket —— 成对圆括号（前奏 / 间奏 / 和声伴唱那一段）
#   ending  —— 「第 n 结尾」框（房子记号，配合反复用）
FRAME_KINDS = ("bracket", "ending")


def _field(e, name: str, default=None):
    """同时兼容 NoteEvent（属性）与工程里的 doc（dict）——这两条渲染线都要用这个函数"""
    if isinstance(e, dict):
        return e.get(name, default)
    return getattr(e, name, default)


def pair_frames(events, kind: str) -> tuple:
    """把同一种「框类记号」按出现顺序配成对，返回 (pairs, unpaired)。

      * pairs    = [(起点下标, 终点下标, 序号), ...]
      * unpaired = [(下标, 方向, 序号), ...] —— 只有一侧的记号。
        这种画不出框来，界面上只能提示用户补另一半（见 project.build_render_inputs）。

    配对用**栈**（后开的先合），所以 `[1 … [2 … 2] … 1]` 这类嵌套也能各归各的；
    更常见的「先 1 后 2」顺序写法自然也正确。

    NoteEvent 与 doc（dict）都认：导出走前者、编谱器画布走后者。
    """
    pairs, stack, unpaired = [], [], []
    for i, e in enumerate(events):
        if _field(e, "kind", "") != kind:
            continue
        n = int(_field(e, "ending", 0) or _field(e, "n", 0) or 0)
        if _field(e, "direction", "start") == "start":
            stack.append((i, n))
        elif stack:
            i0, n0 = stack.pop()
            pairs.append((i0, i, n0 or n))
        else:
            unpaired.append((i, "end", n))
    for i, n in stack:
        unpaired.append((i, "start", n))
    return pairs, unpaired


def duration_beams(duration: float) -> int:
    """时值 -> 简谱时值横线条数（四分 0 条、八分 1 条、十六分 2 条，附点同理）"""
    base = duration / DOT_FACTOR if is_dotted(duration) else duration
    if base <= 0.25 + 1e-9:
        return 2
    if base <= 0.5 + 1e-9:
        return 1
    return 0


def is_dotted(duration: float) -> bool:
    """是否为附点时值（基数 × 1.5：1.5 / 0.75 / 0.375 / 3.0 …）"""
    for base in (4.0, 2.0, 1.0, 0.5, 0.25, 0.125):
        if abs(duration - base * DOT_FACTOR) < 1e-6:
            return True
    return False


def duration_name(duration: float) -> str:
    """时值的中文名，用于界面显示"""
    names = {1.0: "四分", 0.5: "八分", 0.25: "十六分",
             1.5: "附点四分", 0.75: "附点八分", 0.375: "附点十六分"}
    for k, v in names.items():
        if abs(duration - k) < 1e-6:
            return v
    return f"{duration:g} 拍"


@dataclass
class NoteEvent:
    """一个解析后的简谱事件"""
    kind: str            # 'note' | 'rest' | 'hold' | 'bar' | 'repeat'
    token: str           # 原始记号（用于谱面显示）
    degree: int = 0      # 1-7
    accidental: int = 0  # -1, 0, +1
    octave: int = 0      # 相对中音组：-1 低八度, +1 高八度
    duration: float = 1.0  # 时值：1=四分, 0.5=八分, 0.25=十六分
    semitone: int = 0    # 调内绝对半音值（调主音=0）
    index: int = 0       # 在序列中的序号
    short: bool = False  # 切音记号（吐音/切分；谱面自占一个小窄格放在本音前面）
    slur_start: bool = False   # 连音线起点
    slur_end: bool = False     # 连音线终点
    tie: bool = False          # 与下一个同音相连（延音线）
    breath: bool = False       # 换气记号（画成数字上方一个小 v）
    direction: str = ""        # 反复记号方向：'start' | 'end' | 'both'
                               # 整段括号 / 结尾框也用：'start' | 'end'
    ending: int = 0            # 结尾框序号（1 = 第一结尾），非结尾事件为 0
    lyric: str = ""            # 可选歌词（第一行），画在数字与笛身之间
    lyric_lines: list = field(default_factory=list)   # 全部歌词行（多段词用；空则看 lyric）

    def note_name(self, tonic: int) -> str:
        """给定调主音半音值，返回绝对音名"""
        return NOTE_NAMES_SHARP[(tonic + self.semitone) % 12]


@dataclass
class ParsedScore:
    events: list = field(default_factory=list)
    ignored: list = field(default_factory=list)   # 被忽略的片段（供调试）
    tonic: int = 2            # 调主音绝对半音值（C=0）
    key: str = "D"            # 实际采用的调（规范名，如 "G"、"bB"）
    key_source: str = "default"  # 调号来源：param（显式指定）| text（谱内标注）| default（默认）

    @property
    def notes(self):
        return [e for e in self.events if e.kind == "note"]


def normalize_text(text: str) -> str:
    """归一化 OCR / 用户输入文本"""
    text = text.translate(_NORMALIZE_MAP)
    # 去掉组合上下点（U+0307 U+0323 等），八度改由成像分析或用户用 ./' 显式标注
    text = re.sub(r"[̣̇ˋˊ]", "", text)
    return text


def normalize_key(name) -> str | None:
    """把各种写法的调名规范为 KEY_SEMITONES 中的键；无法识别返回 None。

    例："g" -> "G"，"Bb" -> "bB"，"#f" -> "#F"，"♭E" -> "bE"
    """
    if not name:
        return None
    s = str(name).strip().replace("♯", "#").replace("♭", "b")
    m = _KEY_NAME_RE.fullmatch(s)
    if not m:
        return None
    letter = m.group(2).upper()
    acc = m.group(1) or m.group(3)
    if acc in ("b", "B"):
        cand = "b" + letter
    elif acc == "#":
        cand = "#" + letter
    else:
        cand = letter
    return cand if cand in KEY_SEMITONES else None


def is_frame_close(kind: str, direction: str = "start") -> bool:
    """这个框类记号是不是「收尾的那一侧」（`）` / `n]`）。

    排版上有个硬口径：**收尾那一侧留在小节线之前、起点那一侧落在小节线之后**
    （`（ 5 6 5 3 ） |`、`| （ 5 6 5 3`）—— 这样框才跟小节对齐。
    所以自动小节线填满一小节时，要先把紧跟其后的收尾记号让过去、再落线。
    编谱器走 project.display_notes，两边都必须调这个函数，口径才不会分叉。
    """
    return kind in FRAME_KINDS and str(direction or "start") != "start"


def insert_auto_bars(events, beats: str = "4/4"):
    """按拍号在事件序列里自动插入小节线（分隔符自动确定），并重排 index。

    - 逐音累计时值，填满一小节即插入一条小节线；溢出部分带入下一小节；
    - 原有小节线事件被丢弃（由算法统一重排）；
    - 末尾补收尾小节线。

    切音的时值照常累计（谱面只是把它画成小窄格，不代表它不占时间）。
    因此当切音正好补满一小节时，小节线会落在**切音之后**——此时切音本身是这一小节的
    末拍、它后面那个音起下一小节（记谱上是「装饰音在小节线前」，属于正常写法）。
    若希望切音落在小节内部，把切音前面的音排短一点即可（见 tests/notation_demo.py）。

    反复记号（`|:` `:|` `:|:`）是段落边界：**保留**（不像手写 `|` 会被重排）、不占时值。
    它自己就起小节线的作用（反复记号本来就是小节线的一种），所以同一个位置上
    **不会**再出现一条普通小节线：

    - 紧挨在它前面的那条普通小节线会被顶掉（免得 `|` 和 `|:` 叠在一起）；
    - 它出现在小节中间时，前面那半小节就由它收尾——**不补**收尾小节线，
      否则会画出 `1 2 3 | |: …` 这种「小节线和反复记号同时出现」的毛病。

    整段括号（`(` `)`）与结尾框（`[1` `1]`）同样**原样保留、不占时值**，但它们是
    **记号而不是小节线**：既不算小节边界，也不顶掉相邻的小节线——它们只是一个
    画在谱面上的框/括号，落在哪一拍就是哪一拍。

    唯一的例外是**贴着小节边界的那一侧**（见 `is_frame_close`）：收尾那一侧要留在
    小节线**之前**、起点那一侧落在小节线**之后**，框才跟小节对齐。所以填满一小节时，
    落线会先让过紧跟其后的收尾记号（`（ 5 6 5 3 ）` → `（ 5 6 5 3 ） |`，而不是
    `（ 5 6 5 3 | ）`）。
    """
    cap = BEATS_PER_MEASURE.get(beats)
    if not cap:
        return events
    for i, e in enumerate(events):
        e.index = i
    out, acc = [], 0.0
    pending = False      # 本小节已填满，但线要「让过」紧跟其后的收尾记号再落

    def add_bar():
        out.append(NoteEvent(kind="bar", token="|", index=len(out)))

    def flush_bar():
        nonlocal pending
        if pending:
            add_bar()
            pending = False

    for e in events:
        if e.kind == "bar":
            continue
        if e.kind == "repeat":
            flush_bar()                        # 反复记号就落在小节线该在的位置上
            if out and out[-1].kind == "bar":
                out.pop()                      # 反复记号自己就是小节线，取代紧邻那条
            # 反复记号本身就是小节线，它出现的地方就是小节边界：哪怕前面那半小节
            # 没填满，也由它来收尾。这里绝不能补 add_bar()，否则会画出 `| |:`。
            e.index = len(out)
            out.append(e)
            acc = 0.0
            continue
        if e.kind in FRAME_KINDS:
            # 括号 / 结尾框：不占时值，也不影响小节累计（它不改变音乐的时间线）
            if not is_frame_close(e.kind, getattr(e, "direction", "")):
                flush_bar()                    # 起点那一侧：落在小节线**之后**
            e.index = len(out)
            out.append(e)                      # 收尾那一侧：留在小节线**之前**（不清 pending）
            continue
        flush_bar()
        e.index = len(out)
        out.append(e)
        dur = 1.0 if e.kind == "hold" else getattr(e, "duration", 1.0)
        acc += dur
        if acc >= cap - 1e-6:
            pending = True
            acc = max(0.0, acc - cap)
    flush_bar()
    if out and out[-1].kind not in ("bar", "repeat"):
        add_bar()
    return out


def parse(text: str, key: str | None = None) -> ParsedScore:
    """把简谱文本解析为 NoteEvent 序列。

    key: 曲调，如 "D"、"G"、"bB"（即 1=D / 1=G / 1=bB）。
         传 None 时优先采用文本中的调号头（1=X），都没有则默认 D。
    """
    explicit = normalize_key(key) if key else None
    if key and explicit is None:
        raise ValueError(f"无法识别的调: {key!r}，可选: {sorted(set(KEY_SEMITONES))}")

    score = ParsedScore()
    text = normalize_text(text)

    # 提取并剔除文本中的调号头（避免 "1=G" 的 1 被当成音符）
    header_key = None

    def _strip_header(m: re.Match) -> str:
        nonlocal header_key
        if header_key is None:
            header_key = normalize_key(m.group(1))
        return " "

    text = _KEY_HEADER_RE.sub(_strip_header, text)

    if explicit is not None:
        resolved, source = explicit, "param"
    elif header_key is not None:
        resolved, source = header_key, "text"
    else:
        resolved, source = "D", "default"
    score.key = resolved
    score.key_source = source
    score.tonic = KEY_SEMITONES[resolved]

    pos = 0
    for m in _TOKEN_RE.finditer(text):
        gap = text[pos:m.start()]
        junk = gap.strip()
        if junk:
            score.ignored.append(junk)
        pos = m.end()
        idx = len(score.events)

        if m.group("repeat_both") is not None:
            score.events.append(NoteEvent(kind="repeat", token=":|:", index=idx,
                                          direction="both"))
            continue
        if m.group("repeat_start") is not None:
            score.events.append(NoteEvent(kind="repeat", token="|:", index=idx,
                                          direction="start"))
            continue
        if m.group("repeat_end") is not None:
            score.events.append(NoteEvent(kind="repeat", token=":|", index=idx,
                                          direction="end"))
            continue
        if m.group("ending_start") is not None:
            score.events.append(NoteEvent(kind="ending", token=m.group(), index=idx,
                                          direction="start",
                                          ending=int(m.group("ending_s_n"))))
            continue
        if m.group("ending_end") is not None:
            score.events.append(NoteEvent(kind="ending", token=m.group(), index=idx,
                                          direction="end",
                                          ending=int(m.group("ending_e_n"))))
            continue
        if m.group("lbracket") is not None:
            score.events.append(NoteEvent(kind="bracket", token=m.group(), index=idx,
                                          direction="start"))
            continue
        if m.group("rbracket") is not None:
            score.events.append(NoteEvent(kind="bracket", token=m.group(), index=idx,
                                          direction="end"))
            continue
        if m.group("bar") is not None:
            score.events.append(NoteEvent(kind="bar", token="|", index=idx))
            continue
        if m.group("dash") is not None:
            score.events.append(NoteEvent(kind="hold", token=m.group("dash"), index=idx))
            continue

        num = int(m.group("num"))
        acc_str = m.group("acc")
        suffix = m.group("suffix") or ""
        octave = suffix.count("'") - suffix.count(".")
        slashes = suffix.count("/")
        duration = 1.0 if slashes == 0 else (0.5 if slashes == 1 else 0.25)
        if "*" in suffix:
            duration *= DOT_FACTOR
        accidental = 1 if acc_str == "#" else (-1 if acc_str == "b" else 0)
        is_short = "!" in suffix            # 切音（吐音/切分）记号
        is_breath = "v" in suffix           # 换气记号（吹奏到这儿歇一口气）
        slur_str = "".join(ch for ch in suffix if ch in "()~")

        if num == 0:
            score.events.append(NoteEvent(kind="rest", token=m.group(),
                                          duration=duration, index=idx))
            continue

        semitone = DEGREE_SEMITONES[num] + accidental + octave * 12
        score.events.append(NoteEvent(
            kind="note", token=m.group(), degree=num,
            accidental=accidental, octave=octave, duration=duration,
            semitone=semitone, index=idx, short=is_short, breath=is_breath,
            slur_start="(" in slur_str, slur_end=")" in slur_str,
            tie="~" in slur_str,
        ))
    tail = text[pos:].strip()
    if tail:
        score.ignored.append(tail)
    return score
