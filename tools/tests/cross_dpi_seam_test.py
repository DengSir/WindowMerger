# -*- coding: utf-8 -*-
"""跨 DPI 缝隙回归：96DPI mspaint（左侧 100% 屏）吸附进 150% 宿主（4K 主屏），
断言子窗口可见缘（ExtFrameBounds）与格子矩形四边 ≤1px（右缘 ≤2px，比例来自 config）。原 CrossDpiSeamTest.ps1。
用法: uv run tools/\tests\\cross_dpi_seam_test.py [--exe 路径]
左显示器不在/非 100% 时 SKIP。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

WM_CLOSE = 0x0010


def close_hosts_gracefully() -> None:
    for h in wm.top_windows_of_pids(wm.pids_by_name("WindowMerger")):
        wm.post_close(h)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    wm.set_dpi_aware_pm2()

    # 1. 优雅关运行中的宿主（持有 exe 锁、会干扰测试）
    close_hosts_gracefully()
    time.sleep(1.0)

    # 2. 拉起 mspaint，停到左显示器（预期 100%）
    mp = subprocess.Popen(["mspaint"])
    time.sleep(2.2)
    mphs = wm.top_windows_of_pids([mp.pid])
    if not mphs:
        print("FAIL_NO_MSPAINT")
        return 1
    mph = mphs[0]
    wm.set_window_pos(mph, None, -2300, 200, 1200, 800, wm.SWP_NOZORDER)
    time.sleep(0.9)
    mp_dpi = wm.get_dpi_for_window(mph)
    if mp_dpi != 96:
        wm.force_kill_pid(mp.pid)
        print(f"SKIP_LEFT_MONITOR_NOT_100PCT dpi={mp_dpi}")
        return 0

    # 3. 宿主 CLI 吸附（纯数字 = PID）；宿主开在 4K 主屏
    host = subprocess.Popen([a.exe, "--left", str(mp.pid)])
    time.sleep(3.5)
    hws = wm.top_windows_of_pids([host.pid])
    if not hws:
        wm.force_kill_pid(mp.pid)
        print("FAIL_NO_HOST")
        return 1
    hw = hws[0]

    # 4. 宿主固定大小停到 4K 固定位（config 尺寸可能巨大），等维护定时器收敛。
    #    2200x900 保证 ratio 0.5 时左格物理宽 ≥ mspaint 最小宽——704DIP×1.5=1056px
    #    （AGENTS 已知边界），左格需 ≥1056+18 外扩=1074 物理 px → 宿主 ≥ 2*1074+16。
    #    更窄会触发 OS 尺寸钳制（子窗口探出格子），缝隙断言就失去意义了
    wm.set_window_pos(hw, None, 400, 150, 2200, 900, wm.SWP_NOZORDER)
    time.sleep(2.5)

    # 5. 期望格子矩形（设备像素；XAML 常量：边框 2 DIP、顶条 28 DIP、分隔条 6 DIP；
    #    ratio 取 config.json = 宿主启动时加载的同一值）
    hr = wm.get_window_rect(hw)
    scale = wm.get_dpi_for_window(hw) / 96.0
    cr = wm.get_window_rect(mph)
    cf = wm.ext_frame_bounds(mph)

    ratio = 0.5
    try:
        ratio = float(wm.load_config().get("Ratio", 0.5)) or ratio
    except Exception:
        pass
    w_dip = hr.width / scale
    pane_l = hr.Left + round(2 * scale)
    pane_t = hr.Top + round((2 + 28) * scale)
    pane_b = hr.Bottom - round(2 * scale)
    # 子窗口吸附在左格：可见右缘 = 左格右缘（分隔条边）
    pane_r = hr.Left + round((2 + (w_dip - 4 - 6) * ratio) * scale)

    ok_l = abs(cf.Left - pane_l) <= 1
    ok_t = abs(cf.Top - pane_t) <= 1
    ok_r = abs(cf.Right - pane_r) <= 2
    ok_b = abs(cf.Bottom - pane_b) <= 1
    print(f"HOST rect=({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom}) "
          f"dpi={wm.get_dpi_for_window(hw)} scale={scale} ratio={ratio}")
    print(f"CHILD visible(extFB)=({cf.Left},{cf.Top})-({cf.Right},{cf.Bottom}) "
          f"liveMargins(L={cf.Left - cr.Left},T={cf.Top - cr.Top},"
          f"R={cr.Right - cf.Right},B={cr.Bottom - cf.Bottom})")
    print(f"PANE expect L={pane_l} T={pane_t} R={pane_r} B={pane_b}")
    print(f"LEFT {'PASS' if ok_l else 'FAIL'} (delta={cf.Left - pane_l})  "
          f"TOP {'PASS' if ok_t else 'FAIL'} (delta={cf.Top - pane_t})  "
          f"RIGHT {'PASS' if ok_r else 'FAIL'} (delta={cf.Right - pane_r})  "
          f"BOTTOM {'PASS' if ok_b else 'FAIL'} (delta={cf.Bottom - pane_b})")

    # 6. 清理：宿主优雅关（还原子窗口），测试 mspaint 强杀
    wm.post_close(hw)
    try:
        host.wait(timeout=6)
    except subprocess.TimeoutExpired:
        pass
    wm.force_kill_pid(mp.pid)
    if ok_l and ok_t and ok_r and ok_b:
        print("RESULT PASS")
        return 0
    print("RESULT FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
