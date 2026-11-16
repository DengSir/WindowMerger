# -*- coding: utf-8 -*-
r"""顶条按钮字形全套断言：UIA 读按钮的 AutomationId→Name 码点逐个比对期望值
（全部 Segoe Fluent/MDL2 字形——功能钮 2026-11-16 迁移，系统钮 266800b 起；FA 内嵌字体
已整体退役，主题菜单对勾 = E73E CaptionIcons），并截功能组按钮区 3x 放大图人工复核。
选窗左右钮/交换钮已随多布局退役（选窗 = 点空格提示按钮 _paneHint0，布局 = 四直排按钮）。
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
    "_layoutLrButton": "\uEE4D",         # EE4D 布局：左右两格（Fluent 专属，MDL2 无 EE 段）
    "_layoutLcrButton": "\uEA4B\uEA4C",  # 三列 SVG（icons8 column 系列）；Name 保留叠加码点串供断言
    "_layoutLtrButton": "\uEE4E",        # EE4E 布局：左+右列上下
    "_layoutQuadButton": "\uEE4F",       # EE4F 布局：四宫格
    "_releaseButton": "\uEA14",    # EA14 解散（Fluent）
    "_shortcutButton": "\uE72D",   # E72D 创建快捷方式（Fluent）
    "_themeButton": "\uE7A1",      # E7A1 跟随系统（Fluent；深色 E708/浅色 E706）
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
        exp = " ".join(f"U+{ord(c):X}" for c in expect)  # LCR 期望是两码点叠加串
        print(f"BTN {aid:<18} got=[{cps or 'EMPTY'}] expect={exp} {mark}")
    extra = set(found) - set(EXPECTED)
    if extra:
        print(f"EXTRA_BUTTONS: {extra}")

    # 功能组按钮区（布局×4 | 释放/快捷方式/主题 | 系统钮）3x 放大（人工复核渲染效果）
    img = wm.capture_window(hm)
    w = img.width
    crop = img.crop((w - 360, 0, w - 2, 30))
    crop.resize((1074, 90), Image.NEAREST).save(
        str(Path(tempfile.gettempdir(), "wm_pickbtns_zoom.png")))
    print("PICK_ZOOM_DONE")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("PICK_BTN_DUMP_DONE")
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
