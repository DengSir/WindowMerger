# -*- coding: utf-8 -*-
"""分隔条悬停检查：分隔条 x 位置中高度竖条（基态/悬停/移开三态 + 像素取色）。
原 DividerHoverTest.ps1。
用法: py tools\\visual\\divider_hover_test.py（对已运行的宿主）
截图: %TEMP%\\wm_divhover_*.png
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    import subprocess
    # 自备环境：强制深色（确定性预期）→ 杀干净 → 带配置启动（主题在启动时读取）
    cfg = wm.load_config()
    cfg["Theme"] = "Dark"
    cfg["Ratio"] = 0.5
    wm.save_config(cfg)
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.8)
    subprocess.Popen([wm.exe_path()])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    host_pid = wm.pid_of(hm)
    wm.set_window_pos(hm, None, 400, 150, 2200, 900, wm.SWP_NOZORDER)
    time.sleep(1.0)
    hr = wm.get_window_rect(hm)
    w, h = hr.width, hr.height
    ratio = 0.5
    print(f"RATIO={ratio}")
    avail = w - 4 - 8
    div_x = int(hr.Left + 2 + avail * ratio + 4)
    wm.set_topmost(hm, True)
    time.sleep(0.3)
    pal = wm.PALETTES["Dark"]
    results = []

    def snap(tag: str) -> None:
        # 探针：分隔条点须命中本宿主（WindowFromPoint 与光标无关；置顶防别的窗压住）。
        # 光标位置由调用方决定（base/left 移开、hover 落分隔条）——snap 里动光标会让
        # 所有状态都变成悬停色（原 PS 缺陷，实测）
        ok = False
        for _ in range(3):
            wm.set_topmost(hm, True)
            time.sleep(0.3)
            if wm.pid_of(wm.window_from_point(div_x, h // 2)) == host_pid:
                ok = True
                break
        if not ok:
            print(f"{tag}: SKIP_COVERED")
            results.append(False)
            return
        time.sleep(0.4)  # 悬停状态渲染
        img = wm.capture_window(hm)
        lx = div_x - hr.Left
        crop = img.crop((lx - 30, 200, lx + 30, 500))
        crop.save(str(Path(tempfile.gettempdir(), f"wm_divhover_{tag}.png")))
        # 中高度分隔条像素取色 + 断言
        c = img.getpixel((lx, h // 2))[:3]
        expected = pal["DividerHover"] if tag == "hover" else pal["Divider"]
        hit = wm.color_close(c, expected)
        print(f"{tag}: divider RGB=({c[0]},{c[1]},{c[2]}) expect={expected} "
              f"{'OK' if hit else 'MISMATCH'}")
        results.append(hit)

    wm.set_cursor_pos(6, 700)
    time.sleep(0.4)
    snap("base")
    wm.set_cursor_pos(div_x, h // 2)
    time.sleep(0.4)
    snap("hover")
    wm.set_cursor_pos(6, 700)
    time.sleep(0.4)
    snap("left")

    wm.set_topmost(hm, False)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    cfg = wm.load_config()
    cfg["Theme"] = "Auto"
    wm.save_config(cfg)
    print("DIVIDER_HOVER_TEST_DONE")
    ok = len(results) == 3 and all(results)
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
