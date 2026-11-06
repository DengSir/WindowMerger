# -*- coding: utf-8 -*-
"""顶条右侧（标题按钮区）PrintWindow 截图 2x 放大。原 SideBtnShot.ps1。对已运行的宿主。
用法: py tools\\visual\\side_btn_shot.py
截图: %TEMP%\\wm_sidebtns.png
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
    w = img.width
    strip = img.crop((w - 340, 0, w, 30))
    strip.resize((680, 60), Image.NEAREST).save(str(Path(tempfile.gettempdir(), "wm_sidebtns.png")))
    print("SIDE_SHOT_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
