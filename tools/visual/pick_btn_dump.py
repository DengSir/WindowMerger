# -*- coding: utf-8 -*-
r"""顶条按钮字形全套断言：UIA 读 9 个按钮的 AutomationId→Name 码点逐个比对期望值
（功能组按钮同时验证 FA 内嵌字体没有缺字回退——Name 来自按钮 Content；系统钮三件
= Segoe Fluent/MDL2 原版字形，266800b 起），并截两选窗按钮区 4x 放大图人工复核。
原 PickBtnDump.ps1。
用法: uv run tools/visual/pick_btn_dump.py [--exe 路径]
警告: 强杀运行中的 WindowMerger。
截图: %TEMP%/wm_pickbtns_zoom.png
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia

# 空宿主态的期望字形（x:Name → 按钮文本）
EXPECTED = {
    "_pickLeftButton": "\uf060",   # ←
    "_pickRightButton": "\uf061",  # →
    "_swapButton": "\uf0ec",       # ⇄
    "_releaseButton": "\uf127",    # ⛓
    "_shortcutButton": "\uf360",   # 📎
    "_themeButton": "\uf042",      # ◐（跟随系统）
    "_minimizeButton": "\uE921",   # E921 最小化（Fluent/MDL2 原版字形）
    "_maxButton": "\uE922",        # E922 最大化（最大化态 UpdateMaxGlyph 切 E923）
    "_closeButton": "\uE8BB",      # E8BB 关闭
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.8)
    subprocess.Popen([a.exe])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1

    main_el = wm_uia.element_from_handle(hm)
    found: dict[str, str] = {}
    for b in wm_uia.find_all_buttons(main_el):
        aid = wm_uia.automation_id_of(b)
        if aid:
            found[aid] = wm_uia.name_of(b)

    ok = True
    for aid, expect in EXPECTED.items():
        got = found.get(aid)
        hit = got == expect
        ok = ok and hit
        mark = "OK" if hit else "MISMATCH"
        cps = " ".join(f"U+{ord(c):X}" for c in (got or ""))
        print(f"BTN {aid:<18} got=[{cps or 'EMPTY'}] expect=U+{ord(expect):X} {mark}")
    extra = set(found) - set(EXPECTED)
    if extra:
        print(f"EXTRA_BUTTONS: {extra}")

    # 两选窗按钮区 4x 放大（人工复核渲染效果）
    img = wm.capture_window(hm)
    crop = img.crop((155, 0, 275, 30))
    crop.resize((480, 120), Image.NEAREST).save(
        str(Path(tempfile.gettempdir(), "wm_pickbtns_zoom.png")))
    print("PICK_ZOOM_DONE")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("PICK_BTN_DUMP_DONE")
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
