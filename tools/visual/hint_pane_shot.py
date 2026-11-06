# -*- coding: utf-8 -*-
"""空格占位提示视觉检查：阶段 1 纯宿主（两格填充+提示）；阶段 2 CLI 吸 notepad 到左格
（左提示消失、notepad 经透明格透出、右提示保留）。置顶+全屏截，还原 NOTOPMOST。
原 HintPaneShot.ps1。
用法: py tools\\visual\\hint_pane_shot.py
截图: %TEMP%\\wm_hint_empty.png / wm_hint_leftoccupied.png
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def shot_host(h: int, tag: str) -> None:
    r = wm.get_window_rect(h)
    wm.set_topmost(h, True)
    time.sleep(0.4)
    big = wm.capture_screen(0, 0, 2560, 1440)
    small = big.crop((r.Left, r.Top, r.Right, r.Bottom))
    small.save(str(Path(tempfile.gettempdir(), f"wm_hint_{tag}.png")))
    wm.set_topmost(h, False)
    print(f"SHOT_{tag}")


def main() -> int:
    # 清理
    wm.graceful_close_by_name("WindowMerger")
    wm.force_kill_by_name("Notepad")
    time.sleep(1.3)

    # 阶段 1：空宿主
    subprocess.Popen([wm.exe_path()])
    time.sleep(3)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    shot_host(hm, "empty")
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)

    # 阶段 2：左格被占
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
    shot_host(hm2, "leftoccupied")

    # 清理
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    wm.force_kill_by_name("Notepad")
    print("HINT_SHOT_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
