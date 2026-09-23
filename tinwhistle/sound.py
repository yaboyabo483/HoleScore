"""试听：合成一个接近哨笛的音色，走声卡放出来（`winsound.PlaySound`）。
# SPDX-FileCopyrightText: 2026 yaboyabo483
# SPDX-License-Identifier: CC-BY-NC-SA-4.0

## 为什么不直接用 `winsound.Beep`

`Beep` 是 PC 蜂鸣器的方波，用户提的三个毛病其实是同一个根因：

* **停不下来**：`Beep(freq, ms)` **阻塞**调用它的线程，中途没有任何办法打断。按了停止，
  最多还得等这一个音放完（本项目整首试听的单音上限本来给到 3000 ms），听着就是「按了没反应」。
* **难听**：方波谐波很硬，起落还没有包络，每一声都带一层爆音。
* **短音等于没声音**：十六分音符只有一百多毫秒，方波在这个长度下基本只剩「咔」的一声，
  听不出音高 —— 用户说的「十六分音符他都放不出来」就是它。

## 现在的做法

按音高与时长**合成一段波形**（正弦基频 + 几个谐波 + 一点点气声，首尾做淡入淡出），
写成临时 `.wav`，再 `PlaySound(path, SND_FILENAME | SND_ASYNC)` **异步**播放：

* **能停**：`PlaySound(None, SND_PURGE)` 立刻掐掉当前声音；`Beeper` 等待用的是
  `Condition.wait(timeout)`，停用/换节目会马上把它唤醒 —— `stop()` 之后几十毫秒内就安静了。
* **音色**：谐波配比照着竖笛/哨笛调（基频为主、二次谐波少量），比方波软得多。
* **短音照样准**：采样级生成，十六分音符也是一段完整的 187 ms 音。

零第三方依赖（只用标准库 `wave` / `math` / `array` / `tempfile`），同一对「音高 + 时长」
复用同一个缓存文件（时长量化到 25 ms 一档），合成一遍之后几乎没有开销。

万一**合成或异步播放失败**（没有音频设备等原因），会退回 `Beep`：难听，但至少还有声音。

Linux / macOS 没有 `winsound`，`available()` 返回 False。

## 音高口径

哨笛的**实际发声**由「哨笛调性 + 指法索引」决定（不是简谱上的八度记号）——
D 哨笛的筒音是 D4（MIDI 62），比它高 n 个半音就加 n。这样听到的与谱面标的音名
（`FingeringResult.note_name`）永远一致，自动移八度的音也能听出真实音高。
"""

from __future__ import annotations

import array
import atexit
import math
import os
import random
import shutil
import tempfile
import threading
import time
import wave

from . import fingering, project as pj
from .jianpu import KEY_SEMITONES

try:                                    # 只有 Windows 有
    import winsound
except ImportError:                     # pragma: no cover - 非 Windows
    winsound = None

A4_HZ = 440.0
A4_MIDI = 69
MIN_HZ, MAX_HZ = 37, 32767             # 频率的合理区间（对外只出这个范围内的整数 Hz）

# D 调哨笛的筒音 = D4（MIDI 62）。别的调性的哨笛按与 D 的半音差平移：
# C 哨笛筒音 C4 = 60、bB 哨笛筒音 bB3 = 58 …（与 fingering.WHISTLE_TONICS 同口径）
BOTTOM_MIDI_OF_D = 62
_D_SEMITONE = KEY_SEMITONES["D"]

# 试听的速度与时长（编谱器里没有速度记号，用一个人耳舒服的默认值）
DEFAULT_BPM = 80
QUARTER_MS = 60_000.0 / DEFAULT_BPM     # 四分音符 = 750ms
PREVIEW_MIN_MS = 90                     # 「选中即试听」最短/最长：一挥而过也要听得见，
PREVIEW_MAX_MS = 600                    # 但拖长音的格子不该让人等。
TUNE_MAX_MS = 3000                      # 整首试听里单个音的封顶（防长延音拖死）

# ---------------- 音色 ----------------
SAMPLE_RATE = 22050                     # 够了：最高用到 ~1500Hz，谐波也就 6kHz
_TONE_GAIN = 0.55                       # 留出余量，几个谐波叠起来也不削波
# 谐波配比（倍数, 幅度）：基频为主、二次谐波少量 —— 竖笛/哨笛就是这个味道；
# 方波则是奇次谐波一路铺上去（那正是 Beep 刺耳的来源）。
_HARMONICS = ((1.0, 1.0), (2.0, 0.22), (3.0, 0.09), (4.0, 0.035))
_AIR_NOISE = 0.025                      # 一点气声，不然太「电子」
_ATTACK_S = 0.012                       # 淡入淡出：Beep 那种爆音就是没有它
_RELEASE_S = 0.045
_GAP_MS = 10                            # 相邻两个音之间留的气口（同音高的连音才糊成一坨）
_QUANT_MS = 25                          # 缓存时长按这个步长取整（不至于每个时长都一份文件）
_MAX_CACHE = 96                         # 缓存文件上限，超了丢最旧的一半

