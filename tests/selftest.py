"""自测脚本（零依赖，托管 Python 直接运行）

覆盖：
  - jianpu：简谱文本解析（时值、八度、调号头/显式调、休止符）；
  - fingering：筒音指法口径（全按只属于第一八度，更高八度一律「放开孔1」）；
  - render/project：端到端生成 SVG + 工程导出落盘，minidom 校验合法性；
  - imageout：截图超时兜底用的「PNG 是否写完」判定（不需要浏览器）；
  - project 读写：分块保存与 json.dump 逐字节一致、保存/读取的进度回调、多页 PNG 并行与取消。

运行: python tests/selftest.py
"""

from __future__ import annotations

import array
import json
import os
import sys
import tempfile
import time
import xml.dom.minidom

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinwhistle import fingering, jianpu, project as pj, render  # noqa: E402

PASSED = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASSED.append(name)
        print(f"  [OK] {name}")
    else:
        raise AssertionError(f"{name} 失败 {detail}")


def gen_svg(text: str, title: str, key=None, whistle: str = "D", beats: str = "4/4"):
    """简谱文本 -> (第 1 页 SVG, ParsedScore, warnings)。

    走的就是编谱器导出那套 render 调用（文字谱只是另一种入口）。
    """
    score = jianpu.parse(text, key=key)
    if beats:
        score.events = jianpu.insert_auto_bars(score.events, beats)
    results, warnings = fingering.map_score(score.events, score.tonic, whistle)
    pages = render.render_svg_pages(score, results, title=title, key=score.key,
                                    whistle_key=whistle, warnings=warnings,
                                    key_source=score.key_source, beats=beats)
    return pages[0], score, warnings


# ---------------------------------------------------------------- jianpu
def test_jianpu() -> None:
    print("== jianpu ==")
    s = jianpu.parse("1=G\n5/ 3// 2 1' 6. - 0 |", key=None)
    check("文本调号生效", s.key == "G" and s.key_source == "text" and s.tonic == 7)
    kinds = [e.kind for e in s.events]
    check("事件序列", kinds == ["note"] * 5 + ["hold", "rest", "bar"], str(kinds))
    durs = [e.duration for e in s.notes]
    check("时值解析", durs == [0.5, 0.25, 1.0, 1.0, 1.0], str(durs))
    check("八度解析", s.notes[3].octave == 1 and s.notes[4].octave == -1)

    s2 = jianpu.parse("1=G 5 3", key="C")
    check("显式调优先且调号头剔除", s2.key == "C" and s2.key_source == "param"
          and len(s2.notes) == 2)

    s3 = jianpu.parse("5 3 2")
    check("默认调 D", s3.key == "D" and s3.key_source == "default" and s3.tonic == 2)

    check("normalize_key", jianpu.normalize_key("Bb") == "bB"
          and jianpu.normalize_key("#f") == "#F"
          and jianpu.normalize_key("♭E") == "bE"
          and jianpu.normalize_key("H") is None)
    try:
        jianpu.parse("5 3", key="X")
        check("非法调抛错", False)
    except ValueError:
        check("非法调抛错", True)

    s4 = jianpu.parse("0/ 0//")
    check("休止符时值", [e.duration for e in s4.events] == [0.5, 0.25])


