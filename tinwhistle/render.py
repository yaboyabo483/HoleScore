"""SVG 洞洞谱渲染器（零依赖，直接生成 SVG 字符串）
# SPDX-FileCopyrightText: 2026 yaboyabo483
# SPDX-License-Identifier: CC-BY-NC-SA-4.0

谱面样式仿常见哨笛洞洞谱：
  - 竖直笛身，6 个圆孔从上到下对应持笛时从上到下的孔 1-6；
  - ● 按住   ○ 放开   ◐ 半孔；
  - 每个笛身正上方是对应的简谱记号（含高低八度点、升降号、时值减时线、附点、换气 v），
    超音域警示单元同样保证记号在正上方；
  - 减时线按简谱规范连尾：同一拍内相邻八分/十六分共用一条连续横线，
    **短休止符也参与连尾**（减时线标记的是「这一拍是几分音符」），
    十六分的第二条线只落在十六分音符下方（由 beaming.beam_segments 统一计算）；
  - 连音线：同音相连=延音线（棕色）、不同音=圆滑线（绿色），画成数字上方的弧线；
  - 切音：**自己占一个小小的窄格子**（列宽 × CUT_CELL_RATIO），紧跟在后一个音前面——
    窄格里是「小数字（被切音的音高）+ 右上角小斜杠」，下面配一张缩小版指法图，
    孔心与小数字同一条竖线；主音仍占满格（布局由 _build_layout 按宽度铺格）；
  - 反复记号（循环符号）：|: 反复开始、:| 反复结束、:|: 收尾并起下一段，
    自占一格、不占时值；
  - 整段括号：成对圆括号把一段音括起来（前奏 / 间奏 / 和声伴唱），
    两侧分别画在起点格的左缘与终点格的右缘、高度与简谱数字齐平，
    跨行时两侧各自画在自己那一行（不会整条消失）；
  - 「第 n 结尾」框（房子记号，配合反复）：手工指定起止（`[1` 起、`1]` 止），
    画成「横线 + 左端向下的短钩 + 标号 1.」，位置在**这一行所有记号之上**
    （比最深的连音弧线还高，见 ENDING_LIFT）；有结尾框的谱行高与页眉带都会
    多留一段头顶空间（见 row_height / header_h），所以不会压到上一行音名或图例；
  - 歌词画在「数字」与「笛身」之间，支持**多行（多段）**：整谱按最多的那几行统一让位，
    第 1 行最靠上；行数一多，笛身/音名整体下移，**行高把这段让位量整段加回去**
    （见 row_height），所以既不会压到下一行、也不会把行间空白吃光；
  - 下方标注绝对音名；第二八度（超吹）在笛顶加 ▲ 标记；
  - 延音线“-”不画新笛身，休止“0”只占位；
  - 超出音域的音以红色警示框标出（保证“看得见的准确”）。

**行间空白是硬需求**：连音弧线画在数字上方、会高出行顶（普通约 29px），
这段高度只能由上一行下方留出的 ROW_GAP 提供（见 row_height 的说明）。
"""

from __future__ import annotations

import contextlib
import html as _html
import math

from . import beaming, fingering
from .jianpu import duration_beams as _duration_beams, is_dotted as _is_dotted
from .jianpu import FRAME_KINDS, pair_frames as _frame_pairs

# ---- 布局常量（像素） ----
# 页面按**真实纸张**来（竖版）：宽度保证是 A4 / B4 / A3，可直接打印。
PAPERS = {                      # 竖版纸张：宽 × 高（毫米）
    "A4": (210, 297),
    "B4": (250, 353),
    "A3": (297, 420),
}
DEFAULT_PAPER = "A4"
MM_PX = 96.0 / 25.4             # 1mm = 3.7795px（浏览器默认 96dpi）
PAGE_WIDTH = round(PAPERS[DEFAULT_PAPER][0] * MM_PX)       # 794（A4 竖版宽）
PAGE_HEIGHT = round(PAPERS[DEFAULT_PAPER][1] * MM_PX)      # 1123（A4 竖版高）
MARGIN = 40
CELL_W = 58           # 每个事件占的**最大**列宽；一行里的实际列距会自适应压缩（见 _plan_rows）
ROW_NOTES_MAX = (PAGE_WIDTH - 2 * MARGIN) // CELL_W   # 一行最多放几个「满格」（切音占窄格）
ROW_H = 214           # 行内内容的基准高度（数字 + 洞洞图 + 音名实际占用约 190，余下是行内空白）
ROW_GAP = 40          # **行与行之间**的净空白。连音弧线画在数字上方、会高出行顶（约 29px，
                      # 嵌套每层 +9px，带换气 +18px），这段高度只能由上一行的行间空白提供，
                      # 所以这个值不能省 —— 省了下一行的弧线就压到上一行最下面的音名上。
                      # A4 竖版：(1123 - 首页页眉 182 - 页脚 30) // 214 = 4 行/页
HEADER_H = 182        # 首页标题区高度（顶部留出连音弧线 + 换气记号的空间）
COMPACT_HEADER_H = 96  # 第二页起的页眉高度（只写曲名/调号/页码，省下的空间多放一行）
FOOTER_H = 30         # 页脚带（页码等）；有警示时还会往下长
FOOTER_PER_WARN = 22
ROW_MEASURES_MAX = 6  # **自动**模式下一行最多排几个小节（实际每行几个见 _row_counts）
# 「一行几个小节」也可以由用户指定固定档：2~6。0 = 自动（按 ROW_MEASURES_MAX 均分）。
ROW_MEASURES_CHOICES = (2, 3, 4, 5, 6)
ROW_MEASURES_AUTO = 0
DEFAULT_ROW_MEASURES = ROW_MEASURES_AUTO
# 列距下限：笛身宽就是 FLUTE_W(=COL_W=24)，再窄笛身图就要叠在一起了，所以留 2px 缝。
# 这个下限决定了「一行 4 小节」能扛多密的谱：4 小节 × 每小节 X 列 × 26 ≤ 页宽-2*边距，
# A4 竖版（714px 可用）算下来是每小节 ≲6 列（如 4/4 里 6 个八分）。
PITCH_MIN = 26
WATERMARK_OPACITY = 0.10   # 水印浓度：刻意做得很淡（灰白底上几乎看不出），任何颜色打印都不影响阅读
C_WATERMARK = "#5b6770"


CURRENT_PAPER = DEFAULT_PAPER    # 当前生效纸型名（set_paper 会更新）
CURRENT_ROW_MEASURES = DEFAULT_ROW_MEASURES   # 当前生效的「一行几个小节」（set_row_measures 会更新）


# ---- 「谱面大小」：导出用的整谱缩放 ----
# 数字字号、洞洞图、各种记号偏移、行高与行距……按**同一个比例**缩放，纸张尺寸不变。
#
# 为什么默认 65%：A4 竖版一行行高 = (ROW_H 214 + ROW_GAP 40) × 比例（有歌词再加
# LYRIC_DY×比例），首页可用高度 = 1123 - 页眉 182 - 页脚 30 = 911px。
#   * 100%：254px/行 → 首页 3 行（下面空掉小半页）
#   * 70% ：178px/行（带一行歌词 193px）→ 5 行 / **带歌词只排 4 行**
#   * 65% ：165px/行（带一行歌词 179px）→ 5 行 / **带歌词也是 5 行**  ← 选它
# 65% 的数字字号 16.9px，正好和编谱器画布上的数字一样大，看着熟悉也不费眼。
#
# **水平布局常量不参与缩放**，这是有意的：「一行几个小节」「列距自适应铺满页宽」
# 这两条规则完全不变，缩小的只是画出来的记号本身和行的高度 —— 于是行变矮、
# 一页能多排两行。要是连 CELL_W / PITCH_MIN 一起缩，一行的列距下限也跟着降，
# 密集谱会突然从小节数变多（谱面密度被悄悄改了，不是这次要的效果）。
# 同理 PAGE_WIDTH/HEIGHT、MARGIN、页眉页脚带（HEADER_H / COMPACT_HEADER_H /
# FOOTER_H）和标题/图例的字号都保持原样 —— 它们是「页面家具」，不随谱面缩。
#
# 编辑器画布**不受影响**：画布用的是 editor.CELL_H / LABEL_CY 那一套常量。
CONTENT_SCALE_MIN = 0.5          # 再小字就看不清了
CONTENT_SCALE_MAX = 1.0
DEFAULT_CONTENT_SCALE = 0.65     # 导出默认；A4 首页 5 行（带一行歌词也是 5 行）
CONTENT_SCALE = 1.0              # 模块当前值。默认 1.0（= 原尺寸），
                                 # 真正的导出走 DEFAULT_CONTENT_SCALE（由 project / editor 传入）



def normalize_row_measures(value) -> int:
    """把「一行几个小节」的输入归一成 0（自动）或 2~6。

    界面给的是「自动 / 2 / 3 / 4 / 5 / 6」，CLI 与工程里是 0/2..6，还可能混进字符串，
    所以统一在这里收口；超出范围的往 2~6 里夹。
    """
    if isinstance(value, str):
        s = value.strip().rstrip("个").replace("小节", "").strip()
        if s.lower() in ("", "自动", "auto", "-", "0"):
            return ROW_MEASURES_AUTO
        try:
            value = int(float(s))
        except ValueError:
            return ROW_MEASURES_AUTO
    try:
        v = int(value)
    except (TypeError, ValueError):
        return ROW_MEASURES_AUTO
    if v <= 0:
        return ROW_MEASURES_AUTO
    return min(max(v, min(ROW_MEASURES_CHOICES)), max(ROW_MEASURES_CHOICES))


def set_row_measures(value) -> int:
    """设定「一行几个小节」（0=自动、2~6=固定上限），返回实际生效值。"""
    global CURRENT_ROW_MEASURES
    CURRENT_ROW_MEASURES = normalize_row_measures(value)
    return CURRENT_ROW_MEASURES


def row_measures_label(value=None) -> str:
    """给界面/摘要看的文字：自动 或 「4 小节」"""
    v = CURRENT_ROW_MEASURES if value is None else normalize_row_measures(value)
    return "自动" if not v else f"{v} 小节/行"


def set_paper(name: str) -> str:
    """切换纸张（A4 / B4 / A3，竖版）：更新 PAGE_WIDTH / PAGE_HEIGHT，返回实际生效的纸型。"""
    global PAGE_WIDTH, PAGE_HEIGHT, CURRENT_PAPER
    key = name if name in PAPERS else DEFAULT_PAPER
    w_mm, h_mm = PAPERS[key]
    PAGE_WIDTH = round(w_mm * MM_PX)
    PAGE_HEIGHT = round(h_mm * MM_PX)
    CURRENT_PAPER = key
    return key


def paper_mm(name: str = "") -> tuple:
    """纸张的毫米尺寸 (宽, 高)；未知纸型退回默认。"""
    return PAPERS.get(name or DEFAULT_PAPER, PAPERS[DEFAULT_PAPER])

# 列宽对齐：数字可视宽度 = 时值横线宽度 = 笛身宽度，三者严格一致，孔心与数字中心同一竖线
COL_W = 24
FLUTE_W = COL_W
FLUTE_H = 104
HOLE_R = COL_W * 0.31      # 孔径小于列宽，全部落在数字正下方
HOLE_DY = 15.5             # 孔间距

