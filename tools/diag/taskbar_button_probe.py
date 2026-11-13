# -*- coding: utf-8 -*-
"""诊断：任务栏按钮图标的分组行为实验（AUMID 分组层，多实例并存时按钮图标取谁）。
E1 = 仅一个接管实例（两 Tk 子窗）→ 期望按钮 = 拼接图标（基线）
E2 = 先起一个空实例（应用图标）再起接管实例 → 同 AUMID 分组，看按钮出几个、图标是什么

用法: uv run tools/diag/taskbar_button_probe.py
输出: %TEMP%\\wm_tb_e1.png / wm_tb_e2.png（按钮像素 4x 放大）+ 控制台按钮清单
"""
import subprocess
import sys
import time
from pathlib import Path
from tempfile import gettempdir

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia

TARGET_SCRIPT = Path(__file__).resolve().parents[1] / "targets" / "snap_target.py"
EXE = wm.exe_path()


def wait_host(pid: int, timeout_s: float = 8.0) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        wins = wm.main_windows_of_pid(pid)
        if wins:
            return wins[0]
        time.sleep(0.1)
    return 0


def wait_attached(*hwnds: int, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if all(wm.is_attached(h) for h in hwnds):
            return True
        time.sleep(0.2)
    return False


def shoot_taskbar(tag: str) -> None:
    """UIA 定位含 窗口合并/WindowMerger 的按钮，裁剪像素 4x 放大存 PNG。"""
    tb = wm_uia.taskbar()
    if tb is None:
        print(f"  {tag}: NO_TASKBAR")
        return
    buttons = wm_uia.dump_taskbar_buttons()
    print(f"  {tag}: buttons={buttons}")
    for needle in ("窗口合并", "WindowMerger"):
        btn = wm_uia.find_by_name(tb, needle)
        if btn is not None:
            x, y, bw, bh = wm_uia.bounding_rect_of(btn)
            scr_w = wm.get_system_metrics(wm.SM_CXSCREEN)
            scr_h = wm.get_system_metrics(wm.SM_CYSCREEN)
            big = wm.capture_screen(0, 0, scr_w, scr_h)
            crop = big.crop((int(x), int(y), int(x) + int(bw), int(y) + int(bh)))
            out = Path(gettempdir(), f"wm_tb_{tag}.png")
            crop.resize((160, 160), Image.NEAREST).save(out)
            print(f"  {tag}: btn rect=({x:.0f},{y:.0f},{bw:.0f},{bh:.0f}) -> {out}")
            return
    print(f"  {tag}: NO_MATCHING_BUTTON")


def kill_targets(procs: list) -> None:
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    procs.clear()
    time.sleep(0.4)


def main() -> int:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.5)

    procs = [subprocess.Popen([sys.executable, str(TARGET_SCRIPT), "WM_TB_A"], env=wm.host_env()),
             subprocess.Popen([sys.executable, str(TARGET_SCRIPT), "WM_TB_B"], env=wm.host_env())]
    time.sleep(1.2)
    ha = wm.find_window_by_title("WM_TB_A")
    hb = wm.find_window_by_title("WM_TB_B")
    print(f"targets A=0x{ha:X} B=0x{hb:X}")

    # E1 仅接管实例
    p1 = subprocess.Popen([EXE, "--left-hwnd", str(ha), "--right-hwnd", str(hb),
                           "--profile", "snap-e1"], env=wm.host_env())
    h1 = wait_host(p1.pid)
    ok1 = wait_attached(ha, hb) if h1 else False
    print(f"E1 host=0x{h1:X} attached={ok1}")
    time.sleep(1.0)
    if ok1:
        shoot_taskbar("e1")
    wm.post_close(h1) if h1 else None
    wm.wait_until(lambda: not wm.pids_by_name("WindowMerger"), 8000, 200)

    # E2 空实例 + 接管实例并存
    p0 = subprocess.Popen([EXE], env=wm.host_env())
    h0 = wait_host(p0.pid)
    time.sleep(1.0)
    p2 = subprocess.Popen([EXE, "--left-hwnd", str(ha), "--right-hwnd", str(hb),
                           "--profile", "snap-e2"], env=wm.host_env())
    h2 = wait_host(p2.pid)
    ok2 = wait_attached(ha, hb) if h2 else False
    print(f"E2 empty=0x{h0:X} snap=0x{h2:X} attached={ok2}")
    time.sleep(1.0)
    if h0 or h2:
        shoot_taskbar("e2")
    for h in (h0, h2):
        if h:
            wm.post_close(h)
    wm.wait_until(lambda: not wm.pids_by_name("WindowMerger"), 8000, 200)
    kill_targets(procs)
    Path(wm.config_path().replace("config.json", "config-snap-e1.json")).unlink(missing_ok=True)
    Path(wm.config_path().replace("config.json", "config-snap-e2.json")).unlink(missing_ok=True)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
