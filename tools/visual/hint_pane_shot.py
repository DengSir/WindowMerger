# -*- coding: utf-8 -*-
"""空格占位提示视觉检查：阶段 1 纯宿主（两格填充+提示）；阶段 2 CLI 吸 notepad 到左格
（左提示消失、notepad 经透明格透出、右提示保留）。置顶+全屏截，还原 NOTOPMOST。
原 HintPaneShot.ps1。
用法: uv run tools/\visual\\hint_pane_shot.py
截图: %TEMP%\\wm_hint_empty.png / wm_hint_leftoccupied.png
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def shot_host(h: int, tag: str) -> object:
    r = wm.get_window_rect(h)
    wm.set_topmost(h, True)
    time.sleep(0.4)
    # 测试显示器全幅截图（宿主钉在 96 DPI 优先屏，主屏 ≠ 测试屏时 (0,0) 会截错屏），
    # 裁剪坐标减屏原点
    mon = wm.pick_test_monitor().rcMonitor
    big = wm.capture_test_screen()
    small = big.crop((r.Left - mon.Left, r.Top - mon.Top,
                      r.Right - mon.Left, r.Bottom - mon.Top))
    small.save(str(Path(tempfile.gettempdir(), f"wm_hint_{tag}.png")))
    wm.set_topmost(h, False)
    print(f"SHOT_{tag}")
    return small


def main() -> int:
    # 自备环境：强制深色（确定性预期）→ 启动（主题在启动时读取）
    cfg = wm.load_config_safe()
    cfg["Theme"] = "Dark"
    cfg["Ratio"] = 0.5
    wm.save_config(cfg)
    pal = wm.PALETTES["Dark"]
    results = []

    # 清理
    wm.graceful_close_by_name("WindowMerger")
    wm.force_kill_by_name("Notepad")
    time.sleep(1.3)

    # 阶段 1：空宿主（两格填充 + 提示文案）
    subprocess.Popen([wm.exe_path()])
    time.sleep(3)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    wm.set_window_pos(hm, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
    time.sleep(1.0)
    img = shot_host(hm, "empty")
    # 左/右格填充 = ThemeBar（避开中央提示文案，采样格内四分位处 3x3 众数）
    for side, ox in (("LEFT", 90), ("RIGHT", img.width - 90)):
        samples = [img.getpixel((ox + dx, 300 + dy))[:3]
                   for dx in (-2, 0, 2) for dy in (-2, 0, 2)]
        hits = sum(wm.color_close(p, pal["Bar"]) for p in samples)
        ok = hits >= 6
        print(f"HINT_FILL_{side} hits={hits}/9 expect={pal['Bar']} {'OK' if ok else 'MISMATCH'}")
        results.append(ok)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)

    # 阶段 2：左格被占（左提示消失、notepad 透出；右提示保留）
    hint = Path(tempfile.gettempdir(), "wmhint.txt")
    hint.write_text("hint-test", encoding="ascii")
    subprocess.Popen(["notepad", str(hint)])
    time.sleep(1.5)
    subprocess.Popen([wm.exe_path(), "--left", "notepad"])
    time.sleep(4)
    hm2 = wm.host_hwnd()
    if not hm2:
        print("NO_HOST_2")
        return 1
    wm.set_window_pos(hm2, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
    time.sleep(1.5)
    img2 = shot_host(hm2, "leftoccupied")
    # 左格判定 = 吸附本身成立（提示消失是其后果；notepad 深色编辑器底色 ≈ ThemeBar，
    # 像素比对不可靠——实测撞色）；右格仍是填充
    nps = wm.main_windows_by_name("Notepad")
    attached = bool(nps) and wm.is_attached(nps[0][1])
    r2 = wm.get_window_rect(hm2)
    pane_cx = r2.Left + 3 + (r2.width - 15) // 4
    pane_cy = r2.Top + 45 + (r2.height - 48) // 2
    left_hit = wm.proc_name_of(wm.window_from_point(pane_cx, pane_cy)).lower()
    left_ok = attached and left_hit == "notepad"
    print(f"OCCUPIED_LEFT_ATTACHED tool={attached} LEFT_HIT={left_hit} "
          f"{'OK' if left_ok else 'MISMATCH'}")
    samples_r = [img2.getpixel((img2.width - 90 + dx, 300 + dy))[:3]
                 for dx in (-2, 0, 2) for dy in (-2, 0, 2)]
    right_hint = sum(wm.color_close(p, pal["Bar"]) for p in samples_r) >= 6
    print(f"OCCUPIED_RIGHT_HINT hits={sum(wm.color_close(p, pal['Bar']) for p in samples_r)}/9 "
          f"{'OK' if right_hint else 'MISMATCH'}")
    results.extend([left_ok, right_hint])

    # 清理
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    wm.force_kill_by_name("Notepad")
    cfg = wm.load_config()
    cfg["Theme"] = "Auto"
    wm.save_config(cfg)
    print("HINT_SHOT_DONE")
    ok = len(results) == 4 and all(results)
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
