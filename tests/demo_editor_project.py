"""生成一份「编谱器出品」的样例工程与 SVG（演示编谱器的导出效果）

运行：python tests/demo_editor_project.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinwhistle import project as pj

TOKENS = [
    "1", "2", "|", "3/", "2/", "1", "6.", "|",
    "5.", "1", "2", "3", "|", "2", "-", "-", "|",
    "5/", "6/", "b7", "1'", "|", "2'", "3'", "2'", "1'", "|",
    "7", "6", "5/", "6/", "1'", "-", "-",
]


def main():
    proj = pj.new_project(title="编谱器示例-爱尔兰风格", key="D", whistle="D")
    for tk in TOKENS:
        doc = pj.token_to_doc(tk)
        if doc:
            proj["notes"].append(doc)
    # 演示「自选指法」：C 自然音（b7）用一个备选按法 ●●●○◐○（孔5半孔）
    for doc in proj["notes"]:
        if doc.get("kind") == pj.KIND_NOTE and doc.get("degree") == 7 and doc.get("accidental") == -1:
            doc["holes"] = [1, 1, 1, 0, 2, 0]
            break
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    path = pj.export_svg(proj, out_dir)
    save = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "projects", "演示工程.json")
    pj.save(proj, save)
    print("SVG :", path)
    print("工程:", save, f"（{len(proj['notes'])} 个事件）")


if __name__ == "__main__":
    main()
