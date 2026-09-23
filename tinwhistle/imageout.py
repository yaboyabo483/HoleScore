"""SVG 谱面 → PNG 图片（按页分文件、可选倍率）

为什么走浏览器：谱面里的汉字、简谱数字、弧线都要**真实字形**，纯 Python 画不出来。
用系统自带的 Edge/Chrome 无头模式截图，既不用装第三方库，又是**矢量按目标像素重画**——
1x/2x/3x 得到的是真分辨率，不是把 1x 放大糊掉。

坑（踩过）：
  * Edge/Chrome 无头模式**进程 0.1 秒就退出，图片要等半秒到两秒才落盘**（截图交给后台进程写）。
    所以截图后必须"轮询等文件出现"，直接 `subprocess.run` 完就检查会误判成失败。
  * `--force-device-scale-factor=N` 配 `--window-size=W,H` 时出图尺寸并不等于 W*N，
    所以倍率不靠它：先把 SVG 的 width/height 改成缩放后的值，再按该尺寸开窗口截图。
  * 给一个独立 `--user-data-dir`，避免去连用户正开着的浏览器实例。
  * **别用 `text=True` 抓浏览器的输出**：它的日志是 UTF-8，中文 Windows 的代码页是 GBK，
    严格解码会在 subprocess 的读取线程里抛 `UnicodeDecodeError`（见 procutil）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from . import procutil

# 常见安装位置（Edge 是 Windows 自带的，Chrome 兜底）
BROWSER_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/microsoft-edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)
SIZES = (1, 2, 3, 4, 5)    # 支持的倍率。1x = 纸张像素（A4 约 794×1123）；
                           # 想印大图 / 放大看细节就往上调，5x 的 A4 约 3970×5615 px。
                           # 都是**矢量按目标像素重画**（不是把 1x 位图放大糊掉），
                           # 代价只是导出更慢、文件更大——所以默认仍走 1x。
DEFAULT_SCALE = 1          # 默认 1 倍：页面像素 = 纸张像素，导出快、文件小
TIMEOUT = 180

# 同时开几个无头浏览器栅格化。单页 ≈ 1s（本机的量），启动是主要开销，所以并行是划算的：
# 实测 12 页 —— 串行 15.2s / 2 路 9.4s / 3 路 9.2s / 4 路 7.4s。
# 不往上加：这台机器上十来个无头实例会互相抢资源，反而每张都变慢（见 MEMORY.md 的孤儿事件）。
PNG_WORKERS = 4

_browser_cache: str | None = None


def find_browser() -> str | None:
    """找一个能用的 Chromium 内核浏览器；找不到返回 None。"""
    global _browser_cache
    if _browser_cache and os.path.isfile(_browser_cache):
        return _browser_cache
    for cand in BROWSER_CANDIDATES:
        if os.path.isfile(cand):
            _browser_cache = cand
            return cand
    for name in ("msedge", "chrome", "chromium", "microsoft-edge"):
        hit = shutil.which(name)
        if hit:
            _browser_cache = hit
            return hit
    return None


def normalize_scale(scale) -> int:
    """把倍率收进 SIZES；非法值退回默认。"""
    try:
        s = int(round(float(scale)))
    except (TypeError, ValueError):
        return DEFAULT_SCALE
    return s if s in SIZES else DEFAULT_SCALE


def svg_size(svg_text: str) -> tuple:
    """读 SVG 根节点上写死的 width/height（找不到就退回 A4 竖版尺寸）。"""
    m = re.search(r'<svg[^>]*?width="([\d.]+)"[^>]*?height="([\d.]+)"', svg_text)
    if not m:
        return 794.0, 1123.0
    return float(m.group(1)), float(m.group(2))


def scale_svg(svg_text: str, scale: float) -> str:
    """把 SVG 根节点的 width/height 乘上倍率（矢量重画，不是位图放大）。"""
    w, h = svg_size(svg_text)
    m = re.search(r'<svg[^>]*?width="[\d.]+"[^>]*?height="[\d.]+"', svg_text)
    if not m:
        return svg_text
    head = m.group(0)
    sw, sh = round(w * scale), round(h * scale)
    new_head = re.sub(r'width="[\d.]+"', f'width="{sw}"', head, count=1)
    new_head = re.sub(r'height="[\d.]+"', f'height="{sh}"', new_head, count=1)
    # viewBox 不动：放大只是让同样一张矢量图按更大的像素栅格画出来
    return svg_text[:m.start()] + new_head + svg_text[m.end():]


def svg_to_png(svg_text: str, png_path: str, scale: float = DEFAULT_SCALE,
               browser: str | None = None) -> str:
    """把一段 SVG 写成 PNG 文件，返回 png 路径。找不到浏览器时抛 RuntimeError。

    坑（踩过）：Edge/Chrome 无头模式**进程 0.1 秒就退出，图片要再等半秒到两秒才落盘**
    （截图交给后台进程写），所以不能 `subprocess.run` 完就检查文件——必须轮询等它出现，
    而且**要等到了再删临时 SVG**，否则后台进程可能读到半个文件。
    """
    browser = browser or find_browser()
    if not browser:
        raise RuntimeError("没有找到 Edge/Chrome，无法把 SVG 转成图片；"
                           "可先用「导出 SVG」再用浏览器另存为图片")
    scale = float(scale)
    w, h = svg_size(svg_text)
    sw, sh = max(1, round(w * scale)), max(1, round(h * scale))
    png_path = os.path.abspath(png_path)
    if os.path.exists(png_path):
        os.remove(png_path)
    tmp = tempfile.mkdtemp(prefix="tinwhistle_png_")
    try:
        tmp_svg = os.path.join(tmp, "page.svg")
        with open(tmp_svg, "w", encoding="utf-8") as f:
            f.write(scale_svg(svg_text, scale))
        prof = os.path.join(tmp, "profile")        # 独立 profile：不去连已在运行的浏览器
        os.makedirs(prof, exist_ok=True)
        cmd = [
            browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--no-first-run", "--no-default-browser-check",
            "--user-data-dir=" + prof,
            f"--window-size={sw},{sh}",
            "--screenshot=" + png_path,
            "file:///" + tmp_svg.replace("\\", "/"),
        ]
        try:
            # 走 procutil：**不能**用 text=True 让它按本机代码页解码。无头浏览器的日志是
            # UTF-8，中文 Windows 的代码页是 GBK，严格解码会在 subprocess 的读取线程里抛
            # UnicodeDecodeError（主线程只看到 stderr 变成 None，控制台却打一整段 traceback）。
            proc = procutil.run_capture(cmd, TIMEOUT, encoding="utf-8")
        except subprocess.TimeoutExpired as exc:
            # 有的机器上无头浏览器**截完图赖着不退出**（卡在自更新 / 扩展注册表 / 同步握手，
            # 日志里刷 external_registry_loader、sync ERR_ABORTED）。这时 subprocess 会报
            # 超时，但图其实早就写好了 —— 只要 PNG 是完整的就不能算失败，否则用户会看到
            # 「导出失败」而磁盘上其实躺着一张好图（踩过：单张要 180s+ 后报错，图却在）。
            if _is_complete_png(png_path):
                return png_path
            raise RuntimeError(
                f"调用浏览器截图失败：{browser} 超过 {int(TIMEOUT)} 秒没有出图。"
                "常见原因：无头浏览器卡住（后台自更新 / 扩展同步握手超时）。"
                "手动打开一次这个浏览器、或重启后再试；也可先用「导出 SVG」再用浏览器另存为图片。"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"调用浏览器截图失败：{exc}") from exc
        if not _wait_for_file(png_path):
            detail = (proc.stderr or proc.stdout or "").strip()[:200]
            if not detail:      # 宽松解码之后仍然啥都没有：给个能查下去的方向
                detail = "浏览器没有输出任何信息（试试手动打开临时 SVG，或检查杀软拦截）"
            raise RuntimeError(f"浏览器没有输出图片（{browser}）：{detail}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return png_path


def _is_complete_png(path: str) -> bool:
    """这个文件是不是一张**写完**的 PNG（存在、非空、以 IEND 块收尾）。

    用来判「超时了但图其实好了」——半截文件不能当成功。
    """
    try:
        if not os.path.isfile(path) or os.path.getsize(path) < 100:
            return False
        with open(path, "rb") as f:
            return f.read(8) == b"\x89PNG\r\n\x1a\n" and _tail(f) == b"IEND\xaeB`\x82"
    except OSError:
        return False


def _tail(f, n: int = 8) -> bytes:
    """读文件最后 n 个字节（PNG 的结尾是 IEND + CRC 正好 8 字节，PNG 里不会有填充）"""
    try:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - n))
        return f.read(n)
    except OSError:
        return b""


def _wait_for_file(path: str, timeout: float = 30.0) -> bool:
    """等文件落盘（无头浏览器是异步写图的，进程退出并不代表图已写完）。"""
    deadline = time.monotonic() + timeout
    last = -1
    while time.monotonic() < deadline:
        if os.path.exists(path):
            size = os.path.getsize(path)
            if size > 100 and size == last:        # 大小稳定下来才算写完
                return True
            last = size
        time.sleep(0.15)
    return os.path.exists(path) and os.path.getsize(path) > 100


def page_name(base_name: str, page: int, total: int, ext: str = ".svg") -> str:
    """页面文件名：单页 = `曲名.svg`；多页 = `曲名-1.svg` / `曲名-2.svg` …"""
    return f"{base_name}-{page + 1}{ext}" if total > 1 else f"{base_name}{ext}"


def pages_to_png(pages, out_dir: str, base_name: str,
                 scale: float = DEFAULT_SCALE, progress=None, cancel=None,
                 max_workers: int = 0) -> list:
    """把多页 SVG 写成 PNG：单页 = 曲名.png，多页 = 曲名-1.png / 曲名-2.png …

    **并行**栅格化（每页一次无头浏览器调用，启动是主要开销，所以并行划算）。
    每页都用**自己独立**的临时 profile 与临时 SVG，浏览器之间不共享状态
    （共享 `--user-data-dir` 会被 Edge 的 SingletonLock 挡住，反而更慢）。

    progress(done, total, label)：每**完成**一页回调一次，label 是给界面看的文字。
    cancel()：返回 True 就不再开新的页——已经在跑的那几页照旧跑完（各约 1 秒），
              返回已完成的文件列表，由调用方决定怎么提示。
    max_workers：并发路数，0/不传 = PNG_WORKERS（再按页数夹一次）。
    """
    scale = normalize_scale(scale)
    os.makedirs(out_dir, exist_ok=True)
    total = len(pages)
    if not total:
        return []
    workers = max(1, min(int(max_workers) or PNG_WORKERS, total))
    done = [0]
    lock = threading.Lock()
    stopped = threading.Event()

    def _stopped() -> bool:
        if stopped.is_set():
            return True
        if cancel is not None and cancel():
            stopped.set()
            return True
        return False

    def _one(i: int):
        if stopped.is_set():
            return i, None
        path = os.path.join(out_dir, page_name(base_name, i, total, ".png"))
        svg_to_png(pages[i], path, scale=scale)
        with lock:
            done[0] += 1
            n = done[0]
        if progress:
            progress(n, total, f"第 {i + 1}/{total} 页")
        return i, path

    out: list = [None] * total
    if workers == 1:
        for i in range(total):
            if _stopped():
                break
            _i, p = _one(i)
            out[_i] = p
        return [p for p in out if p]

    out: list = [None] * total
    # 「滚动提交」：一次只挂 workers 个，完成一个再补一个。
    # 一次性把整批 submit 进去的话，cancel() 根本没机会被调用（任务早就排进队列了，
    # 浏览器被全部开起来）—— 多页导出恰恰是最需要能取消的场景。
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pngpage") as ex:
        pending: set = set()
        nxt = 0
        while nxt < total and not _stopped():
            pending.add(ex.submit(_one, nxt))
            nxt += 1
        while pending:
            done_futs, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done_futs:
                try:
                    i, p = fut.result()
                except Exception:      # 有一页出错就收手，别继续把浏览器开满
                    stopped.set()
                    for f in pending:
                        f.cancel()
                    raise
                out[i] = p
            while nxt < total and not _stopped():     # 补位（取消后就不再开新的）
                pending.add(ex.submit(_one, nxt))
                nxt += 1
    return [p for p in out if p]
