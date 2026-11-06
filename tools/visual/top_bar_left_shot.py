# -*- coding: utf-8 -*-
"""顶条左侧（图标+标题）PrintWindow 截图 3x 放大。原 TopBarLeftShot.ps1。对已运行的宿主。
用法: py tools\\visual\\top_bar_left_shot.py
截图: %TEMP%\\wm_topbar_left.png
"""
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    img = wm.capture_window(hm)
    print("PRINTWINDOW_OK=True")
    strip = img.crop((0, 0, 300, 30))
    strip.resize((900, 90), Image.NEAREST).save(
        str(Path(tempfile.gettempdir(), "wm_topbar_left.png")))
    print("LEFT_SHOT_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
