# -*- coding: utf-8 -*-
"""顶条左侧（图标+标题）PrintWindow 截图 3x 放大 + 非空渲染断言（存在 ThemeText
色像素=标签文字画出来了）。原 TopBarLeftShot.ps1。
用法: uv run tools/\visual\\top_bar_left_shot.py [--exe 路径]
警告: 强杀运行中的 WindowMerger。
截图: %TEMP%\\wm_topbar_left.png
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
    strip = img.crop((0, 0, 300, 30))
    strip.resize((900, 90), Image.NEAREST).save(
        str(Path(tempfile.gettempdir(), "wm_topbar_left.png")))
    text_color = wm.PALETTES["Dark"]["Text"]
    n = sum(wm.color_close(strip.getpixel((x, y)), text_color)
            for x in range(0, 300, 2) for y in range(0, 30, 2))
    print(f"LABEL_PIXELS={n} (expect >=15) {'OK' if n >= 15 else 'MISMATCH'}")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    cfg = wm.load_config()
    cfg["Theme"] = "Auto"
    wm.save_config(cfg)
    print("LEFT_SHOT_DONE")
    ok = n >= 15
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
