"""爱尔兰哨笛指法引擎

孔位顺序：从上到下 1-6（吹奏时持笛的自然顺序，最上为孔1）。
每个指法用 6 元组表示：1=按住  0=放开  2=半孔

支持哨笛调性：D / C / Bb / G / F / Eb
可吹音域：筒音起两个八度（idx 0-24），idx>=22 标记为高难度超吹。
自动策略：
  1. 曲调主音换算到哨笛上的相对半音索引；
  2. 低于筒音的音自动升高八度，高于音域的自动降低八度（并给出提示）；
  3. 每个音给出主指法 + 备选指法（交叉指法 / 半孔）；
  4. 筒音在更高八度的同一个音（idx 12 / 24）主指法是「放开孔1、其余全按」——
     上下两个八度统一（第一八度的筒音 idx 0 照旧全按）。见 HIGH_TONIC。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .jianpu import DEGREE_SEMITONES, KEY_SEMITONES, NOTE_NAMES_SHARP

# 哨笛调性 -> 筒音的绝对半音值（C=0）
WHISTLE_TONICS = {"D": 2, "C": 0, "bB": 10, "G": 7, "F": 5, "bE": 3}

CLOSED, OPEN, HALF = 1, 0, 2
X, O, H = CLOSED, OPEN, HALF  # 简写

# 第一八度指法（idx 0-11，相对筒音的半音数）
#            音        孔1 2 3 4 5 6
_FIRST_OCTAVE = {
    0:  (X, X, X, X, X, X),   # 筒音
    1:  (X, X, X, X, X, H),   # 半孔6
    2:  (X, X, X, X, X, O),
    3:  (X, X, X, H, O, O),   # 半孔3（F natural on D whistle）
    4:  (X, X, X, X, O, O),
    5:  (X, X, X, O, O, O),
    6:  (X, X, H, O, O, O),   # 半孔2
    7:  (X, X, O, O, O, O),
    8:  (H, X, O, O, O, O),   # 半孔1
    9:  (X, O, O, O, O, O),
    10: (O, X, X, O, O, O),   # 交叉指法 C natural
    11: (O, O, O, O, O, O),   # C#（全开）
}

# 备选指法（同一音的其他常用按法，供演奏者选择）
_ALTERNATES = {
    1:  [(X, X, X, X, H, O)],
    3:  [(X, X, O, X, X, O)],          # F nat 交叉指法
    6:  [(H, X, X, O, O, O)],
    8:  [(X, X, X, O, X, X)],          # Bb 交叉指法
    10: [(X, X, X, O, O, H), (O, X, O, O, O, O)],  # C nat 其他按法
    11: [(X, X, O, X, X, X)],          # C# 稳定按法
    12: [(X, X, X, X, X, X)],          # 高八度筒音也可全按硬吹（备选；主指法见 HIGH_TONIC）
}

MAX_INDEX = 24          # 两个八度
HARD_INDEX = 22         # 以上属于高难度超吹

# 高八度筒音（idx 12 = 高一个八度、24 = 高两个八度）的主指法。
# 全按虽然也能靠加重气息硬吹上去，但起音难、音准容易飘；把**从上往下第一个孔（孔1）
# 放开**是通行指法。关键是**每个高八度都要一致**：同一个音名在两个八度里给出
# 互相矛盾的指法（一个放开孔1、一个全按）最容易被当成 bug。
HIGH_TONIC = (O, X, X, X, X, X)


def is_high_tonic(idx: int) -> bool:
    """是否是「筒音在更高八度」的同一个音（idx 12 / 24）——12 的正整数倍"""
    return idx > 0 and idx % 12 == 0


@dataclass
class FingeringResult:
    """一个音在指定哨笛上的映射结果"""
    playable: bool
    index: int = -1                 # 相对筒音的半音索引（八度调整后）
    holes: tuple = ()               # 主指法 6 元组
    alternates: list = field(default_factory=list)
    second_octave: bool = False     # 是否第二八度（超吹）
    hard: bool = False              # 高难度音
    shifted: int = 0                # 自动八度调整量（+12/-12，0=未调整）
    note_name: str = ""             # 绝对音名
    reason: str = ""                # 不可吹时的原因
    custom: bool = False            # 是否用户自选指法（编谱器手点孔位）


def fingering_for_index(idx: int) -> tuple:
    """由相对筒音的半音索引查主指法（0-24）

    筒音在更高八度的同一个音（idx 12 / 24）一律给 HIGH_TONIC（放开孔1、其余全按）——
    不是只处理 idx 12：只写 `idx == 12` 会让 24 掉回第一八度的全按，画出来的指法表里
    同一音名两格自相矛盾（13 格放开孔1、末格全按）。
    """
    if is_high_tonic(idx):
        return HIGH_TONIC
    return _FIRST_OCTAVE[idx % 12]


def map_note(semitone: int, tune_tonic: int, whistle_key: str = "D") -> FingeringResult:
    """把调内半音值映射到哨笛指法。

    semitone:   调内绝对半音（调主音=0，可含八度，如高八度 1 = 12）
    tune_tonic: 调主音的绝对半音值（C=0）
    whistle_key: 哨笛调性
    """
    if whistle_key not in WHISTLE_TONICS:
        raise ValueError(f"不支持的哨笛调性: {whistle_key}，可选: {sorted(WHISTLE_TONICS)}")

    absolute = tune_tonic + semitone              # 绝对半音（含八度）
    idx = absolute - WHISTLE_TONICS[whistle_key]  # 相对筒音
    note_name = NOTE_NAMES_SHARP[absolute % 12]

    shifted = 0
    while idx < 0:
        idx += 12
        shifted += 12
    while idx > MAX_INDEX:
        idx -= 12
        shifted -= 12
    # 防御性检查：上面的 ±12 搬移循环对任意整数输入恒收敛到
    # [0, MAX_INDEX]，因此该分支当前不可达（恒 playable=True）。
    # 保留以便未来改为严格模式（不自动移八度）时直接生效。
    if idx < 0 or idx > MAX_INDEX:
        return FingeringResult(playable=False, note_name=note_name,
                               reason="超出哨笛两个八度音域，无法演奏")

    holes = fingering_for_index(idx)
    alts = list(_ALTERNATES.get(12 if is_high_tonic(idx) else idx % 12, []))
    return FingeringResult(
        playable=True, index=idx, holes=holes, alternates=alts,
        second_octave=idx >= 12, hard=idx >= HARD_INDEX,
        shifted=shifted, note_name=note_name,
    )


def build_reverse_map(whistle_key: str = "D") -> dict:
    """按法反查表：holes 六元组 -> [FingeringResult, ...]（按音高升序）。

    编谱器用它把用户手点的孔位翻译成音名/简谱标记。
    主指法与全部备选指法都会进表；同一个按法不会重复登记。
    """
    rev: dict = {}
    tonic = WHISTLE_TONICS[whistle_key]
    for idx in range(MAX_INDEX + 1):
        combos = [fingering_for_index(idx)]
        combos += _ALTERNATES.get(12 if is_high_tonic(idx) else idx % 12, [])
        for holes in combos:
            key = tuple(holes)
            entry = FingeringResult(
                playable=True, index=idx, holes=key, alternates=[],
                second_octave=idx >= 12, hard=idx >= HARD_INDEX,
                shifted=0, note_name=NOTE_NAMES_SHARP[(tonic + idx) % 12],
            )
            bucket = rev.setdefault(key, [])
            if not any(e.index == idx for e in bucket):
                bucket.append(entry)
    for bucket in rev.values():
        bucket.sort(key=lambda e: e.index)
    return rev


def describe_holes(holes, whistle_key: str = "D"):
    """把一组孔位描述成 (音名, 是否标准按法)。无法识别时返回 ("自定义", False)。"""
    entry = build_reverse_map(whistle_key).get(tuple(holes))
    if not entry:
        return "自定义", False
    primary = entry[0]
    return primary.note_name + (" 高" if primary.second_octave else ""), True


# ---------------- 筒音指法模式（全按作N） ----------------
# 中国笛箫/哨笛传统约定：筒音（全按）落在哪个级数，就称“全按作N”。
#   D 调哨笛：全按作1 -> 1=D；全按作5 -> 1=G；全按作2 -> 1=C …
# 本质只是“1=X”的另一种说法，指法本身不变。
FLAT_KEYS = {0: "C", 1: "#C", 2: "D", 3: "bE", 4: "E", 5: "F",
             6: "#F", 7: "G", 8: "bA", 9: "A", 10: "bB", 11: "B"}

MODE_DEGREES = (1, 2, 3, 4, 5, 6, 7)


def mode_label(whistle_key: str, key: str) -> str:
    """返回指法模式名，如「全按作5」。无法用筒音级数表示时返回空串。"""
    diff = (WHISTLE_TONICS[whistle_key] - KEY_SEMITONES[key]) % 12
    for degree, semi in DEGREE_SEMITONES.items():
        if semi == diff:
            return f"全按作{degree}"
    return ""


def key_for_mode(whistle_key: str, degree: int) -> str:
    """由「全按作N」推回曲调 1=X。"""
    if degree not in DEGREE_SEMITONES:
        raise ValueError(f"级数必须是 1-7，收到 {degree}")
    tonic = (WHISTLE_TONICS[whistle_key] - DEGREE_SEMITONES[degree]) % 12
    return FLAT_KEYS[tonic]


def all_modes(whistle_key: str) -> dict:
    """该哨笛可用的全部「全按作N」指法模式 -> 曲调名"""
    return {f"全按作{d}": key_for_mode(whistle_key, d) for d in MODE_DEGREES}


def map_score(events, tune_tonic: int, whistle_key: str = "D"):
    """批量映射整首曲子，返回 (results, warnings)，与 events 一一对应（仅 note 事件有结果）"""
    results = {}
    warnings = []
    for e in events:
        if e.kind != "note":
            continue
        r = map_note(e.semitone, tune_tonic, whistle_key)
        results[e.index] = r
        if not r.playable:
            warnings.append(f"第 {e.index + 1} 个音 {e.token}({r.note_name})：{r.reason}")
        elif r.shifted:
            direction = "升高" if r.shifted > 0 else "降低"
            warnings.append(f"第 {e.index + 1} 个音 {e.token}({r.note_name})：超出音域，已自动{direction}八度")
        elif r.hard:
            warnings.append(f"第 {e.index + 1} 个音 {e.token}({r.note_name})：高难度超吹音，注意气息")
    return results, warnings