LABEL_DY = 16         # 简谱记号区距行顶的偏移（上方留给高八度点）
LABEL_BASE_GAP = 9    # 主数字**基线**相对「记号区顶」的下移量（LABEL_BASE_DY - LABEL_DY）
LABEL_BASE_DY = LABEL_DY + LABEL_BASE_GAP   # 主数字的**基线**距行顶（SVG 的 text y 是基线）
FLUTE_TOP_DY = 64     # 笛身顶距行顶的偏移（上方留给记号+时值线+低八度点）

# 数字的字形高度 —— 小节线 / 反复记号按它对齐（原来一路拉到笛身那么长）。
# 26px 粗体数字的 cap height ≈ 0.72em ≈ 19px；数字没有降部，所以字形底端就是基线。
NOTE_SIZE = 26        # 主数字字号（音符与休止「0」共用）
NOTE_ASCENT = 19      # 数字字形高度（cap height）
DIGIT_TOP_DY = LABEL_BASE_DY - NOTE_ASCENT   # 数字字形顶端距行顶
DIGIT_BOT_DY = LABEL_BASE_DY                 # 数字字形底端距行顶（就是基线）
REPEAT_DOT_R = 2.6    # 反复点半径
REPEAT_DOT_DY = 5.0   # 两粒反复点相对竖向中心的偏移（与画布侧同口径）

# 延音横线「-」：长度**固定**、水平居中在本格中心、竖向对准数字墨迹中心。
#
# 长度固定是关键：旧口径画的是「格宽 - 12」，而导出里每行的列距是**自适应压缩**的
# （见 _plan_rows，从 CELL_W=58 一路压到 PITCH_MIN=26），于是同一份谱里延音横线会长短
# 不一（一行塞得越满、横线越短），而编谱器画布上的格子是定宽 60、横线恒定 48 ——
# 画布与导出对不上。现在两侧各钉一个常量（render.HOLD_W ↔ editor.HOLD_W）。
#
# 取 18：100% 下 26px 粗体数字的**步进宽 15 / 墨迹宽 13**（实测），横线比数字略宽才
# 读得出是「一道延音」；行压到最紧（PITCH_MIN=26）时相邻两笔之间仍留 8px 缝，不会连成
# 一条长线。它参与「谱面大小」缩放（跟数字一起缩），但不影响分行——HOLD_W < PITCH_MIN。
HOLD_W = 18
HOLD_DY = DIGIT_TOP_DY + NOTE_ASCENT / 2   # 派生：数字墨迹竖向中心（见 _recompute_derived）

UNDERLINE_W = COL_W   # 单音符减时线宽度（同数字宽度）；成组时由首末音中心连线贯穿
UNDERLINE_DY = 6      # 两条减时线的间距
BEAM_DY = 16          # 第一条减时线相对数字中心的距离

SLUR_GAP = 7          # 连音弧线底端相对“记号区顶端”的抬高
SLUR_H = 12           # 连音弧线拱高
SLUR_NEST = 9         # 嵌套连音线的层高

# 歌词（可选）：一个汉字或英文单词，画在「简谱数字」和「洞洞」之间——
# 也就是减时线 / 低八度点之下、笛身之上。这一带本来只留了十几 px，
# 所以一旦有任何一个音带歌词，就把笛身和音名整体下移 LYRIC_DY 让出一条歌词带
# （没有歌词时让位量为 0，谱面完全不变）。
#
# 多行（多段）歌词：一个音可以有多行词，行距 LYRIC_LINE_H。整谱按**最多那几行**统一让位，
# 于是各段词对齐在同一条竖线上，第 1 行永远在最上面（贴数字那侧）；
# 某格只有第一行词时，它就单独占最上面那条基线，不与第二段串行。
# 行数一多，笛身/音名整体往下走，**行高要把这整段让位量加回去**（见 row_height），
# 否则洞洞图会把行与行之间的空白吃光，下一行的连音弧线就压到本行音名上。
LYRIC_DY = 22         # 单行歌词时笛身/音名的整体下移量
LYRIC_SIZE = 13       # 歌词字号
LYRIC_LINE_H = 16     # 歌词行距：每多一行，让位量与每行高度各长这么多
LYRIC_ASCENT = 13     # 歌词字面上沿距基线的高度（按 13px 全角字估，宁大勿小）
C_LYRIC = "#303030"

# 超吹三角标记：画在**洞洞图下、音名上方**那条空带里。
#
# 为什么不在「笛身顶上方」（老口径）：那一带正是歌词带的中心，于是本格一带歌词就得把三角
# 搬到歌词上方再缩小 —— 剩下 8px 高，还夹在减时线/低八度点与歌词之间，缩到 65% 导出后
# 基本看不见（用户反馈「输出谱面里没有超吹记号」）。挪到笛身**下面**之后：
#   * 那一带本来就是空的（往下只有一行音名），不必再让位，歌词侧也不要有任何特殊处理；
#   * 三角能画大一号（12 高 × 14 宽），紧贴自己那支洞洞图的尾端，一眼能对上；
#   * 一列读下来是「简谱数字 → 洞洞图 → ▲ → 音名」，正好说明「这张指法要超吹」。
# 代价是音名整体下移 NAME_DY_FROM_FLUTE - 20 = 10px；行内本来就有余量
# （ROW_H 214，内容约 190），所以**行高与分页都不变**（A4 首页 5 行照旧）。
OCT_MARK_H = 11              # 三角高
OCT_MARK_W = 13              # 三角底边宽
OCT_MARK_GAP = 2             # 三角顶与笛身尾端（洞洞图下沿）的间隙
# 音名基线相对笛身尾端的下移量 —— 中间那条空带留给超吹三角。
# 32 是「往下不越界」的上限附近：笛身尾端 + 32 + 汉字的降部 ≈ 206，仍在 ROW_H 214 之内，
# 所以**行高与分页都不变**（A4 首页 5 行照旧）。同时要保证三角底边（2+11=13）
# 与「音名里汉字的上沿」（32 − 汉字 ascent ≈ 12 → 20）之间留出 7px 净空（65% 下仍有 4.5px）。
NAME_DY_FROM_FLUTE = 32

# 换气记号（数字上方一个小 v）。它站在「数字正上方」那条带里，
# 所以本格带换气时连音弧线要再往上让 BREATH_LIFT（见 _label_top）。
BREATH_SIZE = 11
BREATH_LIFT = 18
BREATH_DY = 22           # v 的基线相对「记号区」(row_top + LABEL_DY) 往上抬多少

# 切音：**自己占一个小小的窄格子**，紧跟在后一个音前面（谱面布局参考常见洞洞谱）：
# 窄格里放「小数字 + 小斜杠」和一张缩小的指法图，主音仍占满格。
CUT_CELL_RATIO = 0.62   # 切音格子宽度 / 正常格子宽度
# 小节线与反复记号也**不占满格**：小节线只是根细竖线，给它整格宽度会让一行少排一个小节。
# 反复记号里有细线+粗线+两粒反复点（横向约 20px），所以留得多一些。
BAR_CELL_RATIO = 0.42      # 小节线格子宽度 / 正常格子宽度
REPEAT_CELL_RATIO = 0.75   # 反复记号格子宽度 / 正常格子宽度
CUT_SIZE = 17           # 切音小数字字号（主数字 26）
CUT_LIFT = 6            # 切音小格整体上提（小数字与小指法图一起抬高，像装饰音）
CUT_SLASH = 9           # 小斜杠长度（小数字右上角，向右上划出）
CUT_ACC_DX = 9          # 小升降号相对小数字中心的横向偏移（左侧）
C_CUT = "#8e2f0f"

# 切音格子里的小指法图（与主指法图同形，按 MINI_S 缩小）
MINI_S = 0.60           # 小指法图相对正常指法图的整体比例
MINI_W = FLUTE_W * MINI_S
MINI_H = FLUTE_H * MINI_S
MINI_HOLE_R = HOLE_R * MINI_S
MINI_HOLE_DY = HOLE_DY * MINI_S
MINI_TOP_DY = FLUTE_TOP_DY - CUT_LIFT    # 小指法图顶端距行顶（跟着小格一起抬高）
# 切音小格里的超吹三角跟着小图缩一号（小图 0.60 倍，三角取 0.75 —— 再小就看不清了）
MINI_OCT_SCALE = 0.75

# 旧名保留（早期版本叫「短音」，今统一称「切音」，外部/历史引用仍可用）
SHORT_COLOR = C_CUT
SHORT_LEN = CUT_SLASH

# ---- 整段括号（前奏/间奏/和声伴唱）与「第 n 结尾」框（房子记号）----
# 两者都是**框类记号**：不占时值、不是小节边界，只在谱面上画出来（见 jianpu.FRAME_KINDS）。
BRACKET_CELL_RATIO = 0.30   # 括号记号格宽 / 正常格宽（括号要一点横向位置，但别占满格）
BRACKET_BULGE = 7           # 括号向外鼓出的深度（弧的矢高）
BRACKET_UP = 3              # 括号上端比数字字形顶再高一点
BRACKET_DOWN = 10           # 括号下端比数字基线再低一点（要盖住低八度点）

ENDING_CELL_RATIO = 0.18    # 结尾记号格宽 / 正常格宽（很窄，只为让它有一格能被点中）
ENDING_TEXT_SIZE = 13       # 标号「1.」的字号
ENDING_TICK = 11            # 框子左端向下的短钩长度
ENDING_INSET = 6            # 标号距框子左端的内缩
ENDING_GAP = 6              # 框子横线到**下方最上层笔画**的净空
ENDING_MARGIN = 6           # 预留头顶空间时多给的余量（别卡到 0）
# 结尾框画在这一行所有记号之上，位置由「这一段里最靠上的记号」算出来（见 ending_top_offset），
# 所以头顶要多留多少也是**算出来的**（见 ending_top_need / _ENDING_SHIFT），不靠拍脑袋。
# 页眉带要额外留多少，取决于页眉自己画到哪 —— 这两个是页眉的「墨迹下沿」，
# 跟 _header_svg / _legend_svg 里的坐标绑在一起（改页眉记得一起改）。
HEADER_INK_BOTTOM = 135         # 首页标题区：第二行图例文字在 y=127（13px），下沿约 131
COMPACT_HEADER_INK_BOTTOM = 80  # 第 2 页起：那条横线就在 y=80


