# -*- coding: utf-8 -*-
"""开发用：Tk 窗口抓屏（DPI 正确版）。

给 `tests/editor_shot.py` / `tests/preview_shot.py` 共用。

**为什么不能直接 CopyFromScreen**：本机显示器是 150% 缩放，而 Tk 与外部截图进程
都是 DPI-unaware。Tk 报的是虚拟坐标（1707x1067），`CopyFromScreen` 却把这些数字
当**物理像素**用 → 真实位置 = Tk 坐标 x 1.5，不换算就偏半屏（踩过很久）。
Tk 也问不出真实缩放（`winfo_fpixels("1i")/96` 恒为 1），所以让一个临时置为
DPI-aware 的 PowerShell 报物理分辨率，再除以 Tk 的虚拟宽度。

另外：**窗口别只占屏幕一小块**。抓屏抓的是屏幕像素，别的窗口会从边缘挤进来。
用 `win.state("zoomed")` 铺满，或像预览那样**只抓目标矩形**（`ox/oy/w/h`）。
"""

import subprocess
import sys
import tkinter as tk

__all__ = ["screen_scale", "shot"]

_SHOT_SCALE = None


def screen_scale():
    """物理像素 / Tk 逻辑像素（本机 2560x1600 物理 vs 1707x1067 逻辑 = 1.5）"""
    global _SHOT_SCALE
    if _SHOT_SCALE is None:
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -MemberDefinition "
            "'[DllImport(\"user32.dll\")] public static extern bool SetProcessDPIAware();'"
            " -Name U -Namespace W;"
            "[W.U]::SetProcessDPIAware() | Out-Null;"
            "$sc=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
            'Write-Output ("$($sc.Width) $($sc.Height)")'
        )
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True)
        txt = (r.stdout or b"").decode("utf-8", "replace").split()
        phys_w = float(txt[0]) if txt and txt[0].isdigit() else 0.0
        t = tk.Tk()
        t.withdraw()
        t.update()
        virt_w = float(t.winfo_screenwidth())
        t.destroy()
        _SHOT_SCALE = (phys_w / virt_w) if phys_w > 0 and virt_w > 0 else 1.0
    return _SHOT_SCALE


def shot(win, path, ox=0, oy=0, w=None, h=None):
    """抓 `win` 的一块（默认整窗）。ox/oy/w/h 按 Tk 逻辑像素给，返回值也是逻辑尺寸。

    内部按物理像素抓（更清晰），再缩回逻辑尺寸输出——README 配图不用那么大。
    """
    sf = screen_scale()
    lw = float(w if w is not None else win.winfo_width())
    lh = float(h if h is not None else win.winfo_height())
    gx, gy = int((win.winfo_rootx() + ox) * sf), int((win.winfo_rooty() + oy) * sf)
    gw, gh = int(lw * sf), int(lh * sf)
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        f"$b=New-Object System.Drawing.Bitmap({gw},{gh});"
        "$g=[System.Drawing.Graphics]::FromImage($b);"
        f"$g.CopyFromScreen({gx},{gy},0,0,$b.Size);"
        f"$o=New-Object System.Drawing.Bitmap({int(lw)},{int(lh)});"
        "$h2=[System.Drawing.Graphics]::FromImage($o);"
        "$h2.InterpolationMode="
        "[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic;"
        f"$h2.DrawImage($b,(New-Object System.Drawing.Rectangle(0,0,{int(lw)},{int(lh)})));"
        f"$b.Dispose();$o.Save('{path}');$o.Dispose()"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True)
    if r.returncode != 0:
        print("  抓屏失败 rc=%s" % r.returncode, file=sys.stderr)
    return int(lw), int(lh)
