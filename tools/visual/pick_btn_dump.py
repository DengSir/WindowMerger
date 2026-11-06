# -*- coding: utf-8 -*-
"""选窗按钮字形码点 dump（UIA Name）+ 两按钮区 4x 放大截图。原 PickBtnDump.ps1。
用法: py tools\\visual\\pick_btn_dump.py（对已运行的宿主）
截图: %TEMP%\\wm_pickbtns_zoom.png
"""
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia


def main() -> int:
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    main_el = wm_uia.element_from_handle(hm)
    for i, b in enumerate(wm_uia.find_all_buttons(main_el)):
        n = wm_uia.name_of(b)
        if n:
            cps = " ".join(f"U+{ord(ch):X4}" for ch in n)
            print(f"BTN[{i}] name-cps: {cps}")

    # 两个选窗按钮区 4x 放大（紧跟应用标签之后）
    img = wm.capture_window(hm)
    crop = img.crop((155, 0, 275, 30))
    crop.resize((480, 120), Image.NEAREST).save(
        str(Path(tempfile.gettempdir(), "wm_pickbtns_zoom.png")))
    print("PICK_ZOOM_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