# ---- 「谱面大小」的实现 ----
# 参与缩放的常量（基准值 = 100%）。**派生量不进这张表**，由 _recompute_derived 重算，
# 这样 LABEL_BASE_DY == LABEL_DY + LABEL_BASE_GAP 这类恒等式在任何比例下都精确成立
# （各乘一次的话会因为四舍五入差个零头，测试里那种「常量自洽」断言就会闪断）。
_SCALED_NAMES = (
    # 洞洞图本体
    "COL_W", "FLUTE_H", "HOLE_DY",
    # 记号区与笛身的纵向位置
    "LABEL_DY", "LABEL_BASE_GAP", "FLUTE_TOP_DY",
    # 数字 / 反复记号 / 延音横线
    "NOTE_SIZE", "NOTE_ASCENT", "REPEAT_DOT_R", "REPEAT_DOT_DY", "HOLD_W",
    # 减时线与连音线
    "UNDERLINE_DY", "BEAM_DY", "SLUR_GAP", "SLUR_H", "SLUR_NEST",
    # 歌词带
    "LYRIC_DY", "LYRIC_SIZE", "LYRIC_LINE_H", "LYRIC_ASCENT",
    # 超吹三角与换气记号
    "OCT_MARK_H", "OCT_MARK_W", "OCT_MARK_GAP", "NAME_DY_FROM_FLUTE",
    "BREATH_SIZE", "BREATH_LIFT", "BREATH_DY",
    # 切音小格
    "CUT_SIZE", "CUT_LIFT", "CUT_SLASH", "CUT_ACC_DX",
    # 整段括号与结尾框
    "BRACKET_BULGE", "BRACKET_UP", "BRACKET_DOWN",
    "ENDING_TEXT_SIZE", "ENDING_TICK", "ENDING_INSET", "ENDING_GAP", "ENDING_MARGIN",
    # 行高与行间空白（这两个一缩，一页就能多排行）
    "ROW_H", "ROW_GAP",
)


def _s(v: float) -> float:
    """按「谱面大小」缩放一个**写在绘制代码里的零散几何量**（基准值 = 100%）。

    命名常量由 set_content_scale 改写全局，不用在这里管；剩下的那些点距、半径、
    字号只在一处用了一下、也没必要各起一个名字，就地乘一次即可。少了这一步，
    缩小以后它们会不成比例 —— 最典型的是高八度点：数字缩到 70% 以后，点还按
    原来的 20px 往上放，就直接飘到数字头顶上方一大截去了。

    100% 时返回 **int**（结果正好是整数的话）：SVG 里的坐标是直接 format 的，
    整数化的偏移量不能让 `y="123"` 变成 `y="123.0"`。
    """
    x = v * CONTENT_SCALE
    return int(x) if float(x).is_integer() else x


def normalize_content_scale(value) -> float:
    """把「谱面大小」收进 [CONTENT_SCALE_MIN, CONTENT_SCALE_MAX]；非法值退回默认。

    界面/工程里可能是 0.7，也可能是 70 / "70" / "70%"（百分数写法），统一在这里收口。
    """
    if isinstance(value, str):
        s = value.strip().rstrip("%").strip()
        if not s:
            return DEFAULT_CONTENT_SCALE
        try:
            value = float(s)
        except ValueError:
            return DEFAULT_CONTENT_SCALE
    try:
        v = float(value)
    except (TypeError, ValueError):
        return DEFAULT_CONTENT_SCALE
    if v > 1.0:                       # 70 -> 0.70
        v /= 100.0
    if v <= 0:
        return DEFAULT_CONTENT_SCALE
    return min(max(v, CONTENT_SCALE_MIN), CONTENT_SCALE_MAX)


def content_scale_label(value=None) -> str:
    """给界面/摘要看的文字，如「70%」。"""
    v = CONTENT_SCALE if value is None else normalize_content_scale(value)
    return f"{round(v * 100)}%"


def _recompute_derived() -> None:
    """按当前的缩放后基准量，重算所有派生常量（恒等式因此永远精确）。"""
    global FLUTE_W, HOLE_R, UNDERLINE_W
    global LABEL_BASE_DY, DIGIT_TOP_DY, DIGIT_BOT_DY, HOLD_DY
    global MINI_W, MINI_H, MINI_HOLE_R, MINI_HOLE_DY, MINI_TOP_DY
    FLUTE_W = COL_W
    HOLE_R = COL_W * 0.31
    UNDERLINE_W = COL_W
    LABEL_BASE_DY = LABEL_DY + LABEL_BASE_GAP
    DIGIT_TOP_DY = LABEL_BASE_DY - NOTE_ASCENT
    DIGIT_BOT_DY = LABEL_BASE_DY
    HOLD_DY = DIGIT_TOP_DY + NOTE_ASCENT / 2      # 延音横线 = 数字墨迹的竖向中心
    MINI_W = FLUTE_W * MINI_S
    MINI_H = FLUTE_H * MINI_S
    MINI_HOLE_R = HOLE_R * MINI_S
    MINI_HOLE_DY = HOLE_DY * MINI_S
    MINI_TOP_DY = FLUTE_TOP_DY - CUT_LIFT


_SCALED_BASE = {_n: globals()[_n] for _n in _SCALED_NAMES}


def _apply_content_scale(k: float) -> None:
    """内部：直接套用某个比例（**不走 normalize**），供 try/finally 精确还原用。"""
    global CONTENT_SCALE
    CONTENT_SCALE = float(k)
    for _n, _base in _SCALED_BASE.items():
        _v = _base * CONTENT_SCALE
        # 基准是整数、乘出来又正好是整数（1.0 / 0.5 这些档）时保持 int：
        # SVG 里的坐标和字号是直接 format 出来的，26 一旦变成 "26.0"，
        # 「字号 26」「rx 12」这类断言就会失配 —— 100% 的导出必须逐字不变。
        globals()[_n] = int(_v) if float(_v).is_integer() else _v
    _recompute_derived()


def set_content_scale(value) -> float:
    """设定「谱面大小」（0.5~1.0，或 70 这样的百分数），返回实际生效值。

    每次都是从 **100% 的基准值**重算（_SCALED_BASE 在导入时抓一次），
    所以来回设置不会累积误差。
    """
    k = normalize_content_scale(value)
    _apply_content_scale(k)
    return k


@contextlib.contextmanager
def content_scale_ctx(value):
    """临时把「谱面大小」设成 value，退出时**原值还原**。

    导出（render_svg_pages）与编辑器分页预览都走它：这样「看一眼 70% 的效果」
    不会把模块状态留在 70% 上，之后任何直调 render 的代码仍按原尺寸出图。
    """
    prev = CONTENT_SCALE
    k = set_content_scale(value)
    try:
        yield k
    finally:
        _apply_content_scale(prev)


C_TEXT = "#1a1a1a"
C_ACCENT = "#23557a"
C_WARN = "#c0392b"
C_FLUTE = "#2c3e50"
C_HALF = "#e67e22"
C_SLUR = "#1f6f43"      # 圆滑线（不同音相连）
C_TIE = "#a35a00"       # 延音线（同音相连）
C_BREATH = "#6a3d9a"    # 换气记号（数字上方一个小 v）

# 调号来源标注
_KEY_SOURCE_TAG = {
    "text": "（谱内标注）",
    "param": "（指定）",
    "default": "（默认）",
}


def _esc(s: str) -> str:
    return _html.escape(str(s), quote=True)


def _duration_count(duration: float) -> int:
    """时值 -> 横线条数（附点沿基数），四分 0 条 / 八分 1 条 / 十六分 2 条"""
    return _duration_beams(duration)


def _repeat_cell(e, x, y, w=None) -> str:
    """反复记号（循环符号）：细线 + 粗线 + 两粒反复点，按方向决定点在哪一侧。

      |:   反复开始        →  细线 粗线 ··
      :|   反复结束        →  ·· 粗线 细线
      :|:  一段收尾并起下一段 →  ·· 细线 粗线 ··

    粗线永远挨着反复点那一侧（`:|` 是 `|:` 的镜像，与五线谱同序），
    点距粗线固定 7px，所以 `|:` 的点在粗线右边，`:|` 的点在粗线左边。

    竖线高度与简谱数字齐平（`DIGIT_TOP_DY` → `DIGIT_BOT_DY`），
    和小节线同一口径 —— 两粒反复点正好落在数字高度内。
    """
    w = CELL_W if w is None else w
    cx = x + w / 2
    direction = getattr(e, "direction", "") or "start"
    # 高度与数字齐平：上端到数字字形顶、下端到数字基线（不再一路拉到笛身）
    top = y + DIGIT_TOP_DY
    bottom = y + DIGIT_BOT_DY
    if direction == "end":
        thick_x, thin_x = cx - 2.0, cx + 2.5
    else:
        thin_x, thick_x = cx - 2.5, cx + 2.0
    parts = [
        f'<line x1="{thin_x}" y1="{top}" x2="{thin_x}" y2="{bottom}" '
        f'stroke="#999" stroke-width="{_s(1.2)}"/>',
        f'<line x1="{thick_x}" y1="{top}" x2="{thick_x}" y2="{bottom}" '
        f'stroke="{C_TEXT}" stroke-width="{_s(3.4)}"/>',
    ]
    mid = (top + bottom) / 2
    for dy in (-REPEAT_DOT_DY, REPEAT_DOT_DY):
        if direction in ("end", "both"):
            parts.append(f'<circle cx="{thick_x - _s(7)}" cy="{mid + dy}" r="{REPEAT_DOT_R}" '
                         f'fill="{C_TEXT}"/>')
        if direction in ("start", "both"):
            parts.append(f'<circle cx="{thick_x + _s(7)}" cy="{mid + dy}" r="{REPEAT_DOT_R}" '
                         f'fill="{C_TEXT}"/>')
    return "".join(parts)


def _is_cut(e) -> bool:
    """是不是「切音」：一个自带窄格子的小音符"""
    return (getattr(e, "kind", "note") == "note"
            and bool(getattr(e, "short", False)))


def _cut_label(e, cx, cy) -> str:
    """切音格子里的小简谱记号：小数字 + 八度点 + 右上角一道小斜杠。"""
    parts = []
    acc = {1: "♯", -1: "♭"}.get(getattr(e, "accidental", 0), "")
    if acc:
        parts.append(f'<text x="{cx - CUT_ACC_DX}" y="{cy + _s(4)}" font-size="{_s(11)}" '
                     f'fill="{C_CUT}" text-anchor="middle">{acc}</text>')
    parts.append(f'<text x="{cx}" y="{cy}" font-size="{CUT_SIZE}" font-weight="bold" '
                 f'fill="{C_CUT}" text-anchor="middle">{e.degree}</text>')
    octv = getattr(e, "octave", 0)
    for i in range(max(0, octv)):          # 小数字自身的高八度点
        parts.append(f'<circle cx="{cx}" cy="{cy - _s(11) - i * _s(5)}" r="{_s(1.5)}" '
                     f'fill="{C_CUT}"/>')
    for i in range(max(0, -octv)):         # 低八度点
        parts.append(f'<circle cx="{cx}" cy="{cy + _s(7) + i * _s(5)}" r="{_s(1.5)}" '
                     f'fill="{C_CUT}"/>')
    # 小斜杠：小数字右上角向右上划出（简谱里切音/装饰音的记号）
    parts.append(f'<line x1="{cx + _s(6)}" y1="{cy - _s(3)}" '
                 f'x2="{cx + _s(6) + CUT_SLASH}" '
                 f'y2="{cy - _s(3) - CUT_SLASH}" stroke="{C_CUT}" stroke-width="1.9" '
                 f'stroke-linecap="round"/>')
    return "".join(parts)