# ---------------------------------------------------------------- 端到端渲染
def test_render(tmp: str) -> None:
    print("== render ==")
    svg, score, _w = gen_svg("1=G\n5/ 3/ 2 1 - 0 | 1' 7 6. 5 - 6.// 5/", "自测样例")
    check("解析摘要", score.key == "G" and score.key_source == "text"
          and len(score.notes) == 10, f"{score.key}/{score.key_source}")
    xml.dom.minidom.parseString(svg)   # 不抛异常即合法 XML
    check("SVG 合法 XML", True)
    check("标题区调号来源", "1 = G（谱内标注）" in svg)
    n_lines = svg.count('stroke-width="2.6"')
    # 连尾减时线（连续横线）：同拍 5/ 3/ 连成 1 条；6.// 5/ 连成主 1 条 + 十六分 1 条；
    # 再加图例里那 1 条示例，共 4 条。
    check("连尾减时线数量", n_lines == 4, f"got {n_lines}")  # 1(同拍) + 1+1(十六分组) + 1(图例)
    check("高八度点渲染", 'r="2.4"' in svg)

    # 超高音自动移八度：给出提示且单元正上方仍有简谱记号
    svg2, _s2, w2 = gen_svg("1=C\n1''' 2 3", "移八度自测")
    check("移八度提示", any("已自动" in w for w in w2), str(w2))
    check("移八度只在页脚警示里说，音符下面不压小字（曾经有个 (已移八度)）",
          "(已移八度)" not in svg2 and any("已自动" in w for w in w2))
    xml.dom.minidom.parseString(svg2)
    check("移八度 SVG 合法", True)

    # 防御性分支：playable=False 单元（当前 fingering 恒 playable，直接构造验证渲染）
    e = jianpu.parse("5", key="D").events[0]
    bad = fingering.FingeringResult(playable=False, note_name="G", reason="自测")
    cell = render._note_cell(e, bad, 40, 150)
    check("警示单元正上方有简谱记号",
          cell.index(">5<") < cell.index("超出音域"), cell[:200])
    xml.dom.minidom.parseString(f'<svg xmlns="http://www.w3.org/2000/svg">{cell}</svg>')
    check("警示单元 SVG 片段合法", True)

    # 显式调号来源标注
    svg3, _s3, _w3 = gen_svg("5 3 2 1", "指定调自测", key="F")
    check("指定调标注", "1 = F（指定）" in svg3)


# ---------------------------------------------------------------- 工程导出落盘
def test_project_export(tmp: str) -> None:
    print("== project 导出 ==")
    out_dir = os.path.join(tmp, "out")
    proj = pj.new_project("自测样例", "G", "D", "4/4", True)
    proj["notes"] = [pj.token_to_doc(t) for t in
                     "5/ 3/ 2 1 6. 5 | 1' 7 6. 5".split()]
    paths = pj.export_svg_pages(proj, out_dir)
    check("单页导出文件名 = 曲名.svg",
          [os.path.basename(p) for p in paths] == ["自测样例.svg"],
          str([os.path.basename(p) for p in paths]))
    check("导出的文件真的落盘", all(os.path.isfile(p) for p in paths))
    with open(paths[0], encoding="utf-8") as f:
        svg = f.read()
    xml.dom.minidom.parseString(svg)
    check("导出的 SVG 合法且是对的曲子", 'data-paper="A4"' in svg and "自测样例" in svg)

    # 参数优先于工程里存的值（编谱器导出面板就是这么传的）
    forced = pj.export_svg_pages(proj, out_dir, paper="B4", watermark="内部")
    check("导出参数优先于工程里的值",
          'data-paper="B4"' in open(forced[0], encoding="utf-8").read()
          and "内部" in open(forced[0], encoding="utf-8").read())

    # 工程存取往返
    saved = os.path.join(tmp, "p.json")
    check("工程存得住", pj.load(pj.save(proj, saved))["notes"] == proj["notes"])


