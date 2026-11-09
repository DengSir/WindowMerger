# -*- coding: utf-8 -*-
"""跨 DPI 缝隙回归：96DPI mspaint 吸附进非 96 DPI（150%）宿主，
断言子窗口可见缘（ExtFrameBounds）与格子矩形四边 ≤1px（右缘 ≤2px，比例来自 config）。
原 CrossDpiSeamTest.ps1。
这是"屏幕超出/跨屏"豁免类测试（不走 test_layout 的 1024x768 预算）：自选显示器——
一块 96 DPI 屏停 mspaint、一块更高 DPI 屏停宿主；任一缺失则 SKIP（本机单 100% 屏 /
CI 必 SKIP）。用法: uv run tools/\tests\\cross_dpi_seam_test.py [--exe 路径]
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

    # 2. 选屏：一块 96 DPI + 一块非 96 DPI（DPI 差异才是被测对象，不限于 150%）
    mon96 = [mi for mi in wm.monitors() if wm.monitor_dpi(mi) == 96]
    monhi = [mi for mi in wm.monitors() if wm.monitor_dpi(mi) != 96]
    if not mon96 or not monhi:
        dpis = [wm.monitor_dpi(mi) for mi in wm.monitors()]
        print(f"SKIP_NO_DPI_PAIR dpis={dpis} （需要 96 + 非 96 两块屏）")
        return 0
    lo, hi = mon96[0], monhi[0]

    # 3. 拉起 mspaint，停到 96 DPI 屏
    mp = subprocess.Popen(["mspaint"])
    time.sleep(2.2)
    mphs = wm.top_windows_of_pids([mp.pid])
    if not mphs:
        print("FAIL_NO_MSPAINT")
        return 1
    mph = mphs[0]
    wa = lo.rcWork
    wm.set_window_pos(mph, None, wa.Left + 40, wa.Top + 200, 1200, 800, wm.SWP_NOZORDER)
    time.sleep(0.9)
    mp_dpi = wm.get_dpi_for_window(mph)
    if mp_dpi != 96:
        wm.force_kill_pid(mp.pid)
        print(f"SKIP_LEFT_MONITOR_NOT_100PCT dpi={mp_dpi}")
        return 0

    # 4. 宿主 CLI 吸附（纯数字 = PID）；宿主开在高 DPI 屏
    host = subprocess.Popen([a.exe, "--left", str(mp.pid)])
    time.sleep(3.5)
    hws = wm.top_windows_of_pids([host.pid])
    if not hws:
        wm.force_kill_pid(mp.pid)
        print("FAIL_NO_HOST")
        return 1
    hw = hws[0]

    # 5. 宿主固定大小停到高 DPI 屏（config 尺寸可能巨大），等维护定时器收敛。
    #    宽度保证 ratio 0.5 时左格物理宽 ≥ mspaint 最小宽——704DIP×(dpi/96)（AGENTS
    #    已知边界，150% 即 1056px，左格需 ≥1056+18 外扩=1074 → 宿主 ≥ 2*1074+16）。
    #    更窄会触发 OS 尺寸钳制（子窗口探出格子），缝隙断言就失去意义了；屏装不下则 SKIP
    hscale = wm.monitor_dpi(hi) / 96.0
    need_w = round(704 * hscale) * 2 + 20
    need_h = round(536 * hscale)
    hwa = hi.rcWork
    host_w = need_w + 68  # 与 test_layout 同款余量
    host_h = need_h
    if (host_w > hwa.Right - hwa.Left - 40 or host_h > hwa.Bottom - hwa.Top - 40):
        wm.force_kill_pid(mp.pid)
        wm.post_close(hw)
        print(f"SKIP_HI_MONITOR_TOO_SMALL need={need_w}x{need_h} "
              f"wa={hwa.Right - hwa.Left}x{hwa.Bottom - hwa.Top}")
        return 0
    hx = hwa.Left + 20
    hy = hwa.Top + (hwa.Bottom - hwa.Top) - 20 - host_h
    wm.set_window_pos(hw, None, hx, hy, host_w, host_h, wm.SWP_NOZORDER)
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