def _mini_flute(cx, top, holes) -> str:
    """切音小格子里的小指法图：缩小版的洞洞图，孔心与小数字同一条竖线。

    用切音色（C_CUT）描边，与主指法图（C_FLUTE 深蓝）区分开，
    让读者一眼看出「这是切开那个音的指法」，而不是第二个正常音。
    """
    parts = [f'<rect x="{cx - MINI_W / 2}" y="{top}" width="{MINI_W}" height="{MINI_H}" '
             f'rx="{_s(12) * MINI_S}" fill="#fdfdf8" stroke="{C_CUT}" '
             f'stroke-width="{_s(1.6)}"/>']
    cy = top + _s(14) * MINI_S
    for state in holes or ():
        if state == 1:
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{MINI_HOLE_R}" fill="{C_CUT}"/>')
        else:
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{MINI_HOLE_R}" fill="#ffffff" '
                         f'stroke="{C_CUT}" stroke-width="{_s(1.3)}"/>')
            if state == 2:
                parts.append(f'<path d="M {cx} {cy - MINI_HOLE_R} '
                             f'A {MINI_HOLE_R} {MINI_HOLE_R} 0 0 0 {cx} {cy + MINI_HOLE_R} Z" '
                             f'fill="{C_HALF}"/>')
        cy += MINI_HOLE_DY
    return "".join(parts)


def _label_top(e, row_top) -> float:
    """该音符“记号区”的顶端 y（已让开高八度点与换气记号），用于摆放连音弧线"""
    cy = row_top + LABEL_DY
    oct_hi = max(0, getattr(e, "octave", 0))
    top = cy - _s(14) - oct_hi * _s(9)
    if getattr(e, "breath", False):
        top -= BREATH_LIFT          # 换气记号站在数字正上方，弧线得再往上让一层
    return top


# ---------------- 歌词 ----------------
_LYRIC_SHIFT = 0      # 让位量（笛身/音名整体下移多少），由 _build_layout 按行数设定
_LYRIC_LINES = 0      # 整谱最多几行歌词，同上
# 「第 n 结尾」框（房子记号）相关的排版状态，全部由 _build_layout 按**实际内容**算出来：
# 框子画在行顶上方，要多高取决于这一段里最高的那个记号（八度点 / 换气 v）与最深的连音弧线。
_HAS_ENDING = False
_ENDING_SHIFT = 0         # 每行头顶额外要留的高度（加进 row_height）
_ENDING_HEAD_EXTRA = 0    # 首页标题带额外要留的高度
_ENDING_CHEAD_EXTRA = 0   # 第 2 页起紧凑页眉额外要留的高度


def lyric_lines_of(e) -> list:
    """该事件的全部歌词行。优先读多行字段 lyric_lines，否则退回单行字段 lyric。"""
    lines = e.get("lyric_lines") if isinstance(e, dict) else getattr(e, "lyric_lines", None)
    if isinstance(lines, list) and lines:
        return [str(x).strip() for x in lines]
    if isinstance(e, dict):
        one = e.get("lyric") or ""
    else:
        one = getattr(e, "lyric", "") or ""
    one = str(one).strip()
    return [one] if one else []


def lyric_of(e) -> str:
    """该事件的第一行歌词（没有就返回空串）。兼容 NoteEvent 与工程里的 dict。"""
    lines = lyric_lines_of(e)
    return lines[0] if lines else ""


def max_lyric_lines(events) -> int:
    """整谱最多几行歌词（排版据此决定让位量与行高）"""
    return max((len(lyric_lines_of(e)) for e in events), default=0)


def has_lyrics(events) -> bool:
    return max_lyric_lines(events) > 0


def lyric_shift_for(n_lines: int) -> float:
    """几行歌词 -> 笛身/音名整体下移多少（0 行 = 不让位）。

    整数运算（返回 int）是刻意的：SVG 里的坐标是直接 format 出来的，
    `0.0` 会写成 "0.0" 而与 "<text y=\\"0\\">" 这类期望对不上。
    """
    if not n_lines:
        return 0
    return LYRIC_DY + (n_lines - 1) * LYRIC_LINE_H


def _lyric_shift() -> float:
    return _LYRIC_SHIFT


def _lyric_baselines(y, flute_top_dy=None) -> list:
    """本格每行歌词的基线 y（第 0 条 = 最上面那行）。

    最后一行贴着笛身顶往上 6px，往上每行递进 LYRIC_LINE_H。
    行数取**整谱**的（_LYRIC_LINES），这样各段词才对得齐；
    画歌词和画超吹三角都用它，别各算一份。

    坑：flute_top_dy 默认值**不能**写成 `= FLUTE_TOP_DY`。默认参数是 def 时求值的，
    而 FLUTE_TOP_DY 会被 set_content_scale 改写 —— 写成默认值就会永远用导入时的
    100% 那个数（谱面一缩，歌词带整条错位）。
    """
    if flute_top_dy is None:
        flute_top_dy = FLUTE_TOP_DY
    n = _LYRIC_LINES
    if not n:
        return []
    last = y + flute_top_dy + _lyric_shift() - _s(6)
    return [last - (n - 1 - k) * LYRIC_LINE_H for k in range(n)]


def _lyric_baseline(y, flute_top_dy=None) -> float:
    """最后一行歌词的基线（兼容旧调用；新代码用 _lyric_baselines）"""
    if flute_top_dy is None:
        flute_top_dy = FLUTE_TOP_DY
    b = _lyric_baselines(y, flute_top_dy)
    return b[-1] if b else y + flute_top_dy - _s(6)


def _oct_mark_svg(cx, flute_bottom, color, scale=1.0) -> str:
    """超吹三角：顶在洞洞图下沿之下 OCT_MARK_GAP 处，横向居中于本列。

    位置**与歌词无关**——三角站在笛身下面那条空带里，永远碰不到歌词
    （老口径站在笛身顶上方、正是歌词带中心，才需要那套「搬到歌词上方并缩小」的让位）。
    scale 给切音的**小**指法图用（图小了，三角也跟着小一号）。

    注意：OCT_MARK_* 在 `_SCALED_NAMES` 里，`set_content_scale()` 会**就地**改这三个
    模块级的值，所以这里**不能再套 `_s()`** —— 套了就缩两次（65% 下三角会掉到 0.65² 倍，
    并且音名也会跟着错位，实测 32 变成 13.5）。
    """
    return (f'<path d="M {cx} {flute_bottom + OCT_MARK_GAP * scale} '
            f'l {OCT_MARK_W / 2 * scale} {OCT_MARK_H * scale} '
            f'h {-OCT_MARK_W * scale} Z" fill="{color}"/>')


def _lyric_svg(e, cx, y, avail=None, flute_top_dy=None) -> str:
    """歌词：画在数字与笛身之间的歌词带里，与数字同一竖线居中。

    多行歌词逐行往上摞（第 1 行在最上面）；空的那些行**不画字但照样占位**，
    这样各段词在整谱里始终对齐同一条基线，不会因为某格缺字就串行。
    y 为行顶；avail 是本格可用宽度（切音窄格要传 35.96，别按满格量）；
    flute_top_dy 是本格笛身顶距行顶的偏移（切音小格子整体上提，要传 MINI_TOP_DY，
    否则歌词会落到小指法图身上）；默认值见 _lyric_baselines 的说明。
    长词会自动缩小字号，免得串到左右邻格上去；字号下限 8px——切音那种窄格里塞
    很长的英文单词本来就不合常理，宁可小一点也不撑破格子。
    """
    if flute_top_dy is None:
        flute_top_dy = FLUTE_TOP_DY
    lines = lyric_lines_of(e)
    if not lines:
        return ""
    limit = (CELL_W if avail is None else avail) * 0.92
    bases = _lyric_baselines(y, flute_top_dy)
    parts = []
    for k, text in enumerate(lines):
        if not text:
            continue                       # 空行占位不画字（多段词要对齐）
        size = LYRIC_SIZE
        while size > _s(8) and len(text) * size > limit:
            size -= 1
        ty = bases[k] if k < len(bases) else (bases[-1] if bases else y)
        parts.append(f'<text x="{cx}" y="{ty}" font-size="{size}" fill="{C_LYRIC}" '
                     f'text-anchor="middle">{_esc(text)}</text>')
    return "".join(parts)


def _jianpu_label(e, x, y) -> str:
    """简谱记号 + 八度点 + 附点 + 换气记号，(x,y) 为数字中心。

    横向对齐约束：数字以 x 居中；附点画在数字右侧；换气记号 v 画在数字正上方
    （高八度点之上，所以连音弧线要按 _label_top 再让一层）；
    减时线不在这里画——由 render_svg 的连尾层统一画成连续横线；
    切音也不在这里画——切音走 _cut_label，画在自己那个窄格子里。
    """
    parts = []
    acc = ""
    if e.accidental == 1:
        acc = "♯"
    elif e.accidental == -1:
        acc = "♭"
    if acc:
        parts.append(f'<text x="{x - _s(15)}" y="{y + _s(7)}" font-size="{_s(18)}" '
                     f'fill="{C_TEXT}" text-anchor="middle">{acc}</text>')
    parts.append(f'<text x="{x}" y="{y + LABEL_BASE_GAP}" font-size="{NOTE_SIZE}" font-weight="bold" '
                 f'fill="{C_TEXT}" text-anchor="middle">{e.degree}</text>')
    for i in range(e.octave):          # 高八度：数字上方加点
        parts.append(f'<circle cx="{x}" cy="{y - _s(20) - i * _s(7)}" r="{_s(2.4)}" '
                     f'fill="{C_TEXT}"/>')
    if getattr(e, "breath", False):    # 换气：数字正上方一个小 v（高八度点之上）
        vy = y - BREATH_DY - max(0, e.octave) * _s(7)
        parts.append(f'<text x="{x}" y="{vy}" font-size="{BREATH_SIZE}" '
                     f'fill="{C_BREATH}" text-anchor="middle">v</text>')
    duration = getattr(e, "duration", 1.0)
    n_lines = _duration_count(duration)
    if _is_dotted(duration):            # 附点：数字右侧中点
        parts.append(f'<circle cx="{x + _s(12)}" cy="{y - _s(1)}" r="{_s(2.6)}" '
                     f'fill="{C_TEXT}"/>')
    dot_y = y + BEAM_DY + _s(3) + max(1, n_lines) * UNDERLINE_DY
    for i in range(-e.octave):         # 低八度：减时线之下再加点
        parts.append(f'<circle cx="{x}" cy="{dot_y + i * _s(7)}" r="{_s(2.4)}" '
                     f'fill="{C_TEXT}"/>')
    return "".join(parts)


def _hole_svg(cx, cy, state) -> str:
    """单个孔：1=按 0=放 2=半孔"""
    if state == 1:
        return f'<circle cx="{cx}" cy="{cy}" r="{HOLE_R}" fill="{C_FLUTE}"/>'
    if state == 0:
        return (f'<circle cx="{cx}" cy="{cy}" r="{HOLE_R}" fill="#ffffff" '
                f'stroke="{C_FLUTE}" stroke-width="{_s(1.6)}"/>')
    # 半孔：左半填橙，右半留白
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{HOLE_R}" fill="#ffffff" '
        f'stroke="{C_FLUTE}" stroke-width="{_s(1.6)}"/>'
        f'<path d="M {cx} {cy - HOLE_R} A {HOLE_R} {HOLE_R} 0 0 0 {cx} {cy + HOLE_R} Z" '
        f'fill="{C_HALF}"/>'
    )


