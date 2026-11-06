# -*- coding: utf-8 -*-
"""Tooltip 主题检查：强制深/浅色各悬停主题按钮一次，Tooltip 是独立弹层必须
CopyFromScreen 全屏截，打印采样 RGB 像素做确定性校验，存 3x 放大裁片，
还原 NOTOPMOST + 优雅关。原 TooltipShot.ps1。
用法: py tools\\visual\\tooltip_shot.py
截图: %TEMP%\\wm_tooltip_Dark.png / wm_tooltip_Light.png
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    # 比例复位，保证按钮坐标计算稳定
    cfg = wm.load_config()
    cfg["Ratio"] = 0.5
    wm.save_config(cfg)

    for theme in ("Dark", "Light"):
        cfg = wm.load_config()
        cfg["Theme"] = theme
        wm.save_config(cfg)

        subprocess.Popen([wm.exe_path()])
        time.sleep(3)
        hosts = wm.host_hwnds()
        if not hosts:
            print(f"NO_HOST_{theme}")
            continue
        hm = hosts[0]
        hr = wm.get_window_rect(hm)

        # 置顶让悬停到达宿主（最后还原）
        wm.set_topmost(hm, True)
        time.sleep(0.4)

        # 主题按钮中心：[左][右][交换][释放][主题]|分隔| [─][□][✕]
        bx = hr.Right - 140
        by = hr.Top + 16
        wm.set_cursor_pos(bx, by)
        time.sleep(1.2)  # tooltip 初始延迟 + 淡入

        cap_w, cap_h = 340, 90
        cap_x = bx - 80
        cap_y = hr.Top
        big = wm.capture_screen(0, 0, 2560, 1440)

        # 确定性取色：顶条（文字上方干净区）+ tooltip 内部网格（字形间隙，众数 = tooltip 底色）
        bar = big.getpixel((hr.Left + 60, hr.Top + 5))
        print(f"BAR_{theme} rgb({bar[0]},{bar[1]},{bar[2]})")
        for dy in (40, 46, 52):
            for dx in (0, 20, 60, 100, 140):
                p = big.getpixel((bx + dx, hr.Top + dy))
                print(f"TIP_{theme} d({dx},{dy}) rgb({p[0]},{p[1]},{p[2]})")

        crop = big.crop((cap_x, cap_y, cap_x + cap_w, cap_y + cap_h))
        crop.resize((cap_w * 3, cap_h * 3), Image.NEAREST).save(
            str(Path(tempfile.gettempdir(), f"wm_tooltip_{theme}.png")))
        print(f"SHOT_{theme} at ({cap_x},{cap_y})")

        # 还原 NOTOPMOST、优雅关、等完全退出
        wm.set_topmost(hm, False)
        wm.graceful_close_by_name("WindowMerger")
        time.sleep(1.5)

    # 恢复用户主题设置
    cfg = wm.load_config()
    cfg["Theme"] = "Auto"
    wm.save_config(cfg)
    print("TOOLTIP_SHOT_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