def test_png_guard(tmp: str) -> None:
    """截图超时的兜底：只有**写完的** PNG 才能当成功（半截文件不行）。

    背景：有的机器上无头浏览器截完图赖着不退出，subprocess 会报超时，而图其实已经好了。
    这时靠 `imageout._is_complete_png` 认（PNG 头 + 以 IEND 收尾 + 不是空壳）。
    """
    from tinwhistle import imageout
    body = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200 + b"IEND\xaeB`\x82"
    good = os.path.join(tmp, "good.png")
    with open(good, "wb") as f:
        f.write(body)
    check("写完的 PNG 认得出来（超时兜底靠它）", imageout._is_complete_png(good))
    half = os.path.join(tmp, "half.png")
    with open(half, "wb") as f:
        f.write(body[:-8])                 # 少了 IEND
    check("半截 PNG 不算成功", not imageout._is_complete_png(half))
    tiny = os.path.join(tmp, "tiny.png")
    with open(tiny, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
    check("太小的不算成功", not imageout._is_complete_png(tiny))
    check("不存在的文件不算成功",
          not imageout._is_complete_png(os.path.join(tmp, "nope.png")))


def test_save_chunked(tmp: str) -> None:
    """分块保存必须与 `json.dump(indent=1)` **逐字节一致**。

    工程 JSON 是给人看、给 diff 看的（缩进 1 空格）。保存之所以要分块，是为了让
    进度条能按「第 N/M 个音」推进；代价是「拼出来的字符串」容易跟 json.dump 差一个
    空格 —— 那样每次保存的 diff 会整片乱跳。所以这里把几种形状都钉死。
    """
    print("== 分块保存 ==")
    cases = {}
    empty = pj.new_project("空工程")
    cases["空工程"] = empty
    small = pj.new_project("小曲", "G", "D", "3/4", False)
    small["notes"] = [pj.token_to_doc(t) for t in "5 3 2".split()]
    small["notes"][0]["lyric"] = ["啦", "啦"]
    cases["3 单元+歌词"] = small
    full = pj.new_project("全字段", "F", "C", "6/8", True)
    full["notes"] = [pj.token_to_doc(t) for t in "1 2 3 4 5 6 7 | 1'".split()]
    full["notes"][1]["holes"] = [1, 0, 1, 0, 1, 0]
    full["paper"] = "B4"
    full["watermark"] = "内部资料"
    full["scale"] = 3
    full["content_scale"] = 0.8
    full["row_measures"] = 5
    cases["全字段"] = full
    many = pj.new_project("很多音")
    many["notes"] = [pj.token_to_doc(t) for t in ["5"] * 300]
    cases["300 音"] = many

    for name, proj in cases.items():
        got = "".join(piece for piece, _n in pj.iter_save_pieces(proj))
        # 拼出来的文本重新解析一次、再按 json.dump(indent=1) 的规则渲染，应当一模一样
        # —— 差一个空格就会让每次保存的 diff 整片乱跳。（不看 saved_at，它是时间戳）
        canon = json.dumps(json.loads(got), ensure_ascii=False, indent=1)
        check(f"分块保存与 json.dump 逐字节一致（{name}）", got == canon,
              _first_diff(got, canon))
        want_obj = {k: v for k, v in proj.items() if k != "_path"}
        want_obj["version"] = pj.DOC_VERSION
        obj = json.loads(got)
        check(f"分块保存不缺字段、值也不走样（{name}）",
              set(obj) == set(want_obj)
              and all(obj[k] == v for k, v in want_obj.items() if k != "saved_at"),
              str(sorted(set(obj) ^ set(want_obj))))
        path = os.path.join(tmp, f"chunk_{name}.json")
        pj.save(proj, path)
        with open(path, encoding="utf-8") as f:
            disk = f.read()
        check(f"落盘内容同样一致（{name}）",
              disk == json.dumps(json.loads(disk), ensure_ascii=False, indent=1))
        check(f"存盘后再读出来自洽（{name}）",
              pj.load(path)["notes"] == proj["notes"])


def _first_diff(got: str, want: str) -> str:
    for i, (a, b) in enumerate(zip(got, want)):
        if a != b:
            return f"第 {i} 字符：got {got[max(0, i - 20):i + 20]!r} want {want[max(0, i - 20):i + 20]!r}"
    return f"长度不同 {len(got)} vs {len(want)}"


def test_io_progress(tmp: str) -> None:
    """保存/读取的进度回调：单调不回头，且一定走到终点。

    进度条靠这些数字推进，回调要是「跳一下又退回去」或者「永远到不了 100%」，
    界面上的条就会抽风或者一直停在半截。
    """
    print("== 读写进度 ==")
    proj = pj.new_project("进度自测")
    proj["notes"] = [pj.token_to_doc(t) for t in ["5", "3", "2", "1"] * 50]
    total = len(proj["notes"])

    seen = []
    path = os.path.join(tmp, "prog.json")
    pj.save(proj, path, progress=lambda d, t, l: seen.append((d, t, l)))
    check("保存进度不回头", all(a[0] <= b[0] for a, b in zip(seen, seen[1:])),
          str(seen[:6]))
    check("保存进度总数 = 音数", all(t == total for _d, t, _l in seen), str(seen[:3]))
    check("保存进度走到终点", seen and seen[-1][0] == total, str(seen[-3:]))
    check("保存进度带说明文字", any("个音" in l for _d, _t, l in seen), str(seen[:3]))

    seen2 = []
    data = pj.load(path, progress=lambda d, t, l: seen2.append((d, t, l)))
    check("读取进度不回头", all(a[0] <= b[0] for a, b in zip(seen2, seen2[1:])),
          str(seen2))
    check("读取进度到 100", seen2 and seen2[-1][0] == 100, str(seen2[-3:]))
    check("读取进度按百分比（total 恒 100）", all(t == 100 for _d, t, _l in seen2))
    check("读取的内容没错", len(data["notes"]) == total, len(data["notes"]))

    # 空工程也不能卡在 0/0（除零会让进度条显示成 NaN）
    seen3 = []
    pj.save(pj.new_project("空"), os.path.join(tmp, "empty.json"),
            progress=lambda d, t, l: seen3.append((d, t, l)))
    check("空工程保存的进度条不会是 0/0", seen3 and seen3[-1][0] == seen3[-1][1] > 0,
          str(seen3))


def test_png_parallel(tmp: str) -> None:
    """多页 PNG 并行：每页都要出图，取消后不再开新的页（不真起浏览器）。

    真起无头浏览器一页要一秒多，测试里不划算；这里把 `svg_to_png` 换成桩，
    只验证「并行调度 + 进度 + 取消」这套逻辑，出图本身另有 test_png_guard 兜底。
    """
    print("== 多页 PNG 并行 ==")
    from tinwhistle import imageout

    def fake_svg_to_png(svg_text, out_path, width=0, height=0, scale=1, timeout=0):
        with open(out_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64 + b"IEND\xaeB`\x82")
        time.sleep(0.05)
        return out_path

    orig = imageout.svg_to_png
    imageout.svg_to_png = fake_svg_to_png
    try:
        pages = ["<svg/>"] * 6
        seen = []
        paths = imageout.pages_to_png(pages, tmp, "并行", scale=1,
                                      progress=lambda d, t, l: seen.append((d, t)))
        check("6 页并行出 6 张图", len(paths) == 6, str(paths))
        check("并行出的图都在盘上", all(os.path.isfile(p) for p in paths))
        check("文件名按 名称-1… 排号",
              [os.path.basename(p) for p in paths]
              == [f"并行-{i}.png" for i in range(1, 7)],
              str([os.path.basename(p) for p in paths]))
        check("并行也会逐页报进度（走到 6/6）",
              seen and seen[-1] == (6, 6), str(seen[-3:]))

        # 取消：跑完第 1 页就喊停，剩下的页不该再开
        hits = {"n": 0}

        def counting(svg_text, out_path, **kw):
            hits["n"] += 1
            return fake_svg_to_png(svg_text, out_path)

        imageout.svg_to_png = counting
        out2 = os.path.join(tmp, "cancel")
        os.makedirs(out2, exist_ok=True)
        paths2 = imageout.pages_to_png(["<svg/>"] * 8, out2, "取消", scale=1,
                                       cancel=lambda: hits["n"] >= 1)
        check("取消后不再开新的页（出图次数远小于页数）",
              len(paths2) < 8 and hits["n"] < 8, f"{len(paths2)} 张 / 起了 {hits['n']} 次")
        check("取消后已完成的那几页照常留下",
              all(os.path.isfile(p) for p in paths2), str(paths2))
    finally:
        imageout.svg_to_png = orig
    check("PNG_WORKERS 是个正整数", isinstance(imageout.PNG_WORKERS, int)
          and imageout.PNG_WORKERS >= 1, str(imageout.PNG_WORKERS))


def test_sound(tmp: str) -> None:
    """试听：音高口径 + 事件序列 + 播放线程的「能停 / 最新请求胜出」+ 合成出来的音色。

    真发声会吵（CI 上也没有音频设备），所以把 `sound._tone` / `sound._stop_now` 换成桩：
    只验「该响什么、响多久、能不能立刻停下来」，以及合成出来的波形对不对，不验声音本身。
    """
    print("== 试听（合成音色） ==")
    from tinwhistle import sound

    # 音高口径：哨笛的**实际发声** = 哨笛调性 + 指法索引（不是简谱上写的八度）
    check("D 哨笛筒音 = D4（294Hz）", sound.hz_for_midi(sound.midi_for_index(0, "D")) == 294,
          str(sound.hz_for_midi(sound.midi_for_index(0, "D"))))
    check("D 哨笛高一个八度 = D5（587Hz）",
          sound.hz_for_midi(sound.midi_for_index(12, "D")) == 587,
          str(sound.hz_for_midi(sound.midi_for_index(12, "D"))))
    check("C 哨笛筒音 = C4（262Hz，与 D 哨笛差两个半音）",
          sound.hz_for_midi(sound.midi_for_index(0, "C")) == 262,
          str(sound.hz_for_midi(sound.midi_for_index(0, "C"))))
    check("频率落在可发声的范围里",
          sound.hz_for_midi(0) >= sound.MIN_HZ and sound.hz_for_midi(127) <= sound.MAX_HZ,
          f"{sound.hz_for_midi(0)} / {sound.hz_for_midi(127)}")
    check("不可吹的音不给频率", sound.hz_for_result(None) is None
          and sound.hz_for_result(_fake_result(False, -1)) is None)
    check("谱面上的音名与听到的音是一对（1'=D5）",
          sound.hz_of_doc(pj.token_to_doc("1'"), "D", "D") == 587,
          str(sound.hz_of_doc(pj.token_to_doc("1'"), "D", "D")))
    check("休止 / 延音 / 小节线没音高可响",
          all(sound.hz_of_doc(pj.token_to_doc(t), "D", "D") is None
              for t in ("0", "-", "|")))
    # 自选指法按**孔位的实际发声**响（不是简谱上写的音）
    custom = pj.token_to_doc("3")
    custom["holes"] = [0, 1, 1, 1, 1, 1]      # 放开孔1 = 筒音高八度 D5
    check("自选指法按孔位发声（放开孔1 → D5）",
          sound.hz_of_doc(custom, "D", "D") == 587,
          str(sound.hz_of_doc(custom, "D", "D")))

    # **被搬过八度的音，试听要响谱面上写的那个音**。指法为了塞进哨笛的两个八度音域，
    # 会把超出音域的音整体搬一个八度（`shifted`）—— 指法图照搬是对的（只按得出那些孔），
    # 但照搬去响就成了「谱面写高音、耳朵听到低音」。下面这两个音都在音域外，正是这条的锁。
    check("搬过八度的高音：响谱面写的那个（1=A 的 5' = E6 1319Hz，不是 E5 659Hz）",
          sound.hz_of_doc(pj.token_to_doc("5'"), "A", "D") == 1319,
          str(sound.hz_of_doc(pj.token_to_doc("5'"), "A", "D")))
    check("搬过八度的低音同理（1=C 的 5. = G3 196Hz，不是 G4 392Hz）",
          sound.hz_of_doc(pj.token_to_doc("5."), "C", "D") == 196,
          str(sound.hz_of_doc(pj.token_to_doc("5."), "C", "D")))

    # 事件序列：音符 / 休止（静音占时间）/ 延音（接在前一个音后）/ 小节线（跳过）
    proj = pj.new_project("试听")
    proj["notes"] = [pj.token_to_doc(t) for t in ("1", "0/", "5'", "-")]
    proj["notes"][1]["duration"] = 0.5
    seq = sound.sequence(proj, bpm=120)        # 120 → 四分音符 500ms
    hzs = [hz for hz, _ms, _i in seq]
    check("整首序列只留有时值的单元（小节线/记号不占时间）", len(seq) == 3, str(seq))
    check("休止是静音（hz=None）但照样占时间", hzs[1] is None and seq[1][1] == 250, str(seq[1]))
    # 延音接在**紧挨着的前一个单元**后面继续响（这里是 5'，所以 500+500=1000）
    check("延音接在前一个音后面继续响", seq[2][0] == 880 and seq[2][1] == 1000, str(seq[2]))
    check("时值按 bpm 换算（120 → 四分 500ms）", seq[0][1] == 500, str(seq[0]))
    # 延音前面是休止 → 不该凭空冒出声音
    proj2 = pj.new_project("试听2")
    proj2["notes"] = [pj.token_to_doc("0"), pj.token_to_doc("-")]
    check("延音前面是休止时不出声", sound.sequence(proj2) == [(None, 750, 0)],
          str(sound.sequence(proj2)))
    check("单音试听时长夹在 90~600ms（太短听不出音高，太长让人等）",
          sound.preview_ms(pj.token_to_doc("1")) == 600
          and sound.preview_ms(pj.token_to_doc("1'")) == 600)

    # ---------------- 音色：自己合成的那段波形 ----------------
    frames = sound.synth_frames(440.0, 200)
    s = array.array("h")
    s.frombytes(frames)
    peak = max(abs(v) for v in s)
    check("200ms 的音合成出对得上的采样点数",
          len(s) == int(round(200 / 1000.0 * sound.SAMPLE_RATE)), len(s))
    check("合成音不削波也不至于听不见", 8000 < peak < 32767, str(peak))
    check("首尾是淡入淡出（不再是 Beep 那种爆音）",
          abs(s[0]) < 200 and abs(s[-1]) < 200, f"首 {s[0]} / 末 {s[-1]}")
    s90 = array.array("h")
    s90.frombytes(sound.synth_frames(880.0, 90))
    check("90ms 的极短音包络按比例收，不会被淡出吃光",
          8000 < max(abs(v) for v in s90) < 32767, str(max(abs(v) for v in s90)))

    # 十六分音符：以前交给 Beep 是「咔」一声，现在是一段完整的采样
    p16 = pj.new_project("十六分")
    p16["notes"] = [pj.token_to_doc(t) for t in ("1//", "2//", "3//", "4//")]
    for n in p16["notes"]:
        n["duration"] = 0.25
    seq16 = sound.sequence(p16, bpm=100)          # 100bpm → 十六分 = 150ms
    check("十六分音符进节目单是一整段音（不再是被 Beep 吃成的一声响）",
          len(seq16) == 4 and all(hz and ms == 150 for hz, ms, _i in seq16), str(seq16))
    s16 = array.array("h")
    s16.frombytes(sound.synth_frames(880.0, 150))
    check("150ms 的十六分音符照样合成得出来（听得出音高的那一段）",
          len(s16) == int(round(150 / 1000.0 * sound.SAMPLE_RATE))
          and max(abs(v) for v in s16) > 8000,
          f"{len(s16)} 采样 / 峰值 {max(abs(v) for v in s16)}")

    # 同一个「音高+时长档」复用同一个缓存文件（别每个音都写一遍盘）
    t1 = sound.ensure_tone(440, 200)
    t2 = sound.ensure_tone(440, 205)
    t3 = sound.ensure_tone(880, 200)
    check("同一档时长复用同一个音色文件", t1 == t2, f"{t1} / {t2}")
    check("不同音高是不同的文件", t1 != t3, f"{t1} / {t3}")
    check("音色文件是真 wav（RIFF 头）",
          open(t1, "rb").read(4) == b"RIFF" and os.path.getsize(t1) > 1000,
          str(os.path.getsize(t1)))

    # ---------------- Beeper：能停 / 最新请求胜出 ----------------
    played, stops = [], []
    orig_tone, orig_stop = sound._tone, sound._stop_now

    def fake_tone(hz, ms):          # 异步口吻：记一笔就返回，不等时间
        played.append((hz, ms))

    def fake_stop():
        stops.append(1)

    sound._tone, sound._stop_now = fake_tone, fake_stop
    try:
        bp = sound.Beeper()
        bp.submit([(440, 300, 1), (550, 300, 2), (660, 300, 3)])
        _wait_until(lambda: played == [(440, 300)], 2.0)
        n_played, n_stops = len(played), len(stops)
        check("第一个音已经在响（用例前提成立）", n_played == 1, str(played))
        bp.stop()
        # 以前这里要等这个音放完（最长 3 秒）才轮到线程去看 flag，用户就以为按了没反应
        check("停止立刻掐音（不用等这个音放完）", len(stops) == n_stops + 1, str(stops))
        time.sleep(0.45)            # 剩下的两个音本来会在这个窗口里响出来
        check("停下之后后面的音一个都不响", len(played) == n_played, str(played))
        check("stop 之后 busy 为假（不再有待播的节目）", not bp.busy())

        played.clear()
        bp.submit([(330, 40, 9)])
        _wait_until(lambda: not bp.busy(), 5.0)
        check("单个音照样播完", played == [(330, 40)], str(played))

        # 休止要把可能在响的声音掐掉，再静静地占时间
        stops.clear()
        played.clear()
        bp.submit([(None, 100, None)])
        _wait_until(lambda: stops, 2.0)
        check("休止先把声音掐掉再计时", bool(stops) and not played, str(stops))

        # 最新请求胜出：连按 ←→ 不该追着响一串旧的
        played.clear()
        bp.submit([(440, 300, 1), (440, 300, 2), (440, 300, 3)])
        time.sleep(0.05)
        bp.submit([(880, 30, 7)])
        _wait_until(lambda: not bp.busy(), 5.0)
        check("最新请求胜出（旧节目不再接着响）",
              played == [(440, 300), (880, 30)], str(played))
        bp.close()
    finally:
        sound._tone, sound._stop_now = orig_tone, orig_stop
        sound.cleanup_tones()


def _fake_result(playable: bool, index: int):
    from tinwhistle import fingering
    return fingering.FingeringResult(playable=playable, index=index)


def _wait_until(fn, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.02)
    return False


def test_fingering() -> None:
    """筒音指法口径：**全按只属于第一八度**，往上的每个八度都是「放开孔1、其余全按」。

    回归锁——这里原来只写了 `idx == 12` 一条特例，于是指法表第 13 格（筒音高一个八度，
    标签 `5`）放开孔1，末格（高两个八度，标签 `5'`）却掉回 `_FIRST_OCTAVE[0]` 画成全按：
    同一个音名在两个八度里给出了互相矛盾的指法。所以下面不只锁 12，而是把「往上每一格」
    一起锁住，以后谁再把口径改回特例都会红。
    """
    print("== fingering ==")
    closed, top_open = (1, 1, 1, 1, 1, 1), (0, 1, 1, 1, 1, 1)

    check("第一八度筒音 idx 0 = 全按", fingering.fingering_for_index(0) == closed)
    check("高一个八度的筒音 idx 12 = 放开孔1",
          fingering.fingering_for_index(12) == top_open)
    check("高两个八度的筒音 idx 24 = 放开孔1（不许退回全按）",
          fingering.fingering_for_index(24) == top_open)

    # 通则：整个音域里**只有**第一八度的筒音是全按
    all_closed = [i for i in range(fingering.MAX_INDEX + 1)
                  if fingering.fingering_for_index(i) == closed]
    check("全音域只有 idx 0 是全按", all_closed == [0], str(all_closed))

    highers = [i for i in range(fingering.MAX_INDEX + 1) if i % 12 == 0][1:]
    check("is_high_tonic 只认 12 的正整数倍",
          [i for i in range(fingering.MAX_INDEX + 1) if fingering.is_high_tonic(i)]
          == highers, str(highers))
    check("更高八度的筒音一律取 HIGH_TONIC（不是特例）",
          highers == [12, 24]
          and all(fingering.fingering_for_index(i) == fingering.HIGH_TONIC
                  for i in highers), str(highers))

    # 反查：全按仍然认作**第一八度**的筒音（手点孔位不该被认成高八度）
    check("反查 全按 -> 筒音 D（不是 D 高）",
          fingering.describe_holes(closed, "D") == ("D", True),
          str(fingering.describe_holes(closed, "D")))
    check("反查 放开孔1 -> D 高",
          fingering.describe_holes(top_open, "D") == ("D 高", True),
          str(fingering.describe_holes(top_open, "D")))

    # 备选指法：每个高八度筒音都保留「全按硬吹」
    check("高八度筒音的备选里保留全按硬吹",
          all(list(fingering.map_note(12 * k, 2, "D").alternates) == [closed]
              for k in (1, 2)))


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="tw_selftest_")
    test_jianpu()
    test_fingering()
    test_render(tmp)
    test_project_export(tmp)
    test_save_chunked(tmp)
    test_io_progress(tmp)
    test_png_parallel(tmp)
    test_png_guard(tmp)
    test_sound(tmp)
    print(f"\n全部通过：{len(PASSED)} 项检查")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
