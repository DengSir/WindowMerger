# -*- coding: utf-8 -*-
"""内嵌 FA 字形渲染验证（PrintWindow，z 序免疫）：截顶条右侧按钮区，断言存在
ThemeText 色像素（字形画出来了=没缺字回退成空白/方块），存 3x 放大图人工复核。
原 GlyphVerify.ps1。
用法: py tools\\visual\\glyph_verify.py [--exe 路径]
警告: 强杀运行中的 WindowMerger。
截图: %TEMP%\\wm_captionbtns.png
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    # 强制深色（字形色 = Text 216,216,216 确定性；结束恢复 Auto）
    cfg = wm.load_config()
    cfg["Theme"] = "Dark"
    wm.save_config(cfg)
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.8)
    subprocess.Popen([a.exe])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    wm.set_window_pos(hm, None, 400, 150, 2200, 900, wm.SWP_NOZORDER)
    time.sleep(1.0)

    img = wm.capture_window(hm)
    w = img.width
    strip = img.crop((w - 340, 0, w, 30))
    strip.resize((1020, 90), Image.NEAREST).save(
        str(Path(tempfile.gettempdir(), "wm_captionbtns.png")))
    # 断言：按钮区存在字形色像素（>=15 个，阈值远低于实际字形像素量级）
    text_color = wm.PALETTES["Dark"]["Text"]
    n = sum(wm.color_close(strip.getpixel((x, y)), text_color)
            for x in range(0, 340, 2) for y in range(0, 30, 2))
    print(f"GLYPH_PIXELS={n} (expect >=15) {'OK' if n >= 15 else 'MISMATCH'}")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    cfg = wm.load_config()
    cfg["Theme"] = "Auto"
    wm.save_config(cfg)
    print("GLYPH_SHOT_DONE")
    ok = n >= 15
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
