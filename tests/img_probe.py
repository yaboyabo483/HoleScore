# -*- coding: utf-8 -*-
"""把一张图转成字符画（用无头 Edge 的 canvas + --dump-dom 取回文本）。

用法：
  python tests/img_probe.py <图片> [x0 y0 x1 y1] [列数]

为什么走浏览器：本机托管 Python 没有 PIL/Pillow，PowerShell 的 System.Drawing
又被安全策略拦；而 Edge 无头模式能跑 JS，把像素分析结果写进 DOM，
再用 --dump-dom 把文本读回来——顺便还能做对比度拉伸、投影分析。
"""

import os
import re
import subprocess
import sys

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "output", "_probe")

_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>probe</title></head>
<body><pre id="out">loading...</pre>
<script>
const COLS = __COLS__;
const CROP = __CROP__;
const GAMMA_LO = 0.02, GAMMA_HI = 0.98;
const RAMP = '@%#*+=-:. ';
const img = new Image();
img.onload = () => {
  const W = img.naturalWidth, H = img.naturalHeight;
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d'); g.drawImage(img, 0, 0);
  const d = g.getImageData(0, 0, W, H).data;
  const gray = new Float32Array(W * H);
  for (let i = 0, p = 0; i < d.length; i += 4, p++)
    gray[p] = 0.299 * d[i] + 0.587 * d[i+1] + 0.114 * d[i+2];
  const hist = new Uint32Array(256);
  for (let p = 0; p < gray.length; p++) hist[gray[p]|0]++;
  let lo = 0, hi = 255, acc = 0; const total = gray.length;
  for (let v = 0; v < 256; v++) { acc += hist[v]; if (acc >= total*GAMMA_LO) { lo = v; break; } }
  acc = 0;
  for (let v = 255; v >= 0; v--) { acc += hist[v]; if (acc >= total*(1-GAMMA_HI)) { hi = v; break; } }
  const st = new Float32Array(W * H);
  for (let p = 0; p < gray.length; p++)
    st[p] = Math.max(0, Math.min(1, (gray[p]-lo)/Math.max(1, hi-lo)));
  const box = CROP || {x0:0, y0:0, x1:W, y1:H};
  const bw = box.x1-box.x0, bh = box.y1-box.y0;
  const cw = bw / COLS;
  const ROWS = Math.max(1, Math.round(bh / (cw*2.05)));
  const ch = bh / ROWS;
  let lines = ['IMG '+W+'x'+H+'  stretch lo='+lo+' hi='+hi+'  crop '+bw+'x'+bh
               +'  cell '+cw.toFixed(2)+'x'+ch.toFixed(2)+'  grid '+COLS+'x'+ROWS];
  for (let r = 0; r < ROWS; r++) {
    let s = '';
    for (let q = 0; q < COLS; q++) {
      let sum = 0, n = 0;
      const x0 = box.x0+Math.floor(q*cw), x1 = Math.min(box.x1, box.x0+Math.ceil((q+1)*cw));
      const y0 = box.y0+Math.floor(r*ch), y1 = Math.min(box.y1, box.y0+Math.ceil((r+1)*ch));
      for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { sum += st[y*W+x]; n++; }
      const v = n ? sum/n : 1;
      s += RAMP[Math.min(RAMP.length-1, Math.floor((1-v)*RAMP.length))];
    }
    lines.push(String(r).padStart(3,' ')+'|'+s);
  }
  // 列向墨迹投影：暗像素比例，用于定位竖线 / 音符列（低对比照片阈值要放宽）
  const TH = 0.72;
  let p1 = '';
  for (let q = 0; q < COLS; q++) {
    let dark = 0, n = 0;
    const x0 = box.x0+Math.floor(q*cw), x1 = Math.min(box.x1, box.x0+Math.ceil((q+1)*cw));
    for (let y = box.y0; y < box.y1; y++)
      for (let x = x0; x < x1; x++) { if (st[y*W+x] < TH) dark++; n++; }
    const pct = n ? dark/n*100 : 0;
    p1 += pct >= 60 ? 'X' : pct >= 35 ? 'x' : pct >= 15 ? '.' : ' ';
  }
  lines.push('INK|' + p1);
  document.getElementById('out').textContent = lines.join('\\n');
};
img.onerror = () => { document.getElementById('out').textContent = 'LOAD ERROR'; };
img.src = 'ref.jpg';
</script></body></html>
"""


def probe(image: str, box=None, cols: int = 160, timeout: int = 60) -> str:
    """返回字符画文本（含尺寸/拉伸信息 + 列向墨迹投影）"""
    os.makedirs(TMP, exist_ok=True)
    import shutil

    shutil.copyfile(image, os.path.join(TMP, "ref.jpg"))
    html = _TEMPLATE.replace("__COLS__", str(cols)).replace(
        "__CROP__",
        "null" if not box else
        "{x0:%d,y0:%d,x1:%d,y1:%d}" % (box[0], box[1], box[2], box[3]),
    )
    page = os.path.join(TMP, "probe.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)
    r = subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", "--allow-file-access-from-files",
         "--virtual-time-budget=8000", "--dump-dom",
         "file:///" + page.replace("\\", "/")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout or "", re.S)
    if not m:
        raise RuntimeError("浏览器没有返回字符画（Edge 缺失或被拦？）")
    return (m.group(1).replace("&amp;", "&").replace("&lt;", "<")
            .replace("&gt;", ">").replace("&quot;", '"'))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    img = sys.argv[1]
    box = None
    cols = 160
    args = sys.argv[2:]
    if len(args) >= 4:
        box = tuple(int(v) for v in args[:4])
        args = args[4:]
    if args:
        cols = int(args[0])
    print(probe(img, box, cols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
