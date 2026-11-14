# -*- coding: utf-8 -*-
"""snap 检测 NO_LAYOUT 排查 dump（非常驻回归）：按 SnapLayoutDetector 同款判据
（EFB 物理像素、工作区容差 8、面积 ≥5%、互不重叠贪心、并集≈工作区、共享竖边）
逐屏逐窗打印候选与判据结果，定位高 DPI 屏抓不到布局卡在哪一条。
用法: uv run tools/diag/snap_detect_dump.py
标记（英文）：MONITOR / CAND / DROP / KEPT / VERDICT / DONE
"""
import ctypes
import ctypes.wintypes as wt
import sys
from ctypes import byref, sizeof
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm  # noqa: E402

TOL = 8
MIN_ZONE = 0.05
EXCLUDED_CLASSES = {
    "Shell_TrayWnd", "Progman", "WorkerW", "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow", "ApplicationFrameWindow",
}

_u = ctypes.windll.user32
_dwm = ctypes.windll.dwmapi


class EFB_RECT(ctypes.Structure):
    _fields_ = [("L", ctypes.c_long), ("T", ctypes.c_long),
                ("R", ctypes.c_long), ("B", ctypes.c_long)]


def efb_of(h: int) -> tuple[int, int, int, int] | None:
    r = EFB_RECT()
    if _dwm.DwmGetWindowAttribute(wt.HWND(h), 9, byref(r), sizeof(EFB_RECT)) == 0:
        return (r.L, r.T, r.R, r.B)
    return None


def enum_tops() -> list[int]:
    out: list[int] = []
    CB = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    @CB
    def cb(h, _lp):
        out.append(h)
        return True

    _u.EnumWindows(cb, 0)
    return out


def mon_of(h: int) -> int:
    return _u.MonitorFromWindow(wt.HWND(h), 2)  # MONITOR_DEFAULTTONEAREST


def mon_center_hmon(m) -> int:
    pt = wt.POINT((m.rcMonitor.Left + m.rcMonitor.Right) // 2,
                  (m.rcMonitor.Top + m.rcMonitor.Bottom) // 2)
    return _u.MonitorFromPoint(pt, 2)


def main() -> int:
    mons = wm.monitors()
    print(f"MONITORS {len(mons)}")
    for i, m in enumerate(mons):
        rm, rw = m.rcMonitor, m.rcWork
        print(f"  MONITOR[{i}] full=({rm.Left},{rm.Top})-({rm.Right},{rm.Bottom}) "
              f"wa=({rw.Left},{rw.Top})-({rw.Right},{rw.Bottom}) dpi={wm.monitor_dpi(m)}")

    cands: list[tuple[int, str, str, tuple[int, int, int, int]]] = []
    for h in enum_tops():
        if not _u.IsWindowVisible(h) or wm.is_cloaked(h) or _u.IsIconic(h) or _u.IsZoomed(h):
            continue
        if _u.GetWindowLongW(h, -20) & 0x80:  # WS_EX_TOOLWINDOW
            continue
        if _u.GetWindow(h, 4):  # GW_OWNER
            continue
        cls = wm.get_class_name(h)
        if cls in EXCLUDED_CLASSES:
            continue
        if wm.pid_of(h) == ctypes.windll.kernel32.GetCurrentProcessId():
            continue
        title = wm.get_text(h)
        if not title:
            continue
        e = efb_of(h)
        if not e:
            continue
        cands.append((h, title[:36], cls, e))

    print(f"CANDS {len(cands)}")
    for h, t, cls, e in cands:
        print(f"  CAND hwnd={h} mon={mon_of(h):x} efb={e} "
              f"proc={wm.proc_name_of(h)} class={cls} title={t!r}")

    for i, m in enumerate(mons):
        rw = m.rcWork
        wl, wt_, wr, wb = rw.Left, rw.Top, rw.Right, rw.Bottom
        work = (wr - wl) * (wb - wt_)
        hmon = mon_center_hmon(m)
        elig = []
        for h, t, cls, (L, T, R, B) in cands:
            if mon_of(h) != hmon:
                continue
            ok_in = (L >= wl - TOL and T >= wt_ - TOL and R <= wr + TOL and B <= wb + TOL)
            zone = (R - L) * (B - T)
            ok_area = zone >= work * MIN_ZONE
            if ok_in and ok_area:
                elig.append((h, t, (L, T, R, B), zone / work))
            else:
                why = []
                if not ok_in:
                    why.append(f"出工作区(L{L}<wl-TOL or T{T}<wt-TOL or R{R}>wr+TOL or B{B}>wb+TOL)")
                if not ok_area:
                    why.append(f"面积比 {zone / work:.2f}")
                print(f"  M[{i}] DROP hwnd={h} {t!r} efb={(L, T, R, B)} {'; '.join(why)}")
        print(f"  M[{i}] eligible={len(elig)}")

        kept = []
        for h, t, r, frac in sorted(elig,
                                    key=lambda x: -(x[2][2] - x[2][0]) * (x[2][3] - x[2][1])):
            ok = True
            for kh, kt, kr, kf in kept:
                ox = min(r[2], kr[2]) - max(r[0], kr[0])
                oy = min(r[3], kr[3]) - max(r[1], kr[1])
                if ox > TOL and oy > TOL:
                    ok = False
                    print(f"  M[{i}] OVERLAP-DROP hwnd={h} {t!r} vs {kt!r} ox={ox} oy={oy}")
                    break
            if ok:
                kept.append((h, t, r, frac))
        for h, t, r, frac in kept:
            print(f"  M[{i}] KEPT hwnd={h} {t!r} efb={r} frac={frac:.2f}")

        if len(kept) < 2:
            print(f"  M[{i}] VERDICT NO_LAYOUT (kept<2)")
            continue
        l = min(r[0] for _h, _t, r, _f in kept)
        t0 = min(r[1] for _h, _t, r, _f in kept)
        r0 = max(r[2] for _h, _t, r, _f in kept)
        b0 = max(r[3] for _h, _t, r, _f in kept)
        tiles = (abs(l - wl) <= TOL and abs(t0 - wt_) <= TOL
                 and abs(r0 - wr) <= TOL and abs(b0 - wb) <= TOL)
        if not tiles:
            print(f"  M[{i}] VERDICT NO_LAYOUT bbox=({l},{t0},{r0},{b0}) 拼不满工作区")
            continue
        if len(kept) == 2:
            (_ha, _ta, ra, _fa), (_hb, _tb, rb, _fb) = kept
            sv = abs(ra[2] - rb[0]) <= TOL or abs(rb[2] - ra[0]) <= TOL
            sh = abs(ra[3] - rb[1]) <= TOL or abs(rb[3] - ra[1]) <= TOL
            if sv:
                print(f"  M[{i}] VERDICT PAIR 左右对分 OK")
            elif sh:
                print(f"  M[{i}] VERDICT STACKED 上下")
            else:
                print(f"  M[{i}] VERDICT NO_LAYOUT 两窗有缝（不共享边）")
        else:
            print(f"  M[{i}] VERDICT TOO_MANY:{len(kept)}")
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
