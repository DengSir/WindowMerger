# -*- coding: utf-8 -*-
"""悬停视觉测试：光标移到 分隔条/远离/最大化/关闭 上，各 PrintWindow 截顶条条带。
强制深色保证颜色确定（结束恢复 Auto）。原 HoverVisualTest.ps1。
用法: uv run tools/\visual\\hover_visual_test.py
警告: 强杀运行中的 WindowMerger；需 notepad/mspaint 可被 CLI 吸附。
截图: %TEMP%\\wm_hover_*.png
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    # 强制深色（确定性预期；结束恢复 Auto）
    cfg = wm.load_config()
    cfg["Theme"] = "Dark"
    cfg["Ratio"] = 0.5
    wm.save_config(cfg)

    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.8)
    subprocess.Popen([wm.exe_path(), "--left", "notepad", "--right", "mspaint"])
    time.sleep(4)

    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    hr = wm.get_window_rect(hm)
    w = hr.width
    wm.set_topmost(hm, True)  # 悬停才能到达宿主
    time.sleep(0.4)

    pal = wm.PALETTES["Dark"]
    results = []

    def snap(tag: str) -> None:
        time.sleep(0.4)
        img = wm.capture_window(hm)
        strip = img.crop((0, 0, w, 30))
        strip.save(str(Path(tempfile.gettempdir(), f"wm_hover_{tag}.png")))
        print(f"SHOT_{tag}")
        snap.img = img

    def check(tag: str, x: int, y: int, expected: tuple, ok: bool) -> None:
        px = snap.img.getpixel((x, y))[:3]
        hit = wm.color_close(px, expected)
        print(f"PIX_{tag} rgb=({px[0]},{px[1]},{px[2]}) expect={expected} {'OK' if hit else 'MISMATCH'}")
        results.append(ok and hit)

    # 分隔条中心（比例 0.5）：悬停高亮蓝
    avail = w - 4 - 8
    div_x = int(hr.Left + 2 + avail * 0.5 + 4)
    wm.set_cursor_pos(div_x, (hr.Top + hr.Bottom) // 2)
    snap("divider")
    check("DIVIDER_HOVER", div_x - hr.Left, hr.height // 2, pal["DividerHover"], True)

    # 移开 → 基态（分隔条回到普通色，不得残留高亮）
    wm.set_cursor_pos(6, 700)
    snap("away")
    check("DIVIDER_BASE", div_x - hr.Left, hr.height // 2, pal["Divider"], True)

    # 最大化按钮（普通悬停：浅灰）。按钮宽 36 DIP：close 占右缘 33 DIP，max 中心 =
    # w-(3+54·scale)（150% 下即 w-84）；100% 下写死 w-84 会落到左侧相邻按钮上、
    # 靠悬停色相同侥幸通过。采样取按钮顶部无字形区（正中是 □ 字形，会采到反锯齿边）
    scale = wm.get_dpi_for_window(hm) / 96.0
    max_cx = int(3 + 54 * scale)
    wm.set_cursor_pos(hr.Right - max_cx, hr.Top + 16)
    snap("max")
    check("MAX_HOVER", w - max_cx, 5, pal["ButtonHover"], True)

    # 关闭按钮（危险悬停：红）。100% 下按钮 36px 宽，(w-22,16) 正压 ✕ 字形会采到
    # 反锯齿混色（CI 实测 214,198,197）——采样取按钮顶部无字形区
    wm.set_cursor_pos(hr.Right - 22, hr.Top + 16)
    snap("close")
    check("CLOSE_HOVER", w - 22, 4, pal["DangerHover"], True)

    # 再移开
    wm.set_cursor_pos(6, 700)
    snap("away2")

    wm.set_topmost(hm, False)

    # 恢复用户设置
    cfg = wm.load_config()
    cfg["Theme"] = "Auto"
    wm.save_config(cfg)
    print("HOVER_TEST_DONE")
    ok = len(results) == 4 and all(results)
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
