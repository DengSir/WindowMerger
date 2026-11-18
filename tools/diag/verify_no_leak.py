"""验证精确就位判定修复漏底：吸附 ZCode 到右格，测多个比例点——分隔条右侧第一列
（= 右格边线列）在 60 行采样上方差：恒 3A = 边线盖住透明边列；高方差/偏亮 = 仍漏。"""
import ctypes, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import wm  # noqa: E402
import wm_uia  # noqa: E402
from ctypes import wintypes  # noqa: E402

WM_OPEN_HOST = 0x0400 + 1
CONFIG = os.path.join(os.environ["APPDATA"], "WindowMerger", "config.json")
_user32 = ctypes.windll.user32

def edit_ratio(r):
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["Ratio"] = round(r, 6)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def close_hosts():
    for h in wm.top_windows_of_pids(wm.pids_by_name("WindowMerger")):
        wm.post_close(h)
    dl = time.monotonic() + 5
    while time.monotonic() < dl and wm.host_hwnd():
        time.sleep(0.2)

def open_host():
    tw = wm.find_tray_message_window()
    _user32.PostMessageW(wintypes.HWND(tw), wintypes.UINT(WM_OPEN_HOST), wintypes.WPARAM(0), wintypes.LPARAM(0))
    dl = time.monotonic() + 8
    while time.monotonic() < dl:
        h = wm.host_hwnd()
        if h:
            return h
        time.sleep(0.2)
    return 0

def zcode_hwnd():
    for pid in wm.pids_by_name("ZCode"):
        mains = wm.main_windows_of_pid(pid)
        if mains:
            return mains[0]
    return 0

def probe(h, kids):
    """找分隔条带（3C 连续段），返回右缘后第一列的 60 行采样方差与颜色集合。"""
    efb = wm.ext_frame_bounds(h)
    W = efb.Right - efb.Left
    img = wm.capture_screen(efb.Left, efb.Top + 300, W, 1)
    px = img.load()
    cols = ["%02X" % (sum(px[x, 0][:3]) // 3) for x in range(W)]
    # 分隔条 = 3C 连续段
    div = [x for x, c in enumerate(cols) if c == "3C"]
    if not div:
        return None
    a, b = div[0], div[-1]
    lane = b + 1  # 右格第一列（边线列）
    vals = []
    y0, y1 = efb.Top + 40, efb.Bottom - 20
    for y in range(y0, y1, max(1, (y1 - y0) // 60)):
        img2 = wm.capture_screen(efb.Left + lane, y, 1, 1)
        p2 = img2.load()
        vals.append(sum(p2[0, 0][:3]) // 3)
    return {"div": (a, b), "lane": lane, "min": min(vals), "max": max(vals),
            "varies": (max(vals) - min(vals)) > 6, "vals": vals[:8]}

def main():
    ratios = [0.5317, 0.3, 0.5, 0.699541]
    out = []
    for r in ratios:
        close_hosts()
        edit_ratio(r)
        h = open_host()
        np = zcode_hwnd()
        if not np:
            print("NO_ZCODE")
            return 1
        done = wm_uia.attach_via_panes(h, [(1, "zcode")])
        time.sleep(0.8)
        kids = [w for w in wm.z_walk() if wm.is_window_visible(w) and wm.corner_pref(w) == 1]
        res = probe(h, kids)
        if res is None:
            print(f"ratio={r} NO_DIVIDER_BAND")
            continue
        status = "LEAK" if res["varies"] or res["min"] > 70 else "clean"
        print(f"ratio={r} div={res['div']} lane_col={res['lane']} min={res['min']} max={res['max']} -> {status} vals={res['vals']}")
        out.append((r, status))
        # 释放 ZCode
        el = wm_uia.element_from_handle(h)
        btn = wm_uia.find_by_automation_id(el, "_releaseButton")
        if btn:
            wm_uia.invoke(btn)
        time.sleep(0.4)
    print("RESULT:", out)
    close_hosts()
    edit_ratio(0.5)
    open_host()
    return 0

if __name__ == "__main__":
    sys.exit(main())
