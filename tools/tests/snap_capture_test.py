# -*- coding: utf-8 -*-
"""snap 接管回归（--detect-snap 检测 / --left-hwnd 直连 / --profile 配置隔离）：
  S1 检测命中：两靶窗 EFB 对半排满测试屏工作区 → ok=true、左右句柄、比例、屏序号正确
  S1b 2:1 变体：左 2/3 右 1/3 → ratio ≈ 0.6667
  S2 接管 e2e：--left-hwnd/--right-hwnd/--profile → 双窗吸附（corner==1）、宿主矩形=工作区、
     profile 配置落盘孤儿记录；优雅关 → 双窗回吸附前矩形 + 圆角还原 + 记录清空
  S3 配置隔离：默认 config.json 不含接管实例的孤儿记录（多实例互不覆盖）
  S4 报因：三窗三等分 TOO_MANY:3 / 上下排列 STACKED / 两窗留缝 NO_LAYOUT / 单窗半屏 NO_LAYOUT
  S5 无效句柄：--left-hwnd 99999999 → 状态栏报"句柄无效"
用法: uv run tools/tests/snap_capture_test.py [--exe 路径]
警告: 会强杀所有 WindowMerger/Notepad；结束自己拉起的 snap 靶窗。
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia


class _ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG), ("bmHeight", wintypes.LONG),
                ("bmWidthBytes", wintypes.LONG), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p)]


_user32_probe = ctypes.windll.user32
_gdi32_probe = ctypes.windll.gdi32
_user32_probe.SendMessageW.restype = ctypes.c_ssize_t  # LRESULT 64 位，默认 c_int 会截断句柄
_user32_probe.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32_probe.GetIconInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ICONINFO)]
_gdi32_probe.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.POINTER(_BITMAP)]
_gdi32_probe.DeleteObject.argtypes = [wintypes.HANDLE]


def host_icon_size(h: int) -> tuple[int, int] | None:
    """宿主 WM_GETICON(ICON_BIG) 的图标本征尺寸：双窗拼接 = SM_CXICON 尺寸，
    回退应用图标 = 256px 大帧——黑盒区分"拼图管线是否生效"。"""
    hicon = _user32_probe.SendMessageW(wintypes.HWND(h), 0x7F, wintypes.WPARAM(1), wintypes.LPARAM(0))
    if not hicon:
        return None
    ii = _ICONINFO()
    if not _user32_probe.GetIconInfo(wintypes.HANDLE(hicon), ctypes.byref(ii)):
        return None
    bm = _BITMAP()
    _gdi32_probe.GetObjectW(wintypes.HANDLE(ii.hbmColor), ctypes.sizeof(_BITMAP), ctypes.byref(bm))
    _gdi32_probe.DeleteObject(ii.hbmMask)
    _gdi32_probe.DeleteObject(ii.hbmColor)
    return (bm.bmWidth, bm.bmHeight)

SWP_FLAGS = 0x0004 | 0x0010  # SWP_NOZORDER | SWP_NOACTIVATE
TARGET_SCRIPT = Path(__file__).resolve().parents[1] / "targets" / "snap_target.py"


TARGET_TITLES = ("WM_SNAP_A", "WM_SNAP_B", "WM_SNAP_C", "WM_SNAP_D", "WM_SNAP_E")


def kill_title_owners() -> None:
    """强杀残留靶窗的属主进程：中途崩溃的旧 run 来不及 terminate 时，同名残留窗
    会占据检测布局并让 find_window_by_title 命中旧窗（实测污染整轮 S4）。"""
    for t in TARGET_TITLES:
        h = wm.find_window_by_title(t)
        if h:
            wm.force_kill_pid(wm.pid_of(h))


def profile_config_path(name: str) -> str:
    return os.path.join(os.environ["APPDATA"], "WindowMerger", f"config-{name}.json")


def read_json_file(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def wait_window(title: str, timeout_ms: int = 8000) -> int:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        h = wm.find_window_by_title(title)
        if h:
            return h
        time.sleep(0.1)
    return 0


class Rig:
    """靶窗/宿主/检测的公共脚手架。"""

    def __init__(self, exe: str):
        self.exe = exe
        self.procs: list[subprocess.Popen] = []

    def spawn_target(self, title: str) -> int:
        p = subprocess.Popen([sys.executable, str(TARGET_SCRIPT), title], env=wm.host_env())
        self.procs.append(p)
        h = wait_window(title)
        if not h:
            raise RuntimeError(f"target window {title} not shown")
        time.sleep(0.3)  # tkinter 首帧布局稳定
        return h

    def start_host(self, args: list[str]) -> int:
        p = subprocess.Popen([self.exe] + args, env=wm.host_env())
        self.procs.append(p)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            wins = wm.main_windows_of_pid(p.pid)
            if wins:
                return wins[0]
            time.sleep(0.1)
        return 0

    def detect(self) -> dict:
        p = subprocess.run([self.exe, "--detect-snap"], capture_output=True, timeout=30)
        out = p.stdout.decode("utf-8", errors="replace")
        lines = [l for l in out.strip().splitlines() if l.strip()]
        if not lines:
            raise RuntimeError(f"detect no output rc={p.returncode} "
                               f"stderr={p.stderr.decode(errors='replace')[:200]}")
        return json.loads(lines[-1])

    def kill_all(self) -> None:
        for p in self.procs:
            try:
                p.terminate()
            except Exception:
                pass
        self.procs.clear()
        # 等靶窗真正消失再返回：tkinter 退出有延迟，残留同名窗会被下一场景
        # 的 find_window_by_title 命中（THIRDS 场景曾因此拼图窗口互相重叠 → NO_LAYOUT 假失败）
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            alive = [t for t in ("WM_SNAP_A", "WM_SNAP_B", "WM_SNAP_C", "WM_SNAP_D", "WM_SNAP_E")
                     if wm.find_window_by_title(t)]
            if not alive:
                break
            time.sleep(0.1)
        time.sleep(0.2)


def efb_align(h: int, target: tuple[int, int, int, int]) -> bool:
    """把窗口的可见边界（EFB）对齐到目标矩形：设 GetWindowRect → 读 EFB → 差值修正。
    靶窗模拟真实 snap 必须按 EFB 对齐——GetWindowRect 有 ~7px 隐形边，直接摆
    GetWindowRect 会让相邻窗 EFB 重叠/留缝，检测口径（EFB）下必失败。"""
    ok = False
    for _ in range(5):
        e = wm.ext_frame_bounds(h)
        if e is None:
            return False
        dx = target[0] - e.Left
        dy = target[1] - e.Top
        dw = target[2] - e.Right
        dh = target[3] - e.Bottom
        if max(abs(dx), abs(dy), abs(dw), abs(dh)) <= 1:
            ok = True
            break
        r = wm.get_window_rect(h)
        if r is None:
            return False
        wm.set_window_pos(h, None, r.Left + dx, r.Top + dy, r.width + dw, r.height + dh, SWP_FLAGS)
    e = wm.ext_frame_bounds(h)
    if e is None:
        return False
    return max(abs(target[0] - e.Left), abs(target[1] - e.Top),
               abs(target[2] - e.Right), abs(target[3] - e.Bottom)) <= 2


def foreign_big_windows(wa) -> list[str]:
    """测试屏上 ≥1/3 工作区面积的外来可见窗（标题列表）。detector 的面积降序贪心会被
    它们抢先把靶窗挤掉——三等分靶窗（各 33%）小于任何更大的外来窗（ZCode 主窗实测）。"""
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    out: list[str] = []
    work = (wa.Right - wa.Left) * (wa.Bottom - wa.Top)

    def cb(h, _lp):
        if wm.is_window_visible(h) and not wm.is_cloaked(h) and not wm.is_iconic(h) \
                and not wm.is_zoomed(h) and not wm.is_toolwindow(h):
            t = wm.get_text(h)
            if t:
                e = wm.ext_frame_bounds(h)
                if e and (e.Right - e.Left) * (e.Bottom - e.Top) >= work // 3:
                    out.append(t[:30])
        return True

    _user32_probe.EnumWindows(EnumProc(cb), 0)
    return out


def pick_clean_monitor() -> tuple[object, bool]:
    """选测试屏：优先无大外来窗的 96DPI 屏；全都有外来窗时回退 pick_test_monitor 并
    返回 skip_detect=True——S1/S4 检测场景标 SKIP（S2/S3/S5/S6 不依赖检测照常跑）。"""
    cands = ([m for m in wm.monitors() if wm.monitor_dpi(m) == 96]
             or [m for m in wm.monitors() if m.dwFlags & 1]
             or list(wm.monitors()))
    for m in cands:
        if not foreign_big_windows(m.rcWork):
            return m, False
    return wm.pick_test_monitor(), bool(foreign_big_windows(wm.pick_test_monitor().rcWork))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    rig = Rig(a.exe)
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    # ---------- 清场 ----------
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger", "Notepad")
    time.sleep(0.5)
    kill_title_owners()
    for name in ("snap-test", "snap-test2"):
        Path(profile_config_path(name)).unlink(missing_ok=True)
    wm.remove_config()

    mi, skip_detect = pick_clean_monitor()
    wa = mi.rcWork
    mons = wm.monitors()
    mon_index = next((i for i, m in enumerate(mons)
                      if (m.rcMonitor.Left, m.rcMonitor.Top) == (mi.rcMonitor.Left, mi.rcMonitor.Top)), 0)
    mid_x = (wa.Left + wa.Right) // 2
    if skip_detect:
        print("SKIP_FOREIGN_WINDOW: 测试屏全被 ≥1/3 工作区的外来大窗占用（S1/S4 检测场景跳过）")

    # 基线默认 config（空孤儿记录）：无参宿主起→停到测试屏→优雅关落盘
    hm0 = rig.start_host([])
    if hm0:
        wm.set_window_pos(hm0, None, wa.Left + 20, wa.Top + 20,
                          min(900, (wa.Right - wa.Left) // 2), min(600, (wa.Bottom - wa.Top) // 2),
                          SWP_FLAGS)
        wm.post_close(hm0)
        wm.wait_until(lambda: not wm.pids_by_name("WindowMerger"), 8000, 200)
    time.sleep(0.5)
    check("S0_BASELINE_CONFIG", bool(read_json_file(wm.config_path())))

    try:
        # ---------- S1 检测命中（50/50） ----------
        ha = rig.spawn_target("WM_SNAP_A")
        hb = rig.spawn_target("WM_SNAP_B")
        check("S1_ALIGN_L", efb_align(ha, (wa.Left, wa.Top, mid_x, wa.Bottom)))
        check("S1_ALIGN_R", efb_align(hb, (mid_x, wa.Top, wa.Right, wa.Bottom)))

        d = rig.detect() if not skip_detect else {"ok": False, "skipped": True}
        check("S1_DETECT_OK" if not skip_detect else "S1_SKIP_FOREIGN_WINDOW",
              bool(d.get("ok")) if not skip_detect else True, f"d={d}")
        if d.get("ok"):
            check("S1_HWNDS", d.get("left") == ha and d.get("right") == hb,
                  f"left={d.get('left')}/{ha} right={d.get('right')}/{hb}")
            check("S1_RATIO", abs(float(d.get("ratio", 0)) - 0.5) < 0.02, f"ratio={d.get('ratio')}")
            check("S1_MONITOR", d.get("monitor") == mon_index,
                  f"got={d.get('monitor')} expect={mon_index}")

        # ---------- S1b 2:1 变体 ----------
        w13 = (wa.Right - wa.Left) // 3
        check("S1B_ALIGN_L", efb_align(ha, (wa.Left, wa.Top, wa.Left + w13 * 2, wa.Bottom)))
        check("S1B_ALIGN_R", efb_align(hb, (wa.Left + w13 * 2, wa.Top, wa.Right, wa.Bottom)))
        # 吸附前矩形基线必须在最后一次对齐之后记录（捕获时窗口就在这里，释放应回这里）
        pre_a, pre_b = wm.get_window_rect(ha), wm.get_window_rect(hb)
        d2 = rig.detect() if not skip_detect else {"ok": False}
        check("S1B_RATIO" if not skip_detect else "S1B_SKIP_FOREIGN_WINDOW",
              bool(d2.get("ok")) and abs(float(d2.get("ratio", 0)) - 2 / 3) < 0.02
              if not skip_detect else True, f"d={d2}")

        # ---------- S2 接管 e2e + S3 配置隔离 ----------
        host = rig.start_host(["--left-hwnd", str(ha), "--right-hwnd", str(hb),
                               "--profile", "snap-test"])
        check("S2_HOST_ALIVE", bool(host))
        if host:
            attached = wm.wait_until(lambda: wm.is_attached(ha) and wm.is_attached(hb), 10000, 200)
            check("S2_ATTACHED", attached, f"corner_a={wm.corner_pref(ha)} corner_b={wm.corner_pref(hb)}")
            # 拼接图标管线：吸附后宿主大图标 = SM_CXICON(metric 11) 尺寸的拼图（Tk 靶有类图标素材），
            # 若回退成应用 256px 大帧说明拼图没画——注意 wm.SM_CXICON 是错名常量（实为 49=SM_CXSMICON/16px）
            ico = host_icon_size(host) if attached else None
            sm = (wm.get_system_metrics(11), wm.get_system_metrics(12))
            check("S2_ICON_COMPOSITE", ico == sm, f"icon={ico} expect={sm}")
            r = wm.get_window_rect(host)
            union = (wa.Left, wa.Top, wa.Right, wa.Bottom)
            host_union_ok = bool(r) and all(abs(x - y) <= 2 for x, y in
                                            zip((r.Left, r.Top, r.Right, r.Bottom), union))
            check("S2_HOST_RECT", host_union_ok,
                  f"host=({r.Left},{r.Top},{r.Right},{r.Bottom}) union={union}")
            pcfg = read_json_file(profile_config_path("snap-test"))
            hwnds = set(pcfg.get("AttachedHwnds") or []) if pcfg else set()
            check("S2_PROFILE_ORPHAN_RECORD", {ha, hb} <= hwnds, f"pcfg={pcfg}")
            dcfg = read_json_file(wm.config_path())
            dhwnds = set(dcfg.get("AttachedHwnds") or []) if dcfg else set()
            check("S3_DEFAULT_CONFIG_UNTOUCHED", not (dhwnds & {ha, hb}), f"dcfg_hwnds={dhwnds}")

            wm.post_close(host)
            released = wm.wait_until(lambda: not wm.pids_by_name("WindowMerger"), 8000, 200)
            check("S2_HOST_CLOSED", released)
            time.sleep(0.5)
            ra, rb = wm.get_window_rect(ha), wm.get_window_rect(hb)
            back_a = bool(ra) and all(abs(x - y) <= 2 for x, y in
                                      zip((ra.Left, ra.Top, ra.Right, ra.Bottom),
                                          (pre_a.Left, pre_a.Top, pre_a.Right, pre_a.Bottom)))
            back_b = bool(rb) and all(abs(x - y) <= 2 for x, y in
                                      zip((rb.Left, rb.Top, rb.Right, rb.Bottom),
                                          (pre_b.Left, pre_b.Top, pre_b.Right, pre_b.Bottom)))
            check("S2_RESTORE_A", back_a, f"now=({ra.Left},{ra.Top},{ra.Right},{ra.Bottom}) "
                                          f"pre=({pre_a.Left},{pre_a.Top},{pre_a.Right},{pre_a.Bottom})")
            check("S2_RESTORE_B", back_b, f"now=({rb.Left},{rb.Top},{rb.Right},{rb.Bottom})")
            check("S2_CORNERS_BACK", wm.corner_pref(ha) == 0 and wm.corner_pref(hb) == 0,
                  f"corner_a={wm.corner_pref(ha)} corner_b={wm.corner_pref(hb)}")
            pcfg2 = read_json_file(profile_config_path("snap-test"))
            check("S2_PROFILE_RECORD_CLEARED",
                  bool(pcfg2) and not (pcfg2.get("AttachedHwnds") or []), f"pcfg2={pcfg2}")

        rig.kill_all()

        # ---------- S4 报因场景（检测依赖测试屏无大外来窗，否则标 SKIP） ----------
        if skip_detect:
            check("S4_SKIP_FOREIGN_WINDOW", True, "SKIP_FOREIGN_WINDOW")
        else:
            # 单窗半屏
            h1 = rig.spawn_target("WM_SNAP_C")
            efb_align(h1, (wa.Left, wa.Top, mid_x, wa.Bottom))
            d = rig.detect()
            check("S4_SINGLE_NO_LAYOUT", not d.get("ok") and d.get("reason") == "NO_LAYOUT", f"d={d}")
            rig.kill_all()

            # 两窗留缝（并集 bbox=工作区但中间空 20px → 不成布局，不得误报 STACKED）
            h1 = rig.spawn_target("WM_SNAP_C")
            h2 = rig.spawn_target("WM_SNAP_D")
            efb_align(h1, (wa.Left, wa.Top, mid_x - 10, wa.Bottom))
            efb_align(h2, (mid_x + 10, wa.Top, wa.Right, wa.Bottom))
            d = rig.detect()
            check("S4_GAP_NO_LAYOUT", not d.get("ok") and d.get("reason") == "NO_LAYOUT", f"d={d}")
            rig.kill_all()

            # 上下排列
            mid_y = (wa.Top + wa.Bottom) // 2
            h1 = rig.spawn_target("WM_SNAP_C")
            h2 = rig.spawn_target("WM_SNAP_D")
            efb_align(h1, (wa.Left, wa.Top, wa.Right, mid_y))
            efb_align(h2, (wa.Left, mid_y, wa.Right, wa.Bottom))
            d = rig.detect()
            check("S4_STACKED", not d.get("ok") and d.get("reason") == "STACKED", f"d={d}")
            rig.kill_all()

            # 三窗三等分
            w13 = (wa.Right - wa.Left) // 3
            h1 = rig.spawn_target("WM_SNAP_C")
            h2 = rig.spawn_target("WM_SNAP_D")
            h3 = rig.spawn_target("WM_SNAP_E")
            check("S4_ALIGN_C", efb_align(h1, (wa.Left, wa.Top, wa.Left + w13, wa.Bottom)))
            check("S4_ALIGN_D", efb_align(h2, (wa.Left + w13, wa.Top, wa.Left + w13 * 2, wa.Bottom)))
            check("S4_ALIGN_E", efb_align(h3, (wa.Left + w13 * 2, wa.Top, wa.Right, wa.Bottom)))
            d = rig.detect()
            check("S4_THIRDS_TOO_MANY", not d.get("ok") and d.get("reason") == "TOO_MANY:3", f"d={d}")
            rig.kill_all()

        # ---------- S5 无效句柄 ----------
        host = rig.start_host(["--left-hwnd", "99999999", "--profile", "snap-test2"])
        check("S5_HOST_ALIVE", bool(host))
        if host:
            st = None
            got = wm.wait_until(lambda: (s := wm_uia.status_text(host)) and "句柄无效" in s, 6000, 200)
            try:
                st = wm_uia.status_text(host)
            except Exception:
                pass
            check("S5_INVALID_HWND_NOTICE", got, f"status={st!r}")
            wm.post_close(host)
            wm.wait_until(lambda: not wm.pids_by_name("WindowMerger"), 8000, 200)

        # ---------- S6 托盘生命周期（--tray：常驻 + 单实例 mutex） ----------
        # 热键/捕捉路径与 --detect-snap + spawn 共用代码，上面已测；这里只验进程语义
        tray1 = subprocess.Popen([rig.exe, "--tray"], env=wm.host_env())
        time.sleep(2.5)
        check("S6_TRAY_ALIVE", tray1.poll() is None)  # 零窗口下常驻（ShutdownMode 显式）
        tray2 = subprocess.Popen([rig.exe, "--tray"], env=wm.host_env())
        tray2_exited = wm.wait_until(lambda: tray2.poll() is not None, 6000, 100)
        check("S6_TRAY_SINGLE_INSTANCE", tray2_exited and tray2.returncode == 0,
              f"rc={tray2.returncode}")
        tray1.terminate()  # 测试清理用强杀；正式退出走托盘菜单（Exit→Shutdown）
        try:
            tray1.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tray1.kill()
        check("S6_TRAY_STOPPED", tray1.poll() is not None)
    finally:
        rig.kill_all()
        kill_title_owners()
        wm.graceful_close_by_name("WindowMerger")
        for name in ("snap-test", "snap-test2"):
            Path(profile_config_path(name)).unlink(missing_ok=True)
        wm.remove_config()  # 还原干净状态（后续测试约定 config 从零开始自管）

    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
