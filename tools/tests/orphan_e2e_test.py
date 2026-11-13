# -*- coding: utf-8 -*-
r"""孤儿清理端到端：CLI 吸附 notepad → 强杀宿主留孤儿 → 扫描确认吸附态残留 →
重启宿主，启动清理（按 HWND 精确）必须救回。原 OrphanE2ETest.ps1。
吸附态探针 = 圆角直角化（corner_pref==1，DeleteTab 方案下不再有 TOOLWINDOW 样式）。
用法: uv run tools/tests/orphan_e2e_test.py [--exe 路径]
警告: 会强杀所有 WindowMerger/Notepad/mspaint。
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def scan_notepad_orphans() -> list[str]:
    """notepad 进程全部有标题或处吸附态（corner_pref==1）的顶层窗口行。"""
    np_pids = set(wm.pids_by_name("Notepad"))
    results = []
    for i, h in enumerate(wm.z_walk()):
        if i >= 600:
            break
        if wm.pid_of(h) not in np_pids:
            continue
        attached = wm.corner_pref(h) == 1
        title = wm.get_text(h, 64)
        if attached or title:
            r = wm.get_window_rect(h)
            results.append(f"hwnd=0x{h:X} attached={attached} vis={wm.is_window_visible(h)} "
                           f"rect=({r.Left},{r.Top}) title=[{title}]")
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    # 1. 全杀 + 删配置 + 起 notepad
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    Path(wm.config_path()).unlink(missing_ok=True)
    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t1.write_text("orphan-e2e", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    if not wm.wait_main_windows("Notepad"):
        print("FAIL_TARGET_NOT_RUNNING")
        return 1

    # 2. CLI 吸附后强杀宿主 → 孤儿
    host = subprocess.Popen([a.exe, "--left", "notepad"])
    time.sleep(4)
    if not wm.pids_by_name("WindowMerger"):
        print("NO_HOST")
        return 1
    print("CONFIG_PIDS_SAVED:")
    cfg = Path(wm.config_path())
    if cfg.exists():
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if "Attached" in line:
                print(line)
    wm.force_kill_pid(host.pid)  # 事故现场：带着吸附子窗口强杀
    time.sleep(0.8)

    print("--- scan after force-kill (expect attached=True orphan) ---")
    for row in scan_notepad_orphans():
        print(row)

    # 3. 重启宿主（无 CLI）：启动清理必须救回孤儿（重录任务栏 + 圆角还原）
    subprocess.Popen([a.exe])
    time.sleep(4)

    print("--- scan after relaunch (expect attached=False, vis=True) ---")
    after = scan_notepad_orphans()
    for row in after:
        print(row)

    # 4. 清理测试环境
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("Notepad", "mspaint")
    print("ORPHAN_E2E_DONE")
    # 判定：重启后 notepad 主窗必须脱离吸附态（圆角还原）且可见（孤儿被启动清理救回）
    main_rows = [x for x in after if "Notepad]" in x or " - 记事本" in x]
    ok = bool(main_rows) and all("attached=False" in x and "vis=True" in x for x in main_rows)
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
