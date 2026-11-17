# -*- coding: utf-8 -*-
"""拖到另一侧换侧回归（注入拖动，固定布局）：自写 tkinter 靶窗吸附在左格 → 抓其标题条
（透过透明格子命中子窗口）拖到右格中心松手 → 吸附态整体换侧（TryAttach 换侧分支）。
用法: uv run tools/\tests\\drag_switch_side_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

HOST_RECT = wm.test_layout()["host"]
TARGET_TITLE = "WM_DRAG_TARGET"


def kill_title_owners(title: str) -> None:
    """按标题杀全部属主进程树（taskkill /T /F）：残留靶窗的属主可能是 Popen 直接子进程
    的后代（uv venv python trampoline），target.kill() 够不着——按窗口标题反查 PID 才是
    完整口径（AGENTS：测试启动/收尾必须 kill_title_owners）。"""
    import ctypes, subprocess
    for h in wm.z_walk():
        if wm.get_text(h).strip() == title and wm.is_window_visible(h):
            pid = wm.pid_of(h)
            if pid:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, check=False)


def drag(from_x, from_y, to_x, to_y, steps=20):
    wm.set_cursor_pos(from_x, from_y)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.15)
    for i in range(1, steps + 1):
        wm.set_cursor_pos(from_x + int((to_x - from_x) * i / steps),
                          from_y + int((to_y - from_y) * i / steps))
        time.sleep(0.025)
    time.sleep(0.2)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(1.2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    kill_title_owners("WM_DRAG_TARGET")  # 按标题杀残留靶窗属主（uv venv python 可能是
    # trampoline：target.kill() 只杀 stub，持窗真实解释器残留 → 同名旧窗污染本测）
    time.sleep(0.8)
    wm.remove_config()
    # 宿主内部时序 trace（DIAG 用）：清掉旧 trace 保证本测日志纯净
    trace_log = Path(tempfile.gettempdir(), "wm_trace.log")
    trace_log.unlink(missing_ok=True)
    # 自写靶窗（tkinter，标题 WM_DRAG_TARGET）：零 Ribbon/零 PMv2，标题几何已知
    target = subprocess.Popen([sys.executable,
                               str(Path(__file__).resolve().parents[1] / "targets" / "drag_target.py")])
    th = 0
    for _ in range(50):  # 等靶窗真实存在再起宿主（吸附发生在 Loaded，CI 冷启动竞速）
        th = wm.find_window_by_title("WM_DRAG_TARGET")
        if th:
            break
        time.sleep(0.2)
    if not th:
        print("FAIL_NO_TARGET")
        target.kill()
        return 1
    host_env = dict(os.environ, WM_TRACE="1")
    subprocess.Popen([a.exe, "merge", "--left", str(target.pid)], env=host_env)
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    hx, hy, hw, hh = HOST_RECT
    wm.set_window_pos(hm, None, hx, hy, hw, hh, wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm, True)
    time.sleep(0.4)

    pane_w = (hw - 15) // 2
    left_cx = hx + 3 + pane_w // 2
    right_cx = hx + 3 + pane_w + 9 + pane_w // 2
    mid_y = hy + 45 + (hh - 48) // 2

    for _ in range(3):  # busy 桌面：topmost 别的窗口压住探点时重新置顶宿主再探
        pre_l = wm.proc_name_of(wm.window_from_point(left_cx, mid_y)).lower()
        if pre_l == "python":
            break
        wm.set_topmost(hm, True)
        time.sleep(0.4)
    print(f"PRE LEFT_HIT={pre_l}")
    if pre_l != "python":
        print("FAIL_NOT_ATTACHED_LEFT")
        return 1

    # 抓靶窗标题条（透过透明左格命中吸附子窗口；WM_NCHITTEST 探测真实 HTCAPTION），
    # 拖到右格中心 → 换侧
    t_r = wm.get_window_rect(th)
    grab_x, grab_y = wm.title_grab_point(th)
    if wm.proc_name_of(wm.window_from_point(grab_x, grab_y)).lower() != "python":
        print("SKIP_COVERED_GRAB")
        return 1
    swapped = False
    for attempt in range(3):
        wm.keybd_event(0x12, 0, 0)
        wm.set_foreground_window(th)
        wm.keybd_event(0x12, 0, 2)
        time.sleep(0.3)
        drag(grab_x, grab_y, right_cx, mid_y)
        post_l_try = wm.proc_name_of(wm.window_from_point(left_cx, mid_y)).lower()
        if post_l_try != "python":
            swapped = True
            break
        print(f"DIAG attempt{attempt}: rect=({t_r.Left},{t_r.Top})-"
              f"({t_r.Right},{t_r.Bottom}) still attached left")

    post_l = wm.proc_name_of(wm.window_from_point(left_cx, mid_y)).lower()
    post_r = wm.proc_name_of(wm.window_from_point(right_cx, mid_y)).lower()
    still_tool = wm.is_attached(th)
    print(f"POST LEFT_HIT={post_l} RIGHT_HIT={post_r} tool={still_tool}")
    if not (swapped and post_r == "python" and still_tool):
        # 失败取证（决定性探针 = 状态栏文本：宿主自己认为的格子占用 vs 窗口实际位置）。
        # 全块容错——取证代码绝不能自己炸掉测试
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
            import wm_uia
            status = wm_uia.status_text(hm)
        except Exception as e:
            status = f"<status err {e}>"
        try:
            cx, cy = wm.get_cursor_pos()
        except Exception:
            cx = cy = -1
        try:
            below = wm.get_window(hm, wm.GW_HWNDNEXT)  # 宿主正下方第一个窗（正常 = 靶窗）
            below_proc = wm.proc_name_of(below) if below else "?"
        except Exception as e:
            below_proc = f"<z err {e}>"
        try:
            tr = wm.get_window_rect(th)
            tr = tr.as_tuple() if tr else None
        except Exception as e:
            tr = f"<rect err {e}>"
        # 同名靶窗清单（残留假说）：多窗 = th 不是宿主吸的那个
        peers = []
        try:
            for h in wm.z_walk():
                if wm.get_text(h).strip() == TARGET_TITLE and wm.is_window_visible(h):
                    r = wm.get_window_rect(h)
                    peers.append((h, r.as_tuple() if r else None, wm.corner_pref(h)))
        except Exception as e:
            peers = [f"<enum err {e}>"]
        try:
            cfg_hwds = wm.load_config().get("AttachedHwnds")  # 宿主记录的吸附句柄（对照 th）
        except Exception as e:
            cfg_hwds = f"<cfg err {e}>"
        # th 的 z 序正上方窗口（子窗永远插在其宿主正下方）——若 != hm，说明 hm 不是
        # th 的宿主（第二个 WindowMerger 进程/宿主错位实锤）
        try:
            prev_of_th = wm.get_window(th, wm.GW_HWNDPREV)
            prev_desc = f"{prev_of_th}({'hm' if prev_of_th == hm else wm.proc_name_of(prev_of_th)})"
        except Exception as e:
            prev_desc = f"<prev err {e}>"
        merger_pids = wm.pids_by_name("WindowMerger")
        print(f"DIAG status='{status}' rect={tr} cursor=({cx},{cy}) "
              f"host_below={below_proc} corner={wm.corner_pref(th)} th={th} th_prev={prev_desc} "
              f"hm={hm} merger_pids={merger_pids} "
              f"cfg_hwnds={cfg_hwds} peers={peers} "
              f"panes L=({hx},{hy},{hx + pane_w},{hy + hh}) "
              f"R=({hx + pane_w},{hy},{hx + hw},{hy + hh})")
        # 宿主内部时序 trace 尾部（MOVESIZE/END 到达、HitTestSlot 判定、TryAttach 分支、
        # Maintain 清格——run_all 子测试输出进主日志，一次 run 直接定位）
        try:
            lines = trace_log.read_text(encoding="utf-8", errors="replace").splitlines()
            print("TRACE_TAIL >>>")
            for ln in lines[-40:]:
                print(f"TRACE| {ln}")
        except Exception as e:
            print(f"TRACE read err {e}")
    wm.set_topmost(hm, False)

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    target.kill()
    print("DRAG_SWITCH_SIDE_TEST_DONE")
    ok = swapped and post_r == "python" and still_tool
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
