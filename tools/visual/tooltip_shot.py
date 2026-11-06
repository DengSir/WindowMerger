# -*- coding: utf-8 -*-
"""Tooltip 主题检查：强制深/浅色各悬停主题按钮一次，Tooltip 是独立弹层必须
CopyFromScreen 全屏截，打印采样 RGB 像素做确定性校验，存 3x 放大裁片，
还原 NOTOPMOST + 优雅关。原 TooltipShot.ps1。
用法: uv run tools/\visual\\tooltip_shot.py
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

    results = []
    for theme in ("Dark", "Light"):
        pal = wm.PALETTES[theme]
        cfg = wm.load_config()
        cfg["Theme"] = theme
        wm.save_config(cfg)

        subprocess.Popen([wm.exe_path()])
        time.sleep(3)
        hosts = wm.host_hwnds()
        if not hosts:
            print(f"NO_HOST_{theme}")
            results.append(False)
            continue
        hm = hosts[0]
        # 固定布局钉位（主屏），采样坐标静态可推
        wm.set_window_pos(hm, None, 400, 150, 2200, 900, wm.SWP_NOZORDER)
        time.sleep(1.0)
        hr = wm.get_window_rect(hm)

        # 置顶让悬停到达宿主（最后还原）
        wm.set_topmost(hm, True)
        time.sleep(0.4)

        # 主题按钮中心：UIA 取真实矩形（按 DPI 写死偏移会落到别的按钮上，
        # 实测 150% 下 w-140 是最小化按钮）。悬停其上 tooltip 必为主题提示
        import uiautomation as auto
        main_el = auto.ControlFromHandle(hm)
        theme_btn = None
        for b in [c for c, _ in auto.WalkControl(main_el, includeTop=False, maxDepth=6)
                  if c.ControlTypeName == "ButtonControl"]:
            if (b.HelpText or "").startswith("主题"):
                theme_btn = b
                break
        if theme_btn is None:
            print(f"NO_THEME_BUTTON_{theme}")
            results.append(False)
            wm.set_topmost(hm, False)
            wm.graceful_close_by_name("WindowMerger")
            time.sleep(1.5)
            continue
        rect = theme_btn.BoundingRectangle
        bx, by = int((rect.left + rect.right) / 2), int((rect.top + rect.bottom) / 2)
        wm.set_cursor_pos(bx, by)
        time.sleep(1.2)  # tooltip 初始延迟 + 淡入

        cap_w, cap_h = 340, 90
        cap_x = bx - 80
        cap_y = hr.Top
        big = wm.capture_screen(0, 0, 3840, 2160)  # 主屏全幅（4K）

        # 确定性取色：顶条（文字上方干净区）+ tooltip 内部网格（字形间隙，众数 = tooltip 底色）
        bar = big.getpixel((hr.Left + 60, hr.Top + 5))[:3]
        bar_ok = wm.color_close(bar, pal["Bar"])
        print(f"BAR_{theme} rgb({bar[0]},{bar[1]},{bar[2]}) expect={pal['Bar']} {'OK' if bar_ok else 'MISMATCH'}")
        tip_samples = []
        for dy in (40, 46, 52):
            for dx in (0, 20, 60, 100, 140):
                p = big.getpixel((bx + dx, hr.Top + dy))[:3]
                tip_samples.append(p)
        n_hit = sum(wm.color_close(p, pal["Bar"]) for p in tip_samples)
        tip_ok = n_hit >= 5  # 网格多数命中 tooltip 底色（其余采样落在文字/边框上）
        print(f"TIP_{theme} bg_hits={n_hit}/15 expect={pal['Bar']} {'OK' if tip_ok else 'MISMATCH'}")

        crop = big.crop((cap_x, cap_y, cap_x + cap_w, cap_y + cap_h))
        crop.resize((cap_w * 3, cap_h * 3), Image.NEAREST).save(
            str(Path(tempfile.gettempdir(), f"wm_tooltip_{theme}.png")))
        print(f"SHOT_{theme} at ({cap_x},{cap_y})")
        results.append(bar_ok and tip_ok)

        # 还原 NOTOPMOST、优雅关、等完全退出
        wm.set_topmost(hm, False)
        wm.graceful_close_by_name("WindowMerger")
        time.sleep(1.5)

    # 恢复用户主题设置
    cfg = wm.load_config()
    cfg["Theme"] = "Auto"
    wm.save_config(cfg)
    print("TOOLTIP_SHOT_DONE")
    ok = len(results) == 2 and all(results)
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
