# -*- coding: utf-8 -*-
"""拖入规则回归（注入拖动，固定布局）——占用格 / Ctrl 替换 / 拖出自愈 / 宿主移动联动：
  D1 占用格无 Ctrl 拖入新窗口 → 拒绝：不吸附、原子窗原样（IsDropAllowed=false 不亮框，
     HitTestSlot 返回 null，TryAttach 不会执行——不产生任何通知）
  D2 按住 Ctrl 拖入占用格 → 替换：新窗口吸附、旧窗口回吸附前矩形（TryAttach 替换分支
     child.Restore()）。Ctrl 注入 = 宿主前台时真实 keydown（进 WPF 键盘表）；拖动循环用
     PostMessage(WM_NCLBUTTONDOWN, HTCAPTION) 启动——不走真实点击就不会激活 mspaint，
     宿主保持前台，Ctrl 按下态存活到 MOVESIZEEND 检查（真实点击会激活靶窗、宿主失活
     时 WPF 重置键盘表——滞留技巧实测失败，见 git 历史）
  D3 已吸附子窗拖出宿主松手 → side=null 不吸附，250ms 维护定时器把窗口拉回格子（自愈）
  D4 宿主顶条拖动 → 子窗口 MoveBy 同步跟随（dx/dy 累计一次断言）
用法: uv run tools\\tests\\pane_drag_rules_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

VK_CONTROL = 0x11
KEYEVENTF_KEYUP = 0x2


def drag(from_x: int, from_y: int, to_x: int, to_y: int, steps: int = 20) -> None:
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
    time.sleep(1.0)


def grab_target(mh: int) -> tuple[int, int]:
    """置前靶窗并确认抓点可抓（busy 桌面被盖时重试）。"""
    for _ in range(3):
        wm.keybd_event(0x12, 0, 0)  # ALT
        wm.set_foreground_window(mh)
        wm.keybd_event(0x12, 0, KEYEVENTF_KEYUP)
        time.sleep(0.4)
        gx, gy = wm.title_grab_point(mh)
        if wm.proc_name_of(wm.window_from_point(gx, gy)).lower() == "mspaint":
            return gx, gy
    return 0, 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    # ---------- 环境：notepad 左格 + 空右格；mspaint 待拖 ----------
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    wm.save_config({"Ratio": 0.5})
    t1 = Path(tempfile.gettempdir(), "wmpd1.txt")
    t1.write_text("pane-rules", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.2)
    msp = subprocess.Popen(["mspaint"])
    time.sleep(1.8)
    mps = wm.main_windows_by_name("mspaint")
    if not mps:
        print("FAIL_NO_MSPAINT")
        return 1
    mh = mps[0][1]
    nps0 = wm.main_windows_by_name("Notepad")
    if not nps0:
        print("FAIL_NO_NOTEPAD")
        return 1
    npre = wm.get_window_rect(nps0[0][1])  # 吸附前矩形（D2 替换还原断言的基准）
    subprocess.Popen([a.exe, "--left", "notepad"], env=wm.host_env())
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    wm.set_window_pos(hm, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm, True)
    time.sleep(0.4)
    hr = wm.get_window_rect(hm)
    nps = wm.main_windows_by_name("Notepad")
    if not nps:
        print("FAIL_NO_NOTEPAD")
        return 1
    nh = nps[0][1]
    print(f"HOST ({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom}) "
          f"NOTEPAD pre=({npre.Left},{npre.Top})-({npre.Right},{npre.Bottom})")
    # 左格中心（拖放点取格中心偏下 60px：拖入窗标题条落在格内、不被宿主顶条压住）
    pane_w = (hr.width - 15) // 2
    drop_x = hr.Left + 3 + pane_w // 2
    drop_y = hr.Top + 45 + (hr.height - 48) // 2 + 60

    # ---------- D1 占用格无 Ctrl → 拒绝 ----------
    gx, gy = grab_target(mh)
    if not gx:
        print("SKIP_GRAB")
        return 1
    drag(gx, gy, drop_x, drop_y)
    r1 = wm.get_window_rect(mh)
    d1_ok = (not wm.is_toolwindow(mh) and wm.is_toolwindow(nh)
             and wm.proc_name_of(wm.window_from_point(drop_x, hr.Top + hr.height // 2)).lower()
             == "notepad")
    check("D1_OCCUPIED_REJECT", d1_ok,
          f"mp_tool={wm.is_toolwindow(mh)} np_tool={wm.is_toolwindow(nh)}")

    # D1 拒收后 mspaint 停在左格上方——被已吸附的 notepad（宿主正下方槽位）压住，
    # 标题条抓不到（实测点击穿透命中的是 notepad）。挪到宿主右侧屏内 + 提到普通带
    # 顶端，D2 才能直接抓它
    wm.set_window_pos(mh, None, hr.Right + 40, hr.Top + 120,
                      r1.width, r1.height, wm.SWP_NOZORDER)
    wm.set_topmost(mh, True)
    time.sleep(0.2)
    wm.set_topmost(mh, False)
    time.sleep(0.3)

    # ---------- D2 Ctrl 拖入 → 替换 ----------
    # Ctrl 注入约束（实测）：keydown 必须落在宿主前台时（ALT+setFG 后真实 keydown，
    # 直达 WPF 键盘表）；拖动中切前台会取消 mspaint 的移动循环、MOVESIZEEND 在半路
    # 触发（实测吸附到了半路所在的空右格）——所以拖动全程不再碰前台。keyup 在
    # MOVESIZEEND 处理完之后再发（全局/线程键盘态都到那时才清）
    gx, gy = grab_target(mh)
    if not gx:
        print("SKIP_GRAB2")
        return 1
    wm.keybd_event(0x12, 0, 0)  # ALT + setFG：把前台真正切到宿主
    wm.set_foreground_window(hm)
    wm.keybd_event(0x12, 0, KEYEVENTF_KEYUP)
    time.sleep(0.3)
    wm.keybd_event(VK_CONTROL, 0, 0)  # 宿主前台时按下
    wm.set_cursor_pos(gx, gy)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)  # 点击激活 mspaint、开始拖
    time.sleep(0.15)
    for i in range(1, 21):
        wm.set_cursor_pos(gx + int((drop_x - gx) * i / 20),
                          gy + int((drop_y - gy) * i / 20))
        time.sleep(0.025)
    time.sleep(0.2)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(1.2)  # ≥ dispatcher 派发周期，MOVESIZEEND 处理完再松 Ctrl
    wm.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP)
    time.sleep(0.5)
    import wm_uia as _u
    print(f"DIAG status={_u.status_text(hm)!r}")
    np_now = wm.get_window_rect(nh)
    d2_ok = wm.is_toolwindow(mh) and not wm.is_toolwindow(nh)
    check("D2_CTRL_REPLACE_ATTACH", d2_ok,
          f"mp_tool={wm.is_toolwindow(mh)} np_tool={wm.is_toolwindow(nh)}")
    back_ok = (abs(np_now.Left - npre.Left) <= 3 and abs(np_now.Top - npre.Top) <= 3
               and abs(np_now.Right - npre.Right) <= 3 and abs(np_now.Bottom - npre.Bottom) <= 3)
    check("D2_OLD_RESTORED_RECT", back_ok,
          f"now=({np_now.Left},{np_now.Top})-({np_now.Right},{np_now.Bottom}) "
          f"pre=({npre.Left},{npre.Top})-({npre.Right},{npre.Bottom})")

    # ---------- D3 拖出宿主松手 → 自愈拉回格子 ----------
    mp_r0 = wm.get_window_rect(mh)
    gx, gy = wm.title_grab_point(mh)
    out_x, out_y = hr.Right - 60, hr.Top - 40  # 宿主上方外侧（屏内，避开靶窗区）
    drag(gx, gy, out_x, out_y)
    # 250ms 维护周期把仍在吸附引用上的窗口拉回格子；拖回原格走同一 ApplyLayoutTo

    def back_in_pane() -> bool:
        r = wm.get_window_rect(mh)
        return abs(r.Left - mp_r0.Left) <= 4 and abs(r.Top - mp_r0.Top) <= 4

    healed = wm.wait_until(back_in_pane, 3000, 150)
    check("D3_DRAGOUT_SELF_HEAL", healed,
          f"rect=({wm.get_window_rect(mh).Left},{wm.get_window_rect(mh).Top}) "
          f"expect~({mp_r0.Left},{mp_r0.Top})")

    # ---------- D4 宿主顶条拖动 → 子窗口同步跟随 ----------
    hm_r0 = wm.get_window_rect(hm)
    mp_r0 = wm.get_window_rect(mh)
    gx, gy = wm.title_grab_point(hm)
    if not gx:
        check("D4_HOST_GRAB", False, "title_grab_point 未命中 HTCAPTION")
    else:
        dx, dy = 90, 70
        drag(gx, gy, gx + dx, gy + dy)
        time.sleep(0.8)  # LocationChanged → MoveBy 已同步；留一拍
        hm_r1 = wm.get_window_rect(hm)
        mp_r1 = wm.get_window_rect(mh)
        moved_host = (hm_r1.Left - hm_r0.Left, hm_r1.Top - hm_r0.Top)
        moved_child = (mp_r1.Left - mp_r0.Left, mp_r1.Top - mp_r0.Top)
        check("D4_HOST_MOVED", abs(moved_host[0] - dx) <= 8 and abs(moved_host[1] - dy) <= 8,
              f"host moved={moved_host}")
        check("D4_CHILD_FOLLOWS", abs(moved_child[0] - moved_host[0]) <= 3
              and abs(moved_child[1] - moved_host[1]) <= 3,
              f"child moved={moved_child} host moved={moved_host}")

    wm.set_topmost(hm, False)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    wm.force_kill_by_name("Notepad", "mspaint")
    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
