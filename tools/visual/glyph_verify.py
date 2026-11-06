# -*- coding: utf-8 -*-
"""内嵌 FA 字形渲染验证（PrintWindow，z 序免疫）：截顶条右侧按钮区 3x 放大。
原 GlyphVerify.ps1。对已运行的宿主。
用法: py tools\\visual\\glyph_verify.py
截图: %TEMP%\\wm_captionbtns.png
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
    print("PRINTWINDOW_OK=True")
    # 顶条右侧：标题按钮区，3x 放大
    strip = img.crop((w - 340, 0, w, 30))
    strip.resize((1020, 90), Image.NEAREST).save(str(Path(tempfile.gettempdir(), "wm_captionbtns.png")))
    print("GLYPH_SHOT_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
