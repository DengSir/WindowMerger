# -*- coding: utf-8 -*-
"""遮挡格拒收人工验证（IsCoveredAtCursor）：准备空宿主 + 右格上的置顶红色遮罩窗，
**人工**两步拖 notepad：①拖到被遮的右格松手 → 必须无高亮不吸附；②拖到空左格 →
吸附。每步后回本控制台按 ENTER，脚本打印判定（TOOLWINDOW + 落格位置）。原 CoveredDragTest.ps1。
用法: uv run tools/\manual\\covered_drag_test.py
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def wait_enter(root) -> None:
    while msvcrt.kbhit():
        msvcrt.getwch()
    print("...press ENTER when done")
    while True:
        while msvcrt.kbhit():
            if msvcrt.getwch() == "\r":
                return
        root.update()  # 等价 Application.DoEvents：维持遮罩窗消息循环
        time.sleep(0.05)


def main() -> int:
    import msvcrt
    import tkinter

    # 清理
    wm.graceful_close_by_name("WindowMerger")
    wm.force_kill_by_name("Notepad")
    time.sleep(1.3)

    t1 = Path(tempfile.gettempdir(), "wmcovered.txt")
    t1.write_text("covered-drag-test", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.5)
    nps = wm.main_windows_by_name("Notepad")
    if not nps:
        print("FAIL_NO_NOTEPAD")
        return 1
    n = nps[0][1]

    subprocess.Popen([wm.exe_path()])
    time.sleep(3)
    hm = wm.host_hwnd()
    if not hm:
        print("FAIL_NO_HOST")
        return 1

    hr = wm.get_window_rect(hm)
    w = hr.width

    # 右格上的遮罩窗，盖在置顶宿主之上（tkinter 无边框窗替代 WinForms Form）
    wm.set_topmost(hm, True)
    time.sleep(0.2)
    cover = tkinter.Tk()
    cover.title("COVER")
    cover.overrideredirect(True)
    cover.attributes("-topmost", True)
    cx = int(hr.Left + w * 0.55)
    cy = int(hr.Top + 40)
    cw = int(w * 0.4)
    ch = int(hr.Bottom - hr.Top - 60)
    cover.geometry(f"{cw}x{ch}+{cx}+{cy}")
    cover.configure(bg="firebrick")
    tkinter.Label(cover, text="COVERED RIGHT PANE - drops here must be refused",
                  fg="white", bg="firebrick").pack(expand=True, fill="both")
    cover.update()

    print(f"HOST ({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom})  notepad hwnd=0x{n:X}")
    print("STEP 1: drag notepad by its title bar over the RED right pane and release there.")
    wait_enter(cover)
    if wm.is_toolwindow(n):
        print("STEP1 FAIL: notepad got docked despite covered pane")
    else:
        print("STEP1 PASS: notepad not docked (covered drop ignored)")

    print("STEP 2: drag notepad over the free LEFT pane and release there.")
    wait_enter(cover)
    nr = wm.get_window_rect(n)
    in_left = (hr.Left - 30 < nr.Left < hr.Left + w * 0.5
               and nr.Top > hr.Top and nr.Bottom <= hr.Bottom + 30)
    if wm.is_toolwindow(n) and in_left:
        print(f"STEP2 PASS: notepad docked into left pane rect=({nr.Left},{nr.Top})-({nr.Right},{nr.Bottom})")
    else:
        print(f"STEP2 FAIL: toolwindow={wm.is_toolwindow(n)} inLeft={in_left} "
              f"rect=({nr.Left},{nr.Top})-({nr.Right},{nr.Bottom})")

    # 清理：宿主优雅关释放 notepad；还原 NOTOPMOST
    wm.set_topmost(hm, False)
    cover.destroy()
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    wm.force_kill_by_name("Notepad")
    print("COVERED_DRAG_TEST_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
