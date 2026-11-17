# -*- coding: utf-8 -*-
"""cli_args_test C1/C5 失败现场诊断：起 notepad + `merge notepad` 宿主，打全量现场
（宿主清单/矩形/状态栏 UIA/吸附 corner/探针命中/UIA 子树 AutomationId 清单）。
用法: uv run tools\\diag\\cli_c1_probe.py
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia


def main() -> int:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.5)

    t1 = Path(tempfile.gettempdir(), "c1probe.txt")
    t1.write_text("c1-probe", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    if not wm.wait_main_windows("Notepad"):
        print("FAIL_NO_NOTEPAD")
        return 1

    subprocess.Popen([wm.exe_path(), "merge", "notepad"], env=wm.host_env())
    time.sleep(3.0)
    hosts = wm.main_windows_by_name("WindowMerger")
    print(f"HOST_COUNT={len(hosts)}")
    if not hosts:
        return 1
    hm = hosts[0][1]
    r = wm.get_window_rect(hm)
    print(f"HOST_RECT=({r.Left},{r.Top},{r.Right},{r.Bottom}) pid={wm.pid_of(hm)}")
    time.sleep(1.0)
    st = wm_uia.status_text(hm)
    print(f"STATUS={st!r}")

    nh = wm.main_windows_by_name("Notepad")
    print(f"NOTEPAD count={len(nh)} corner={wm.corner_pref(nh[0][1]) if nh else '?'}")

    # 状态栏 UIA 子树：宿主 AutomationId 全清单（看 _status 在不在）
    el = wm_uia.element_from_handle(hm)
    ids = wm_uia.all_automation_ids(el) if hasattr(wm_uia, "all_automation_ids") else None
    if ids is None:
        # 兜底：walk 一层
        import uiautomation as auto
        ids = []
        for c, _ in auto.WalkControl(el, includeTop=False, maxDepth=4):
            aid = c.AutomationId or ""
            if aid:
                ids.append(f"{aid}:{c.ControlTypeName}")
    print(f"UIA_IDS={ids[:40]}")

    # 探针：宿主中部左 1/4
    if r.Right > r.Left:
        px = r.Left + 2 + int((r.Right - r.Left - 12) * 0.25)
        py = (r.Top + r.Bottom) // 2
        print(f"PROBE_HIT={wm.proc_name_of(wm.window_from_point(px, py))}")

    # 清理
    wm.post_close(hm)
    time.sleep(1.5)
    wm.force_kill_by_name("Notepad")
    print("PROBE_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
