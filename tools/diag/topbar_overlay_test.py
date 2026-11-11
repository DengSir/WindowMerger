# -*- coding: utf-8 -*-
r"""最大化顶条自动隐藏（移入显示）可视化验证：
吸附 mspaint → 最大化 → 子窗占满全高（TopInset=0，EFB 顶=宿主顶）→ 顶条自动收起
（关闭钮 UIA 包围盒上移出窗顶）→ 光标移入顶条带 → 滑入盖在子窗上方 → 移出收起 →
还原正常态顶条恒显、子窗回顶条下方。放大截图落 %TEMP%\wm_corner\。
用法: uv run tools/diag/topbar_overlay_test.py
标记（英文）：A1_CHILD_FULL / A2_HIDDEN / B1_SHOWN / C2_REHIDDEN / D_NORMAL / PASS / FAIL
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm  # noqa: E402
import wm_uia  # noqa: E402
from PIL import Image  # noqa: E402

OUT = Path(tempfile.gettempdir()) / "wm_corner"
STRIP = 44  # 截条高（物理 px，含顶条 28 DIP@96DPI）


def close_btn_top(hm: int) -> float | None:
    """关闭钮 UIA 包围盒 top（屏幕物理 px）：顶条滑入时 ≈ 窗顶内 ~7*scale；
    收起时整条上移 _topBarH+2 DIP → top 明显小于窗顶（负偏移）。"""
    b = wm_uia.find_by_automation_id(wm_uia.element_from_handle(hm), "_closeButton")
    if b is None:
        return None
    l, t, w, h = wm_uia.bounding_rect_of(b)
    return t


def strip_shot(hm: int, tag: str) -> None:
    wm.set_topmost(hm, True)
    time.sleep(0.15)
    r = wm.get_window_rect(hm)
    img = wm.capture_screen(r.Left, r.Top, r.width, STRIP)
    wm.set_topmost(hm, False)
    OUT.mkdir(exist_ok=True)
    img.resize((r.width * 2, STRIP * 2), Image.NEAREST).save(OUT / f"overlay_{tag}.png")
    print(f"  saved {OUT / ('overlay_' + tag + '.png')}")


def main() -> int:
    cp = wm.config_path()
    backup = Path(cp).read_text(encoding="utf-8") if os.path.exists(cp) else None
    if wm.main_windows_by_name("mspaint"):
        print("BUSY 已有 mspaint（可能是用户在用），跳过")
        return 1

    subprocess.Popen(["mspaint"])
    if not wm.wait_until(lambda: wm.main_windows_by_name("mspaint"), 20000):
        print("NO_MSPAINT")
        return 1
    target = wm.main_windows_by_name("mspaint")[0][1]
    # 用户可能正开着自己的宿主（installed 版）——按 PID 跟踪本测试实例，别碰别人的
    proc = subprocess.Popen([wm.exe_path(), "--left", "mspaint"], env=wm.host_env())
    if not wm.wait_until(lambda: bool(wm.main_windows_of_pid(proc.pid)), 15000) \
            or not wm.wait_until(lambda: wm.is_toolwindow(target), 15000):
        print("NO_ATTACH")
        wm.post_close(wm.main_windows_of_pid(proc.pid)[0] if wm.main_windows_of_pid(proc.pid) else 0)
        return 1
    hm = wm.main_windows_of_pid(proc.pid)[0]
    wa = wm.pick_test_monitor().rcWork
    hw = min(1500, wa.Right - wa.Left - 40)
    hh = min(620, wa.Bottom - wa.Top - 120)
    wm.set_window_pos(hm, None, wa.Left + 20, wa.Top + 20, 0, 0,
                      wm.SWP_NOSIZE | wm.SWP_NOZORDER | wm.SWP_NOACTIVATE)
    wm.set_window_pos(hm, None, 0, 0, hw, hh,
                      wm.SWP_NOMOVE | wm.SWP_NOZORDER | wm.SWP_NOACTIVATE)
    time.sleep(1.0)
    scale = wm.get_dpi_for_window(hm) / 96.0
    cx = wa.Left + 20 + hw // 2

    ok = True
    # ---- 最大化：子窗占满全高 + 顶条自动收起 ----
    wm.show_window(hm, 3)  # SW_MAXIMIZE（wm.py 无此常量，与测试同用字面量）
    time.sleep(1.2)  # 两段布局收敛 + 维护周期放置
    mr = wm.get_window_rect(hm)
    efb = wm.ext_frame_bounds(target)
    a1 = efb is not None and abs(efb.Top - mr.Top) <= 2
    print(f"A1_CHILD_FULL efb_top={efb.Top if efb else None} host_top={mr.Top} {'OK' if a1 else 'FAIL'}")
    ok = ok and a1

    wm.set_cursor_pos(cx, mr.Top + 300)  # 光标远离顶条带
    time.sleep(0.7)  # 轮询 100ms + 滑出动画
    t_hidden = close_btn_top(hm)
    a2 = t_hidden is not None and t_hidden < mr.Top - 5 * scale
    print(f"A2_HIDDEN close_top={t_hidden} host_top={mr.Top} {'OK' if a2 else 'FAIL'}")
    ok = ok and a2
    strip_shot(hm, "hidden")

    # ---- 光标移入顶条带 → 滑入盖在子窗上方 ----
    wm.set_cursor_pos(cx, mr.Top + 8)
    time.sleep(0.7)
    t_shown = close_btn_top(hm)
    b1 = t_shown is not None and t_shown >= mr.Top
    print(f"B1_SHOWN close_top={t_shown} {'OK' if b1 else 'FAIL'}")
    ok = ok and b1
    strip_shot(hm, "shown")

    # ---- 移出 → 再收起 ----
    wm.set_cursor_pos(cx, mr.Top + 300)
    time.sleep(0.7)
    t2 = close_btn_top(hm)
    c2 = t2 is not None and t2 < mr.Top - 5 * scale
    print(f"C2_REHIDDEN close_top={t2} {'OK' if c2 else 'FAIL'}")
    ok = ok and c2

    # ---- 还原正常态：顶条恒显占位，子窗回顶条下方 ----
    wm.show_window(hm, wm.SW_RESTORE)
    time.sleep(1.2)
    nr = wm.get_window_rect(hm)
    efb2 = wm.ext_frame_bounds(target)
    t = close_btn_top(hm)
    exp_top = nr.Top + round((2 + 28) * scale)
    d1 = efb2 is not None and abs(efb2.Top - exp_top) <= 3 and t is not None and t >= nr.Top
    print(f"D_NORMAL child_top={efb2.Top if efb2 else None} expect~{exp_top} "
          f"close_top={t} {'OK' if d1 else 'FAIL'}")
    ok = ok and d1
    strip_shot(hm, "normal")

    wm.post_close(hm)
    wm.wait_until(lambda: not wm.is_window(hm), 8000)
    time.sleep(0.8)
    wm.force_kill_by_name("mspaint")
    if backup is not None:
        Path(cp).write_text(backup, encoding="utf-8")
    elif os.path.exists(cp):
        os.remove(cp)
    print(f"{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