def _cut_cell(e, result, x, y, w) -> str:
    """切音单元：自己占一个窄格子——小数字 + 小斜杠，下面配一张小指法图（同一条竖线）。"""
    cx = x + w / 2
    cy = y + LABEL_BASE_DY - CUT_LIFT     # 与主数字基线对齐后再整体上提
    out = [_cut_label(e, cx, cy)]
    out.append(_lyric_svg(e, cx, y, w, MINI_TOP_DY))   # 切音带歌词时按窄格宽 + 小图顶算位置
    flute_top = y + MINI_TOP_DY + _lyric_shift()
    if not result.playable:               # 防御性：超音域时画个小警示框
        out.append(f'<rect x="{x + _s(3)}" y="{flute_top - _s(6)}" '
                   f'width="{w - _s(6)}" height="{MINI_H + _s(14)}" '
                   f'rx="{_s(6)}" fill="none" stroke="{C_WARN}" '
                   f'stroke-width="{_s(1.6)}" stroke-dasharray="4 3"/>')
        return "".join(out)
    out.append(_mini_flute(cx, flute_top, result.holes))
    if result.second_octave:              # 超吹标记：画在**小**洞洞图下沿之下（口径同 _note_cell）
        color = C_WARN if result.hard else C_ACCENT
        out.append(_oct_mark_svg(cx, flute_top + MINI_H, color, MINI_OCT_SCALE))
    return "".join(out)


def _note_cell(e, result, x, y, w=None) -> str:
    """一个音符单元。x=单元左缘, y=行顶, w=列宽。简谱记号永远在单元正上方。"""
    w = CELL_W if w is None else w
    cx = x + w / 2
    if _is_cut(e):
        return _cut_cell(e, result, x, y, w)
    out = [_jianpu_label(e, cx, y + LABEL_DY)]
    out.append(_lyric_svg(e, cx, y))
    dy = _lyric_shift()               # 有歌词时笛身/音名整体下移，给歌词让位
    # 超音域警示分支（简谱记号同样保留在正上方）。
    # 注意：当前不可达——fingering.map_note 的八度搬移循环对任意整数输入
    # 恒收敛到 [0, MAX_INDEX]，恒返回 playable=True。此分支保留作防御性
    # 渲染：若未来 fingering 改为严格模式（不自动移八度），谱面仍能正确警示。
    if not result.playable:
        out.append(f'<rect x="{x + _s(4)}" y="{y + FLUTE_TOP_DY + dy - _s(8)}" '
                   f'width="{w - _s(8)}" height="{FLUTE_H + _s(44)}" '
                   f'rx="{_s(8)}" fill="none" stroke="{C_WARN}" stroke-width="{_s(2)}" '
                   f'stroke-dasharray="5 4"/>')
        out.append(f'<text x="{cx}" y="{y + FLUTE_TOP_DY + dy + _s(66)}" '
                   f'font-size="{_s(13)}" fill="{C_WARN}" '
                   f'text-anchor="middle">超出音域</text>')
        out.append(f'<text x="{cx}" y="{y + FLUTE_TOP_DY + dy + FLUTE_H + _s(46)}" '
                   f'font-size="{_s(15)}" fill="{C_WARN}" '
                   f'text-anchor="middle">{_esc(result.note_name)}?</text>')
        return "".join(out)

    flute_top = y + FLUTE_TOP_DY + dy
    fx = cx - FLUTE_W / 2
    out.append(f'<rect x="{fx}" y="{flute_top}" width="{FLUTE_W}" height="{FLUTE_H}" '
               f'rx="{_s(12)}" fill="#fdfdf8" stroke="{C_FLUTE}" stroke-width="{_s(2)}"/>')
    hole_cy = flute_top + _s(14)
    for state in result.holes:
        out.append(_hole_svg(cx, hole_cy, state))
        hole_cy += HOLE_DY
    if result.second_octave:           # 超吹三角：洞洞图下沿之下、音名上方（见 OCT_MARK_H 的说明）
        out.append(_oct_mark_svg(cx, flute_top + FLUTE_H,
                                 C_WARN if result.hard else C_ACCENT))
    name_y = flute_top + FLUTE_H + NAME_DY_FROM_FLUTE   # 该常量在 _SCALED_NAMES 里，别再套 _s()
    name = _esc(result.note_name) + (" 高" if result.second_octave else "")
    color = C_WARN if result.hard else C_ACCENT
    out.append(f'<text x="{cx}" y="{name_y}" font-size="{_s(14)}" fill="{color}" '
               f'text-anchor="middle">{name}</text>')
    if getattr(result, "custom", False):     # 编谱器手选指法：谱面标明，便于演奏者核对
        out.append(f'<text x="{cx}" y="{name_y + _s(13)}" font-size="{_s(10)}" '
                   f'fill="{C_HALF}" text-anchor="middle">自选指法</text>')
    # 自动移八度**不在音符下面标注**：在单元格里再压一行小字既挤又难看，
    # 而这件事页脚警示区已经逐音写清楚了（「第 N 个音 …：超出音域，已自动降低八度」）。
    return "".join(out)


# ---------------- 列布局（按小节排、按纸张分页） ----------------
_LAYOUT = []          # [(x_left, width, 页内行顶 y), ...] 由 _build_layout 填充
_ROW_OF = []          # 每个事件的「全局行号」（跨页也算不同行 → 连尾/连音不会跨行串联）
_PAGE_OF = []         # 每个事件在哪一页（0 基）
_ROW_PAGE = []        # 每一行在哪一页
_ROW_TOP = []         # 每一行的行顶（**页内**坐标）
N_PAGES = 1           # 总页数
ROW_AREA = 0          # 有多少行是「被迫从别的小节里挤进来的」（正常排版下应为 0）
ROW_PLAN = []         # 每一行由哪些事件下标组成（按排版顺序）——测试用它核对 4~6 小节/行
MEASURES = []         # 小节切分（每个小节的**事件下标**列表）——同上，便于核对「没从小节中间断」
_BAR_KINDS = ("bar", "repeat")


def cell_width(e) -> float:
    """一个事件占的列宽（「自然列距」下的宽度；行内实际列距由 _plan_rows 自适应）：

      * 切音 → 窄格（小数字 + 小指法图）
      * 小节线 → 更窄（就一根细竖线）
      * 反复记号 → 略窄（细线 + 粗线 + 两粒反复点）
      * 整段括号 → 略窄（就是一道弧，别占满格）
      * 结尾框记号 → 更窄（框子画在音符上方，这一格只是让它在谱面上有个位置）
      * 其余 → 满格
    """
    if _is_cut(e):
        return CELL_W * CUT_CELL_RATIO
    kind = getattr(e, "kind", "")
    if kind == "bar":
        return CELL_W * BAR_CELL_RATIO
    if kind == "repeat":
        return CELL_W * REPEAT_CELL_RATIO
    if kind == "bracket":
        return CELL_W * BRACKET_CELL_RATIO
    if kind == "ending":
        return CELL_W * ENDING_CELL_RATIO
    return CELL_W


def has_endings(events) -> bool:
    """这份谱里有没有「第 n 结尾」框（有的话行高与页眉带都要多留头顶空间）"""
    return any(getattr(e, "kind", "") == "ending" for e in events)


def content_bottom_dy() -> float:
    """一行**内容**的最低点距行顶多远（音名文字那一行，含「自选指法」小字）。

    行顶上方能用多少余量 = row_height() - 这个值（见 base_row_slack）：
    连音弧线、结尾框都画在这一段里。所以这个数只能从绘制代码里推导，不能另写一个。
    """
    return FLUTE_TOP_DY + FLUTE_H + _s(20) + _s(13)


def base_row_slack() -> float:
    """不加结尾框时，行顶上方本来就有多少余量。

    行底内容到「下一行行顶」之间的空白 = ROW_H + ROW_GAP（+ 歌词/结尾框让位）- 内容高度。
    连音弧线（普通约 29px、嵌套每层 +9）已经住在这段里，结尾框还要更高一点，
    所以「够不够」得用这个余量去比。
    """
    return ROW_H + ROW_GAP + _LYRIC_SHIFT - content_bottom_dy()


def ending_top_offset(events, i0: int, i1: int) -> float:
    """第 (i0..i1) 这个结尾框的横线 y 距**行顶**的偏移（负数 = 在行顶上方）。

    框子要压在这一段所有记号之上，所以起点取「这一段里最靠上的记号区顶」
    （`_label_top` 已经把高八度点、换气 v 算进去了），再往上让开落在这段里的
    连音弧线（按最深的那层算）与净空 ENDING_GAP。
    """
    top_dy = min((_label_top(events[i], 0) for i in range(i0, i1 + 1)), default=0.0)
    spans = beaming.slur_spans(events)
    depth = 0
    for sp in spans:
        if i0 <= sp["i0"] and sp["i1"] <= i1:
            depth = max(depth, min(3, beaming.span_depth(spans, sp)))
    return (top_dy - SLUR_GAP - depth * SLUR_NEST
            - (2 * SLUR_H if depth else 0) - ENDING_GAP)


def ending_top_need(events) -> float:
    """有结尾框时，行顶上方**至少要**让出多少（正数 = 需要这么多余量）。

    把所有结尾框算一遍取最大 —— 整谱的行高是统一的，只能用最费的那一个当基准。
    跨行的结尾框按「整段一起算」偏保守（每一行都比整段矮），保守是对的。
    """
    pairs, _unpaired = _frame_pairs(events, "ending")
    return max((-ending_top_offset(events, i0, i1) for i0, i1, _n in pairs), default=0.0)


def header_h(first: bool) -> float:
    """页眉带的高度（首页是大标题区、后续页是紧凑页眉）。

    有结尾框时整条带子要更高：框子画在行顶上方，行顶又紧贴页眉带下沿，
    不留够就会直接压到图例 / 页眉横线上（见 _ENDING_HEAD_EXTRA）。
    """
    base = HEADER_H if first else COMPACT_HEADER_H
    if _HAS_ENDING:
        base += _ENDING_HEAD_EXTRA if first else _ENDING_CHEAD_EXTRA
    return base


def row_height() -> float:
    """当前行高 = 行内内容 + 行间净空白（+ 有结尾框时额外让出的头顶空间）。

    三个坑，都是「行与行之间不留空」造成的：

      * **歌词让位量要整段加回来**。笛身/音名整体下移 _LYRIC_SHIFT，内容底就跟着往下，
        行高必须同步长这么多。原来只补了「第 2 行起」的部分（max(0, 行数-1)），
        第 1 行的 LYRIC_DY 想靠 ROW_H 原有的余量硬吃 —— 结果余量直接归零
        （214 - 213 = 1px），行与行贴死。
      * **连音弧线是画在数字上方的，会高出行顶**。普通弧线约 29px，嵌套每层 +9px，
        本格带换气记号再 +18px。这段高度只能由「上一行的行间空白」提供，
        不留够，下一行的弧线就会压住上一行最下面的音名（实测压 28px）。
      * **结尾框比弧线还高**（框子横线在这一段最高记号之上、还要再让开弧线与净空）。
        要多少由 ending_top_need 按实际内容算，减去本来就有余量 base_row_slack
        就是要补的那部分（_ENDING_SHIFT）。只有真有结尾框、且原来的余量不够时才补，
        免得白占高度少排一行。
    """
    return ROW_H + _LYRIC_SHIFT + ROW_GAP + _ENDING_SHIFT