_SIN_N = 4096
_SIN = [math.sin(2.0 * math.pi * i / _SIN_N) for i in range(_SIN_N)]
_NOISE = None                           # 首次用时生成（固定种子 —— 同一个音每次听起来一样）


def available() -> bool:
    """这个平台能不能发声（Windows 才有 winsound）。"""
    return winsound is not None


def _noise_table():
    global _NOISE
    if _NOISE is None:
        r = random.Random(20260923)
        _NOISE = [r.uniform(-1.0, 1.0) for _ in range(_SIN_N)]
    return _NOISE


def _sin_unit(phase: float) -> float:
    """sin(2π·phase)（phase 取小数部分）—— 查表替掉每采样点一次 `math.sin`，合成快几倍。"""
    return _SIN[int(phase * _SIN_N) & (_SIN_N - 1)]


def synth_frames(hz: float, ms: int) -> bytes:
    """合成一段 16bit 单声道采样数据（`miusicv` 自己的音色，见模块头）。"""
    n = max(1, int(round(ms / 1000.0 * SAMPLE_RATE)))
    atk = max(1, int(_ATTACK_S * SAMPLE_RATE))
    rel = max(1, int(_RELEASE_S * SAMPLE_RATE))
    if atk + rel >= n:                  # 短音（十六分）：包络按比例收，别把整个音吃掉
        atk = max(1, int(n * 0.15))
        rel = max(1, int(n * 0.30))
    noise = _noise_table()
    step = hz / SAMPLE_RATE             # 每个采样点推进的相位
    buf = array.array("h", bytes(2 * n))
    for i in range(n):
        ph = step * i
        v = 0.0
        for mult, amp in _HARMONICS:
            v += amp * _sin_unit(ph * mult)
        v += _AIR_NOISE * noise[i & (_SIN_N - 1)]
        if i < atk:
            v *= i / atk
        elif i > n - rel:
            v *= (n - i) / rel
        buf[i] = int(v * 32767.0 * _TONE_GAIN)
    return buf.tobytes()


_tone_cache: dict = {}                  # (hz, 时长档) -> wav 路径
_tone_dir = None
_cache_lock = threading.Lock()


def _ensure_dir() -> str:
    global _tone_dir
    if _tone_dir is None:
        _tone_dir = tempfile.mkdtemp(prefix="miusicv-tone-")
    return _tone_dir


