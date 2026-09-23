"""图形化编谱器（键盘编谱 + 点洞洞编谱，实时预览，自动保存工程）

界面布局：
  ┌ 工具栏：新建 打开 保存 导出SVG 整谱预览 撤销 重做 | 曲名 | 1=X | 哨笛 | 全按作N
  ├ 谱面编辑区（横向滚动条整条可拖；滚轮横向滚、Shift+滚轮纵向滚）：
  │                        每个音一列 —— 数字在上，洞洞在下，两者严格同列同宽；
  │                        小节线按拍号自动分隔
  ├ 属性条：选中音的时值/八度/升降/删除/左右移动/恢复自动指法
  ├ 左：简谱键盘（低/中/高三行 × 1-7）+ 休止/延音/小节线 + 时值/附点/升降 + 节拍
  ├ 右：自选指法（逐孔切换 按→放→半）+ 大图预览 + 反查音名/简谱
  ├ 指法表：当前哨笛 + 当前「全按作N」下的两个八度指法（点格子即可编谱）
  └ 状态栏：工程路径、音数、自动保存时间、提示

物理键盘：1-7 加音，0 加休止（用当前时值：q/w/e 定四分/八分/十六分，于是 0、0/、0//），
          - 延音，r / Shift+r 加反复记号 |: / :|，z/x 换八度，= 附点，t 切音，v 换气，
          s/♯、d/♭ 定升降，[ ] 连音线起止，\\ 延音线，() 整段括号起止，
          Alt+[ / Alt+] 第 n 结尾框起止，← → 选音，Del 删除，
          Ctrl+L 填词（可写多段词），Ctrl+Z/Y 撤销重做，Ctrl+S 保存，Ctrl+E 导出，
          F5 整谱预览。

整谱预览（F5 / 工具栏「整谱预览」）：
  谱面主区是一条无限长的横带（方便连续编谱），看不到「导出后长什么样」。
  预览窗口补上这一环：用导出那一套版式（render._build_layout：纸张、一行几个小节、
  不从小节中间换行、行不跨页）把整首曲子**一页一页摊开**，单格仍用主谱面区的画法
  （draw_cell / draw_mark_layer），所以「预览 = 主谱面区的画法 + 导出版式」。
  窗口内可缩放/滚动、可跟随编辑自动刷新，也可以一键用浏览器打开真实导出 SVG（100% 保真）。

输出（工具栏下方的「纸张 / 一行 / 水印 / 图片倍率」一条设置栏，会随工程存盘）：
  - 纸张：竖版 A4 / B4 / A3（页宽页高按毫米换算，可直接打印）；
  - 一行：一行排几个小节——「自动」= 按最少行数均分成 4~6 个，也可固定成 2/3/4/5/6 个；
  - 水印：自选文字，淡淡一层（10% 不透明度、灰色斜排、画在谱面**下面**），
    任何颜色打印都不影响阅读；
  - 图片倍率：1x ~ 5x（都是矢量按目标像素重画，不是位图放大；默认 1x）；
  - 「导出 SVG」与「导出图片 PNG」都按这条设置走：**放不下自动分页**，
    单页输出 曲名.svg，多页输出 曲名-1.svg / 曲名-2.svg …（图片同理）。

大工程不卡：tk 是单线程的，打开 / 保存 / 导出期间界面必然冻住，所以这些活统一丢给
工作线程（`_run_busy`），主线程弹进度条（`BusyDialog`，不到 300ms 干完就不弹）。
另外打开工程时十几个控件连着 set，每个都挂着 trace（→ 重画整张谱面），大谱子会重画
十几次，所以批量 set 期间用 `_bulk_set` 屏蔽掉，末尾只重画一次。

自动跟随：新加的音如果落在谱面可见区之外（长谱往右写出去时），谱面区会**自动横向滚**
  到那个新音上（左边留半格上下文），不用再手动拖横向滚动条。

光标：编辑区里当前是**竖线光标**（亮蓝 I 形，上下带横帽），不是整格方框——
  不开「插入到选中音前」时光标在**曲末**（新音追加到最后），
  开了且选中了某个音时光标在那个格子的**左边缘**（新音插在它前面）。
  它与小节线刻意做了区分：小节线是灰色细竖线、没有横帽。

记谱规范（与导出 SVG 完全一致）：
  - 减时线连尾：同一拍内相邻的八分 / 十六分共用一条连续横线，十六分的第二条线只落在
    十六分音符下方（beaming.beam_segments 统一计算，拍号决定分组单位）；
  - 休止符：有八分 / 十六分的休止（0/、0//）。**短休止符和音符一样参与连尾**
    （减时线是「这一拍是几分音符」的标记，把休止挖掉会把同一拍切成好几截），
    所以画布与导出都走同一条连尾层；
  - 反复记号（循环符号）：|: 反复开始、:| 反复结束、:|: 收尾并起下一段。它自占一格、
    不占时值，在自动小节线模式下不会被重排掉；
  - 换气记号 v：画在数字正上方（高八度点之上），本格带换气时连音弧线自动往上让一层；
  - 整段括号：成对圆括号把一段音整段括起来（前奏 / 间奏 / 和声伴唱），`(` 起、`)` 止。
    左右两侧**各自自足**（左括号画在起点那格左缘、右括号画在终点那格右缘），
    所以跨行也不会像连音线那样整条丢掉；不占时值，也不是小节边界；
    **贴着小节边界的那一侧按记谱口径让位**：起落在小节线之后、止落在小节线之前
    （`（ 5 6 5 3 ） |` 而不是 `（ 5 6 5 3 | ）`），框才跟小节对齐（见 jianpu.is_frame_close）；
  - 「第 n 结尾」框（房子记号，配合反复用）：`[n` 起、`n]` 止，起止**手工指定**。
    横线压在这一段所有记号（高八度点 / 换气 v / 连音弧线）之上，标号「n.」写在框子
    里面左端；框子画在行顶上方，所以画布顶部/行高/页眉带都会按**实际内容**多留一点
    （见 frame_top_need 与 render.ending_top_need），不会压到上一行或图例；
  - 歌词：画在「数字」与「笛身」之间，可以**多行（多段）**——整谱按最多的那几行统一
    让位、逐行往上摞（第 1 行最靠上），行数一多谱面/行高自动往下长，不会互相压；
  - 连音线：起点/终点配成弧线，同音高=延音线（棕）、不同音高=圆滑线（绿）；
  - 切音记号：**自己占一个小小的窄格子**（列宽 × CUT_CELL_RATIO），紧跟在后一个音前面——
    窄格里是「小数字（被切音的音高）+ 右上角小斜杠（吐音 / 切分）」，
    下面配一张缩小版指法图（被切音自己的指法），孔心与小数字同一条竖线；
    主音仍占满格，谱面按格子宽度逐行铺排（与 SVG 导出完全一致）。
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
import tkinter as tk
from copy import deepcopy
from tkinter import filedialog, messagebox, ttk

from tinwhistle import (apppaths, beaming, fingering, imageout, jianpu,
                        project as pj, render, sound)

# ---- 产品名（改这里，窗口标题就跟着变）----
APP_NAME = "笛洞工坊"                       # 中文名：笛（哨笛）+ 洞（洞洞谱）+ 工坊（编谱这套工具）
APP_NAME_EN = "HoleScore"                   # 英文名：代码常量 / 仓库名用
APP_TITLE = f"{APP_NAME} —— 爱尔兰哨笛简谱编谱器"

KEY_LIST = ["C", "#C", "D", "bE", "E", "F", "#F", "G", "bA", "A", "bB", "B"]
WHISTLE_LIST = list(fingering.WHISTLE_TONICS.keys())
BEATS_LIST = list(jianpu.BEATS_PER_MEASURE.keys())
PAPER_LIST = list(render.PAPERS.keys())          # 竖版纸张：A4 / B4 / A3
ROW_MEASURE_LIST = ["自动"] + [str(n) for n in render.ROW_MEASURES_CHOICES]  # 自动 / 2~6
ROW_MEASURE_LABELS = ["自动"] + [f"{n} 个" for n in render.ROW_MEASURES_CHOICES]
# 「谱面大小」下拉里给的几档（控件是 normal 的，也允许直接敲任意 50~100 的数）
CONTENT_SCALE_CHOICES = (100, 90, 80, 70, 60, 50)
# 工程与输出目录都按**程序根目录**定位（源码运行 = 项目根，打包后 = exe 所在目录）。
# 不能写成 os.path.dirname(__file__)：打包后那是解包目录，自动保存会落在临时目录里，
# 一关程序工程就没了（详见 tinwhistle/apppaths.py）。
PROJECT_DIR = apppaths.sub_dir("projects")
AUTOSAVE_PATH = os.path.join(PROJECT_DIR, "autosave.json")
OUTPUT_DIR = apppaths.sub_dir("output")

# ---- 画布几何（scale=1 时的像素值） ----
# 对齐约束：数字中心 = 时值横线中点 = 笛身中心 = 六个孔心所在竖线，宽度统一为 COL_W
CELL_W, CELL_H = 60, 204
COL_W = 24
LABEL_CY = 26
# 数字字形高度 —— 小节线 / 反复记号的竖线按它对齐，只盖住数字本身，
# 不再一路拉到笛身那么长。口径与 render.DIGIT_TOP_DY / DIGIT_BOT_DY 一致
# （那边是 SVG 字号 26 的 19px；画布这边字号 17，实测墨迹 ≈ 18px）。
# 注意：Tk 的文字锚点按**行框**居中（行框含降部空白），所以数字墨迹的竖向中心
# 比 LABEL_CY 低约 1px——拿 LABEL_CY 当中心会让竖线整体偏高 1px（标定实验所得）。
DIGIT_H = 18
DIGIT_INK_CY = LABEL_CY + 1
DIGIT_TOP = DIGIT_INK_CY - DIGIT_H / 2        # = 18
DIGIT_BOT = DIGIT_INK_CY + DIGIT_H / 2        # = 36
# 延音横线「-」的口径，和 render.HOLD_W / render.HOLD_DY 是一对：
#   * 长度**定长**（不跟格宽走）—— 画布格子定宽 60，导出那边列距是自适应压出来的，
#     跟格宽走的话同一份谱两处长短不一；
#   * 竖向中心对准数字墨迹中心（画布上就是 DIGIT_INK_CY）。
# 画布数字比导出的略小一号（墨迹 18 vs 19、步进 14 vs 15），长度也跟着小 1px：
# 17 ≈ round(render.HOLD_W 18 × 18 / 19)。
HOLD_W = 17
REPEAT_DOT_R = 2.4        # 反复点半径（竖线只有数字那么高，点要跟着收）
REPEAT_DOT_DY = 4.8       # 两粒反复点相对竖向中心的偏移
FLUTE_TOP, FLUTE_W, FLUTE_H = 58, COL_W, 100
HOLE_R, HOLE_DY = COL_W * 0.31, 15.0
# 音名基线相对「笛身尾端」的下移量 —— 中间那条 12px 的空带留给超吹三角
# （口径与 render.NAME_DY_FROM_FLUTE 一致；CELL_H 有余量，下移不需要改格子高度）。
NAME_DY = 29
BEAM_Y1, BEAM_Y2 = 40, 45
BAR_EXTRA_W = 14          # 小节线格子的额外宽度
SCORE_TOP = 36            # 谱面顶部留白（给连音弧线 / 换气记号让位）
CHART_SCALE = 0.55        # 两八度指法表缩放
CHART_ROW_H = 136         # 指法表画布高度：格子本身只到 4 + CELL_H*CHART_SCALE ≈ 116，
                          # 下面再放一行 8px 的音名。原来是 150，白留了 14px；
                          # 这 14px 挪给谱面区（谱面区装下整个格子要 258px 起）。
PREVIEW_ZOOMS = (0.45, 0.6, 0.75, 1.0)   # 整谱预览的缩放档位
PREVIEW_LIVE_MS = 80      # 预览「跟随编辑」的合并窗口
PREVIEW_LIVE_MAX = 800    # 音数超过这个值就把合并窗口拉长（重画约 100ms/600 格）
PREVIEW_PAD = 12          # 整谱预览里页面四周的留白（页面竖着摊开，页与页留 PREVIEW_PAD+6）
SCORE_MIN_H = 120         # 谱面区画布的**保底**高度（窗口矮到装不下时一路让到这个值）
#  (PRE / TAIL / WAIT 三档，前两版修复都在调它们的数值。2026-09-23 拿到用户端的真实日志后
#  整套删掉了 —— 见 `_lyric_commit_next`：Tk 在上屏事件里就把答案给了（`event.char` 是上屏
#  的那个字），不需要也不应该用时间窗口去猜。
#  留下的教训：**这类「按键被输入法吃了」的岔子，先去 `event.char` 里找答案，别急着调等待时间**。）


# --------------------------------------------------------------------------------
# 输入法状态：查 imm32（只是**兜底**，有些输入法查不到）
# --------------------------------------------------------------------------------
# 「这个按键到底给没给输入法」的答案，Tk 已经放在 `event.char` 里了（见 `_lyric_commit_next`）。
# 这条 imm32 查询只在拿不到那个答案时补一刀：**正在组字** ⇒ 空格必然是上屏用的 ⇒ 不跳。
#
# 注意它**不是**万能的：用户的输入法走 TSF 框架时，`ImmGetCompositionString` 在整段组字期间
# 都返回 0（实测日志里 `comp=0` 从头到尾），这条路等于不存在 —— 所以它只能当兜底，当不了主判据。
_GCS_COMPSTR = 0x0008                 # ImmGetCompositionString 的「正在组的串」索引
_IMM32 = None                         # None = 还没试过；False = 这机器查不了；否则是 WinDLL


def _win_imm32():
    """加载 imm32（Windows 输入法接口）。拿不到就返回 None —— 调用方退回时间判据。"""
    global _IMM32
    if _IMM32 is None:
        try:
            import ctypes
            from ctypes import wintypes
            imm = ctypes.WinDLL("imm32")
            imm.ImmGetContext.restype = wintypes.HANDLE
            imm.ImmGetContext.argtypes = [wintypes.HWND]
            imm.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
            imm.ImmReleaseContext.restype = wintypes.BOOL
            imm.ImmGetCompositionStringW.argtypes = [
                wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
            imm.ImmGetCompositionStringW.restype = ctypes.c_long
            _IMM32 = imm
        except Exception:
            _IMM32 = False            # 非 Windows / 没有 imm32：别再反复试了
    return _IMM32 or None


def ime_is_composing(hwnd=None) -> bool:
    """焦点所在的输入框里，输入法**此刻**是不是正在组字（打了拼音还没上屏）。

    **兜底用**（真正的主力判据是 `event.char`，见 `_lyric_commit_next`）：走 TSF 的输入法
    压根不填这个 composition string，查出来恒为 0 —— 那种机器上这条等于不存在。

    hwnd 不传就用当前焦点窗口。查不了（非 Windows / 聚焦在别的控件 / 输入法不填 composition）
    一律返回 False ——「查不出来」不等于「没在组字」，别拿它当否定证据。
    """
    imm = _win_imm32()
    if imm is None:
        return False
    try:
        if not hwnd:
            import ctypes
            hwnd = ctypes.windll.user32.GetFocus()
        if not hwnd:
            return False
        himc = imm.ImmGetContext(hwnd)
    except Exception:
        return False
    if not himc:
        return False
    try:
        # 传空缓冲只问长度：> 0 表示有正在组的串，即「还在组字」
        return imm.ImmGetCompositionStringW(himc, _GCS_COMPSTR, None, 0) > 0
    except Exception:
        return False
    finally:
        try:
            imm.ImmReleaseContext(hwnd, himc)
        except Exception:
            pass


# --------------------------------------------------------------------------------
# 「输入法抢空格」诊断开关（默认关，带上 MIUSICV_IME_DEBUG 环境变量才开）
# --------------------------------------------------------------------------------
# 这个 bug 的答案全在那台机器的真实时序里：按键到底比上屏早到还是晚到、那一刻输入法是不是
# 还在组字、会不会多漏一个按键给 Tk —— 每家输入法都不一样，在这台机器上量出来的数字到
# 用户那边常常对不上，猜是猜不出来的（前面连着两版修复都栽在这上面）。
# 于是留个开关：这么启动
#     set MIUSICV_IME_DEBUG=1
#     G:\Conda\python.exe editor.py
# 歌词框的一举一动就都会写进 `tests/_ime_debug.log`，把那份日志发回来即可对准症状下药。
_IME_DEBUG_FILE = ""
if os.environ.get("MIUSICV_IME_DEBUG"):
    _IME_DEBUG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "tests", "_ime_debug.log")
_IME_DEBUG_T0 = None


def _ime_debug(msg: str):
    """给歌词输入的时间线记一行（没开诊断就什么都不做，平时零开销）。"""
    global _IME_DEBUG_T0
    if not _IME_DEBUG_FILE:
        return
    now = time.monotonic()
    if _IME_DEBUG_T0 is None:
        _IME_DEBUG_T0 = now
    try:
        with open(_IME_DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write("[%+8.1f ms] %s\n" % ((now - _IME_DEBUG_T0) * 1000.0, msg))
    except OSError:
        pass


def _ime_probe_state() -> str:
    """诊断专用：当时输入法组字串的长度（0 = 没在组字；负 / 文字 = 这条路查不了）。"""
    imm = _win_imm32()
    if imm is None:
        return "comp=不可用"
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetFocus()
        if not hwnd:
            return "comp=无焦点"
        himc = imm.ImmGetContext(hwnd)
        if not himc:
            return "comp=无上下文"
        try:
            return "comp=%d" % imm.ImmGetCompositionStringW(himc, _GCS_COMPSTR, None, 0)
        finally:
            imm.ImmReleaseContext(hwnd, himc)
    except Exception:
        return "comp=异常"


# 键盘说明。**不要贴在界面上**：这段文字排下来要 106px，而窗口总共只有 1000px，
# 谱面区（需要 CELL_H + SCORE_TOP = 258px 才装得下整个格子）是唯一能让步的一块，
# 于是它被挤到只剩 154px，笛身和音名直接被下边缘裁掉。挪进「键盘说明」弹窗后，
# 谱面区才拿得到它需要的完整高度（信息一点没少，点一下就看得到）。
KEY_HELP_TEXT = (
    "1-7 加音（按 z/x 定的八度），0 加休止，- 延音，| 小节线\n"
    "r / Shift+r 反复起 |: / 反复止 :|\n"
    "z / x 换八度，q / w / e 四分·八分·十六分，= 附点\n"
    "t 切音，v 换气，s / d 升·降号，[ ] 连音线起止，\\ 延音线\n"
    "( ) 整段括号起止，Alt+[ / Alt+] 第 n 结尾框起止（n 见「第 n 结尾」；\n"
    "  结尾收尾那个 n] 里的 n 是标号、与 [n 呼应，不是音符 —— 要在这个位置放音\n"
    "  就单独写一格，比如 1 1]）\n"
    "← / → 选音，Del 删除\n"
    "Ctrl+L 填词（「＋行」可写多段词），Ctrl+Z/Y 撤销·重做\n"
    "  填词时空格 / Tab 跳到下一个音；中文输入法会拿空格去选候选上屏，\n"
    "  碰上（比如打「映」这种要手动选的字）按 Tab —— 它不会被输入法吃掉\n"
    "Ctrl+S 保存，Ctrl+E 导出 SVG，F5 整谱预览\n"
    "p 试听选中的音，Ctrl+P 整首试听（再按一次停；状态栏可关「选中即试听」、调速度）\n"
    "  试听是按采样合成的哨笛音色（不是蜂鸣器）：翻到 ■ 就立刻停，十六分音符也听得清\n"
    "\n"
    "休止符也吃当前时值：w 再按 0 = 八分休止 0/，e 再按 0 = 十六分休止 0//"
)

# 歌词（可选）：一个汉字或英文单词，画在「简谱数字」和「洞洞」之间。
# 这一带只留了十几 px（减时线 / 低八度点就占住了），所以只要整谱里有任何一个音带歌词，
# 就把笛身与音名整体下移 LYRIC_DY 让出一条歌词带（CELL_H 不动，用行底余量消化）。
# 与 render.py 同口径；没有歌词时谱面完全不变。
# 多行（多段）歌词：整谱按最多的那几行统一让位、逐行往上摞（第 1 行最靠上）；
# 行数一多画布也要跟着长高（见 redraw_score 的 scrollregion），否则最下面一行会被裁掉。
LYRIC_DY = 22
LYRIC_SIZE = 13
LYRIC_LINE_H = 16         # 歌词行距（与 render.LYRIC_LINE_H 同值）
_LYRIC_SHIFT = 0          # 由 redraw_score / 预览在绘制前设置
_LYRIC_LINES = 0          # 整谱最多几行歌词，同上

# ---- 整段括号（前奏/间奏/和声伴唱）与「第 n 结尾」框（房子记号）----
# 口径与 render.py 成对：括号侧自足（左右各画在自己那一格边缘）、高度与简谱数字齐平；
# 结尾框横线压在这一段所有记号之上（八度点 / 换气 v / 连音弧线都要让开）。
BRACKET_CELL_RATIO = 0.30   # 括号记号格宽 / 正常格宽（与 render 同值）
BRACKET_BULGE = 7           # 括号向外鼓出的深度（弧的矢高）
BRACKET_UP = 3              # 括号上端比数字字形顶再高一点
BRACKET_DOWN = 10           # 括号下端比数字基线再低一点（要盖住低八度点）
ENDING_CELL_RATIO = 0.18    # 结尾记号格宽 / 正常格宽（很窄，只为让它有一格能被点中）
ENDING_TEXT_SIZE = 13       # 标号「1.」的字号
ENDING_TICK = 11            # 框子左端向下的短钩长度
ENDING_INSET = 6            # 标号距框子左端的内缩
ENDING_GAP = 6              # 框子横线到**下方最上层笔画**的净空
FRAME_TOP_MARGIN = 4        # 结尾框最上端距画布顶至少留这么多（别贴着边裁掉）
_ENDING_TOP = 0           # 有结尾框时谱面区顶部额外让出的高度（redraw_score 里算）


def ending_lift(depth: int = 0) -> float:
    """结尾框横线要抬到「记号区顶」之上多高（跟着连音弧线一起算）。

    数值口径与 render.ending_top_offset 同源：连音弧线底 = 记号区顶 -(5 + 层数×9)，
    拱高 11（画布这边的弧高就是 11，见 draw_mark_layer）；再留 ENDING_GAP 的净空。
    层数为 0（这一段里没有连音线）时就是单单一个净空。
    """
    return 5 + depth * 9 + (11 if depth else 0) + ENDING_GAP


def label_top_y(doc, y0: float, scale: float = 1.0) -> float:
    """该音符「记号区顶」的 y（已让开高八度点与换气记号）。

    连音弧线（draw_mark_layer）与结尾框（draw_frame_layer）都从它往上排——
    两边必须共用这一个函数，否则「框子压在弧线上」这类错位会随改动悄悄回来。
    数字在画布上是字号 17，所以这几档偏移是画布自己的口径（与 render._label_top
    同源但数值不同：那边字号 26、高八度点是 9 不是 7）。
    """
    cy = y0 + LABEL_CY * scale
    top = cy - (18 + max(0, doc.get("octave", 0)) * 7) * scale
    if doc.get("breath"):
        top -= BREATH_LIFT * scale      # 换气记号 v 站在数字正上方，得再让一层
    return top


def frame_top_need(docs) -> float:
    """有结尾框时，画布顶部要**额外**留出多少高度（0 = 现有的 SCORE_TOP 就够）。

    口径与 draw_frame_layer / render.ending_top_offset 完全同源：框子横线压在这一段
    最靠上的「记号区顶」（高八度点、换气 v 都算）与**最深的连音弧线**之上。
    算出来再看谱面顶原有的 SCORE_TOP 吃不吃得下，吃不下的那截才是要额外让出来的；
    不让的话框子会被画到画布外面（编辑时看不见整条框）。
    """
    if not docs:
        return 0.0
    spans = beaming.slur_spans(docs)
    pairs, _unpaired = jianpu.pair_frames(docs, pj.KIND_ENDING)
    need = 0.0
    for i0, i1, _n in pairs:
        depth = 0
        for sp in spans:                    # 落在这个框里的连音线：框子要压到它上面
            if i0 <= sp["i0"] and sp["i1"] <= i1:
                depth = max(depth, min(3, beaming.span_depth(spans, sp)))
        seg_top = min((label_top_y(docs[i], 0.0) for i in range(i0, i1 + 1)),
                      default=LABEL_CY)
        base = seg_top - ending_lift(depth)          # 相对行顶（负数 = 在行顶上方）
        need = max(need, FRAME_TOP_MARGIN - (SCORE_TOP + base))
    return max(0.0, need)

# 换气记号（数字正上方一个小 v）。与 render.py 同口径。
BREATH_SIZE = 11
BREATH_LIFT = 18          # 本格带换气时，连音弧线要再往上让这么多
BREATH_DY = 27            # v 的中心相对「数字中心」往上抬多少

# 超吹三角：画在**洞洞图下沿之下、音名之上**（口径与 render 一致）。
# 老口径画在笛身顶上方，那一带正是歌词带中心，于是有歌词时得把它搬到歌词上方再缩小 ——
# 缩到 8px 后基本看不见（用户反馈「输出谱面里没有超吹记号」）。搬到笛身下面之后那一带本来
# 就空着（往下只有一行音名），不必让位，也能画大一档。数字比导出那边小一号
# （画布音名 10px / 导出 14px），所以三角也相应小一点（10 高 × 12 宽）。
OCT_MARK_H = 10
OCT_MARK_W = 12
OCT_MARK_GAP = 2          # 三角顶与洞洞图下沿的间隙

BG, C_TEXT, C_ACCENT = "#ffffff", "#1a1a1a", "#23557a"
C_FLUTE, C_HALF, C_SEL, C_WARN = "#2c3e50", "#e67e22", "#cfe4f5", "#c0392b"
C_SHORT, C_SLUR, C_TIE = "#8e2f0f", "#1f6f43", "#a35a00"
C_CUT = C_SHORT          # 切音记号（早期叫「短音」）；小数字 + 小斜杠落在自己的窄格里
C_LYRIC = "#303030"      # 歌词（与 render.C_LYRIC 同色）
C_BREATH = "#6a3d9a"     # 换气记号 v（与 render.C_BREATH 同色）

# 光标（竖线），替换原来的整格方框：
#   * 竖线画在**插入点**上——不开插入模式 = 曲末（最后一个音右边），开了插入模式 = 选中格左边；
#   * 与小节线区分：光标是亮蓝、更粗，上下两端各有一道小横帽（像文本光标 I 形），
#     小节线则是灰色细竖线、没有横帽；
#   * 选中音自己只留一层很淡的底色（不加边框），不至于跟光标抢眼。
C_CARET = "#1f6feb"      # 光标颜色（比主题蓝更亮，一眼区别于灰色小节线）
CARET_W = 2.2            # 竖线粗细
CARET_CAP = 5.5          # 上下横帽的半宽
CARET_MARGIN = 6         # 竖线端头距格子上下边的留白

# 切音：自己占一个小小的窄格子（布局口径与 render.py 一致），紧跟在后一个音前面。
# 注意：画布有独立的设计坐标（下面这些值最后都乘缩放系数 s），
# 所以具体数字与 render.py 不必相等，横向比例对齐即可。
CUT_CELL_RATIO = 0.62    # 切音格子宽度 / 正常格子宽度（与 render.py 同值）
CUT_SIZE = 17            # 切音小数字字号（主数字 17 —— 编谱器画布缩放后的字号）
CUT_LIFT = 6             # 切音小格整体上提（小数字与小指法图一起抬高，与 render.py 同值）
CUT_SLASH = 9            # 小斜杠长度（小数字右上角）
CUT_ACC_DX = 9           # 小升降号相对小数字中心的横向偏移（左侧）
MINI_S = 0.60            # 小指法图相对正常指法图的比例
MINI_W = FLUTE_W * MINI_S
MINI_H = FLUTE_H * MINI_S
MINI_OCT_SCALE = 0.75    # 小格子里的超吹三角（与 render.MINI_OCT_SCALE 同值）
MINI_HOLE_R = HOLE_R * MINI_S
MINI_HOLE_DY = HOLE_DY * MINI_S

STATE_CYCLE = {1: 0, 0: 2, 2: 1}   # 按住 -> 放开 -> 半孔 -> 按住


def score_content_h() -> float:
    """谱面区当前需要的高度。

    歌词行数多了，笛身/音名整体下移 _LYRIC_SHIFT，光靠 CELL_H 装不下最后一行，
    所以这里跟着长——「洞洞图自动往下适配」在画布这一侧就是它。
    有结尾框时（_ENDING_TOP > 0）顶部也要跟着长：框子画在行顶之上，
    不留就整条被画到可视区外面去。
    """
    return CELL_H + SCORE_TOP + _ENDING_TOP + 18 + max(0.0, _LYRIC_SHIFT - LYRIC_DY)


def _font(size: int, bold: bool = False):
    return ("Microsoft YaHei", max(6, int(size)), "bold" if bold else "normal")


def _dur_suffix_text(dur: float) -> str:
    return pj.duration_suffix(dur)


# ---------------- 绘制 ----------------
def lyric_shift_for(n_lines: int) -> float:
    """几行歌词 -> 笛身/音名整体下移多少（0 行 = 不让位）。与 render 同口径。

    整数运算（返回 int）是刻意的：导出 SVG 里坐标是直接 format 出来的，
    0.0 会写成 "0.0"，和单行/无歌词时代生成的字符串对不上。
    """
    if not n_lines:
        return 0
    return LYRIC_DY + (n_lines - 1) * LYRIC_LINE_H


def set_lyric_shift(docs) -> None:
    """按整谱最多的歌词行数，把笛身/音名整体下移，让出歌词带。

    画布是「主谱面区」和「整谱预览」共用的，所以这个状态放在模块级
    （与 render.py 的 _LYRIC_SHIFT 同做法），绘制前各自设一次。
    """
    global _LYRIC_SHIFT, _LYRIC_LINES
    _LYRIC_LINES = pj.lyric_line_count(docs)
    _LYRIC_SHIFT = lyric_shift_for(_LYRIC_LINES)


def _lyric_bases(y: float, s: float, flute_top: float, shift: float | None = None) -> list:
    """本格每行歌词的基线（第 0 条 = 最上面那行）。行数取整谱的，各段词才对得齐。"""
    if not _LYRIC_LINES:
        return []
    shift = _LYRIC_SHIFT if shift is None else shift
    last = y + (flute_top + shift - 6) * s
    return [last - (_LYRIC_LINES - 1 - k) * LYRIC_LINE_H * s for k in range(_LYRIC_LINES)]


def draw_lyric(cv: tk.Canvas, cx: float, y: float, doc: dict, s: float,
               avail: float | None = None, flute_top: float = FLUTE_TOP,
               tags=("cell",), lyric_shift: float | None = None) -> float | None:
    """歌词：画在数字与笛身之间的歌词带里，与数字同一竖线居中；多行逐行往上摞。

    返回**最上面那行有字**的歌词的基线 y（本格没词则 None）——画超吹三角时靠它避让，
    别在外面另算一份（多行时三角该躲的是第一行，不是最后一行）。
    avail 是本格可用宽度（切音窄格要传窄格宽，别按满格量）；
    flute_top 是本格笛身顶的纵坐标（切音小格子整体上提，要传 FLUTE_TOP - CUT_LIFT，
    否则歌词会落到小指法图上）；
    lyric_shift 是这一格用的让位量，None = 用模块级的整谱让位量；
    长词自动缩小字号，免得串到左右邻格上（与导出 SVG 同一口径）。
    """
    lines = pj.lyric_lines_of(doc)
    if not lines:
        return None
    limit = (CELL_W if avail is None else avail) * 0.92
    bases = _lyric_bases(y, s, flute_top, lyric_shift)
    top_drawn = None
    for k, text in enumerate(lines):
        if not text:
            continue                     # 空行占位不画字（多段词要对齐）
        size = LYRIC_SIZE
        while size > 8 and len(text) * size > limit:
            size -= 1
        ty = bases[k] if k < len(bases) else (bases[-1] if bases else y)
        cv.create_text(cx, ty, text=text, font=_font(size * s), fill=C_LYRIC, tags=tags)
        if top_drawn is None:
            top_drawn = ty
    return top_drawn


def draw_caret(cv: tk.Canvas, cx: float, y: float, h: float, scale: float = 1.0,
               tags=("cell",)) -> None:
    """竖线光标：一条亮蓝竖线 + 上下两道小横帽（I 形）。

    与小节线的区别是刻意的：小节线是灰色细线、没有横帽、只有数字那么高；
    光标是亮蓝、更粗、两端有横帽，而且只画在插入点上。
    """
    s = scale
    top, bot = y + CARET_MARGIN * s, y + h - CARET_MARGIN * s
    cv.create_line(cx, top, cx, bot, fill=C_CARET, width=CARET_W * s,
                   capstyle=tk.ROUND, tags=tags)
    for yy in (top, bot):
        cv.create_line(cx - CARET_CAP * s, yy, cx + CARET_CAP * s, yy,
                       fill=C_CARET, width=CARET_W * s, capstyle=tk.ROUND, tags=tags)


def draw_cell(cv: tk.Canvas, x: float, y: float, doc: dict, key: str, whistle: str,
              scale: float = 1.0, w: float = CELL_W, selected: bool = False,
              tags=("cell",), show_name: bool = True, own_beams: bool = True,
              lyric_shift: float | None = None) -> None:
    """在画布上画一列：简谱数字（含八度点、附点）在上，洞洞图正下方，同列同宽。

    own_beams=False 时不画本音的减时线——由 draw_mark_layer 统一画成「连尾」连续横线。

    lyric_shift 是「歌词让位量」（笛身/音名整体下移多少），None = 用模块级的整谱让位量。
    主谱面区和整谱预览里有歌词，该跟着下移；**指法表 / 自定义指法预览没有歌词**，
    必须显式传 0 —— 否则谱面一加歌词行，那两处的洞洞图也会跟着往下串（画布还不够高，
    直接就串出可视区了）。
    """
    s = scale
    shift = _LYRIC_SHIFT if lyric_shift is None else lyric_shift
    cx = x + w * s / 2
    if selected:
        # 选中音：只留一层很淡的底色（原来是整格方框，会和光标、小节线抢视觉）
        cv.create_rectangle(x + 1, y + 1, x + w * s - 1, y + CELL_H * s - 1,
                            fill=C_SEL, outline="", tags=tags)
    kind = doc.get("kind", pj.KIND_NOTE)
    if kind == pj.KIND_BAR:
        cv.create_line(cx, y + DIGIT_TOP * s, cx, y + DIGIT_BOT * s,
                       fill="#8a949c", width=1.4, tags=tags)
        return
    if kind == pj.KIND_REPEAT:
        draw_repeat(cv, cx, y, doc, s, tags=tags)
        return
    if kind == pj.KIND_HOLD:
        # 延音横线：定长（HOLD_W）、居中于本格、竖向对准数字墨迹中心。
        # 口径与 render._simple_cell 的 hold 分支一致（两边都别改成跟着格宽走）。
        cy = y + DIGIT_INK_CY * s
        cv.create_line(cx - HOLD_W * s / 2, cy, cx + HOLD_W * s / 2, cy,
                       fill=C_TEXT, width=2.4, tags=tags)
        return
    if kind in pj.FRAME_KINDS:
        # 整段括号（跨格）与「第 n 结尾」框（画在行顶上方）都不是一格能画完的，
        # 由 draw_frame_layer 统一画；这里只留着这一格的位置——不画东西，
        # 免得落到下面当成音符画出个「1」来（选中时那层淡底色仍在，点得到）。
        return
    if kind == pj.KIND_NOTE and doc.get("short"):
        # 切音自带窄格子：小数字 + 小斜杠 + 小指法图，整格自己画完
        draw_cut_cell(cv, x, y, doc, key, whistle, s, w, tags=tags, lyric_shift=shift)
        return

    dur = doc.get("duration", 1.0)
    degree_text = "0" if kind == pj.KIND_REST else str(doc.get("degree", 1))
    accidental = doc.get("accidental", 0)
    if accidental and kind == pj.KIND_NOTE:
        cv.create_text(cx - 13 * s, y + LABEL_CY * s, text="♯" if accidental > 0 else "♭",
                       font=_font(12 * s), fill=C_TEXT, tags=tags)
    cv.create_text(cx, y + LABEL_CY * s, text=degree_text,
                   font=_font(17 * s, True), fill=C_TEXT, tags=tags)
    octave = doc.get("octave", 0)
    dot_r = 2.4 * s
    for i in range(max(0, octave)):        # 高八度：数字上方加点
        cy = y + (LABEL_CY - 15 - i * 6.5) * s
        cv.create_oval(cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r,
                       fill=C_TEXT, outline="", tags=tags)
    if doc.get("breath"):
        # 换气记号：数字正上方一个小 v（高八度点之上）。连音弧线要按 BREATH_LIFT 再让一层，
        # 见 draw_mark_layer.label_top。
        vy = y + (LABEL_CY - BREATH_DY - max(0, octave) * 6.5) * s
        cv.create_text(cx, vy, text="v", font=_font(BREATH_SIZE * s),
                       fill=C_BREATH, tags=tags)
    beams = jianpu.duration_beams(dur)
    # 减时线：own_beams=False 时一律交给 draw_mark_layer 画成「连尾」连续横线——
    # 休止符也走这条线（beaming 现在把短休止和音符一视同仁，见其模块文档第 4 条），
    # 于是 `5/ 0/ 5/` 是贯穿三格的一条线，而不是三段各画各的。
    if own_beams:
        hw = min(COL_W, w) * s / 2
        for i in range(beams):             # 时值横线：中心 = cx
            by = y + (BEAM_Y1 + i * 5) * s
            cv.create_line(cx - hw, by, cx + hw, by,
                           fill=C_TEXT, width=1.6, tags=tags)
    if jianpu.is_dotted(dur):              # 附点：数字右侧
        cv.create_oval(cx + 11 * s - dot_r, y + (LABEL_CY - 3) * s - dot_r,
                       cx + 11 * s + dot_r, y + (LABEL_CY - 3) * s + dot_r,
                       fill=C_TEXT, outline="", tags=tags)
    for i in range(max(0, -octave)):       # 低八度：时值线之下再加点
        oy = y + (BEAM_Y1 + max(1, beams) * 5 + 3 + i * 6.5) * s
        cv.create_oval(cx - dot_r, oy - dot_r, cx + dot_r, oy + dot_r,
                       fill=C_TEXT, outline="", tags=tags)

    if kind == pj.KIND_REST:
        return

    draw_lyric(cv, cx, y, doc, s, tags=tags, lyric_shift=shift)   # 歌词：数字与洞洞之间
    result = pj.to_result(doc, 0, key, whistle)
    ftop = y + (FLUTE_TOP + shift) * s
    fw, fh = FLUTE_W * s, FLUTE_H * s
    fx = cx - fw / 2                        # 笛身中心 = 数字中心
    cv.create_rectangle(fx, ftop + fw / 2, fx + fw, ftop + fh - fw / 2,
                        fill="#fdfdf8", outline=C_FLUTE, width=1.8, tags=tags)
    cv.create_oval(fx, ftop, fx + fw, ftop + fw, fill="#fdfdf8", outline=C_FLUTE,
                   width=1.8, tags=tags)
    cv.create_oval(fx, ftop + fh - fw, fx + fw, ftop + fh, fill="#fdfdf8",
                   outline=C_FLUTE, width=1.8, tags=tags)
    hole_cy = ftop + 13 * s
    hr = HOLE_R * s
    for state in (result.holes or ()):
        bbox = (cx - hr, hole_cy - hr, cx + hr, hole_cy + hr)   # 孔心同样落在 cx
        if state == 1:
            cv.create_oval(*bbox, fill=C_FLUTE, outline=C_FLUTE, tags=tags)
        else:
            cv.create_oval(*bbox, fill="#ffffff", outline=C_FLUTE, width=1.4, tags=tags)
            if state == 2:
                cv.create_arc(*bbox, start=90, extent=180, style="pieslice",
                              fill=C_HALF, outline=C_FLUTE, width=1.2, tags=tags)
        hole_cy += HOLE_DY * s
    if not result.playable:
        cv.create_rectangle(fx - 3, ftop - 3, fx + fw + 3, ftop + fh + 3,
                            outline=C_WARN, dash=(4, 3), width=1.4, tags=tags)
    if result.second_octave:
        # 超吹三角：画在洞洞图下沿之下、音名上方（口径与 render._oct_mark_svg 一致）。
        # 这里**不需要**管歌词：三角站在笛身下面，离歌词带还有一整支笛身。
        draw_oct_mark(cv, cx, ftop + fh, C_WARN if result.hard else C_ACCENT, s, tags=tags)
    if show_name:
        cv.create_text(cx, ftop + fh + NAME_DY * s, font=_font(10 * s),
                       text=(result.note_name or "?") + (" 高" if result.second_octave else ""),
                       fill=C_WARN if (result.hard or not result.playable) else C_ACCENT,
                       tags=tags)
        if doc.get("holes"):
            cv.create_text(cx, ftop + fh + (NAME_DY + 11) * s, font=_font(8 * s),
                           text="自选", fill=C_HALF, tags=tags)


def draw_mini_flute(cv: tk.Canvas, cx: float, top: float, holes, scale: float = 1.0,
                    tags=("cell",)) -> None:
    """切音小格子里的小指法图：孔心与小数字同一条竖线（与导出 SVG 同形）。"""
    s = scale
    w, h = MINI_W * s, MINI_H * s
    cv.create_rectangle(cx - w / 2, top, cx + w / 2, top + h,
                        fill="#fdfdf8", outline=C_CUT, width=max(1.0, 1.6 * s), tags=tags)
    cy = top + 14 * MINI_S * s
    r = MINI_HOLE_R * s
    for state in (holes or ()):
        bbox = (cx - r, cy - r, cx + r, cy + r)
        if state == 1:
            cv.create_oval(*bbox, fill=C_CUT, outline=C_CUT, tags=tags)
        else:
            cv.create_oval(*bbox, fill="#ffffff", outline=C_CUT,
                           width=max(0.9, 1.3 * s), tags=tags)
            if state == 2:
                cv.create_arc(*bbox, start=90, extent=180, style="pieslice",
                              fill=C_HALF, outline=C_CUT, width=1.0, tags=tags)
        cy += MINI_HOLE_DY * s


def draw_cut_cell(cv: tk.Canvas, x: float, y: float, doc: dict, key: str, whistle: str,
                  s: float, w: float, tags=("cell",),
                  lyric_shift: float | None = None) -> None:
    """切音单元：窄格子里一个小数字（+ 右上角小斜杠）和一张小指法图，同一条竖线。

    lyric_shift 同 draw_cell：None = 用整谱让位量，指法表那类没歌词的地方要传 0。
    """
    shift = _LYRIC_SHIFT if lyric_shift is None else lyric_shift
    cx = x + w * s / 2
    cy = y + (LABEL_CY - CUT_LIFT) * s
    accidental = doc.get("accidental", 0)
    if accidental:
        cv.create_text(cx - CUT_ACC_DX * s, cy + 4 * s,
                       text="♯" if accidental > 0 else "♭",
                       font=_font(10 * s), fill=C_CUT, tags=tags)
    cv.create_text(cx, cy, text=str(doc.get("degree", 1)),
                   font=_font(CUT_SIZE * s, True), fill=C_CUT, tags=tags)
    r = 1.5 * s
    octave = doc.get("octave", 0)
    for i in range(max(0, octave)):        # 小数字自身的高八度点
        oy = cy - (11 + i * 5) * s
        cv.create_oval(cx - r, oy - r, cx + r, oy + r, fill=C_CUT, outline="", tags=tags)
    for i in range(max(0, -octave)):       # 低八度点
        oy = cy + (7 + i * 5) * s
        cv.create_oval(cx - r, oy - r, cx + r, oy + r, fill=C_CUT, outline="", tags=tags)
    cv.create_line(cx + 6 * s, cy - 3 * s, cx + (6 + CUT_SLASH) * s, cy - (3 + CUT_SLASH) * s,
                   fill=C_CUT, width=max(1.2, 1.9 * s), tags=tags)
    draw_lyric(cv, cx, y, doc, s, avail=w, flute_top=FLUTE_TOP - CUT_LIFT, tags=tags,
               lyric_shift=shift)
    res = pj.to_result(doc, 0, key, whistle)
    ftop = y + (FLUTE_TOP - CUT_LIFT + shift) * s
    draw_mini_flute(cv, cx, ftop, res.holes, scale=s, tags=tags)
    if res.second_octave:
        # 超吹三角：贴在**小**洞洞图下沿之下（小图小一号，三角跟着小，口径同 draw_cell）
        draw_oct_mark(cv, cx, ftop + MINI_H * s, C_WARN if res.hard else C_ACCENT, s,
                      scale=MINI_OCT_SCALE, tags=tags)


def draw_oct_mark(cv: tk.Canvas, cx: float, flute_bottom: float, color: str,
                  s: float = 1.0, scale: float = 1.0, tags=("cell",)) -> None:
    """超吹三角：顶在洞洞图下沿之下 OCT_MARK_GAP 处，横向居中于本列。

    scale 给切音小格子里那张**小**洞洞图用（图小一号，三角也跟着小）。
    口径与 render._oct_mark_svg 是一对（那边按「谱面大小」的 _s() 缩，这边按画布 s 缩）。
    """
    tip = flute_bottom + OCT_MARK_GAP * scale * s
    hw = OCT_MARK_W / 2 * scale * s
    h = OCT_MARK_H * scale * s
    cv.create_polygon(cx, tip, cx + hw, tip + h, cx - hw, tip + h,
                      fill=color, outline="", tags=tags)


def draw_repeat(cv: tk.Canvas, cx: float, y: float, doc: dict, s: float,
                tags=("cell",)) -> None:
    """反复记号（循环符号）：细线 + 粗线 + 两粒反复点，方向决定点在哪一侧。

      |:   反复开始        →  细线 粗线 ··
      :|   反复结束        →  ·· 粗线 细线
      :|:  一段收尾并起下一段 →  ·· 细线 粗线 ··

    口径与 render._repeat_cell 完全一致（粗线贴着反复点那一侧），
    竖线高度也和它一样**只盖住数字**（DIGIT_TOP → DIGIT_BOT），不跟笛身长短。
    """
    direction = doc.get("direction", "start")
    top = y + DIGIT_TOP * s
    bottom = y + DIGIT_BOT * s
    if direction == "end":
        thick_x, thin_x = cx - 2.0 * s, cx + 2.5 * s
    else:
        thin_x, thick_x = cx - 2.5 * s, cx + 2.0 * s
    cv.create_line(thin_x, top, thin_x, bottom, fill="#8a949c", width=max(1.0, 1.2 * s), tags=tags)
    cv.create_line(thick_x, top, thick_x, bottom, fill=C_TEXT, width=max(1.4, 3.0 * s), tags=tags)
    mid = (top + bottom) / 2
    # 两粒点在「数字高度」这条短竖线里：半径与间距都随它收一收，
    # 不然按原来的 ±5 / r=2.6 会正好顶到竖线两端（16px 高装不下 15.2px 的点距）。
    r = REPEAT_DOT_R * s
    for dy in (-REPEAT_DOT_DY * s, REPEAT_DOT_DY * s):
        if direction in ("end", "both"):
            cv.create_oval(thick_x - 7 * s - r, mid + dy - r, thick_x - 7 * s + r, mid + dy + r,
                           fill=C_TEXT, outline="", tags=tags)
        if direction in ("start", "both"):
            cv.create_oval(thick_x + 7 * s - r, mid + dy - r, thick_x + 7 * s + r, mid + dy + r,
                           fill=C_TEXT, outline="", tags=tags)


def draw_mark_layer(cv: tk.Canvas, docs, cells, y0: float, beats: str = "4/4",
                    scale: float = 1.0, tags=("cell",),
                    group_docs=None, group_offset: int = 0) -> None:
    """连尾减时线层 + 连音/延音弧线层（跨音符统一绘制，保证规范）。

    docs  : 与 cells 等长的 NoteDoc 序列（展示顺序，含自动小节线）
    cells : [(x, w), ...] 每格的左缘与宽度，用于算数字中心
    y0    : 本行顶端的 y
    group_docs / group_offset:
        整谱预览是「逐行画」的，本行往往只是整谱的一段。若只用本行的 docs 去算分组，
        `beaming` 会以为这段从第 0 拍开始，连尾就会分错。所以预览传**整谱** docs +
        本行起始下标，分组口径与导出 SVG 完全一致：
        - 跨行的连尾横线按行切断（与 `render._beam_layer` 同做法）；
        - 跨行的连音弧线不画（与 `render._slur_layer` 同做法）。
        不传时就是原来的单行行为（编谱器主谱面区）。
    """
    if not docs:
        return
    s = scale
    gdocs = docs if group_docs is None else group_docs
    off = group_offset
    n_local = len(docs)

    def cx_of(i):
        x, w = cells[i]
        return x + w * s / 2

    def label_top(doc):
        return label_top_y(doc, y0, s)

    def half_w(i):
        """减时线半宽：切音格子窄，线也跟着收窄，免得压到邻格"""
        return min(COL_W, cells[i][1]) * s / 2

    # ---- 减时线：同一拍内相邻八分/十六分共用一条连续横线 ----
    for i0, i1, level in beaming.beam_segments(gdocs, beats or "4/4"):
        a, b = i0 - off, i1 - off
        if b < 0 or a > n_local - 1:
            continue                       # 整段不在本行
        a, b = max(a, 0), min(b, n_local - 1)   # 跨行的按行切断
        if a > b:
            continue
        x0 = cx_of(a) - half_w(a)
        x1 = cx_of(b) + half_w(b)
        by = y0 + (BEAM_Y1 + level * 5) * s
        cv.create_line(x0, by, x1, by, fill=C_TEXT, width=1.6, tags=tags)

    # ---- 连音线：同音相连=延音线（棕）、不同音=圆滑线（绿） ----
    spans = beaming.slur_spans(gdocs)
    for sp in sorted(spans, key=lambda d: (d["i0"], -d["i1"])):
        a, b = sp["i0"] - off, sp["i1"] - off
        if not (0 <= a < n_local and 0 <= b < n_local):
            continue                       # 跨行的连音线暂不画
        depth = min(3, beaming.span_depth(spans, sp))
        base = min(label_top(docs[a]), label_top(docs[b])) - (5 + depth * 9) * s
        x0, x1 = cx_of(a), cx_of(b)
        if x1 < x0:
            x0, x1 = x1, x0
        color = C_TIE if sp["kind"] == "tie" else C_SLUR
        cv.create_line(x0, base, (x0 + x1) / 2, base - 11 * s, x1, base,
                       smooth=True, splinesteps=24, fill=color, width=1.8, tags=tags)
    # 切音不在这里画：它自带一个窄格子，由 draw_cell 的切音分支整格画掉


def draw_frame_layer(cv: tk.Canvas, docs, cells, y0: float, scale: float = 1.0,
                     tags=("cell",), group_docs=None, group_offset: int = 0) -> None:
    """整段括号层 + 「第 n 结尾」框层（跨格绘制，口径与 render 的两层一致）。

    docs  : 与 cells 等长的 NoteDoc 序列（展示顺序，含自动小节线）
    cells : [(x, w), ...] 每格的左缘与宽度
    y0    : 行顶的 y（已经含结尾框让位 _ENDING_TOP）
    group_docs / group_offset:
        整谱预览是「逐行画」的，本行往往只是整谱的一段。结尾框的**配对**必须用整谱
        （否则跨行的框两边配不上），所以预览传整谱 docs + 本行起始下标；跨行的框
        按行切开画（本行不是起点就不画左端短钩与标号），与 render._ending_layer 同做法。
        不传时就是单行行为（编谱器主谱面区）。

    括号两侧各自自足（左右各画在自己那一格边缘，跨行也不丢），
    结尾框按 `[1`…`1]` 手工配对的起止画。
    """
    s = scale
    top = y0 + (DIGIT_TOP - BRACKET_UP) * s
    bottom = y0 + (DIGIT_BOT + BRACKET_DOWN) * s
    ym = (top + bottom) / 2
    b = BRACKET_BULGE * s
    for i, doc in enumerate(docs):
        if doc.get("kind") != pj.KIND_BRACKET:
            continue
        x, w = cells[i]
        if doc.get("direction", "start") == "start":
            bx = x * 1.0                                  # 起点那格的左缘
            cv.create_line(bx + b, top, bx, ym, bx + b, bottom,
                           smooth=True, splinesteps=16, fill=C_TEXT, width=1.6, tags=tags)
        else:
            bx = x + w * s                                # 终点那格的右缘
            cv.create_line(bx - b, top, bx, ym, bx - b, bottom,
                           smooth=True, splinesteps=16, fill=C_TEXT, width=1.6, tags=tags)

    if not docs:
        return
    gdocs = docs if group_docs is None else group_docs
    off = group_offset
    n_local = len(docs)
    pairs, _unpaired = jianpu.pair_frames(gdocs, pj.KIND_ENDING)
    spans = beaming.slur_spans(gdocs)
    for i0, i1, n in pairs:
        a, bcell = i0 - off, i1 - off           # 换算到本行；a<0 / bcell>末格 = 跨行
        if bcell < 0 or a > n_local - 1:
            continue                            # 整条不在本行
        depth = 0
        for sp in spans:                        # 落在这个框里的连音线：框子要压到它上面
            if i0 <= sp["i0"] and sp["i1"] <= i1:
                depth = max(depth, min(3, beaming.span_depth(spans, sp)))
        base = min(label_top_y(docs[i], y0, s)
                   for i in range(max(a, 0), min(bcell, n_local - 1) + 1)) \
            - ending_lift(depth) * s
        starts_here, ends_here = a >= 0, bcell <= n_local - 1
        # 跨行时本行只画中间那一段：起点不在本行就从本行最左格起、终点不在就画到最右格
        x0 = cells[max(a, 0)][0] if starts_here else cells[0][0]
        last = min(bcell, n_local - 1)
        x1 = cells[last][0] + cells[last][1] * s if ends_here \
            else cells[last][0] + cells[last][1]
        if x1 <= x0:
            continue
        cv.create_line(x0, base, x1, base, fill=C_TEXT, width=1.4, tags=tags)
        if starts_here:
            cv.create_line(x0, base, x0, base + ENDING_TICK * s,
                           fill=C_TEXT, width=1.4, tags=tags)
            # 标号写在横线**下方**（框子里面），贴在左端
            cv.create_text(x0 + ENDING_INSET * s, base + ENDING_TEXT_SIZE * s,
                           text=f"{max(1, n or 1)}.",
                           font=_font(ENDING_TEXT_SIZE * s, True),
                           fill=C_TEXT, anchor="w", tags=tags)
        if ends_here:
            cv.create_line(x1, base, x1, base + ENDING_TICK * s,
                           fill=C_TEXT, width=1.4, tags=tags)


# ---------------- 进度条弹窗 ----------------
# 大工程（几千个音 / 几 MB 的 JSON）打开、保存、导出图片都要花上好几秒，
# 界面在这期间是**冻住的**（tk 单线程），用户只看到窗口没反应，会以为卡死了。
# 所以这些操作统一丢到工作线程里跑，主线程弹一个进度条、靠 after() 泵界面。
BUSY_SHOW_MS = 300        # 不到这个时间就干完了 → 根本不弹窗（小工程不该闪一下）
BUSY_PUMP_MS = 60         # 主线程泵界面的间隔


class BusyDialog:
    """「正在干活」的进度条弹窗。

    用法（由 `EditorApp._run_busy` 包一层，业务代码一般不直接用）：

        dlg = BusyDialog(root, "正在打开工程", cancelable=False)
        dlg.report(done, total, label)     # 可以**在任意线程**里调
        dlg.pump()                         # 只准主线程调（after 循环里）
        dlg.close()

    两个关键点：
    - `report()` 只把数字记下来不动控件：**tkinter 不是线程安全的**，从工作线程里
      直接 `config()` 会随机崩（表现是整窗闪退或画面撕裂），所以真正的界面更新
      都推到主线程的 `pump()`；
    - 延迟 `BUSY_SHOW_MS` 才建窗：打开一个 30 个音的小工程只要几毫秒，
      弹窗一闪而过反而像抽搐，所以先不建窗，超时了才建。
    """

    def __init__(self, root, title: str, cancelable: bool = False):
        self.root = root
        self.title = title
        self.cancelable = cancelable
        self._state = (0, 0, "准备…")     # (done, total, label)
        self._canceled = False
        self._win = None
        self._bar = None
        self._lbl = None
        self._indet = False        # 进度条当前是不是「来回扫」的不确定模式
        self._t0 = time.monotonic()
        self._shown = False

    # ---- 工作线程侧 ----
    def report(self, done, total=0, label=""):
        self._state = (done, total, label or "")

    def canceled(self) -> bool:
        return self._canceled

    def _on_cancel(self):
        self._canceled = True
        if self._lbl is not None:
            self._lbl.config(text="正在取消…（已开始的那一页会先跑完）")

    # ---- 主线程侧 ----
    def pump(self) -> None:
        """把最新进度刷到界面上；到点了该建窗就建窗。"""
        if not self._shown and (time.monotonic() - self._t0) * 1000 >= BUSY_SHOW_MS:
            self._build()
        if not self._shown:
            return
        done, total, label = self._state
        if total > 0:
            pct = max(0.0, min(1.0, done / float(total)))
            if self._indet:            # 不确定模式有自己的定时器，不 stop 会接着改 value
                self._bar.stop()
                self._indet = False
            self._bar.config(mode="determinate", value=pct * 100)
            txt = f"{label}　{pct:.0%}" if label else f"{pct:.0%}"
        else:
            # 总数还没定（比如还在排版）→ 走「来回扫」的不确定模式
            if not self._indet:
                self._bar.config(mode="indeterminate")
                self._bar.start(12)
                self._indet = True
            txt = label or "请稍候…"
        self._lbl.config(text=txt)
        self._win.update_idletasks()

    def _build(self):
        self._shown = True
        win = tk.Toplevel(self.root)
        self._win = win
        win.title(self.title)
        win.transient(self.root)
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", lambda: None)   # 干活途中不允许关掉
        frm = ttk.Frame(win, padding=14)
        frm.pack(fill=tk.BOTH)
        ttk.Label(frm, text=self.title, font=_font(11, True)).pack(anchor=tk.W)
        self._lbl = ttk.Label(frm, text="请稍候…")
        self._lbl.pack(anchor=tk.W, pady=(6, 4))
        self._bar = ttk.Progressbar(frm, orient=tk.HORIZONTAL, length=380,
                                    mode="indeterminate", maximum=100)
        self._bar.pack(fill=tk.X)
        if self.cancelable:
            ttk.Button(frm, text="取消", command=self._on_cancel).pack(anchor=tk.E, pady=(8, 0))
        win.update_idletasks()
        # 居中在主窗口上
        try:
            win.geometry(f"+{self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_reqwidth()) // 2}"
                         f"+{self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_reqheight()) // 2}")
        except tk.TclError:
            pass
        try:
            win.grab_set()          # 干活期间不许再去点谱面（点了会改数据）
        except tk.TclError:
            pass

    def close(self):
        if self._win is not None:
            try:
                self._bar.stop()
            except (AttributeError, tk.TclError):
                pass
            try:
                self._win.grab_release()
            except tk.TclError:
                pass
            try:
                self._win.destroy()
            except tk.TclError:
                pass
        self._win = None
        self._bar = None
        self._lbl = None
        self._shown = False


# ---------------- 主应用 ----------------
class EditorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_TITLE)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        # 谱面区需要 CELL_H + SCORE_TOP 的高度，窗口尽量开高一点，避免笛身被裁。
        # 这里贴着屏幕可用高度取值（留 40px 给任务栏/标题栏）：窗口高一点，
        # 谱面区才拿得下「歌词 2~3 行时变高的格子」，不用把别的面板挤瘦。
        root.geometry(f"{min(1320, sw - 40)}x{min(1040, sh - 40)}")
        root.minsize(1040, 720)
        self.proj = pj.new_project()
        self.proj["_path"] = None
        self.sel = -1                  # 选中音的【文档】下标（小节线不占位、不可选）
        # 「插入到选中音前」只对**用户自己点/走出来的**选中音生效：追加完一个音后也会
        # 把选中框落在它身上，若不加这个区分，连敲两下就会把第二个音插到第一个前面（顺序反转）。
        self._sel_user = False
        self._cell_map = []            # [(x0, x1, 文档下标或None), ...]
        self._scroll_to_doc = None     # 待自动跳转到的音（新加的音，滚出屏外时用）
        self.undo_stack, self.redo_stack = [], []
        self._save_job = None
        self._dirty = False
        self._page_win = None          # 整谱预览窗口（未打开时为 None）
        self._page_job = None          # 预览的延迟刷新任务号
        # 批量 set 控件期间置真：几个 Var 都挂了 trace（→ _meta_changed /
        # _on_output_changed → redraw_all），打开一个大工程会连着 set 十几个控件，
        # 于是重画十几次（1200 个音每次 0.14s，光这一下就卡 1 秒多）。置真期间
        # 一律不响应，最后统一重画一次 —— 见 _load_project / new_project / _restore。
        self._bulk_set = False
        # 试听：Beeper 自带工作线程，发声是异步的（界面不会被它占住）。
        # _listen_sel 记住「上一次响过的那个音」，避免同一个音被反复响（见 _maybe_listen）。
        self.beeper = sound.Beeper()
        self._listen_sel = -1
        self._tune_gen = 0             # 整首试听的代次：停掉 / 重开时把旧回调作废
        self.st_octave = 0
        self.st_acc = 0
        self.st_dur = 1.0
        self.st_dot = False
        self.st_short = False
        self.custom_holes = [1, 1, 1, 1, 1, 1]
        self._build()
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Configure>", self._on_root_resize, add="+")
        self.redraw_all()
        self._sync_mode_box()
        self.root.after(300, self._offer_recover)

    # ---------- 界面搭建 ----------
    def _build(self):
        bar = ttk.Frame(self.root, padding=6)
        bar.pack(fill=tk.X)
        for text, cmd in (("新建", self.new_project), ("打开", self.open_project),
                          ("保存", self.save_project), ("导出 SVG", self.export_svg),
                          ("整谱预览", self.open_page_preview),
                          ("键盘说明", self.show_key_help),
                          ("撤销", self.undo), ("重做", self.redo)):
            ttk.Button(bar, text=text, command=cmd).pack(side=tk.LEFT, padx=2)
        ttk.Label(bar, text="曲名:").pack(side=tk.LEFT, padx=(10, 2))
        self.title_var = tk.StringVar(value="未命名")
        ttk.Entry(bar, textvariable=self.title_var, width=14).pack(side=tk.LEFT)
        ttk.Label(bar, text="1=").pack(side=tk.LEFT, padx=(10, 2))
        self.key_var = tk.StringVar(value="D")
        ttk.Combobox(bar, textvariable=self.key_var, values=KEY_LIST, width=4,
                     state="readonly").pack(side=tk.LEFT)
        ttk.Label(bar, text="哨笛:").pack(side=tk.LEFT, padx=(10, 2))
        self.whistle_var = tk.StringVar(value="D")
        ttk.Combobox(bar, textvariable=self.whistle_var, values=WHISTLE_LIST, width=4,
                     state="readonly").pack(side=tk.LEFT)
        ttk.Label(bar, text="全按:").pack(side=tk.LEFT, padx=(10, 2))
        self.mode_var = tk.StringVar(value=fingering.mode_label("D", "D"))
        self.mode_box = ttk.Combobox(bar, textvariable=self.mode_var,
                                     values=list(fingering.all_modes("D")),
                                     width=8, state="readonly")
        self.mode_box.pack(side=tk.LEFT)
        self.mode_box.bind("<<ComboboxSelected>>", self._on_mode_pick)
        ttk.Label(bar, text="拍号:").pack(side=tk.LEFT, padx=(10, 2))
        self.beats_var = tk.StringVar(value="4/4")
        ttk.Combobox(bar, textvariable=self.beats_var, values=BEATS_LIST, width=5,
                     state="readonly").pack(side=tk.LEFT)
        self.autobar_var = tk.IntVar(value=1)
        ttk.Checkbutton(bar, text="自动小节线", variable=self.autobar_var,
                        command=self._meta_changed).pack(side=tk.LEFT, padx=8)
        self.autosave_lbl = ttk.Label(bar, text="", foreground="#2e7d32")
        self.autosave_lbl.pack(side=tk.RIGHT, padx=8)
        self.key_var.trace_add("write", lambda *_: self._meta_changed())
        self.whistle_var.trace_add("write", lambda *_: self._meta_changed())
        self.title_var.trace_add("write", lambda *_: self._meta_changed())
        self.beats_var.trace_add("write", lambda *_: self._meta_changed())

        # 输出设置（纸张 / 水印 / 图片倍率）：一条常驻设置栏，
        # 导出 SVG 与导出图片都按这里的设置走。
        outbar = ttk.Frame(self.root, padding=(6, 0, 6, 6))
        outbar.pack(fill=tk.X)
        ttk.Label(outbar, text="纸张(竖版):").pack(side=tk.LEFT)
        self.paper_var = tk.StringVar(value=render.DEFAULT_PAPER)
        ttk.Combobox(outbar, textvariable=self.paper_var, values=PAPER_LIST, width=4,
                     state="readonly").pack(side=tk.LEFT, padx=(2, 10))
        ttk.Label(outbar, text="一行:").pack(side=tk.LEFT)
        self.rowmeas_var = tk.StringVar(value="自动")
        ttk.Combobox(outbar, textvariable=self.rowmeas_var, values=ROW_MEASURE_LIST, width=4,
                     state="readonly").pack(side=tk.LEFT, padx=(2, 10))
        ttk.Label(outbar, text="水印:").pack(side=tk.LEFT)
        self.watermark_var = tk.StringVar(value="")
        ttk.Entry(outbar, textvariable=self.watermark_var, width=14).pack(side=tk.LEFT, padx=2)
        # 谱面大小：简谱数字 + 洞洞图 + 行高按同一比例缩，纸张与「一行几个小节」不变。
        # 默认 65% —— A4 竖版首页 5 行（带一行歌词也是 5 行；100% 只排 3 行）。
        # 只影响**导出**：编谱器主画布（上面那块）始终是原始尺寸，编辑手感不变。
        ttk.Label(outbar, text="谱面:").pack(side=tk.LEFT, padx=(10, 0))
        self.content_scale_var = tk.StringVar(
            value=str(round(render.DEFAULT_CONTENT_SCALE * 100)))
        ttk.Combobox(outbar, textvariable=self.content_scale_var,
                     values=[str(p) for p in CONTENT_SCALE_CHOICES], width=4,
                     state="normal").pack(side=tk.LEFT, padx=2)
        ttk.Label(outbar, text="%（导出用，50~100）").pack(side=tk.LEFT)
        ttk.Label(outbar, text="图片倍率:").pack(side=tk.LEFT, padx=(10, 0))
        self.scale_var = tk.StringVar(value=str(imageout.DEFAULT_SCALE))
        ttk.Combobox(outbar, textvariable=self.scale_var,
                     values=[str(s) for s in sorted(imageout.SIZES)], width=3,
                     state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Label(outbar, text="x").pack(side=tk.LEFT)
        ttk.Button(outbar, text="导出图片 PNG", command=self.export_png).pack(side=tk.LEFT,
                                                                       padx=(12, 2))
        ttk.Label(outbar, text="　（不从小节中间换行；放不下自动分页，"
                              "多页导出成 曲名-1 / -2 …）",
                  foreground="#666").pack(side=tk.LEFT)
        self.paper_var.trace_add("write", lambda *_: self._on_output_changed())
        self.rowmeas_var.trace_add("write", lambda *_: self._on_output_changed())
        self.watermark_var.trace_add("write", lambda *_: self._on_output_changed())
        self.scale_var.trace_add("write", lambda *_: self._on_output_changed())
        self.content_scale_var.trace_add("write", lambda *_: self._on_output_changed())

        score_box = ttk.LabelFrame(self.root, text="谱面（数字在上，洞洞正下方同列同宽；同一拍的八分/十六分自动连尾；点格子选中）",
                                  padding=4)
        self._score_h = int(round(score_content_h()))   # 画布当前设过的高度（歌词变了要跟着长）
        self.score = tk.Canvas(score_box, background=BG, highlightthickness=0,
                               height=self._score_h)
        self.score_hs = ttk.Scrollbar(score_box, orient=tk.HORIZONTAL, command=self.score.xview)
        self.score_vs = ttk.Scrollbar(score_box, orient=tk.VERTICAL, command=self.score.yview)
        self.score.configure(xscrollcommand=self.score_hs.set,
                             yscrollcommand=self.score_vs.set)
        # 用 grid 而不是 pack：pack 按顺序分配空间，画布一旦 fill=BOTH+expand=True 先占满，
        # 后 pack 的横向滚动条就只能分到 0 高度（表现为一条挤扁、拉不动的小条）。
        score_box.columnconfigure(0, weight=1)
        score_box.rowconfigure(0, weight=1)
        self.score.grid(row=0, column=0, sticky="nsew")
        self.score_vs.grid(row=0, column=1, sticky="ns")
        self.score_hs.grid(row=1, column=0, sticky="ew")
        self.score.bind("<Button-1>", self.on_canvas_click)
        # 滚轮：默认横向滚动（谱面是一条长横带），Shift+滚轮纵向
        self.score.bind("<MouseWheel>", lambda e: self._wheel_scroll(e))

        insp = ttk.LabelFrame(self.root, text="选中音属性 / 记号（切音、连音线）", padding=4)
        row1 = ttk.Frame(insp)
        row1.pack(fill=tk.X)
        self.info_lbl = ttk.Label(row1, text="未选中", width=40)
        self.info_lbl.pack(side=tk.LEFT)
        for text, cmd in (("四分", lambda: self.set_dur(1.0)), ("八分", lambda: self.set_dur(0.5)),
                          ("十六分", lambda: self.set_dur(0.25)),
                          ("附点", self.toggle_dot),
                          ("降八度", lambda: self.shift_octave(-1)), ("升八度", lambda: self.shift_octave(1)),
                          ("♯", lambda: self.shift_acc(1)), ("♭", lambda: self.shift_acc(-1)),
                          ("←", lambda: self.move_note(-1)), ("→", lambda: self.move_note(1)),
                          ("删除", self.delete_note), ("恢复自动指法", self.reset_holes)):
            ttk.Button(row1, text=text, width=8, command=cmd).pack(side=tk.LEFT, padx=1)

        row2 = ttk.Frame(insp)
        row2.pack(fill=tk.X, pady=(4, 0))
        self.mark_lbl = ttk.Label(row2, text="选中音记号：—", width=24, foreground=C_ACCENT)
        self.mark_lbl.pack(side=tk.LEFT)
        for text, cmd in (("切音 ⇄", self.toggle_short),
                          ("连音线起点 [", lambda: self.set_slur("start")),
                          ("连音线终点 ]", lambda: self.set_slur("end")),
                          ("延音线(同音)", lambda: self.set_slur("tie")),
                          ("清除连线", lambda: self.set_slur("clear"))):
            ttk.Button(row2, text=text, width=13, command=cmd).pack(side=tk.LEFT, padx=1)
        ttk.Button(row2, text="换气 v", width=8,
                   command=self.toggle_breath).pack(side=tk.LEFT, padx=1)
        ttk.Label(row2, text="　减时线按拍号自动连尾（同一拍共用一条，休止符也参与）",
                  foreground="#666").pack(side=tk.LEFT)

        bottom = ttk.Frame(self.root)
        self._build_keyboard(bottom)
        self._build_hole_panel(bottom)
        self._build_chart()

        statusbar = ttk.Frame(self.root)
        self.status = ttk.Label(statusbar, text="就绪", anchor=tk.W, padding=(8, 2))
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        # 试听控件挂在**状态栏右端**，刻意不另起一行：谱面区只剩 12px 余量，
        # 在属性条里加一行会把洞洞图挤出可视区（历史上就是这么被裁掉的）。
        ttk.Separator(statusbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        # 默认**关**：编谱器一打开就跟着点格子响，在别人旁边 / 戴着耳机时很吵，
        # 而且多数时候是在改指法、写歌词，并不需要听。想听就勾上（勾上时会响一声确认）。
        self.listen_var = tk.BooleanVar(value=False)
        self._listen_on = False                   # 见 _on_listen_toggle：只在**真的变了**时才响
        # 开关走变量的 write trace：点按钮改的也是这个变量，一条路就够，
        # 再挂 Checkbutton 的 command 会因为「点一下触发两次」响两声
        self.listen_var.trace_add("write", lambda *_a: self._on_listen_toggle())
        ttk.Checkbutton(statusbar, text="选中即试听", variable=self.listen_var).pack(side=tk.LEFT)
        ttk.Button(statusbar, text="▶ 试听整首", width=10,
                   command=self.toggle_tune).pack(side=tk.LEFT, padx=(6, 1))
        ttk.Button(statusbar, text="■", width=3,
                   command=self.stop_audio).pack(side=tk.LEFT, padx=1)
        ttk.Label(statusbar, text="速度").pack(side=tk.LEFT, padx=(6, 1))
        self.bpm_var = tk.StringVar(value=str(sound.DEFAULT_BPM))
        ttk.Spinbox(statusbar, from_=40, to=200, width=4, increment=5,
                    textvariable=self.bpm_var).pack(side=tk.LEFT)
        ttk.Label(statusbar, text="（哨笛音色，p 试听选中音 / Ctrl+P 整首 / ■ 立即停）",
                  foreground="#666").pack(side=tk.LEFT, padx=6)

        # 自下而上排布：指法表/键盘/属性条优先占位，谱面占剩余空间（空间不足时谱面内部滚动）
        # 谱面区**先 pack**：pack 是按调用顺序分配空间的，谱面区光装下整个格子就要
        # 258px 起（歌词多了还更高），排在最后就只能捡别人挑剩的 —— 那正是「洞洞图被
        # 下边缘裁掉、加歌词更严重」的根因。放在最前，它先拿到自己需要的高度。
        score_box.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=(4, 2))
        statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.chart_box.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(0, 2))
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(0, 2))
        insp.pack(side=tk.BOTTOM, fill=tk.X, padx=6)

    def _build_keyboard(self, parent):
        left = ttk.LabelFrame(parent, text="简谱键盘（键盘模式：直接按键或点格子编谱）", padding=6)
        left.pack(side=tk.LEFT, fill=tk.Y)
        pad = ttk.Frame(left)
        pad.pack()
        oct_rows = ((f"低  ", -1), ("中  ", 0), (f"高  ", 1))
        for r, (label, octv) in enumerate(oct_rows):
            ttk.Label(pad, text=label).grid(row=r, column=0, sticky=tk.W)
            for d in range(1, 8):
                mark = "." * max(0, -octv) + "'" * max(0, octv)
                ttk.Button(pad, text=f"{d}{mark}", width=4,
                           command=lambda d=d, o=octv: self.append_doc(
                               self._mk_note(d, octave=o))).grid(row=r, column=d, padx=1, pady=1)
        marks = ttk.Frame(left)
        marks.pack(pady=(4, 0))
        # 休止按钮的文字跟着当前时值走（见 _refresh_state_label）——
        # 否则按钮上只写「0 休止」，看着就像只能加四分休止，其实它吃当前时值。
        self.rest_btn = ttk.Button(marks, text="0 休止", width=12, command=self.append_rest)
        self.rest_btn.grid(row=0, column=0, padx=1)
        for i, (text, cmd) in enumerate((("- 延音", self.append_hold),
                                         ("| 小节线", self.append_bar),
                                         ("|: 反复起", lambda: self.append_repeat("start")),
                                         (":| 反复止", lambda: self.append_repeat("end")))):
            ttk.Button(marks, text=text, width=9, command=cmd).grid(row=0, column=i + 1, padx=1)
        # 框类记号（整段括号 / 第 n 结尾框）：都是画在音符上下的**记号**，不占时值、
        # 也不是小节边界，所以另起一排。结尾框手工指定起止：先点「[n 起」再点「n] 止」，
        # 序号由左边的「第 n 结尾」定（默认 1）。
        fr = ttk.Frame(left)
        fr.pack(pady=(4, 0))
        ttk.Button(fr, text="（ 括号起", width=9,
                   command=lambda: self.append_bracket("start")).grid(row=0, column=0, padx=1)
        ttk.Button(fr, text="） 括号止", width=9,
                   command=lambda: self.append_bracket("end")).grid(row=0, column=1, padx=1)
        ttk.Label(fr, text="第").grid(row=0, column=2, padx=(8, 0))
        self.ending_n_var = tk.StringVar(value="1")
        ttk.Spinbox(fr, from_=1, to=9, width=3,
                    textvariable=self.ending_n_var).grid(row=0, column=3)
        ttk.Label(fr, text="结尾").grid(row=0, column=4, padx=(2, 4))
        ttk.Button(fr, text="[ n 起", width=8,
                   command=lambda: self.append_ending("start")).grid(row=0, column=5, padx=1)
        ttk.Button(fr, text="n ] 止", width=8,
                   command=lambda: self.append_ending("end")).grid(row=0, column=6, padx=1)
        st = ttk.Frame(left)
        st.pack(pady=(6, 0))
        ttk.Label(st, text="升降:").grid(row=0, column=0)
        for i, (text, val) in enumerate((("♮", 0), ("♯ s", 1), ("♭ d", -1))):
            ttk.Button(st, text=text, width=4,
                       command=lambda v=val: self.set_state("acc", v)).grid(row=0, column=i + 1)
        ttk.Label(st, text="八度:").grid(row=0, column=4, padx=(8, 0))
        for i, (text, val) in enumerate((("低 z", -1), ("中", 0), ("高 x", 1))):
            ttk.Button(st, text=text, width=4,
                       command=lambda v=val: self.set_state("octave", v)).grid(row=0, column=5 + i)
        st2 = ttk.Frame(left)
        st2.pack(pady=(4, 0))
        ttk.Label(st2, text="时值:").grid(row=0, column=0)
        for i, (text, val) in enumerate((("四分 q", 1.0), ("八分 w", 0.5), ("十六 e", 0.25))):
            ttk.Button(st2, text=text, width=6,
                       command=lambda v=val: self.set_state("dur", v)).grid(row=0, column=i + 1)
        self.dot_btn = ttk.Button(st2, text="附点(=): 关", width=11, command=self.toggle_dot_state)
        self.dot_btn.grid(row=0, column=4, padx=(8, 0))
        self.short_btn = ttk.Button(st2, text="切音(t): 关", width=11,
                                    command=self.toggle_short_state)
        self.short_btn.grid(row=0, column=5, padx=(6, 0))

        # 插入位置 + 歌词（都在「往谱面里写字」这条线上，所以放一起）
        st3 = ttk.Frame(left)
        st3.pack(pady=(6, 0))
        self.ins_before = tk.IntVar(value=1)
        ttk.Checkbutton(st3, text="插入到选中音前", variable=self.ins_before,
                        command=self._on_insert_toggle).grid(row=0, column=0, padx=(0, 8))
        ttk.Label(st3, text="歌词:").grid(row=0, column=1)
        self.lyric_var = tk.StringVar()
        self._lyric_sync = False
        self._lyric_sel = None
        self.lyric_box = ttk.Entry(st3, textvariable=self.lyric_var, width=14)
        self.lyric_box.grid(row=0, column=2, padx=2)
        self.lyric_box.bind("<KeyPress-space>", self._lyric_commit_next)
        self.lyric_box.bind("<Return>", self._lyric_commit_next)
        # Tab 是**没有歧义**的「下一个音」：输入法不用它选候选，所以不用押后就立刻跳
        self.lyric_box.bind("<KeyPress-Tab>", self._lyric_tab_next)
        self.lyric_box.bind("<FocusOut>", lambda e: self._load_lyric_box())
        if _IME_DEBUG_FILE:                # 诊断模式：把**每一个**按键都记下来
            self.lyric_box.bind(
                "<KeyPress>",
                lambda e: _ime_debug("   Key %-12s char=%r | %s | var=%r"
                                     % (e.keysym, e.char, _ime_probe_state(),
                                        self.lyric_var.get())), add="+")
        self.lyric_var.trace_add("write", self._on_lyric_typed)
        ttk.Button(st3, text="✎ 填词", width=7,
                   command=self.start_lyric_input).grid(row=0, column=3, padx=2)
        ttk.Button(st3, text="清空", width=5,
                   command=self.clear_lyric).grid(row=0, column=4, padx=2)
        # 多行（多段）歌词：选第几行来编，＋行 / －行 增删段数；
        # 段数一多，谱面（画布与导出）会自动往下让位并跟着长高。
        ttk.Label(st3, text="第").grid(row=0, column=5, padx=(8, 0))
        self.lyric_line_var = tk.StringVar(value="1")
        self.lyric_line_box = ttk.Combobox(st3, textvariable=self.lyric_line_var,
                                           width=3, state="readonly", values=("1",))
        self.lyric_line_box.grid(row=0, column=6)
        self.lyric_line_box.bind("<<ComboboxSelected>>", lambda e: self._load_lyric_box())
        ttk.Label(st3, text="行").grid(row=0, column=7)
        ttk.Button(st3, text="＋行", width=6,
                   command=self.add_lyric_line).grid(row=0, column=8, padx=2)
        ttk.Button(st3, text="－行", width=6,
                   command=self.remove_lyric_line).grid(row=0, column=9, padx=2)
        ttk.Label(st3, text="空格/Tab=下一个音", foreground="#666").grid(row=0, column=10, padx=(6, 0))

        self.state_lbl = ttk.Label(left, text="", foreground=C_ACCENT)
        self.state_lbl.pack(pady=(6, 0))
        # 键盘说明不贴在这里（见 KEY_HELP_TEXT 的说明：它要 106px，谱面区就没了），
        # 挪到工具栏的「键盘说明」按钮上。

    def _build_hole_panel(self, parent):
        right = ttk.LabelFrame(parent, text="自选指法（点孔切换：按→放→半）", padding=6)
        right.pack(side=tk.LEFT, fill=tk.Y, padx=(6, 0))
        hole_box = ttk.Frame(right)
        hole_box.pack(side=tk.LEFT)
        self.hole_btns = []
        for i in range(6):
            b = ttk.Button(hole_box, text=f"孔{i + 1} ●", width=7,
                           command=lambda i=i: self.toggle_hole(i))
            b.grid(row=i, column=0, pady=1)
            self.hole_btns.append(b)
        ttk.Label(hole_box, text="(从上到下)", foreground="#777").grid(row=6, column=0, pady=(4, 0))
        self.preview = tk.Canvas(right, width=int(CELL_W * 1.15) + 12, height=int(CELL_H * 1.15) + 12,
                                 background=BG, highlightthickness=0)
        self.preview.pack(side=tk.LEFT, padx=8)
        ops = ttk.Frame(right)
        ops.pack(side=tk.LEFT, fill=tk.Y)
        self.holes_lbl = ttk.Label(ops, text="", foreground=C_ACCENT, font=_font(10, True))
        self.holes_lbl.pack(anchor=tk.W)
        ttk.Button(ops, text="追加为自选指法", width=16,
                   command=self.append_custom).pack(pady=3)
        ttk.Button(ops, text="应用到选中音", width=16,
                   command=self.apply_custom_to_sel).pack(pady=3)

    def _build_chart(self):
        box = ttk.LabelFrame(self.root, padding=4)
        self.chart_box = box
        head = ttk.Frame(box)
        head.pack(fill=tk.X)
        self.chart_title = ttk.Label(head, text="", foreground=C_ACCENT)
        self.chart_title.pack(side=tk.LEFT)
        ttk.Label(head, text="　点格子即可加入谱面（两个八度全覆盖，含半孔与调外音）",
                  foreground="#666").pack(side=tk.LEFT)
        wrap = ttk.Frame(box)
        wrap.pack(fill=tk.X)
        self.chart = tk.Canvas(wrap, background=BG, highlightthickness=0, height=CHART_ROW_H + 8)
        self.chart_hs = ttk.Scrollbar(wrap, orient=tk.HORIZONTAL, command=self.chart.xview)
        self.chart.configure(xscrollcommand=self.chart_hs.set)
        # 同上：横向滚动条必须写在画布之前 pack，否则会被 fill=X 的画布挤成一条细缝
        self.chart_hs.pack(side=tk.BOTTOM, fill=tk.X)
        self.chart.pack(fill=tk.X)
        self.chart.bind("<Button-1>", self.on_chart_click)
        self._chart_map = []

    def _bind_keys(self):
        """物理键盘 = 界面上那排简谱按钮的键位等价（键位都标在按钮文字上）。

        统一走 _key() 包一层：焦点在歌词/曲名输入框里时全部让路，
        否则往输入框打「5」会顺手在谱面插一个音。
        """

        def _key(seq, fn):
            self.root.bind(seq, lambda e, fn=fn: None if self._typing() else fn())

        for d in range(1, 8):
            _key(str(d), lambda d=d: self.append_degree(d))
        _key("0", self.append_rest)
        _key("-", self.append_hold)
        _key("<KeyPress-bar>", self.append_bar)          # | 小节线
        _key("q", lambda: self.set_state("dur", 1.0))    # 时值：四分 / 八分 / 十六分
        _key("w", lambda: self.set_state("dur", 0.5))
        _key("e", lambda: self.set_state("dur", 0.25))
        _key("<Delete>", self.delete_note)
        _key("<BackSpace>", self.delete_note)
        _key("<Left>", lambda: self.move_sel(-1))
        _key("<Right>", lambda: self.move_sel(1))
        _key("<Up>", lambda: self.set_state("octave", min(1, self.st_octave + 1)))
        _key("<Down>", lambda: self.set_state("octave", max(-1, self.st_octave - 1)))
        _key("z", lambda: self.set_state("octave", max(-1, self.st_octave - 1)))
        _key("x", lambda: self.set_state("octave", min(1, self.st_octave + 1)))
        _key("=", self.toggle_dot_state)
        _key("s", lambda: self.set_state("acc", 1 if self.st_acc != 1 else 0))
        _key("d", lambda: self.set_state("acc", -1 if self.st_acc != -1 else 0))
        # 记号：t 切音（有选中音则改选中音，否则切换“新音符默认带切音”），
        # [ ] 连音线起止，\ 延音线（用显式 <KeyPress-…> 写法，简写形式对 [ ] \ 不触发）
        _key("<KeyPress-t>", lambda: (self.toggle_short() if self._need_sel_silent()
                                      else self.toggle_short_state()))
        _key("<KeyPress-T>", lambda: self.toggle_short_state())
        _key("<KeyPress-bracketleft>", lambda: self.set_slur("start"))
        _key("<KeyPress-bracketright>", lambda: self.set_slur("end"))
        _key("<KeyPress-backslash>", lambda: self.set_slur("tie"))
        # 反复记号（循环符号）：r = |: 反复起，Shift+R = :| 反复止；v = 换气记号
        _key("<KeyPress-r>", lambda: self.append_repeat("start"))
        _key("<KeyPress-R>", lambda: self.append_repeat("end"))
        # 框类记号：( ) = 整段括号起止；Alt+[ / Alt+] = 第 n 结尾框起止
        # （[ ] 已被连音线占着，结尾框又需要一个序号，所以让 n 走界面上的「第 n 结尾」）
        _key("<KeyPress-parenleft>", lambda: self.append_bracket("start"))
        _key("<KeyPress-parenright>", lambda: self.append_bracket("end"))
        _key("<Alt-KeyPress-bracketleft>", lambda: self.append_ending("start"))
        _key("<Alt-KeyPress-bracketright>", lambda: self.append_ending("end"))
        _key("<KeyPress-v>", self.toggle_breath)
        _key("<KeyPress-V>", self.toggle_breath)
        _key("<Control-z>", self.undo)
        _key("<Control-y>", self.redo)
        _key("<Control-s>", self.save_project)
        _key("<Control-e>", self.export_svg)
        _key("<F5>", self.open_page_preview)
        # 歌词：回车进输入框继续填（空格在输入框里是「下一个音」）
        _key("<Control-l>", self.start_lyric_input)
        # 试听：p = 响一下当前选中的音；Ctrl+P = 整首试听（再按一次停）
        _key("<KeyPress-p>", lambda: self.listen_selected(force=True))
        _key("<Control-p>", self.toggle_tune)

    # ---------- 状态 ----------
    def _on_mode_pick(self, event=None):
        """选「全按作N」：换算曲调 1=X（指法本身不变，只是记谱口径变了）"""
        whistle = self.whistle_var.get()
        degree = int(self.mode_var.get().replace("全按作", ""))
        key = fingering.key_for_mode(whistle, degree)
        self.key_var.set(key)
        self.status.config(text=f"{whistle} 调哨笛，全按作 {degree}：即 1={key}"
                                f"（筒音记作 {degree}）")

    def _sync_mode_box(self):
        whistle, key = self.whistle_var.get(), self.key_var.get()
        self.mode_box.config(values=list(fingering.all_modes(whistle)))
        label = fingering.mode_label(whistle, key)
        self.mode_var.set(label or "无对应")
        if label:
            self.status.config(text=f"1={key} 即 {whistle} 调哨笛「{label}」")
        else:
            self.status.config(text=f"1={key} 无法用「全按作N」表示（需半孔/交叉指法）")

    def _meta_changed(self):
        if self._bulk_set:          # 批量 set 中（打开工程/撤销重做）：末尾统一重画
            return
        self.proj["title"] = self.title_var.get().strip() or "未命名"
        self.proj["key"] = self.key_var.get()
        self.proj["whistle"] = self.whistle_var.get()
        self.proj["beats"] = self.beats_var.get()
        self.proj["auto_bars"] = bool(self.autobar_var.get())
        self._sync_mode_box()
        self.redraw_all()
        self._touch()

    def _mk_note(self, degree: int, octave: int | None = None) -> dict:
        """按当前键盘状态造一个音符（含升降/八度/时值/附点/切音）"""
        octv = self.st_octave if octave is None else octave
        dur = self.st_dur * (jianpu.DOT_FACTOR if self.st_dot else 1.0)
        return pj.new_note(degree, self.st_acc, octv, dur, short=self.st_short)

    def set_state(self, which: str, value):
        if which == "acc":
            self.st_acc = value
        elif which == "octave":
            self.st_octave = value
        else:
            self.st_dur = value
        self._refresh_state_label()
        self.redraw_preview()

    def toggle_dot_state(self):
        self.st_dot = not self.st_dot
        self.dot_btn.config(text=f"附点(=): {'开' if self.st_dot else '关'}")
        self._refresh_state_label()

    def toggle_short_state(self):
        """新加的音默认带切音记号（渲染时切音自占一个小窄格，紧跟在该音前面）"""
        self.st_short = not self.st_short
        self.short_btn.config(text=f"切音(t): {'开' if self.st_short else '关'}")
        self._refresh_state_label()

    def _refresh_state_label(self):
        acc = {1: "♯", -1: "♭", 0: "♮"}[self.st_acc]
        oct_name = {-1: "低八度", 0: "中音", 1: "高八度"}[self.st_octave]
        dur = jianpu.duration_name(self.st_dur * (jianpu.DOT_FACTOR if self.st_dot else 1.0))
        # 休止按钮的文字跟着时值走：不然按钮上只写「0 休止」，看不出它其实吃当前时值
        rest_btn = getattr(self, "rest_btn", None)
        if rest_btn is not None:
            rest_btn.config(text=f"0 休止({dur})")
        tail = "　切音" if self.st_short else ""
        # 插入模式要说清楚「新音会插到哪」，否则用户以为坏了
        at = self._insert_at()
        if at is None:
            where = "　→ 追加到末尾"
        else:
            where = f"　→ 插到第 {at + 1} 个音前"
        self.state_lbl.config(text=f"当前：{acc} {oct_name} {dur}{tail}{where}")

    def _refresh_holes_label(self):
        for i, st in enumerate(self.custom_holes):
            mark = {1: "●", 0: "○", 2: "◐"}[st]
            self.hole_btns[i].config(text=f"孔{i + 1} {mark}")
        name, known = fingering.describe_holes(self.custom_holes, self.whistle_var.get())
        token, note = self._holes_to_jianpu(self.custom_holes)
        self.holes_lbl.config(
            text=f"当前指法：{name if known else '自定义指法'}\n"
                 f"对应简谱：{token}　音名：{note}")

    # ---------- 指法反查 ----------
    def _whistle_index(self, holes) -> int | None:
        bucket = fingering.build_reverse_map(self.whistle_var.get()).get(tuple(holes))
        return bucket[0].index if bucket else None

    def _abs_to_jianpu(self, absolute: int):
        """绝对半音值 -> (简谱记号文本, 音名)，按当前调号推导，调外音用升降号表示"""
        note_name = jianpu.NOTE_NAMES_SHARP[absolute % 12]
        rel = absolute - jianpu.KEY_SEMITONES[self.key_var.get()]
        octave, pc = rel // 12, rel % 12      # 中音组 1-7 对应 rel 0-11
        major = jianpu.DEGREE_SEMITONES
        if pc in major.values():
            degree = [d for d, v in major.items() if v == pc][0]
            acc = 0
        elif pc == major[6] + 1:               # 升六级 = 降七级，按演奏惯例记作 b7
            degree, acc = 7, -1
        else:                                  # 其余调外音取更近的一侧，平局用升号
            lower = max(d for d, v in major.items() if v < pc)
            upper = min(d for d, v in major.items() if v > pc)
            dl, du = pc - major[lower], major[upper] - pc
            degree, acc = (lower, dl) if dl <= du else (upper, -du)
        doc = pj.new_note(degree, acc, max(-1, min(1, octave)))
        return pj.token_of(doc), note_name

    def _holes_to_jianpu(self, holes):
        idx = self._whistle_index(holes)
        if idx is None:
            return "—", "—"
        tonic = fingering.WHISTLE_TONICS[self.whistle_var.get()]
        token, note_name = self._abs_to_jianpu(tonic + idx)
        return token, note_name + (" 高" if idx >= 12 else "")

    def toggle_hole(self, i: int):
        self.custom_holes[i] = STATE_CYCLE[self.custom_holes[i]]
        self._refresh_holes_label()
        self.redraw_preview()

    # ---------- 编辑操作 ----------
    def _snapshot(self):
        self.undo_stack.append(self._snapshot_state())
        if len(self.undo_stack) > 120:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _snapshot_state(self):
        return {"notes": deepcopy(self.proj["notes"]), "sel": self.sel,
                "title": self.title_var.get(), "key": self.key_var.get(),
                "whistle": self.whistle_var.get(), "beats": self.beats_var.get(),
                "auto_bars": bool(self.autobar_var.get())}

    def _after_edit(self, select: int | None = None, scroll_to: int | None = None):
        if select is not None:
            self.sel = select
        if scroll_to is not None:
            self._scroll_to_doc = scroll_to   # 让 redraw_score 结束后把新音滚进视野
        self.redraw_all()
        self._touch()

    def _insert_at(self):
        """「插到哪个下标之前」；不插入时返回 None。

        插入模式下若**用户选中了**某个音，新音就插在它**前面**；没选中（或关掉插入）就追加到末尾。
        插完选中框留在原来的音上（它的下标 +1），于是连续敲键时新音会按敲键顺序排在它前面。
        """
        if not getattr(self, "ins_before", None) or not self.ins_before.get():
            return None
        if not self._sel_user:                 # 选中框是「追加落下来的」，不是用户点的
            return None
        if not (0 <= self.sel < len(self.proj["notes"])):
            return None
        return self.sel

    def _on_insert_toggle(self):
        """勾上「插入到选中音前」时，把当前选中音当成插入目标（否则用户会以为勾了没反应）。"""
        if self.ins_before.get() and 0 <= self.sel < len(self.proj["notes"]):
            self._sel_user = True
        self._refresh_state_label()

    def append_doc(self, doc: dict):
        self._snapshot()
        notes = self.proj["notes"]
        at = self._insert_at()
        if at is None:
            notes.append(doc)
            new_idx = len(notes) - 1
            self._after_edit(new_idx, scroll_to=new_idx)
            self._sel_user = False             # 选中框是追加落下来的 → 下一个继续追加
        else:
            notes.insert(at, doc)
            new_idx = at
            # 选中框留在原音上（连敲键按顺序排在它前面），但视线跟到**新加的这个音**
            self._after_edit(at + 1, scroll_to=new_idx)
        tail = f"（已插到第 {at + 1} 个音前）" if at is not None else ""
        self.status.config(text=f"已加入 {pj.token_of(doc)}{tail}")

    def append_degree(self, degree: int):
        self.append_doc(self._mk_note(degree))

    def append_rest(self):
        self.append_doc(pj.new_simple(pj.KIND_REST, self._mk_note(1)["duration"]))

    def append_hold(self):
        self.append_doc(pj.new_simple(pj.KIND_HOLD))

    def append_bar(self):
        self.append_doc(pj.new_simple(pj.KIND_BAR))

    def append_repeat(self, direction: str = "start"):
        """追加反复记号（循环符号）：start=|: 反复开始、end=:| 反复结束。

        它不占时值，所以在自动小节线模式下不会被重排掉；`:|` 还会把刚生成的那条
        普通小节线顶掉（它自己就是收尾）。
        """
        self.append_doc(pj.new_repeat(direction))
        self.status.config(text=f"已加入反复记号 {pj.REPEAT_DIRS.get(direction, '|:')}")

    def _ending_n(self) -> int:
        """界面上「第 n 结尾」的序号（1~9，取值异常就退回 1）"""
        try:
            return max(1, min(9, int(self.ending_n_var.get())))
        except (ValueError, AttributeError, TypeError):
            return 1

    def append_bracket(self, direction: str = "start"):
        """追加整段括号的一侧（前奏 / 间奏 / 和声伴唱）：start=（ 、end=）。

        不占时值、也不是小节边界（自动小节线模式下不会被重排掉）。左右两侧**各自自足**：
        左括号画在起点那格左缘、右括号画在终点那格右缘，所以跨行时不会像连音线那样丢。
        **贴着小节边界时按记谱口径让位**：起点落在小节线之后、终点落在小节线之前
        （`（ 5 6 5 3 ） |`），框才跟小节对齐（见 jianpu.is_frame_close）。
        """
        self.append_doc(pj.new_bracket(direction))
        self.status.config(text="已加入整段括号 "
                                + ("（（括号起点）" if direction == "start" else "）（括号终点）"))

    def append_ending(self, direction: str = "start"):
        """追加「第 n 结尾」框的一侧：start=[n 起、end=n] 止（序号取界面上的「第 n」）。

        起止**手工指定**：框子从 `[n` 那一格一直画到 `n]` 那一格，压在这一段所有记号
        （高八度点 / 换气 v / 连音弧线）之上。它同样是记号而不是小节线，不占时值；
        贴着小节边界时与整段括号同口径：`[n` 落在小节线之后、`n]` 落在小节线之前。
        """
        n = self._ending_n()
        self.append_doc(pj.new_ending(direction, n))
        self.status.config(text=f"已加入第 {n} 结尾框"
                                + ("（[n 起点）" if direction == "start"
                                   else "（n] 终点）"))

    def append_custom(self):
        token, _ = self._holes_to_jianpu(self.custom_holes)
        doc = pj.token_to_doc(token)
        if doc is None:
            messagebox.showinfo("提示", "当前孔位无法对应到标准音，无法追加")
            return
        doc["duration"] = self._mk_note(1)["duration"]
        doc["holes"] = list(self.custom_holes)
        self.append_doc(doc)
        self.status.config(text=f"已追加 {token}（自选指法）")

    def append_from_scale(self, idx: int):
        tonic = fingering.WHISTLE_TONICS[self.whistle_var.get()]
        token, _ = self._abs_to_jianpu(tonic + idx)
        doc = pj.token_to_doc(token)
        if doc is None:
            return
        doc["duration"] = self._mk_note(1)["duration"]
        self.append_doc(doc)

    def _need_sel(self) -> bool:
        if not (0 <= self.sel < len(self.proj["notes"])):
            self.status.config(text="请先在谱面上选中一个音")
            return False
        return True

    def set_dur(self, dur: float):
        if not self._need_sel():
            return
        self._snapshot()
        doc = self.proj["notes"][self.sel]
        if self.st_dot and not jianpu.is_dotted(dur):
            dur *= jianpu.DOT_FACTOR
        doc["duration"] = dur
        self._after_edit()

    def toggle_dot(self):
        if not self._need_sel():
            return
        doc = self.proj["notes"][self.sel]
        if doc.get("kind") == pj.KIND_HOLD:
            return
        self._snapshot()
        d = doc.get("duration", 1.0)
        doc["duration"] = d / jianpu.DOT_FACTOR if jianpu.is_dotted(d) else d * jianpu.DOT_FACTOR
        self._after_edit()

    def shift_octave(self, delta: int):
        if not self._need_sel():
            return
        doc = self.proj["notes"][self.sel]
        if doc.get("kind") != pj.KIND_NOTE:
            return
        self._snapshot()
        doc["octave"] = max(-1, min(1, doc.get("octave", 0) + delta))
        self._after_edit()

    def shift_acc(self, delta: int):
        if not self._need_sel():
            return
        doc = self.proj["notes"][self.sel]
        if doc.get("kind") != pj.KIND_NOTE:
            return
        self._snapshot()
        doc["accidental"] = max(-1, min(1, doc.get("accidental", 0) + delta))
        self._after_edit()

    # ---------- 记号：切音 / 连音线 ----------
    def toggle_short(self):
        """切换选中音的切音记号（吐音 / 切分；渲染时切音自占一个小窄格放在该音前面）"""
        if not self._need_sel():
            return
        doc = self.proj["notes"][self.sel]
        if doc.get("kind") != pj.KIND_NOTE:
            return
        self._snapshot()
        doc["short"] = not doc.get("short")
        self._after_edit()
        self.status.config(text="已加上切音记号" if doc["short"] else "已取消切音记号")

    def toggle_breath(self):
        """切换选中音的换气记号 v（画在数字正上方；连音弧线会自动往上让一层）"""
        if not self._need_sel():
            return
        doc = self.proj["notes"][self.sel]
        if doc.get("kind") != pj.KIND_NOTE:
            self.status.config(text="休止/延音/小节线不能加换气记号")
            return
        self._snapshot()
        doc["breath"] = not doc.get("breath")
        self._after_edit()
        self.status.config(text="已加上换气记号" if doc["breath"] else "已取消换气记号")

    def set_slur(self, mode: str):
        """连音线：start=起点、end=终点、tie=与下一音相连、clear=清除。

        起点与终点配成一条弧线：两端同音高=延音线（棕），不同音高=圆滑线（绿）。
        """
        if not self._need_sel():
            return
        doc = self.proj["notes"][self.sel]
        if doc.get("kind") != pj.KIND_NOTE:
            self.status.config(text="休止/延音/小节线不能加连音线")
            return
        self._snapshot()
        if mode == "clear":
            for k in ("slur_start", "slur_end", "tie"):
                doc.pop(k, None)
            msg = "已清除选中音的连线"
        elif mode == "tie":
            doc.pop("slur_start", None)
            doc.pop("slur_end", None)
            doc["tie"] = not doc.get("tie")
            msg = ("已设置延音线（与紧邻的下一个音相连）" if doc["tie"] else "已取消延音线")
        else:
            key, other = (("slur_start", "slur_end") if mode == "start"
                          else ("slur_end", "slur_start"))
            doc.pop("tie", None)
            doc[key] = not doc.get(key)
            if doc[key]:
                doc.pop(other, None)
            name = "连音线起点" if mode == "start" else "连音线终点"
            msg = f"已标记{name}" if doc[key] else f"已取消{name}"
        self._after_edit()
        self.status.config(text=msg)

    @staticmethod
    def _mark_text(doc: dict) -> str:
        kind = doc.get("kind", pj.KIND_NOTE)
        if kind == pj.KIND_BRACKET:
            return "整段括号（起）" if doc.get("direction", "start") == "start" else "整段括号（止）"
        if kind == pj.KIND_ENDING:
            n = max(1, int(doc.get("n", 1) or 1))
            return (f"第 {n} 结尾框（起）" if doc.get("direction", "start") == "start"
                    else f"第 {n} 结尾框（止）")
        if kind == pj.KIND_REPEAT:
            return f"反复记号 {pj.REPEAT_DIRS.get(doc.get('direction', 'start'), '|:')}"
        bits = []
        if doc.get("short"):
            bits.append("切音")
        if doc.get("breath"):
            bits.append("换气")
        if doc.get("slur_start"):
            bits.append("连音起")
        if doc.get("slur_end"):
            bits.append("连音止")
        if doc.get("tie"):
            bits.append("延音线")
        return "＋".join(bits) if bits else "—"

    # ---------- 歌词 ----------
    def _typing(self) -> bool:
        """焦点是不是在输入框里（歌词框 / 曲名框 / 下拉框）。

        全局快捷键是绑在 root 上的，Entry 里的按键会继续往上传，
        所以不挡一下的话，往歌词框里打「5」会顺手在谱面插一个音。
        """
        try:
            w = self.root.focus_get()
        except (KeyError, tk.TclError):
            return False
        if w is None:
            return False
        try:
            return str(w.winfo_class()) in ("Entry", "TEntry", "Text", "Combobox",
                                            "TCombobox", "Spinbox", "TSpinbox")
        except tk.TclError:
            return False

    def _lyric_line_index(self) -> int:
        """当前正在编辑第几行歌词（0 基）。取值异常时退回第 0 行。"""
        try:
            return max(0, int(self.lyric_line_var.get()) - 1)
        except (ValueError, AttributeError, TypeError):
            return 0

    def _lyric_line_total(self) -> int:
        """谱面当前留了几行歌词（至少 1，方便界面显示）"""
        return max(1, pj.lyric_line_count(self.proj["notes"]))

    def _refresh_lyric_line_box(self):
        """把「第 N 行」的选项刷成 1..总行数，并把当前选项夹回范围内"""
        n = self._lyric_line_total()
        self.lyric_line_box.config(values=tuple(str(i) for i in range(1, n + 1)))
        cur = min(self._lyric_line_index() + 1, n)
        self._lyric_sync = True          # 别让 set 触发回写
        try:
            self.lyric_line_var.set(str(cur))
        finally:
            self._lyric_sync = False

    def _load_lyric_box(self):
        """把选中音「第 N 行」的歌词读进输入框（切歌、换行、撤销后都要同步一次）"""
        self._refresh_lyric_line_box()
        text = ""
        if 0 <= self.sel < len(self.proj["notes"]):
            lines = pj.lyric_lines_of(self.proj["notes"][self.sel])
            k = self._lyric_line_index()
            text = lines[k] if k < len(lines) else ""
        self._lyric_sync = True          # 防止回写触发 trace 再改工程
        try:
            self.lyric_var.set(text)
        finally:
            self._lyric_sync = False
        self._lyric_sel = None           # 换了音/行了 → 下次改动重新记撤销点

    def _on_lyric_typed(self, *_):
        """输入框内容一变就写进当前音的当前行（IME 上屏也能触发，所以走 StringVar trace）"""
        if self._lyric_sync:
            return                        # 我们自己回填的不算「用户/输入法改的」
        if _IME_DEBUG_FILE:
            _ime_debug("   TRACE var=%r | %s" % (self.lyric_var.get(), _ime_probe_state()))
        if not (0 <= self.sel < len(self.proj["notes"])):
            return
        doc = self.proj["notes"][self.sel]
        if doc.get("kind") != pj.KIND_NOTE:
            return
        if self._lyric_sel != self.sel:   # 每个音第一次改动才记一次撤销点
            self._snapshot()
            self._lyric_sel = self.sel
        lines = pj.lyric_lines_of(doc)
        k = self._lyric_line_index()
        while len(lines) <= k:            # 直接在第 2 行打字时，前面补空行占位
            lines.append("")
        lines[k] = self.lyric_var.get()
        pj.set_lyric_lines(doc, lines)
        self.redraw_score()               # 只重画谱面：改歌词不必重建指法表
        self._schedule_page_refresh()
        self._touch()

    def add_lyric_line(self):
        """给整个工程加一行歌词段（每个音都补一个空行占位，谱面自动往下让位）"""
        if not self.proj["notes"]:
            self.status.config(text="还没有音符，先加几个音再写歌词")
            return
        self._snapshot()
        total = pj.lyric_line_count(self.proj["notes"]) + 1
        for doc in self.proj["notes"]:
            if doc.get("kind") != pj.KIND_NOTE:
                continue
            lines = pj.lyric_lines_of(doc)
            while len(lines) < total:
                lines.append("")
            pj.set_lyric_lines(doc, lines)
        self.redraw_all()
        self.lyric_line_var.set(str(total))
        self._load_lyric_box()
        self._touch()
        self.status.config(text=f"已加到第 {total} 段歌词；洞洞图自动往下让位")

    def remove_lyric_line(self):
        """删掉最后一段歌词（其余行保留）"""
        total = pj.lyric_line_count(self.proj["notes"])
        if total <= 1:
            self.status.config(text="只有一段歌词，不用删（要清词点「清空」）")
            return
        self._snapshot()
        for doc in self.proj["notes"]:
            lines = pj.lyric_lines_of(doc)
            if len(lines) >= total:
                pj.set_lyric_lines(doc, lines[:total - 1])
                continue
            pj.set_lyric_lines(doc, lines)
        self.redraw_all()
        self.lyric_line_var.set(str(total - 1))
        self._load_lyric_box()
        self._touch()
        self.status.config(text=f"已删掉第 {total} 段歌词")

    def start_lyric_input(self):
        """「✎ 填词」：把焦点交给歌词框，从当前音开始填"""
        if not (0 <= self.sel < len(self.proj["notes"])):
            self.status.config(text="先在谱面上点一个音（或按 ← → 选音），再填词")
            return
        if self.proj["notes"][self.sel].get("kind") != pj.KIND_NOTE:
            self.status.config(text="这个格子不是音符（休止/延音/小节线）不能填词")
            return
        self._load_lyric_box()
        self.lyric_box.focus_set()
        self.lyric_box.select_range(0, tk.END)
        self.status.config(text="输入即写入当前音；按空格或 Tab 存好并跳到下一个音"
                                "（输入法抢空格时按 Tab 一定跳）")

    def clear_lyric(self):
        """清空当前音**当前这一行**的歌词（行数不变；要减段用「－行」）"""
        if not (0 <= self.sel < len(self.proj["notes"])):
            return
        doc = self.proj["notes"][self.sel]
        self._snapshot()
        lines = pj.lyric_lines_of(doc)
        k = self._lyric_line_index()
        while len(lines) <= k:              # 直接清第 2 行时，前面补空行占位
            lines.append("")
        lines[k] = ""
        if any(lines):
            pj.set_lyric_lines(doc, lines)  # 别的行还有词 → 这一行的空位留着（谱面照旧让位）
        else:
            pj.set_lyric_lines(doc, [])     # 全清空了 → 键也删干净，JSON 里不留空壳
        self._lyric_sel = None
        self._load_lyric_box()
        self.redraw_all()
        self._touch()
        self.status.config(text=f"已清空这个音第 {k + 1} 行的歌词")

    def _lyric_commit_next(self, event=None):
        """空格 / 回车：本音填完，自动跳到下一个音继续填。

        中文输入法里空格 / 回车也是「选候选上屏」用的，于是同一个按键有了两种含义。
        **Tk 其实把答案直接写在事件里了** —— 这是用户那边开诊断后的实录（`tests/_ime_debug.log`）：

            [ +1920.4 ms] ── KeyPress space  char='映' state=0x8 | comp=0 | var=''

        keysym 还是 `space`，但 **`event.char` 是上屏的那个字**。答案有了，就不用再猜时间，
        于是这一版的判据只有一条（外加一条 imm32 兜底）：

        * `event.char` 是**别的字**（不是空格 / 回车本身）⇒ 这个键被输入法拿去上屏了 ⇒
          **放行、留在这一格**：返回 `None` 而不是 `"break"`，让 Tk 照常把字插进输入框。
          这一点是前两版修错的关键地方 —— 老实现在这儿 `return "break"` 把上屏事件截断了，
          字被挡在框外（`var` 一直是空的），「等会儿看看字有没有来」当然永远等不到，
          于是判定「不是输入法」→ 跳格。**bug 绕一圈回来靠的就是这个 break。**
        * `event.char` 就是空格 / 回车 ⇒ 输入法没吃这个键 ⇒ **立刻跳**，不必押后等待。
        * `ime_is_composing()`（imm32）兜底：某些输入法走 TSF、查不到组字状态（用户机器上
          `comp` 一直是 0，这条路等于不存在），但只要查得到且在组字，就不跳。

        顺带回答「为什么只有一部分字会犯」：候选唯一的常用字（应 / 影）输入法**自动上屏**，
        用户压根不用按空格；要翻页 / 手动选候选的字（映）才会按下空格、才会产生这种事件。
        跟输入法快慢、跟等待窗口长短都没有关系 —— 前两版一直往那边猜，白改了两次。

        event is None 表示不是按键触发的（代码直接调，见测试），那就没有输入法这一说，立刻跳。
        """
        if event is None:
            self._lyric_jump_next()
            return "break"
        ch = getattr(event, "char", "") or ""
        if ch and ch not in (" ", "\r", "\n"):
            _ime_debug("   └ char=%r 是输入法上屏 → 放行（字进输入框，不跳）" % ch)
            return None                   # 放行：让 Tk 把上屏的字插进输入框
        if self._ime_is_composing():
            _ime_debug("   └ 输入法正在组字 → 不跳")
            return "break"                # 还在组字：这个键给了输入法 —— 留在这一格
        _ime_debug("   └ 真·%s → 立刻跳" % (getattr(event, "keysym", "?"),))
        self._lyric_jump_next()
        return "break"                    # 别把空格 / 回车打进输入框

    def _ime_is_composing(self) -> bool:
        """歌词框里输入法是不是正在组字（见模块里的 `ime_is_composing`）。

        单独包一层是为了**测试可以打桩**：IME 状态没法在 CI 里真的造出来。
        """
        try:
            return ime_is_composing(self.lyric_box.winfo_id())
        except Exception:
            return False

    def _lyric_tab_next(self, event=None):
        """Tab = 立刻跳到下一个音。

        输入法不用 Tab（它只吃空格 / 回车 / 数字键选候选），所以这一键没有任何歧义。
        （有了 `event.char` 判据之后空格其实已经很准了，Tab 留着只是换种手感 + 万一的兜底。）
        """
        self._lyric_jump_next()
        return "break"

    def _lyric_jump_next(self):
        """本音填完 → 跳到下一个可填词的音（跳过休止 / 延音 / 小节线）"""
        _ime_debug("   ⇒ 跳格！sel %d" % self.sel)
        self._load_lyric_box()            # 把输入框里剩的字落进当前音
        n = len(self.proj["notes"])
        i = self.sel + 1
        while i < n and self.proj["notes"][i].get("kind") != pj.KIND_NOTE:
            i += 1                        # 跳过休止/延音/小节线
        if i >= n:
            self.status.config(text="已经是最后一个音了")
            return
        self.sel = i
        self._sel_user = True                  # 空格跳下一个音 = 用户走到的位置
        self.redraw_all()
        self._load_lyric_box()
        self.lyric_box.select_range(0, tk.END)
        self.status.config(text=f"已跳到第 {i + 1} 个音（第 {n} 个音收尾）")

    def move_note(self, delta: int):
        if not self._need_sel():
            return
        target = self.sel + delta
        if not (0 <= target < len(self.proj["notes"])):
            return
        self._snapshot()
        notes = self.proj["notes"]
        notes[self.sel], notes[target] = notes[target], notes[self.sel]
        self._after_edit(target)

    def move_sel(self, delta: int):
        if not self.proj["notes"]:
            return
        self.sel = max(0, min(len(self.proj["notes"]) - 1, self.sel + delta))
        self._sel_user = True                  # 用户走出来的选中音 → 可作为插入目标
        self.redraw_all()

    def delete_note(self):
        if not self._need_sel():
            return
        self._snapshot()
        del self.proj["notes"][self.sel]
        self.sel = min(self.sel, len(self.proj["notes"]) - 1)
        self._sel_user = False                 # 删除后落下来的选中位置不是用户点的
        self._after_edit()

    def apply_custom_to_sel(self):
        if not self._need_sel():
            return
        doc = self.proj["notes"][self.sel]
        if doc.get("kind") != pj.KIND_NOTE:
            return
        self._snapshot()
        doc["holes"] = list(self.custom_holes)
        self._after_edit()
        self.status.config(text="已把当前自选指法应用到选中音")

    def reset_holes(self):
        if not self._need_sel():
            return
        doc = self.proj["notes"][self.sel]
        if doc.get("kind") != pj.KIND_NOTE:
            return
        self._snapshot()
        doc["holes"] = None
        self._after_edit()
        self.status.config(text="已恢复自动指法")

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self._snapshot_state())
        self._restore(self.undo_stack.pop())

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self._snapshot_state())
        self._restore(self.redo_stack.pop())

    def _restore(self, state):
        self.proj["notes"] = deepcopy(state["notes"])
        self.sel = min(state["sel"], len(self.proj["notes"]) - 1)
        self._sel_user = False                 # 撤销/重做后的选中位置不是用户点的
        self._bulk_set = True                  # 撤销/重做是高频操作，别每个控件重画一次
        try:
            self.title_var.set(state["title"])
            self.key_var.set(state["key"])
            self.whistle_var.set(state["whistle"])
            self.beats_var.set(state.get("beats", "4/4"))
            self.autobar_var.set(1 if state.get("auto_bars", True) else 0)
        finally:
            self._bulk_set = False
        self._sync_mode_box()
        self.redraw_all()
        self._touch()

    # ---------- 绘制刷新 ----------
    def redraw_all(self):
        self.redraw_score()
        self.redraw_preview()
        self.redraw_chart()
        self._refresh_holes_label()
        self._refresh_state_label()
        if getattr(self, "lyric_box", None) is not None:
            self._load_lyric_box()        # 选中音变了 → 歌词框跟着换内容
        self._maybe_listen()              # 选中音变了 → 响一下对应的音（开关见状态栏）
        self._schedule_page_refresh()

    def _schedule_page_refresh(self):
        """预览窗口开着时跟着编辑走。

        连续敲键会触发很多次重画，所以延迟合并一下。重画耗时大致与音数成正比
        （实测 600 格约 100ms），所以长曲子把合并窗口拉长，免得敲键卡手。
        """
        win = getattr(self, "_page_win", None)
        if win is None or not win.winfo_exists():
            return
        if not getattr(self, "_page_follow", None) or not self._page_follow.get():
            return
        job = getattr(self, "_page_job", None)
        if job:
            try:
                self.root.after_cancel(job)
            except (tk.TclError, ValueError):
                pass
        delay = PREVIEW_LIVE_MS if len(self.proj["notes"]) <= PREVIEW_LIVE_MAX else 300
        self._page_job = self.root.after(delay, self.refresh_page_preview)

    def _caret_x(self, default: float):
        """竖线光标的 x —— 插入点在哪就画在哪。

        插入模式下且用户选中了某个音 → 画在那个音格子的**左边缘**（新音会插在它前面）；
        否则画在**曲末**（新音追加到最后）。空谱就画在起笔处。
        """
        if not self._cell_map:
            return default
        at = self._insert_at()
        if at is None:
            return self._cell_map[-1][1]           # 曲末
        for x0, _x1, doc_idx in self._cell_map:
            if doc_idx == at:
                return max(x0, 6.0)                # 选中格左边缘（不越出画布）
        return self._cell_map[-1][1]

    def _scroll_to_doc_cell(self, doc_idx):
        """把某个音所在的格子横向滚进可见范围（已经在视野里就什么都不做）。

        「新加的音超到谱图外面去了就自动跳过去」——编长谱时不必再手动拖横向滚动条。
        只动横向：谱面区是一条长横带，纵向本来就不需要滚。
        """
        if doc_idx is None:
            return
        cell = None
        for x0, x1, idx in self._cell_map:
            if idx == doc_idx:
                cell = (x0, x1)
                break
        if cell is None:                       # 小节线等不可选格子、或映射还没建好
            return
        cv = self.score
        try:
            cv.update_idletasks()
            first, last = cv.xview()
            parts = str(cv.cget("scrollregion")).split()
        except tk.TclError:
            return
        if len(parts) != 4:
            return
        try:
            total = float(parts[2]) - float(parts[0])
        except ValueError:
            return
        if total <= 1:
            return
        vis_w = (last - first) * total
        if vis_w <= 1:                         # 画布还没铺开（宽 1px）→ 不折腾
            return
        x0, x1 = cell
        vis_x0, vis_x1 = first * total, last * total
        if vis_x0 <= x0 and x1 <= vis_x1:      # 整个格子都看得见 → 不动
            return
        left = max(0.0, x0 - CELL_W * 0.5)     # 左边留半格上下文，方便接着往下写
        left = min(left, max(0.0, total - vis_w))
        cv.xview_moveto(left / total)

    def _score_height_limit(self):
        """画布最高能长到多少：窗口高度 − 其它各块要的高度，余下的才是谱面。

        谱面区在窗口里是唯一会让步的一块（其余各块都是定高）。窗口真的装不下
        「歌词 3 行时变高的格子」时，不能让它继续长去挤下面的面板 —— 那会把
        「选中音属性」那排按钮压掉半截（按钮点不到，比看不到笛身更糟）。
        到这儿封顶，多出来的高度交给纵向滚动条。

        窗口矮到连「装下整个格子」都做不到时，一路让到 SCORE_MIN_H：
        谱面是这套界面里**唯一能滚动着看全**的一块，让它先饿着最划算。
        """
        root = self.root
        try:
            avail = root.winfo_height()
        except tk.TclError:
            return 10 ** 6
        if avail <= 1:                       # 窗口还没映射出来 → 先不设限
            return 10 ** 6
        box = self.score.master               # 谱面 LabelFrame：它自身也要吃 padding/标题/滚动条
        overhead = others = 0
        for child in root.winfo_children():
            if child is box:
                try:
                    overhead = max(0, box.winfo_reqheight()
                                   - self.score.winfo_reqheight())
                except tk.TclError:
                    overhead = 0
                continue
            # 只算**主窗口里 pack 着**的那几块。弹窗 / 整谱预览是 Toplevel，
            # 也是 root 的子控件，但它们自成窗口、不占主窗口的高度（而且没有 pack_info）。
            if child.winfo_manager() != "pack":
                continue
            try:
                others += child.winfo_reqheight()
                # pack 的 pady 也占地方，但不计入任何控件的 reqheight，得单独加回来
                pad = child.pack_info().get("pady", 0)
                others += sum(int(x) for x in pad) if isinstance(pad, (tuple, list)) \
                    else 2 * int(pad)
            except tk.TclError:
                pass
        if others < 100:                      # 还没量出来 → 不设限
            return 10 ** 6
        # 末尾再扣 8px：reqheight 之和是「要多少」，实际排布还有边框/取整的零头，
        # 不扣就会让下面板差几个像素（实测 4px），表现为按钮底边被切掉一条。
        return max(SCORE_MIN_H, avail - others - overhead - 8)

    def _fit_score_height(self):
        """把画布控件的高度调成「装得下整个格子」（歌词多了格子自然更高）。

        为什么非做不可：谱面区在窗口里是唯一会让步的一块（其余各块都是定高），所以
        光把 scrollregion 撑大没有用 —— 画布本身还是那么矮，笛身和音名会被下边缘裁掉。
        表现出来就是「加了歌词行以后洞洞图整体往下掉」。这里让它跟着 score_content_h()
        一起长；长到窗口装不下就停在 _score_height_limit()，纵向滚动条随后出场。
        """
        want = min(int(round(score_content_h())), self._score_height_limit())
        if want != self._score_h:
            self._score_h = want
            self.score.configure(height=want)

    def _on_root_resize(self, event):
        """窗口高度变了 → 重新算一次谱面区高度（放大能把整格露全，缩小就上滚动条）。"""
        if event.widget is not self.root or getattr(self, "_in_fit", False):
            return
        if getattr(self, "_last_root_h", None) == event.height:
            return
        self._last_root_h = event.height
        self._in_fit = True
        try:
            self._fit_score_height()
        finally:
            self._in_fit = False

    def redraw_score(self):
        global _ENDING_TOP
        cv = self.score
        cv.delete("all")
        shown, index_map = pj.display_notes(self.proj)
        set_lyric_shift(shown)                 # 有歌词 → 笛身整体下移让出歌词带
        # 「第 n 结尾」框画在行顶上方，画布顶部原有的 SCORE_TOP 不一定吃得下
        # （这一段里有高八度点 / 换气 v / 连音弧线时框子要更高），不够就整条谱面往下推。
        # 必须**先**算出来再定行顶 y0，不能画完再补救（那样第一帧会看到被裁的框）。
        _ENDING_TOP = frame_top_need(shown)
        y0 = SCORE_TOP + _ENDING_TOP
        self._cell_map = []
        cells = []
        x = 10
        for i, doc in enumerate(shown):
            kind = doc.get("kind", pj.KIND_NOTE)
            if kind in (pj.KIND_BAR, pj.KIND_REPEAT):
                w = CELL_W + BAR_EXTRA_W
            elif kind == pj.KIND_BRACKET:
                w = CELL_W * BRACKET_CELL_RATIO     # 括号就一道弧，别占满格
            elif kind == pj.KIND_ENDING:
                w = CELL_W * ENDING_CELL_RATIO      # 结尾框记号更窄（框子画在上方）
            elif kind == pj.KIND_NOTE and doc.get("short"):
                w = CELL_W * CUT_CELL_RATIO      # 切音占一个窄格子
            else:
                w = CELL_W
            doc_idx = index_map[i]
            draw_cell(cv, x, y0, doc, self.key_var.get(), self.whistle_var.get(),
                      w=w, selected=(doc_idx is not None and doc_idx == self.sel),
                      own_beams=False)
            self._cell_map.append((x, x + w, doc_idx))
            cells.append((x, w))
            x += w
        # 连尾减时线 + 连音线：统一绘制，保证同一拍共用一条连续横线
        draw_mark_layer(cv, shown, cells, y0, beats=self.beats_var.get())
        # 整段括号 + 「第 n 结尾」框：跨格绘制（口径与导出 SVG 的两层一致）
        draw_frame_layer(cv, shown, cells, y0)
        # 竖线光标：画在插入点上（不开插入模式 = 曲末，开了 = 选中格左边）
        caret_x = self._caret_x(10.0 if not cells else x - CELL_W)
        if caret_x is not None:
            draw_caret(cv, caret_x, y0, CELL_H)
        cv.configure(scrollregion=(0, 0, max(x + 10, 400), score_content_h()))
        self._fit_score_height()               # 歌词行数变了 → 画布本身也要跟着「撑够」
        if not self.proj["notes"]:
            cv.create_text(260, CELL_H / 2, text="点下面的简谱键盘或指法表开始编谱",
                           font=_font(12), fill="#888")
        self._refresh_info()
        # 新加的音跑到可见区外面了就自动跳过去（谱面是一条长横带，只横向滚）
        if self._scroll_to_doc is not None:
            target, self._scroll_to_doc = self._scroll_to_doc, None
            self._scroll_to_doc_cell(target)

    def _refresh_info(self):
        if self._need_sel_silent():
            doc = self.proj["notes"][self.sel]
            result = pj.to_result(doc, 0, self.key_var.get(), self.whistle_var.get())
            holes = "".join({1: "●", 0: "○", 2: "◐"}[s] for s in (result.holes or ()))
            extra = "自选指法" if doc.get("holes") else "自动指法"
            beats = f"{self.sel + 1}/{len(self.proj['notes'])}"
            lyric = pj.lyric_of(doc)
            self.info_lbl.config(
                text=f"第{beats}个：{pj.token_of(doc)}　"
                     f"{jianpu.duration_name(doc.get('duration', 1.0))}　{holes} "
                     f"{result.note_name or ''}（{extra}）"
                     + (f"　词：{lyric}" if lyric else ""))
            self.mark_lbl.config(text=f"选中音记号：{self._mark_text(doc)}")
        else:
            self.info_lbl.config(text=f"未选中（共 {len(self.proj['notes'])} 个）")
            self.mark_lbl.config(text="选中音记号：—")

    def _need_sel_silent(self) -> bool:
        return 0 <= self.sel < len(self.proj["notes"])

    def redraw_preview(self):
        cv = self.preview
        cv.delete("all")
        token, _ = self._holes_to_jianpu(self.custom_holes)
        doc = pj.token_to_doc(token) if token != "—" else None
        if doc is None:
            doc = pj.new_note(1, 0, 0)
        doc["holes"] = list(self.custom_holes)
        doc["duration"] = self._mk_note(1)["duration"]
        draw_cell(cv, 4, 4, doc, self.key_var.get(), self.whistle_var.get(),
                  scale=1.4, tags=("preview",), lyric_shift=0)

    def redraw_chart(self):
        """两个八度指法表（单行排列、可横向滚动）：随哨笛调性/全按作N/调号联动"""
        cv = self.chart
        cv.delete("all")
        self._chart_map = []
        whistle = self.whistle_var.get()
        key = self.key_var.get()
        mode = fingering.mode_label(whistle, key) or "无对应口径"
        self.chart_title.config(
            text=f"{whistle} 调哨笛 · 1={key} · {mode} · 两个八度指法：")
        scale = CHART_SCALE
        cell = CELL_W * scale
        step = cell + 5
        tonic = fingering.WHISTLE_TONICS[whistle]
        x = 8
        for idx in range(fingering.MAX_INDEX + 1):
            token, _ = self._abs_to_jianpu(tonic + idx)
            doc = pj.token_to_doc(token) or pj.new_note(1, 0, 0)
            doc["holes"] = list(fingering.fingering_for_index(idx))
            draw_cell(cv, x, 4, doc, key, whistle, scale=scale, show_name=False,
                      tags=("chart",), lyric_shift=0)
            cv.create_text(x + cell / 2, CHART_ROW_H - 6, font=_font(8),
                           text=jianpu.NOTE_NAMES_SHARP[(tonic + idx) % 12]
                                + (" 高" if idx >= 12 else ""),
                           fill=C_ACCENT, tags=("chart",))
            self._chart_map.append((x, x + cell, 0, CHART_ROW_H + 8, idx))
            x += step
            if idx == 11:                      # 八度分隔
                cv.create_line(x - step / 2 - 2, 4, x - step / 2 - 2, CHART_ROW_H - 4,
                               fill="#c8d3da", width=1.4, tags=("chart",))
        cv.configure(scrollregion=(0, 0, x + 8, CHART_ROW_H + 8))

    def on_chart_click(self, event):
        x, y = self.chart.canvasx(event.x), self.chart.canvasy(event.y)
        for x0, x1, y0, y1, idx in self._chart_map:
            if x0 <= x <= x1 and y0 <= y <= y1:
                self.append_from_scale(idx)
                self.status.config(text=f"已加入第 {idx + 1} 格（相对筒音 {idx} 个半音）")
                return

    def on_canvas_click(self, event):
        x = self.score.canvasx(event.x)
        for x0, x1, doc_idx in self._cell_map:
            if x0 <= x <= x1 and doc_idx is not None:
                self.sel = doc_idx
                self._sel_user = True          # 点格子选中的音 → 可作为插入目标
                self.redraw_all()
                return

    def _wheel_scroll(self, event):
        """谱面是一条长横带，所以滚轮默认横向滚；按住 Shift 才纵向滚。"""
        step = -1 if event.delta > 0 else 1
        if event.state & 0x0001:          # Shift
            self.score.yview_scroll(step * 2, "units")
        else:
            self.score.xview_scroll(step * 3, "units")

    # ---------- 试听（合成音色 + 声卡播放） ----------
    # 口径见 tinwhistle/sound.py：音高取「哨笛实际发声」（哨笛调性 + 指法索引），
    # 所以自动移八度过的音听到的是谱面上标注的那个音。音是按采样合成的 wav、
    # 交给系统异步播 —— 所以「停止」是真能立刻停住的（不像 Beep 必须把这个音放完）。
    def _on_listen_toggle(self):
        """开关变了：打开时立刻响一下确认听得见，关掉时把正在响的掐掉。

        挂在 listen_var 的 **write trace** 上（不是 Checkbutton 的 command）：command 只在
        鼠标点下去时才调，`var.set()` 改的值它看不见，于是「关掉再打开」会漏掉那声确认音。
        trace 里先比一下旧值——同一个值被重复写入（工程存取也会写）时不该再响一声。
        """
        on = self.listen_var.get()
        if on == self._listen_on:
            return
        self._listen_on = on
        if on:
            self.listen_selected(force=True)
        else:
            self.beeper.stop()

    def listen_selected(self, force: bool = False) -> None:
        """把**当前选中**的音响一下（试听开关关着就不响；force=True 无视开关）。"""
        if not (force or self.listen_var.get()):
            return
        if not sound.available():
            return
        notes = self.proj["notes"]
        if not (0 <= self.sel < len(notes)):
            return
        doc = notes[self.sel]
        hz = sound.hz_of_doc(doc, self.key_var.get(), self.whistle_var.get())
        if hz is None:                            # 休止 / 延音 / 小节线：没音高可响
            return
        self._listen_sel = self.sel
        self.beeper.play_hz(hz, sound.preview_ms(doc))

    def _maybe_listen(self):
        """选中音变了就试听一次。挂在 redraw_all 末尾是**刻意**的：

        点格子、按 ←→、追加新音、撤销重做……每一条会改选中位置的路最后都会重画，
        统一在这里看一眼就不用往七八个地方各插一句（漏一处就成「有时不响」）。
        """
        if self.sel == self._listen_sel:
            return
        self.listen_selected()

    def toggle_tune(self):
        """「▶ 试听整首」：正在放就改成停止，否则从头放一遍。"""
        if self.beeper.busy():
            self.stop_audio()
            return
        self.play_tune()

    def play_tune(self):
        """整首试听：按谱面时值依次响（休止静音，延音接着上一个音响）。"""
        if not sound.available():
            messagebox.showinfo("无法试听", "这个平台没有可用的播放接口（winsound 只在 Windows 有）")
            return
        try:
            bpm = float(self.bpm_var.get())
        except (TypeError, ValueError):
            bpm = float(sound.DEFAULT_BPM)
        seq = sound.sequence(self.proj, bpm=max(20.0, min(400.0, bpm)))
        if not any(hz for hz, _ms, _i in seq):
            self.status.config(text="没有可试听的音（先加几个音）")
            return
        self._tune_gen += 1
        gen = self._tune_gen

        def on_step(doc_idx):
            # 回调在**播放线程**里：只负责挪回主线程（tkinter 不是线程安全的）
            self.root.after(0, lambda: self._follow_tune(gen, doc_idx))

        self.beeper.submit(seq, on_step=on_step)
        self.status.config(text=f"正在试听整首…（{len(seq)} 个单元，速度 {bpm:.0f}）")

    def _follow_tune(self, gen: int, doc_idx: int):
        """整首试听时让选中框跟着走（谱面会滚到正在响的那个音上）。"""
        if gen != self._tune_gen or not self.listen_var.get():
            return
        if 0 <= doc_idx < len(self.proj["notes"]):
            self.sel = doc_idx
            self._listen_sel = doc_idx      # 正在响的就是它，别再叠一遍单音试听
            self.redraw_score()
            self._scroll_to_doc_cell(doc_idx)

    def stop_audio(self):
        """停止试听：**立刻**安静。

        掐音是 `beeper.stop()` 在主线程里做的（`PlaySound(None, SND_PURGE)`），不像 Beep
        那样要等当前这个音放完；这里再把跟随回调作废、状态栏写好提示。
        """
        self._tune_gen += 1
        self.beeper.stop()
        self.status.config(text="已停止试听")

    # ---------- 自动保存 ----------
    def _touch(self):
        self._dirty = True
        self.autosave_lbl.config(text="未保存…", foreground="#c0392b")
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(800, self._autosave)

    def _autosave(self):
        self._save_job = None
        try:
            self._sync_project_meta()
            pj.save(self.proj, AUTOSAVE_PATH)
            self._dirty = False
            self.autosave_lbl.config(
                text=f"已自动保存 {time.strftime('%H:%M:%S')}", foreground="#2e7d32")
        except OSError as exc:
            self.autosave_lbl.config(text=f"自动保存失败: {exc}", foreground=C_WARN)

    def _rowmeas_label(self, value) -> str:
        """「一行几个小节」的存储值（0/2~6）→ 下拉框显示值（自动/2~6）"""
        v = render.normalize_row_measures(value)
        return "自动" if not v else str(v)

    def _sync_project_meta(self):
        self.proj["title"] = self.title_var.get().strip() or "未命名"
        self.proj["key"] = self.key_var.get()
        self.proj["whistle"] = self.whistle_var.get()
        self.proj["beats"] = self.beats_var.get()
        self.proj["auto_bars"] = bool(self.autobar_var.get())
        self.proj["paper"] = self.paper_var.get()
        self.proj["watermark"] = self.watermark_var.get()
        self.proj["scale"] = imageout.normalize_scale(self.scale_var.get())
        self.proj["content_scale"] = render.normalize_content_scale(
            self.content_scale_var.get())
        self.proj["row_measures"] = render.normalize_row_measures(self.rowmeas_var.get())

    def _on_output_changed(self):
        """改了纸张/一行几个小节/水印/谱面大小/倍率：同步进工程（会随工程存盘），预览跟着重画。"""
        if self._bulk_set:          # 批量 set 中：见 _meta_changed 里的说明
            return
        try:
            self._sync_project_meta()
        except AttributeError:      # 界面还没建完（构造过程中 trace 触发）
            return
        self._touch()
        if self._page_win is not None:
            self._schedule_page_refresh()

    def _offer_recover(self):
        if not os.path.isfile(AUTOSAVE_PATH):
            return
        try:
            data = pj.load(AUTOSAVE_PATH)
        except (OSError, ValueError):
            return
        if not data.get("notes"):
            return
        when = time.strftime("%m-%d %H:%M", time.localtime(data.get("saved_at", 0)))
        if messagebox.askyesno("恢复工程",
                               f"发现未完成的工程「{data.get('title')}」"
                               f"（{len(data['notes'])} 个音，保存于 {when}）。\n是否恢复？"):
            self._load_project(data, path=None)
            self.status.config(text="已恢复上次未完成的工程")

    def _load_project(self, data: dict, path: str | None):
        self.proj = data
        self.proj["_path"] = path
        # 「输出设置」要先全部读出来再赋给控件：这几个控件都挂了 trace -> _on_output_changed
        # -> _sync_project_meta，一 set 就会把**当前**控件值反写回 self.proj。
        # 边读边写的话，后读的字段会被刚设过的旧控件值盖掉（一行几个小节就是这么丢的）。
        _paper = data.get("paper", render.DEFAULT_PAPER)
        _watermark = data.get("watermark", "")
        _scale = str(imageout.normalize_scale(
            data.get("scale", imageout.DEFAULT_SCALE)))
        _rowmeas = self._rowmeas_label(data.get("row_measures",
                                                render.DEFAULT_ROW_MEASURES))
        _cs = str(round(render.normalize_content_scale(
            data.get("content_scale", render.DEFAULT_CONTENT_SCALE)) * 100))
        # 下面这一串 set 每个都会触发 trace → 重画整张谱面。几千个音时一次重画就要
        # 零点几秒，十几个控件连着 set 就是「打开大工程卡住」的一大半来源，
        # 所以整段屏蔽掉，末尾只重画一次（_bulk_set 见 __init__ 里的说明）。
        self._bulk_set = True
        try:
            self.title_var.set(data.get("title", "未命名"))
            self.key_var.set(data.get("key", "D"))
            self.whistle_var.set(data.get("whistle", "D"))
            self.beats_var.set(data.get("beats", "4/4"))
            self.autobar_var.set(1 if data.get("auto_bars", True) else 0)
            self.paper_var.set(_paper if _paper in PAPER_LIST else render.DEFAULT_PAPER)
            self.watermark_var.set(_watermark)
            self.scale_var.set(_scale)
            self.content_scale_var.set(_cs)
            self.rowmeas_var.set(_rowmeas)
        finally:
            self._bulk_set = False
        self.sel = len(data.get("notes", [])) - 1
        self._sel_user = False
        self._listen_sel = self.sel       # 刚打开就「叮」一下会吓人：当它已经响过了
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._sync_mode_box()
        self.redraw_all()

    # ---------- 耗时操作：工作线程 + 进度条 ----------
    def _run_busy(self, title, work, on_done=None, cancelable=False, on_error=None):
        """把一件可能很慢的活丢到工作线程，主线程弹进度条（见 BusyDialog）。

        work(progress, cancel) 在**工作线程**里跑 —— 里面不许碰 tkinter 控件，
        只管干活并按 progress(done, total, label) 报进度；
        跑完后回到主线程调 on_done(返回值, 是否被取消)。cancelable=True 时弹窗有
        「取消」按钮，work 自己决定在哪个安全点停下（导出图片是逐页的，取消后
        已经跑完的页照样留下）。

        为什么要绕这一圈：tk 是单线程的，干活期间界面必然冻住；几千个音的谱子
        打开/保存/导出图片都要好几秒，不给反馈用户就以为卡死了。
        """
        dlg = BusyDialog(self.root, title, cancelable=cancelable)
        box = {}

        def worker():
            try:
                box["value"] = work(dlg.report, dlg.canceled)
            except BaseException as exc:        # 原样带回主线程，别在线程里弹框
                box["exc"] = exc

        def pump():
            dlg.pump()
            if th.is_alive():
                self.root.after(BUSY_PUMP_MS, pump)
                return
            dlg.close()
            exc = box.get("exc")
            if exc is not None:
                if on_error is not None:
                    on_error(exc)
                else:
                    messagebox.showerror(title, str(exc))
                return
            if on_done is not None:
                on_done(box.get("value"), dlg.canceled())

        th = threading.Thread(target=worker, daemon=True)
        self.root.after(BUSY_PUMP_MS, pump)
        th.start()

    # ---------- 文件 ----------
    def new_project(self):
        if self.proj["notes"] and not messagebox.askyesno("新建", "当前工程未导出，确定新建吗？"):
            return
        self.proj = pj.new_project()
        self.proj["_path"] = None
        self.sel = -1
        self._sel_user = False
        self._listen_sel = -1
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._bulk_set = True
        try:
            self.title_var.set("未命名")
            self.paper_var.set(render.DEFAULT_PAPER)
            self.rowmeas_var.set("自动")
            self.watermark_var.set("")
            self.scale_var.set(str(imageout.DEFAULT_SCALE))
            self.content_scale_var.set(str(round(render.DEFAULT_CONTENT_SCALE * 100)))
        finally:
            self._bulk_set = False
        self._sync_mode_box()
        self.redraw_all()
        self.status.config(text="已新建工程")

    def open_project(self):
        path = filedialog.askopenfilename(title="打开工程",
                                          initialdir=PROJECT_DIR,
                                          filetypes=[("编谱工程", "*.json"), ("所有文件", "*.*")])
        if not path:
            return

        def done(data, canceled):
            self._load_project(data, path=path)
            self.status.config(text=f"已打开 {path}")

        self._run_busy("正在打开工程",
                       lambda progress, cancel: pj.load(path, progress=progress),
                       done,
                       on_error=lambda exc: messagebox.showerror("打开失败", str(exc)))

    def save_project(self):
        default = (self.title_var.get().strip() or "未命名") + ".json"
        path = self.proj.get("_path") or os.path.join(PROJECT_DIR, default)
        path = filedialog.asksaveasfilename(title="保存工程", initialfile=os.path.basename(path),
                                            initialdir=os.path.dirname(path) or PROJECT_DIR,
                                            defaultextension=".json",
                                            filetypes=[("编谱工程", "*.json")])
        if not path:
            return
        self._sync_project_meta()

        def done(_value, canceled):
            self.proj["_path"] = path
            self.status.config(text=f"已保存 {path}")

        self._run_busy("正在保存工程",
                       lambda progress, cancel: pj.save(self.proj, path, progress=progress),
                       done,
                       on_error=lambda exc: messagebox.showerror("保存失败", str(exc)))

    # ---------- 键盘说明 ----------
    def show_key_help(self):
        """弹出键盘快捷键说明。

        原来这段是贴在简谱键盘面板里的常驻文字，排下来占 106px；而窗口总高 1000px、
        谱面区光装下整个格子就要 258px，于是谱面区被挤到只剩 154px，笛身与音名被下边缘裁掉。
        挪进弹窗后谱面区才拿得到完整高度（内容一字未减）。
        """
        win = getattr(self, "_key_win", None)
        if win is not None and win.winfo_exists():
            win.lift()                     # 已经开着就抬到前面，别开一堆同样的窗
            win.focus_set()
            return
        win = tk.Toplevel(self.root)
        self._key_win = win
        win.title("键盘说明")
        win.transient(self.root)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"520x{min(360, sh - 120)}+{max(0, (sw - 520) // 2)}+80")
        frame = ttk.Frame(win, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="键盘说明（鼠标点格子、点孔位同样可以编谱）",
                  font=_font(12, bold=True)).pack(anchor=tk.W)
        body = tk.Text(frame, wrap=tk.WORD, relief=tk.FLAT, background=BG,
                       font=_font(11), height=12, highlightthickness=0)
        body.insert("1.0", KEY_HELP_TEXT)
        body.config(state=tk.DISABLED)
        body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        ttk.Button(frame, text="关闭", command=win.destroy).pack(anchor=tk.E, pady=(8, 0))

    # ---------- 整谱预览 ----------
    def open_page_preview(self):
        """打开「整谱预览」窗口：按导出 SVG 的换行规则把整首曲子铺成整页。

        谱面主区是一条无限长的横带（方便连续编谱），看不到「导出后长什么样」——
        这个窗口补上这一环：行怎么断、小节线落在哪、记号是否互相压住，一眼就能核对。
        窗口里可以缩放/滚动，也可以一键用浏览器打开真实导出 SVG（100% 保真）。
        """
        if not self.proj["notes"]:
            self.status.config(text="还没有音符，先点简谱键盘或指法表加几个音")
            return
        win = getattr(self, "_page_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_set()
            self.refresh_page_preview()
            return

        win = tk.Toplevel(self.root)
        self._page_win = win
        win.title("整谱预览（换行/版式与导出 SVG 一致）")
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{min(1040, sw - 80)}x{min(880, sh - 100)}")
        win.minsize(560, 400)
        win.protocol("WM_DELETE_WINDOW", self._close_page_preview)

        top = ttk.Frame(win, padding=6)
        top.pack(fill=tk.X)
        ttk.Label(top, text="缩放:").pack(side=tk.LEFT)
        self._page_zoom = tk.StringVar(value="60%")
        zoom = ttk.Combobox(top, textvariable=self._page_zoom, width=6, state="readonly",
                            values=[f"{int(v * 100)}%" for v in PREVIEW_ZOOMS])
        zoom.pack(side=tk.LEFT, padx=(2, 8))
        zoom.bind("<<ComboboxSelected>>", lambda e: self.refresh_page_preview())
        ttk.Button(top, text="刷新", command=self.refresh_page_preview).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="在浏览器中打开",
                   command=self.preview_in_browser).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="导出 SVG…", command=self.export_svg).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="导出图片…", command=self.export_png).pack(side=tk.LEFT, padx=2)
        self._page_follow = tk.IntVar(value=1)
        ttk.Checkbutton(top, text="跟随编辑自动刷新",
                        variable=self._page_follow).pack(side=tk.LEFT, padx=8)
        self._page_info = ttk.Label(top, text="", foreground=C_ACCENT)
        self._page_info.pack(side=tk.RIGHT)

        body = ttk.Frame(win)
        body.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self._page_cv = tk.Canvas(body, background="#eef1f4", highlightthickness=0)
        phs = ttk.Scrollbar(body, orient=tk.HORIZONTAL, command=self._page_cv.xview)
        pvs = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self._page_cv.yview)
        self._page_cv.configure(xscrollcommand=phs.set, yscrollcommand=pvs.set)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self._page_cv.grid(row=0, column=0, sticky="nsew")
        pvs.grid(row=0, column=1, sticky="ns")
        phs.grid(row=1, column=0, sticky="ew")
        self._page_cv.bind("<MouseWheel>", lambda e: self._page_cv.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))
        self._page_cv.bind("<Shift-MouseWheel>", lambda e: self._page_cv.xview_scroll(
            -1 if e.delta > 0 else 1, "units"))
        self._draw_page_preview()

    def _close_page_preview(self):
        """关掉预览窗口。没开过也要能安全调用（点 × 关主窗口时会走这里）。"""
        job = getattr(self, "_page_job", None)
        if job:
            try:
                self.root.after_cancel(job)
            except (tk.TclError, ValueError):
                pass
        self._page_job = None
        win = getattr(self, "_page_win", None)
        if win is not None:
            try:
                win.destroy()
            except tk.TclError:
                pass                       # 已经被用户点 × 关掉了
        self._page_win = None

    def refresh_page_preview(self):
        """重画预览窗口（窗口不在就什么都不做）"""
        self._page_job = None          # 排队的自动刷新已落地（或已被手动刷新顶掉）
        win = getattr(self, "_page_win", None)
        if win is None or not win.winfo_exists():
            return
        self._draw_page_preview()

    def _page_scale(self) -> float:
        """当前缩放比例。只在窗口打开时有意义，取值异常时退回 60%。"""
        try:
            pct = int(str(self._page_zoom.get()).rstrip("%"))
        except (AttributeError, ValueError):
            return 0.6
        return max(0.2, min(1.5, pct / 100.0))

    def _draw_page_preview(self):
        """把整谱按导出的版式铺到预览画布上（**一页一页摊开**）。

        铺格/换行/分页全部用 render._build_layout（导出用的那一套：纸张、一行几个小节、
        不从小节中间换行、行不跨页），单格绘制复用编谱器自己的 draw_cell / draw_mark_layer——
        于是预览看到的就是「主谱面区的画法 + 导出的版式」，两边不会各画一套、也不会越改越不像。

        「谱面大小」也照导出的口径来（见下面的 content_scale 段）：默认 65% 时预览里
        同样是 5 行/页、记号同样小一号。编谱器主画布始终是原始尺寸，编辑手感不变。
        """
        cv = self._page_cv
        cv.delete("all")
        self._sync_project_meta()
        shown, _index_map = pj.display_notes(self.proj)
        if not shown:
            cv.configure(scrollregion=(0, 0, 400, 200))
            self._page_info.config(text="空工程")
            return
        score, _results, warnings, key = pj.build_render_inputs(self.proj)
        # 「谱面大小」：预览必须与**导出同一口径** —— 把 render 的缩放临时套上，
        # 于是行高、字号、洞洞图都按导出那样缩，一页该几行就是几行（默认 65% = 5 行）。
        # 编谱器主画布用的是 editor 自己那套常量，不受影响；画完在 finally 里还原。
        _prev_cs = render.CONTENT_SCALE
        _cs = render.set_content_scale(self.content_scale_var.get())
        try:
            render._build_layout(score.events, self.paper_var.get(),   # 导出用的铺格/换行/分页
                                 render.normalize_row_measures(self.rowmeas_var.get()))
            set_lyric_shift(shown)                                     # 与导出口径一致：有歌词就下移笛身
            k = self._page_scale()
            beats = self.proj.get("beats", "4/4")
            whistle = self.whistle_var.get()
            wm = self.watermark_var.get().strip()

            page_w = render.PAGE_WIDTH * k
            pad, gap = PREVIEW_PAD, PREVIEW_PAD + 6
            heights = [render._page_height(p, len(render.page_rows(p)), len(warnings)) * k
                       for p in range(render.N_PAGES)]
            total_h = pad + sum(h + gap for h in heights)
            ox = pad - render.MARGIN * k            # 减掉页边距，后续直接用导出坐标 × k

            try:
                mode = fingering.mode_label(whistle, key)
            except KeyError:
                mode = ""
            title = self.title_var.get() or "未命名"
            rows_by_page = {p: render.page_rows(p) for p in range(render.N_PAGES)}

            y = pad
            for p, page_h in enumerate(heights):
                cv.create_rectangle(pad, y, pad + page_w, y + page_h,
                                    fill="#ffffff", outline="#c2cad2")
                oy = y
                if p == 0:
                    cv.create_text(ox + page_w / 2, oy + 46 * k, text=title,
                                   font=_font(max(8, 30 * k), True), fill=C_ACCENT,
                                   anchor="center")
                    cv.create_text(ox + page_w / 2, oy + 76 * k,
                                   text=f"1 = {key}（筒音指法：{mode}）　·　拍号 {beats}　·　"
                                        f"哨笛 {whistle} 调　·　共 {len(self.proj['notes'])} 音"
                                        f"　·　{render.CURRENT_PAPER} 竖版"
                                        + (f"　·　共 {render.N_PAGES} 页" if render.N_PAGES > 1
                                           else ""),
                                   font=_font(max(6, 15 * k)), fill=C_TEXT, anchor="center")
                    cv.create_line(ox + render.MARGIN * k, oy + 146 * k,
                                   ox + (render.PAGE_WIDTH - render.MARGIN) * k, oy + 146 * k,
                                   fill=C_ACCENT)
                else:
                    cv.create_text(ox + render.MARGIN * k, oy + 42 * k, text=title,
                                   font=_font(max(8, 20 * k), True), fill=C_ACCENT,
                                   anchor="w")
                    cv.create_text(ox + render.MARGIN * k, oy + 68 * k,
                                   text=f"1 = {key}　·　哨笛 {whistle} 调　·　拍号 {beats}"
                                        f"　·　第 {p + 1} / {render.N_PAGES} 页",
                                   font=_font(max(6, 13 * k)), fill=C_TEXT, anchor="w")
                    cv.create_line(ox + render.MARGIN * k, oy + 80 * k,
                                   ox + (render.PAGE_WIDTH - render.MARGIN) * k, oy + 80 * k,
                                   fill=C_ACCENT)
                if wm:                              # 淡淡的水印：预览里也照着画（转不了就画正的）
                    try:
                        cv.create_text(ox + page_w / 2, oy + page_h * 0.5, text=wm,
                                       font=_font(max(9, render.PAGE_WIDTH * 0.16 * k), True),
                                       fill="#c3c8cc", angle=-24)
                    except tk.TclError:
                        pass

                for r in rows_by_page[p]:
                    idxs = render.ROW_PLAN[r]
                    y0 = oy + render._ROW_TOP[r] * k     # 行顶是**页内**坐标
                    # 单格内容 = 预览缩放 × 谱面大小。这里是**唯一**与导出不同的地方：
                    # draw_cell 的格子宽也要乘 scale，而列距（槽位宽）只按预览缩放变，
                    # 所以左缘右移半个差量，让缩小的内容仍落在槽位中线上（否则整列偏左）。
                    s = k * _cs
                    cells = [(ox + render._LAYOUT[i][0] * k
                              + render._LAYOUT[i][1] * (k - s) / 2, render._LAYOUT[i][1])
                             for i in idxs]
                    for j, i in enumerate(idxs):
                        draw_cell(cv, cells[j][0], y0, shown[i], key, whistle,
                                  scale=s, w=render._LAYOUT[i][1], own_beams=False)
                    # 分组用整谱 docs + 本行起点：连尾/连音口径与导出 SVG 完全一致
                    draw_mark_layer(cv, [shown[i] for i in idxs], cells, y0, beats=beats,
                                    scale=s, group_docs=shown, group_offset=idxs[0])
                    # 整段括号 / 结尾框：同样拿整谱配对（跨行的框才配得上），
                    # 本行只画属于本行的那一段（口径与 render._ending_layer 一致）
                    draw_frame_layer(cv, [shown[i] for i in idxs], cells, y0, scale=s,
                                     group_docs=shown, group_offset=idxs[0])
                cv.create_text(ox + (render.PAGE_WIDTH - render.MARGIN) * k, oy + page_h - 12 * k,
                               text=f"第 {p + 1} / {render.N_PAGES} 页",
                               font=_font(max(6, 11 * k)), fill="#8b949c", anchor="e")
                y += page_h + gap

            cv.configure(scrollregion=(0, 0, page_w + 2 * pad, total_h))
            # 信息栏：纸型 / 页数 / 行数 / 每行几个小节（排版规则一眼可见，出问题好定位）
            _mi = {}
            for _m_no, _m in enumerate(render.MEASURES):
                for _i in _m:
                    _mi[_i] = _m_no
            _mrow = [len({_mi[i] for i in r}) for r in render.ROW_PLAN]
            warn = f"　⚠ {len(warnings)} 处音域问题" if warnings else ""
            # 「一行几个小节」：自动档常是 4~6 的区间，固定档多半每行一样多，写成单个数更好读
            if _mrow and min(_mrow) == max(_mrow):
                _rowtxt = f"　一行 {_mrow[0]} 小节"
            elif _mrow:
                _rowtxt = f"　一行 {min(_mrow)}~{max(_mrow)} 小节"
            else:
                _rowtxt = ""
            self._page_info.config(
                text=f"{render.CURRENT_PAPER} 竖版　{render.N_PAGES} 页　"
                     f"{sum(len(render.page_rows(p)) for p in range(render.N_PAGES))} 行"
                     f"　谱面 {round(_cs * 100)}%"
                     f"　{len(shown)} 格{warn}{_rowtxt}")
        finally:
            render.set_content_scale(_prev_cs)

    def preview_in_browser(self):
        """把当前工程导出成临时 SVG 并交给浏览器——想看 100% 保真效果时用"""
        if not self.proj["notes"]:
            self.status.config(text="还没有音符可预览")
            return
        self._sync_project_meta()
        try:
            path = pj.export_svg(self.proj, tempfile.mkdtemp(prefix="tinwhistle_"),
                                 paper=self.paper_var.get(),
                                 watermark=self.watermark_var.get(),
                                 row_measures=render.normalize_row_measures(
                                     self.rowmeas_var.get()))
        except (OSError, ValueError) as exc:
            messagebox.showerror("预览失败", str(exc))
            return
        try:
            os.startfile(path)                     # Windows 用默认程序（浏览器）打开
        except OSError:
            self.status.config(text=f"已生成 {path}（未能自动打开，请手动打开）")
            return
        self.status.config(text=f"已在浏览器打开预览：{path}")

    def export_svg(self):
        if not self.proj["notes"]:
            messagebox.showinfo("提示", "还没有音符可导出")
            return
        self._sync_project_meta()
        out_dir = filedialog.askdirectory(title="选择导出目录", initialdir=OUTPUT_DIR)
        if not out_dir:
            return
        kw = dict(paper=self.paper_var.get(),
                  watermark=self.watermark_var.get(),
                  row_measures=render.normalize_row_measures(self.rowmeas_var.get()))

        def done(paths, canceled):
            pj.save(self.proj, AUTOSAVE_PATH)
            more = f"（共 {len(paths)} 页，已逐页输出）" if len(paths) > 1 else ""
            self.status.config(text=f"已导出 {len(paths)} 个文件到 {out_dir}")
            listing = "\n".join(os.path.basename(p) for p in paths[:8])
            if len(paths) > 8:
                listing += f"\n…（共 {len(paths)} 个）"
            if messagebox.askyesno("导出成功",
                                   f"已生成 {len(paths)} 个 SVG{more}：\n{listing}\n\n"
                                   f"是否打开所在文件夹？"):
                try:
                    os.startfile(out_dir)
                except OSError:
                    pass

        self._run_busy("正在导出 SVG",
                       lambda progress, cancel: pj.export_svg_pages(
                           self.proj, out_dir, progress=progress, **kw),
                       done,
                       on_error=lambda exc: messagebox.showerror("导出失败", str(exc)))

    def export_png(self):
        """导出 PNG 图片：按当前纸张分页、逐页一个文件，倍率可选 1x ~ 5x。"""
        if not self.proj["notes"]:
            messagebox.showinfo("提示", "还没有音符可导出")
            return
        self._sync_project_meta()
        if not imageout.find_browser():
            messagebox.showwarning(
                "无法导出图片",
                "没有找到 Edge 或 Chrome，无法把谱面转成图片。\n"
                "可以先用「导出 SVG」，再用浏览器打开并另存为图片。")
            return
        out_dir = filedialog.askdirectory(title="选择图片导出目录", initialdir=OUTPUT_DIR)
        if not out_dir:
            return
        scale = imageout.normalize_scale(self.scale_var.get())

        def done(paths, canceled):
            pj.save(self.proj, AUTOSAVE_PATH)
            if canceled:
                self.status.config(
                    text=f"已取消导出（已完成 {len(paths)} 张，在 {out_dir}）")
            else:
                self.status.config(
                    text=f"已导出 {len(paths)} 张图片（{scale}x）到 {out_dir}")
            if not paths:
                return
            listing = "\n".join(os.path.basename(p) for p in paths[:8])
            if len(paths) > 8:
                listing += f"\n…（共 {len(paths)} 张）"
            if messagebox.askyesno("已取消导出" if canceled else "导出成功",
                                   f"已生成 {len(paths)} 张 PNG（{scale}x）：\n{listing}\n\n"
                                   f"是否打开所在文件夹？"):
                try:
                    os.startfile(out_dir)
                except OSError:
                    pass

        # 逐页栅格化是最慢的一步（每页要起一次无头浏览器），所以给「取消」：
        # 点了之后不再开新的页，已经跑完的页照常留在目录里。
        self._run_busy(f"正在导出 {scale}x 图片",
                       lambda progress, cancel: pj.export_png(
                           self.proj, out_dir, paper=self.paper_var.get(),
                           watermark=self.watermark_var.get(), scale=scale,
                           row_measures=render.normalize_row_measures(
                               self.rowmeas_var.get()),
                           progress=progress, cancel=cancel),
                       done, cancelable=True,
                       on_error=lambda exc: (
                           messagebox.showerror("导出图片失败", str(exc)),
                           self.status.config(text="导出图片失败")))

    def on_close(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self.beeper.close()                # 收掉播放线程（别让它响到进程退出之后）
        sound.cleanup_tones()              # 顺手删掉临时音色目录（atexit 也兜一层）
        self._close_page_preview()
        try:
            self._sync_project_meta()
            pj.save(self.proj, AUTOSAVE_PATH)   # 关窗前强制落盘，未完成工程不丢
        except OSError:
            pass
        self.root.destroy()


def run_editor():
    root = tk.Tk()
    EditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    run_editor()