def rows_per_page(first: bool = False) -> int:
    """一页放得下几行（首页要让出大标题区，后续页只让出紧凑页眉）。"""
    return max(1, int((PAGE_HEIGHT - header_h(first) - FOOTER_H) // row_height()))


def _measure_groups(events) -> list:
    """按小节切开事件：每个 bar / repeat 结束一小节（含它自己）。

    没有小节线的长串（关掉自动小节线、又没手写线）算是「一个小节」，
    它太宽时会由 _plan_rows 按列硬拆，保证不越出页面右缘。
    """
    out, cur = [], []
    for i, e in enumerate(events):
        cur.append(i)
        if getattr(e, "kind", "") in _BAR_KINDS:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _units(events, idxs) -> float:
    """一段事件在「列距 = 1」下占的宽度（切音算窄格）"""
    return sum(cell_width(events[i]) / CELL_W for i in idxs)


def _chunk_oversized(events, idxs, avail) -> list:
    """一个小节自己就宽过一页时，只能按列硬拆（极端情况，此时也没有小节线可依）。"""
    out, cur = [], []
    for i in idxs:
        if cur and _units(events, cur + [i]) * PITCH_MIN > avail:
            out.append(cur)
            cur = [i]
        else:
            cur.append(i)
    if cur:
        out.append(cur)
    return out


def row_cap() -> int:
    """一行允许排几个小节的上限：用户指定了就按指定的，否则用自动模式的最大值。"""
    return CURRENT_ROW_MEASURES or ROW_MEASURES_MAX


def _row_counts(n: int) -> list:
    """把 n 个小节切成每行几个。

    **自动**（默认）：尽量均分、且不超过 ROW_MEASURES_MAX。均分是为了别收出一个
    1~2 小节的孤行：8 小节宁可 4+4，也不要 6+2；13 小节宁可 5+4+4，也不要 6+4+3。
    行数取 ceil(n / ROW_MEASURES_MAX)（行数最少）。

    **指定「一行 N 小节」**：就按 N 排（每行尽量满），最后一行短一点；
    但尾行只剩 1 个时从前一行借一个（9 小节 + 一行 4 → 4+3+2，而不是 4+4+1）。
    """
    if n <= 0:
        return []
    if CURRENT_ROW_MEASURES:
        cap = CURRENT_ROW_MEASURES
        counts, left = [], n
        while left > cap:
            counts.append(cap)
            left -= cap
        counts.append(left)
        if counts[-1] == 1 and len(counts) >= 2 and counts[-2] >= 3:
            counts[-2] -= 1
            counts[-1] = 2
        return counts
    rows = max(1, -(-n // ROW_MEASURES_MAX))
    base, extra = divmod(n, rows)
    return [base + (1 if i < extra else 0) for i in range(rows)]


def _plan_rows(events, measures, avail) -> tuple:
    """小节 → 行：一行 4~6 个小节，**绝不从小节中间换行**（小节是最小换行单位）。

    先按 `_row_counts` 均分定出「这一行排几个小节」，再看列距放不放得下：
    列距在 [PITCH_MIN, CELL_W] 之间自适应（放不下就压缩），
    压到 PITCH_MIN（26px，笛身宽 24 再留 2px 缝）仍放不下时本行少排一个、
    把料让给下一行；这是几何上的硬限制（可用宽度 / 小节数 / 每小节列数 < 笛身宽），
    再往下压笛身图就要叠在一起、反而看不清，所以宁可少排一个小节。

    贪心是「能塞多少塞多少」，遇到密谱会把料全塞进前几行、末尾剩一个 1 小节的
    孤行（如 4 个 7 格小节 → 3+1）。所以最后补一步**尾部均分**：末行只剩 1 个、
    且上一行 ≥3 个时，把这两行的料合起来重新均分（→ 2+2），取最均衡且放得下的方案。

    返回 ([(事件下标列表, 该行列距), ...], 被迫硬拆的小节数)。
    """
    blocks, forced = [], []
    for m in measures:                     # 先处理「单小节超宽」的极端情况
        if _units(events, m) * PITCH_MIN > avail:
            for c in _chunk_oversized(events, m, avail):
                blocks.append(c)
                forced.append(True)
        else:
            blocks.append(m)
            forced.append(False)

    def fit(at: int, kk: int):
        """从第 at 个块起连续 kk 个块能否放进一行；放得下就返回该行列距，否则 None。

        kk==1 时无条件接受（单小节再宽也得排，硬拆已在上面处理过）。
        """
        if at + kk > len(blocks):
            return None
        if kk == 1:
            return min(CELL_W, avail / max(_units(events, blocks[at]), 1e-6))
        if forced[at + kk - 1]:
            return None              # 硬拆块只能独占一行
        units = _units(events, [i for b in blocks[at:at + kk] for i in b])
        pitch = (avail / units) if units else CELL_W
        return min(CELL_W, pitch) if pitch >= PITCH_MIN else None

    n = len(blocks)
    row_ks, k = [], 0
    while k < n:
        kk = 1                    # 兜底：kk=1 无条件接受（理论到不了）
        for cand in range(min(_row_counts(n - k)[0], row_cap()), 1, -1):
            if fit(k, cand) is not None:
                kk = cand
                break
        row_ks.append(kk)
        k += kk

    # 尾部均分：别把料全塞到前一行、尾巴甩一个 1 小节的孤行
    if len(row_ks) >= 2 and row_ks[-1] == 1 and row_ks[-2] >= 3:
        start = sum(row_ks[:-2])
        total = row_ks[-2] + 1
        best = None
        for a in range(2, min(total - 2, row_cap()) + 1):
            b = total - a
            if a + b != total or not (2 <= b <= row_cap()):
                continue
            if fit(start, a) is None or fit(start + a, b) is None:
                continue
            key = (abs(a - b), -a)          # 先求均衡，再让前一行更满（[3,2] 优于 [2,3]）
            if best is None or key < best[0]:
                best = (key, [a, b])
        if best is not None:
            row_ks[-2:] = best[1]

    rows, start = [], 0
    for kk in row_ks:
        idxs = [i for b in blocks[start:start + kk] for i in b]
        rows.append((idxs, fit(start, kk)))
        start += kk
    return rows, sum(1 for f in forced if f)


def _build_layout(events, paper: str = "", row_measures=None) -> int:
    """铺格 + 分页。返回**总行数**（跨页累计）。

    顺序要紧：行高取决于「整谱最多几行歌词」，所以歌词行数必须先定；
    页面尺寸取决于纸张、每行几个小节取决于 row_measures，所以这两项也在这里落定
    （传 None 表示沿用当前生效值，不覆盖）。
    """
    global _LAYOUT, _LYRIC_LINES, _LYRIC_SHIFT, _ROW_OF, _PAGE_OF, _ROW_PAGE, _ROW_TOP
    global N_PAGES, ROW_AREA, ROW_PLAN, MEASURES, _HAS_ENDING
    global _ENDING_SHIFT, _ENDING_HEAD_EXTRA, _ENDING_CHEAD_EXTRA
    if paper:
        set_paper(paper)
    if row_measures is not None:
        set_row_measures(row_measures)
    _LYRIC_LINES = max_lyric_lines(events)
    _LYRIC_SHIFT = lyric_shift_for(_LYRIC_LINES)
    # 结尾框的头顶留白：先按实际内容算出「至少要多少」，再减去本来就有的余量。
    # 必须在算 row_h / 页容量之前定下来（和歌词让位同一个道理）。
    _HAS_ENDING = has_endings(events)
    if _HAS_ENDING:
        need = ending_top_need(events) + ENDING_MARGIN
        _ENDING_SHIFT = max(0, math.ceil(need - base_row_slack()))
        _ENDING_HEAD_EXTRA = max(0, math.ceil(need - (HEADER_H - HEADER_INK_BOTTOM)))
        _ENDING_CHEAD_EXTRA = max(
            0, math.ceil(need - (COMPACT_HEADER_H - COMPACT_HEADER_INK_BOTTOM)))
    else:
        _ENDING_SHIFT = _ENDING_HEAD_EXTRA = _ENDING_CHEAD_EXTRA = 0
    row_h = row_height()
    avail = PAGE_WIDTH - 2 * MARGIN
    MEASURES = _measure_groups(events)
    planned, ROW_AREA = _plan_rows(events, MEASURES, avail)
    ROW_PLAN = [idxs for idxs, _pitch in planned]

    lay, row_of, page_of, row_page, row_top = [], [], [], [], []
    page, used = 0, 0
    for idxs, pitch in planned:
        cap = rows_per_page(first=(page == 0))
        if used >= cap:
            page += 1
            used = 0
        head = header_h(page == 0)
        top = head + used * row_h
        row_no = len(row_page)
        row_page.append(page)
        row_top.append(top)
        x = float(MARGIN)
        for i in idxs:
            w = pitch * (cell_width(events[i]) / CELL_W)
            lay.append((x, w, top))
            row_of.append(row_no)
            page_of.append(page)
            x += w
        used += 1
    _LAYOUT, _ROW_OF, _PAGE_OF, _ROW_PAGE, _ROW_TOP = lay, row_of, page_of, row_page, row_top
    N_PAGES = (page + 1) if planned else 1
    return len(planned) if planned else 1


def page_rows(p: int) -> list:
    """第 p 页有哪些行（全局行号）"""
    return [r for r, pg in enumerate(_ROW_PAGE) if pg == p]


def row_top_of(row: int) -> float:
    """某行的行顶（页内坐标）"""
    return _ROW_TOP[row] if 0 <= row < len(_ROW_TOP) else HEADER_H


def page_of(i: int) -> int:
    return _PAGE_OF[i] if 0 <= i < len(_PAGE_OF) else 0


def _row_of(i: int) -> int:
    if not (0 <= i < len(_ROW_OF)):
        return 0
    return _ROW_OF[i]


def _cell_x(i: int) -> float:
    return _LAYOUT[i][0] if 0 <= i < len(_LAYOUT) else MARGIN


def _cell_w(i: int) -> float:
    return _LAYOUT[i][1] if 0 <= i < len(_LAYOUT) else CELL_W


def _cell_cx(i: int) -> float:
    """第 i 个事件所在列的数字中心 x（= 笛身中心 = 孔心竖线）"""
    return _cell_x(i) + _cell_w(i) / 2


def _cell_row_top(i: int) -> float:
    return _LAYOUT[i][2] if 0 <= i < len(_LAYOUT) else HEADER_H


def _beam_layer(events, beats, page=None) -> str:
    """减时线（连尾）层。

    规范：同一拍内相邻的八分 / 十六分共用一条**连续**横线；
    十六分的第二条线只画在十六分音符下方；四分及更长的音符不带线。
    一行放不下时按行切断，避免横线跨行；分页时只画本页的行。
    """
    parts = []
    for i0, i1, level in beaming.beam_segments(events, beats or "4/4"):
        j = i0
        while j <= i1:
            row = _row_of(j)
            k = j
            while k + 1 <= i1 and _row_of(k + 1) == row:
                k += 1
            if page is None or _ROW_PAGE[row] == page:
                x0 = _cell_cx(j) - min(UNDERLINE_W, _cell_w(j)) / 2
                x1 = _cell_cx(k) + min(UNDERLINE_W, _cell_w(k)) / 2
                y = _cell_row_top(j) + LABEL_DY + BEAM_DY + level * UNDERLINE_DY
                parts.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{C_TEXT}" '
                             f'stroke-width="{_s(2.6)}" stroke-linecap="round"/>')
            j = k + 1
    return "".join(parts)


def _slur_layer(events, page=None) -> str:
    """连音线层：同音相连=延音线、不同音=圆滑线，画成数字上方的弧线。

    横跨两行（或两页）的连音线暂不绘制（编谱器里一行的连线最常用）；嵌套的连线自动抬高，
    避免弧线互相压线。
    """
    spans = beaming.slur_spans(events)
    parts = []
    for sp in sorted(spans, key=lambda s: (s["i0"], -s["i1"])):
        i0, i1 = sp["i0"], sp["i1"]
        if _row_of(i0) != _row_of(i1):
            continue
        if page is not None and page_of(i0) != page:
            continue
        depth = min(3, beaming.span_depth(spans, sp))
        row_top = _cell_row_top(i0)
        base = (min(_label_top(events[i0], row_top), _label_top(events[i1], row_top))
                - SLUR_GAP - depth * SLUR_NEST)
        x0, x1 = _cell_cx(i0), _cell_cx(i1)
        if x1 < x0:
            x0, x1 = x1, x0
        h = SLUR_H if (x1 - x0) > 30 else SLUR_H * 0.6
        color = C_TIE if sp["kind"] == "tie" else C_SLUR
        parts.append(f'<path d="M {x0} {base} Q {(x0 + x1) / 2} {base - 2 * h} {x1} {base}" '
                     f'fill="none" stroke="{color}" stroke-width="{_s(1.8)}" '
                     f'stroke-linecap="round"/>')
    return "".join(parts)


def _bracket_layer(events, page=None) -> str:
    """整段括号层：成对的圆括号把一段音括起来（前奏 / 间奏 / 和声伴唱）。

    每一侧都是**自足的**：左括号画在起点那格的左缘、右括号画在终点那格的右缘，
    所以跨行 / 跨页也不会像连音线那样整条丢掉——两侧各自画在自己那一行上。

    高度与简谱数字齐平（上端到字形顶再高一点、下端盖住低八度点），和「竖线只有数字
    那么高」同一口径：括号是标在记号上的，不该一路拉到笛身、更不该进到歌词带里。
    """
    parts = []
    top_dy = DIGIT_TOP_DY - BRACKET_UP
    bot_dy = DIGIT_BOT_DY + BRACKET_DOWN
    b = BRACKET_BULGE
    for i, e in enumerate(events):
        if getattr(e, "kind", "") != "bracket":
            continue
        if page is not None and page_of(i) != page:
            continue
        top = _cell_row_top(i)
        y0, y1 = top + top_dy, top + bot_dy
        ym = (y0 + y1) / 2
        if getattr(e, "direction", "start") == "start":
            x = _cell_x(i)                      # 起点那格的左缘
            d = f"M {x + b} {y0} Q {x} {ym} {x + b} {y1}"
        else:
            x = _cell_x(i) + _cell_w(i)         # 终点那格的右缘
            d = f"M {x - b} {y0} Q {x} {ym} {x - b} {y1}"
        parts.append(f'<path d="{d}" fill="none" stroke="{C_TEXT}" '
                     f'stroke-width="{_s(1.6)}" stroke-linecap="round"/>')
    return "".join(parts)


def _ending_layer(events, page=None) -> str:
    """「第 n 结尾」框层（房子记号）：横线 + 左端向下的短钩 + 标号「1.」。

    起止是**手工指定**的（`[1` … `1]`），所以框子的跨度就是这两个记号在版面上的宽度，
    该框哪几个音完全由用户决定。高度由 `ending_top_offset` 按实际内容算：压在这一段
    所有记号之上（八度点、换气 v、落在这段里的连音弧线），行高与页眉带都为此留了余量
    （见 row_height / header_h），所以不会压到上一行的音名、也不会压到图例。

    跨行时按行切开：起始行从起点画到右页边、中间行整幅、结束行从左边距画到终点，
    长结尾不会整条消失；左端短钩只画在起始行、右端短钩只画在结束行。
    起止没配对上的那种（只写了 `[1` 或只写了 `1]`）画不出来，由导出前的提示提醒。
    """
    pairs, _unpaired = _frame_pairs(events, "ending")
    parts = []
    right = PAGE_WIDTH - MARGIN
    for i0, i1, n in pairs:
        n = max(1, n or 1)
        r0, r1 = _row_of(i0), _row_of(i1)
        for r in range(r0, r1 + 1):
            if page is not None and _ROW_PAGE[r] != page:
                continue
            # 本行里属于这个结尾框的事件（跨行时就是各自那一段）
            here = [i for i in range(i0, i1 + 1) if _row_of(i) == r]
            y = row_top_of(r) + ending_top_offset(events, min(here, default=i0),
                                                  max(here, default=i1))
            x0 = _cell_x(i0) if r == r0 else MARGIN
            x1 = (_cell_x(i1) + _cell_w(i1)) if r == r1 else right
            if x1 <= x0:
                continue
            parts.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" '
                         f'stroke="{C_TEXT}" stroke-width="{_s(1.4)}"/>')
            if r == r0:
                parts.append(f'<line x1="{x0}" y1="{y}" x2="{x0}" y2="{y + ENDING_TICK}" '
                             f'stroke="{C_TEXT}" stroke-width="{_s(1.4)}"/>')
                # 标号写在横线**下方**（框子里面），贴在左端
                parts.append(f'<text x="{x0 + ENDING_INSET}" y="{y + ENDING_TEXT_SIZE}" '
                             f'font-size="{ENDING_TEXT_SIZE}" font-weight="bold" '
                             f'fill="{C_TEXT}">{n}.</text>')
            if r == r1:
                parts.append(f'<line x1="{x1}" y1="{y}" x2="{x1}" y2="{y + ENDING_TICK}" '
                             f'stroke="{C_TEXT}" stroke-width="{_s(1.4)}"/>')
    return "".join(parts)


def _simple_cell(e, x, y, w=None) -> str:
    """休止 / 延音 / 小节线 / 反复记号 / 括号 / 结尾框"""
    w = CELL_W if w is None else w
    cx = x + w / 2
    if e.kind == "rest":
        # 减时线**不在这里画**：短休止符和音符一样参与连尾，由 _beam_layer 统一画
        # （见 beaming 模块文档第 4 条）。这里只画那个「0」。
        return (f'<text x="{cx}" y="{y + LABEL_DY + _s(9)}" font-size="{NOTE_SIZE}" '
                f'font-weight="bold" fill="{C_TEXT}" text-anchor="middle">0</text>')
    if e.kind == "repeat":
        return _repeat_cell(e, x, y, w)
    if e.kind == "hold":
        # 延音横线：定长（HOLD_W）、居中于本格中心、竖向对准数字墨迹中心。
        # 别改成「跟着格宽走」——列距是本行自适应压出来的，那样同一份谱里横线会长短不一。
        cy = y + HOLD_DY
        return (f'<line x1="{cx - HOLD_W / 2}" y1="{cy}" '
                f'x2="{cx + HOLD_W / 2}" y2="{cy}" '
                f'stroke="{C_TEXT}" stroke-width="{_s(2.5)}"/>')
    if e.kind in FRAME_KINDS:
        # 括号与结尾框都是**跨格**的（从起点一直画到终点），没法一格一格画好，
        # 所以交给 _bracket_layer / _ending_layer 统一画；这里只留着这一格的位置。
        return ""
    # 小节线：高度与数字齐平（上端到数字字形顶、下端到数字基线），不跟着笛身往下拉
    return (f'<line x1="{cx}" y1="{y + DIGIT_TOP_DY}" x2="{cx}" y2="{y + DIGIT_BOT_DY}" '
            f'stroke="#999" stroke-width="{_s(1.2)}"/>')


def _text_width(text: str, size: float) -> float:
    """粗略估一行文字的宽度：CJK/全角按字号宽算，西文按 0.55 倍。"""
    return sum(size if ord(ch) > 0x2E80 else size * 0.55 for ch in text)


def _fit_font(text: str, base: float, avail: float | None = None,
              min_size: float = 12.0) -> float:
    """一行文字太长就把字号收一收，别越出页面右缘。"""
    avail = (PAGE_WIDTH - 2 * MARGIN) if avail is None else avail
    width = _text_width(text, base)
    if width <= avail:
        return base
    return max(min_size, base * avail / width)


def _fit_title_font(title: str, base: float = 30.0) -> float:
    return _fit_font(title, base)


def _legend_svg() -> str:
    """两行图例。

    A4 竖版的内容宽只有 713px，一行排不下 9 条图例，所以第 1 行是「怎么读洞洞」，
    第 2 行是各种记号。坐标是手工排的：每条 = 样图 + 文字，文字宽度按「中文 × 字号」估，
    段间至少留 15px，不然加新记号时文字会压到下一段的样图上。
    """
    return (
        f'<g font-size="13" fill="{C_TEXT}">'
        f'<circle cx="{MARGIN + 8}" cy="102" r="6" fill="{C_FLUTE}"/>'
        f'<text x="{MARGIN + 20}" y="107">按住</text>'
        f'<circle cx="{MARGIN + 70}" cy="102" r="6" fill="#fff" stroke="{C_FLUTE}" stroke-width="1.6"/>'
        f'<text x="{MARGIN + 82}" y="107">放开</text>'
        f'<circle cx="{MARGIN + 132}" cy="102" r="6" fill="#fff" stroke="{C_FLUTE}" stroke-width="1.6"/>'
        f'<path d="M {MARGIN + 132} 96 A 6 6 0 0 0 {MARGIN + 132} 108 Z" fill="{C_HALF}"/>'
        f'<text x="{MARGIN + 144}" y="107">半孔</text>'
        # 图例是固定尺寸的一行（字号 13 不参与缩放），三角形也照旧写死，别跟 OCT_MARK_* 联动
        f'<path d="M {MARGIN + 200} 92 l 6 11 h -12 Z" fill="{C_ACCENT}"/>'
        f'<text x="{MARGIN + 212}" y="107">超吹（第二八度，需加急气息）</text>'
        f'</g>'
        # 第 2 行图例：连尾减时线 / 连音线 / 切音 / 换气 / 反复记号（循环符号）
        f'<g font-size="13" fill="{C_TEXT}">'
        f'<line x1="{MARGIN + 8}" y1="124" x2="{MARGIN + 48}" y2="124" stroke="{C_TEXT}" '
        f'stroke-width="2.6" stroke-linecap="round"/>'
        f'<text x="{MARGIN + 54}" y="127">连尾减时线（同拍共用）</text>'
        f'<path d="M {MARGIN + 218} 128 Q {MARGIN + 234} 112 {MARGIN + 250} 128" fill="none" '
        f'stroke="{C_SLUR}" stroke-width="1.8" stroke-linecap="round"/>'
        f'<path d="M {MARGIN + 260} 128 Q {MARGIN + 276} 112 {MARGIN + 292} 128" fill="none" '
        f'stroke="{C_TIE}" stroke-width="1.8" stroke-linecap="round"/>'
        f'<text x="{MARGIN + 300}" y="127" font-size="12">连音线/延音线</text>'
        f'<text x="{MARGIN + 412}" y="128" font-size="14" font-weight="bold" '
        f'fill="{C_CUT}" text-anchor="middle">5</text>'
        f'<line x1="{MARGIN + 417}" y1="131" x2="{MARGIN + 428}" y2="120" '
        f'stroke="{C_CUT}" stroke-width="1.9" stroke-linecap="round"/>'
        f'<text x="{MARGIN + 434}" y="127" font-size="12">切音</text>'
        f'<text x="{MARGIN + 500}" y="127" font-size="{BREATH_SIZE}" fill="{C_BREATH}" '
        f'text-anchor="middle">v</text>'
        f'<text x="{MARGIN + 512}" y="127" font-size="12">换气</text>'
        f'<line x1="{MARGIN + 580}" y1="116" x2="{MARGIN + 580}" y2="136" '
        f'stroke="#999" stroke-width="1.2"/>'
        f'<line x1="{MARGIN + 585}" y1="116" x2="{MARGIN + 585}" y2="136" '
        f'stroke="{C_TEXT}" stroke-width="3.4"/>'
        f'<circle cx="{MARGIN + 592}" cy="121" r="2.2" fill="{C_TEXT}"/>'
        f'<circle cx="{MARGIN + 592}" cy="131" r="2.2" fill="{C_TEXT}"/>'
        f'<text x="{MARGIN + 602}" y="127" font-size="12">反复记号（循环）</text>'
        f'</g>'
        f'<line x1="{MARGIN}" y1="146" x2="{PAGE_WIDTH - MARGIN}" y2="146" '
        f'stroke="{C_ACCENT}" stroke-width="1.5"/>'
    )


def _watermark_svg(text: str, page: int, height: float) -> str:
    """淡淡的水印：整页斜排一行大字，压在谱面**下面**（先画），浓度极低。

    浓度固定 WATERMARK_OPACITY（0.10）：任何颜色打印都不影响阅读——
    灰白底上 10% 的灰几乎看不见，而谱面上的记号是后画的，永远在最上层。

    注意：**字号与位置都要按「本页实际高度」算**。最后一页是按内容裁短的
    （短谱可能只有 400 多 px 高），若按整张纸高去居中，水印会落进纸外的空白里。
    """
    text = (text or "").strip()
    if not text:
        return ""
    head = header_h(page == 0)
    band = max(1.0, height - head - FOOTER_H)       # 本页正文带（不含页眉页脚）
    cx = PAGE_WIDTH / 2
    cy = head + band / 2
    size = max(28.0, min(PAGE_WIDTH * 0.16, band * 0.34))
    return (f'<text x="{cx}" y="{cy}" font-size="{size:.0f}" font-weight="bold" '
            f'fill="{C_WATERMARK}" fill-opacity="{WATERMARK_OPACITY}" '
            f'text-anchor="middle" letter-spacing="6" '
            f'transform="rotate(-24 {cx} {cy})">{_esc(text)}</text>')


def _header_svg(page, n_pages, title, key, whistle_key, key_source, beats, n_notes) -> str:
    """页眉。首页是完整标题区（含图例），第二页起是紧凑页眉（省一行的高度）。"""
    total = f"　·　共 {n_pages} 页" if n_pages > 1 else ""
    if page == 0:
        source_tag = _KEY_SOURCE_TAG.get(key_source, "")
        try:
            mode = fingering.mode_label(whistle_key, key)
        except KeyError:
            mode = ""
        mode_tag = f"（筒音指法：{mode}）" if mode else ""
        beats_tag = f"　·　拍号 {_esc(beats)}" if beats else ""
        head_line = (f"1 = {key}{source_tag}{mode_tag}{beats_tag}　·　"
                     f"爱尔兰哨笛：{whistle_key} 调　·　共 {n_notes} 音")
        sub = head_line + total
        sub_size = _fit_font(sub, 15.0, min_size=10.0)
        return (
            f'<text x="{PAGE_WIDTH / 2}" y="46" font-size="{_fit_title_font(title):.0f}" '
            f'font-weight="bold" fill="{C_ACCENT}" text-anchor="middle">{_esc(title)}</text>'
            f'<text x="{PAGE_WIDTH / 2}" y="76" font-size="{sub_size:.1f}" fill="{C_TEXT}" '
            f'text-anchor="middle">{_esc(sub)}</text>'
            + _legend_svg()
        )
    return (
        f'<text x="{MARGIN}" y="42" font-size="20" font-weight="bold" fill="{C_ACCENT}">'
        f'{_esc(title)}</text>'
        f'<text x="{MARGIN}" y="68" font-size="13" fill="{C_TEXT}">'
        f'1 = {_esc(key)}　·　哨笛 {_esc(whistle_key)} 调　·　拍号 {_esc(beats)}'
        f'　·　第 {page + 1} / {n_pages} 页</text>'
        f'<line x1="{MARGIN}" y1="80" x2="{PAGE_WIDTH - MARGIN}" y2="80" '
        f'stroke="{C_ACCENT}" stroke-width="1.5"/>'
    )


def _footer_svg(page, n_pages, warnings, height) -> str:
    """页脚：页码 +（最后一页的）演奏提示。"""
    parts = []
    if warnings and page == n_pages - 1:
        wy = height - FOOTER_H - len(warnings) * FOOTER_PER_WARN + 12
        parts.append(f'<text x="{MARGIN}" y="{wy}" font-size="13" fill="{C_WARN}">提示：</text>')
        for j, w in enumerate(warnings, 1):
            parts.append(f'<text x="{MARGIN}" y="{wy + j * FOOTER_PER_WARN}" '
                         f'font-size="12" fill="{C_WARN}">{_esc(w)}</text>')
    parts.append(f'<text x="{PAGE_WIDTH - MARGIN}" y="{height - 12}" font-size="11" '
                 f'fill="#8b949c" text-anchor="end">第 {page + 1} / {n_pages} 页</text>')
    return "".join(parts)


def _page_height(page, n_rows_here, n_warnings) -> float:
    """本页高度。**最后一页按内容裁短**（不留一页大空白），中间的页就是整张纸。"""
    if page < N_PAGES - 1:
        return float(PAGE_HEIGHT)
    head = header_h(page == 0)
    extra = n_warnings * FOOTER_PER_WARN if n_warnings else 0
    return head + n_rows_here * row_height() + FOOTER_H + extra


def render_page(score, results, page=0, title="未命名", key="D", whistle_key="D",
                warnings=None, key_source="default", beats="", paper="", watermark="") -> str:
    """渲染**某一页**的 SVG。调用前请先跑过 _build_layout（render_svg_pages 会做）。"""
    warnings = warnings or []
    events = score.events
    rows_here = page_rows(page)
    height = _page_height(page, len(rows_here), len(warnings))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_WIDTH}" height="{height:.0f}" '
        f'viewBox="0 0 {PAGE_WIDTH} {height:.0f}" data-paper="{CURRENT_PAPER}" '
        f'data-row-measures="{CURRENT_ROW_MEASURES or "auto"}" '
        f'data-page="{page + 1}" data-pages="{N_PAGES}" '
        f'font-family="Segoe UI, Microsoft YaHei, sans-serif">',
        f'<rect width="{PAGE_WIDTH}" height="{height:.0f}" fill="#ffffff"/>',
        _watermark_svg(watermark, page, height),
        _header_svg(page, N_PAGES, title, key, whistle_key, key_source, beats,
                    len(score.notes)),
    ]
    for i, e in enumerate(events):
        if page_of(i) != page:
            continue
        x, w, y = _cell_x(i), _cell_w(i), _cell_row_top(i)
        if e.kind == "note":
            parts.append(_note_cell(e, results[e.index], x, y, w))
        else:
            parts.append(_simple_cell(e, x, y, w))
    # 连尾减时线层 + 连音线层：跨音符统一计算，保证规范
    parts.append(_beam_layer(events, beats, page=page))
    parts.append(_slur_layer(events, page=page))
    # 整段括号 + 结尾框：也是跨格的（从起点一直画到终点）
    parts.append(_bracket_layer(events, page=page))
    parts.append(_ending_layer(events, page=page))
    parts.append(_footer_svg(page, N_PAGES, warnings, height))
    parts.append('</svg>')
    return "".join(parts)