def ensure_tone(hz: int, ms: int) -> str:
    """拿到这个「音高 + 时长」的 wav 路径（合成一次之后都是缓存命中）。"""
    play_ms = max(30, int(ms) - min(_GAP_MS, int(ms) * 0.2))
    key = (int(hz), max(1, int(round(play_ms / _QUANT_MS)) * _QUANT_MS))
    with _cache_lock:
        hit = _tone_cache.get(key)
        if hit and os.path.isfile(hit):
            return hit
        if len(_tone_cache) >= _MAX_CACHE:          # 到上限了：丢最旧的一半
            for k in list(_tone_cache)[:_MAX_CACHE // 2]:
                p = _tone_cache.pop(k, None)
                if p:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        path = os.path.join(_ensure_dir(), f"t{key[0]}-{key[1]}.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(synth_frames(float(key[0]), key[1]))
        _tone_cache[key] = path
        return path


def cleanup_tones() -> None:
    """删掉临时音色目录（关窗口时调；atexit 也兜一层）。"""
    global _tone_dir
    with _cache_lock:
        _tone_cache.clear()
        d, _tone_dir = _tone_dir, None
    if d:
        shutil.rmtree(d, ignore_errors=True)


atexit.register(cleanup_tones)


def _tone(hz: int, ms: int) -> None:
    """发一个音（**不阻塞**：交给系统异步播）—— 测试里替换的就是这一个函数。"""
    try:
        path = ensure_tone(int(hz), int(ms))
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        return                          # 声音已经在放了，回来的人自己数时间
    except Exception:                   # noqa: BLE001 - 没音频设备 / 合成失败都要兜住
        pass
    try:                                # 兜底：回到 Beep（难听，但至少有声音）
        winsound.Beep(int(hz), int(ms))
    except Exception:                   # noqa: BLE001
        pass


def _stop_now() -> None:
    """立刻掐掉正在响的声音（测试里替换的就是这一个函数）。"""
    if winsound is None:
        return
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:                   # noqa: BLE001
        pass


# ---------------- 音高换算 ----------------

def midi_for_index(index: int, whistle_key: str = "D") -> int:
    """指法索引（相对筒音的半音数）→ MIDI 音高。"""
    tonic = fingering.WHISTLE_TONICS.get(whistle_key, fingering.WHISTLE_TONICS["D"])
    return BOTTOM_MIDI_OF_D + (tonic - _D_SEMITONE) + int(index)


def hz_for_midi(midi: int) -> int:
    """MIDI → 频率（整数 Hz，夹在合理范围里）"""
    hz = A4_HZ * (2.0 ** ((midi - A4_MIDI) / 12.0))
    return int(max(MIN_HZ, min(MAX_HZ, round(hz))))


def hz_for_result(result, whistle_key: str = "D"):
    """指法结果 → 频率；不可吹 / 索引非法时返回 None。

    **响的是谱面上写的那个音，不是搬过八度后的指法**。指法引擎为了把音塞进哨笛的两个八度
    音域，会把超出音域的音整体搬一个八度（`FingeringResult.shifted`：升高记 +12、
    降低记 -12）。指法图那么画是对的（你只能按得出音域里的孔位），但**试听不能照搬** ——
    否则谱面上的高音会照着搬低后的指法响成低音，听着就是「高音播的都是低音」。
    所以这里把 `shifted` 减回去，还原成谱面音高。
    """
    if result is None or not getattr(result, "playable", False):
        return None
    idx = getattr(result, "index", -1)
    if idx is None or idx < 0:
        return None
    written = idx - int(getattr(result, "shifted", 0) or 0)
    return hz_for_midi(midi_for_index(written, whistle_key))


def hz_for_holes(holes, whistle_key: str = "D"):
    """孔位（自选指法）→ 频率。查不出来返回 None。

    自选指法要按**孔位的实际发声**响，而不是按简谱上写的音高 ——
    编谱器里「音名反查」就是这么定的（孔位才是决定音高的东西）。
    """
    if not holes:
        return None
    try:
        bucket = fingering.build_reverse_map(whistle_key).get(tuple(holes))
    except (ValueError, TypeError):
        return None
    if not bucket:
        return None
    return hz_for_midi(midi_for_index(bucket[0].index, whistle_key))


def hz_of_doc(doc: dict, key: str, whistle: str):
    """一个音符文档（工程里的 note）→ 频率；休止/延音/记号返回 None。"""
    if doc.get("kind", pj.KIND_NOTE) != pj.KIND_NOTE:
        return None
    custom = hz_for_holes(doc.get("holes"), whistle)
    if custom is not None:
        return custom
    return hz_for_result(pj.to_result(doc, 0, key, whistle), whistle)


def ms_of_doc(doc: dict, bpm: float = DEFAULT_BPM, cap: int = TUNE_MAX_MS) -> int:
    """一个单元的时值 → 毫秒（四分音符 = 60000/bpm）。"""
    dur = float(doc.get("duration", 1.0) or 1.0)
    return int(max(20, min(cap, round(dur * 60_000.0 / max(20.0, float(bpm))))))


def preview_ms(doc: dict, bpm: float = DEFAULT_BPM) -> int:
    """「选中即试听」用的时长：按实际时值算，但夹到 [PREVIEW_MIN_MS, PREVIEW_MAX_MS]。"""
    ms = ms_of_doc(doc, bpm, cap=PREVIEW_MAX_MS)
    return int(max(PREVIEW_MIN_MS, min(PREVIEW_MAX_MS, ms)))


def sequence(project: dict, bpm: float = DEFAULT_BPM) -> list:
    """整首试听用的事件表：`[(hz 或 None, ms, 文档下标), ...]`。

    * 音符 → 自己的音高；休止 → None（**静音也要占时间**，不然听不出停顿）；
    * 延音 `-` → 接在上一个音后面继续响（把上一项的 ms 加长；前面是静音就跳过）；
    * 小节线 / 反复记号 / 括号 / 结尾框 → 不占时间，直接跳过。

    音高取的是**实际发声**（见模块头），所以自动移八度过的音听到的是谱面标注的那个音。
    """
    key = project.get("key", "D")
    whistle = project.get("whistle", "D")
    out: list = []
    for i, doc in enumerate(project.get("notes", []) or []):
        kind = doc.get("kind", pj.KIND_NOTE)
        if kind in pj.FRAME_KINDS or kind in (pj.KIND_BAR, pj.KIND_REPEAT):
            continue
        ms = ms_of_doc(doc, bpm)
        if kind == pj.KIND_HOLD:
            if out and out[-1][0] is not None:
                hz, prev_ms, idx = out[-1]
                out[-1] = (hz, prev_ms + ms, idx)
            continue
        out.append((hz_of_doc(doc, key, whistle) if kind == pj.KIND_NOTE else None, ms, i))
    return out


class Beeper:
    """一个工作线程按节目单播放，界面不会被阻塞。（名字留着，其实早就不是 Beep 了）

    设计要点：

    * **能停**：每个音是**异步**放出声的，线程只负责数时间 —— 数时间用
      `Condition.wait(timeout)`，`stop()` 一发就被唤醒。真正的掐音（`PlaySound(None,
      SND_PURGE)`）是**主线程在 `stop()` 里立刻做掉的**，不等线程排班，所以几十毫秒内就安静。
      （老口径用阻塞的 `Beep`，按下停止还得等这一个音放完 —— 长音要等满 3 秒。）
    * **最新请求胜出**：`submit()` / `stop()` 都会把代次 `_gen` +1，旧的那份节目单立刻认输。
      新的音自身会盖掉上一个异步音，所以连按 ←→ 不再追着响一串。
    * `on_step` 回调**在工作线程里**被调用，只用来回报「现在放到第几个音」；
      要动界面的话请自己 `root.after(0, ...)` 转回主线程（tkinter 不是线程安全的）。
    """

    def __init__(self, tone=None, stop=None):
        self._tone = tone if tone is not None else _tone
        self._stop = stop if stop is not None else _stop_now
        self._cv = threading.Condition()
        self._program: list = []
        self._on_step = None
        self._quit = False
        self._active = False
        self._gen = 0                       # 节目单代次：submit / stop / close 都会 +1
        self._thread = None

    # ---- 外部接口 ----
    def play_hz(self, hz, ms: int) -> None:
        """响一个音（hz=None 则静音 ms 毫秒）。"""
        self.submit([(hz, int(ms), None)])

    def submit(self, program, on_step=None) -> None:
        """换一份新节目单（会打断旧的）。program: [(hz|None, ms, payload), ...]"""
        with self._cv:
            self._gen += 1                  # 旧节目单作废（不必显式的掐音：新音自己盖上去）
            self._program = list(program)
            self._on_step = on_step
            self._start_locked()
            self._cv.notify_all()

    def stop(self) -> None:
        """停下：**立刻**安静（当前这个音不用响完）。"""
        self._stop()                        # 主线程先把声音掐掉，不等线程醒过来
        with self._cv:
            self._gen += 1
            self._program = []
            self._on_step = None
            self._cv.notify_all()

    def busy(self) -> bool:
        with self._cv:
            return self._active or bool(self._program)

    def close(self) -> None:
        """收线程（关窗口时调；线程本来就是 daemon，这里只是让它早点退）。"""
        self._stop()
        with self._cv:
            self._gen += 1
            self._quit = True
            self._program = []
            self._cv.notify_all()

    # ---- 内部 ----
    def _start_locked(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="tinwhistle-player",
                                            daemon=True)
            self._thread.start()

    def _wait(self, ms: float, gen: int) -> bool:
        """数 `ms` 毫秒；期间代次变了（停用 / 来了新节目单）就立刻返回 False。"""
        with self._cv:
            if self._quit or self._gen != gen:
                return False
        if ms <= 0:
            return True
        end = time.monotonic() + ms / 1000.0
        with self._cv:
            while True:
                if self._quit or self._gen != gen:
                    return False
                left = end - time.monotonic()
                if left <= 0:
                    return True
                self._cv.wait(min(left, 0.05))

    def _run(self) -> None:
        while True:
            with self._cv:
                while not self._program and not self._quit:
                    self._cv.wait()
                if self._quit:
                    return
                program, on_step, gen = self._program, self._on_step, self._gen
                self._program = []
                self._active = True
            try:
                for hz, ms, payload in program:
                    if hz is None:          # 休止：静音也占时间（换了节目就立刻走人）
                        self._stop()
                        if not self._wait(ms, gen):
                            break
                    else:
                        self._tone(int(hz), int(ms))
                        if not self._wait(ms, gen):
                            break
                    if on_step is not None and payload is not None:
                        try:
                            on_step(payload)
                        except Exception:      # noqa: BLE001 - 回调出错也不该弄死播放线程
                            pass
            finally:
                with self._cv:
                    self._active = False