def render_svg(score, results, title="未命名", key="D", whistle_key="D",
               warnings=None, key_source="default", beats="", paper="",
               watermark="", row_measures=None, content_scale=None) -> str:
    """生成 SVG 谱面字符串（**第 1 页**；多页谱请用 render_svg_pages）。"""
    pages = render_svg_pages(score, results, title=title, key=key, whistle_key=whistle_key,
                             warnings=warnings, key_source=key_source, beats=beats,
                             paper=paper, watermark=watermark,
                             row_measures=row_measures, content_scale=content_scale)
    return pages[0] if pages else ""


def render_svg_pages(score, results, title="未命名", key="D", whistle_key="D",
                     warnings=None, key_source="default", beats="", paper="",
                     watermark="", row_measures=None, content_scale=None) -> list:
    """按纸张分页渲染，返回每页一个 SVG 字符串。

    分页由 `_build_layout` 一起算好（一行几个小节、绝不从小节中间换行、
    行不跨页），这里只负责逐页画出来。

    content_scale = 「谱面大小」（0.5~1.0 或 70 这样的百分数）。给 None 就按当前
    模块状态画（默认 1.0 = 原尺寸）；给了就**临时**套用、画完还原，
    所以它没有副作用，多页导出与直调 render 的测试互不干扰。
    """
    warnings = warnings or []
    ctx = (content_scale_ctx(content_scale) if content_scale is not None
           else contextlib.nullcontext(CONTENT_SCALE))
    with ctx:
        # _build_layout 先定下：歌词让位量、行高、列距、分页（页宽取决于纸张、每行小节数也在这里定）
        _build_layout(score.events, paper, row_measures)
        if not score.events:
            _build_layout([], paper, row_measures)
        return [render_page(score, results, page=p, title=title, key=key,
                            whistle_key=whistle_key, warnings=warnings,
                            key_source=key_source, beats=beats, paper=paper,
                            watermark=watermark)
                for p in range(N_PAGES)]


def render_index(items, index_title="哨笛洞洞谱合集") -> str:
    """批量总览 HTML。items: [(标题, svg文件名), ...]"""
    cards = []
    for title, fname in items:
        cards.append(
            f'<section class="card"><h2>{_esc(title)}</h2>'
            f'<a href="{_esc(fname)}" target="_blank">'
            f'<img src="{_esc(fname)}" alt="{_esc(title)}"></a></section>'
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{_esc(index_title)}</title>
<style>
body{{font-family:"Microsoft YaHei",sans-serif;background:#f4f6f8;margin:0;padding:24px}}
h1{{color:{C_ACCENT};text-align:center}}
.card{{background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.08);
padding:16px 20px;margin:20px auto;max-width:1260px}}
.card h2{{margin:4px 0 12px;color:{C_ACCENT};font-size:20px}}
.card img{{width:100%;border:1px solid #e3e7ea;border-radius:6px}}
</style></head><body>
<h1>{_esc(index_title)}</h1>
{''.join(cards)}
</body></html>"""
