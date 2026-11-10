# -*- coding: utf-8 -*-
"""分隔条两侧透明缝诊断（用户实测：拖宿主边缘缩放后，分隔条左右各出现一条透明缝，
能看到后面的窗口；再拖分隔条本身恢复不透明）。

目的：分辨缝的来源——
  A) 子窗口放置脱节：子窗可见内容边缘（EFB）短于格子矩形，缝在子窗与分隔条之间
     （宿主表面该处本来就是 alpha=0 格子，属放置问题）；
  B) 宿主 WPF 表面自身缺像素：子窗就位仍有缝（陈旧未重绘/分数像素 AA），
     缝与分隔条本体可见宽度直接相关。

方法：品红标记窗垫在宿主后面 → 注入拖宿主右缘/左缘缩放（真实 WM_SIZING 循环）→
后台高频采样分隔条带状区域，按列分类（M=纯品红缝 / D=#3C3C3C 分隔条 / W=子窗白底 /
b=混合过渡）→ 对照子窗 EFB 矩形 → 再注入拖分隔条验证恢复。

诊断脚本，不进 run_all。
用法: uv run tools/diag/divider_seam_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
"""
import argparse
import ctypes
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

MARKER_PID = 0
SNAP_DIR = Path(tempfile.gettempdir()) / "wm_seam_diag"

# 布局常量（DIP；测试屏优先 96 DPI，此时 DIP==物理像素）
BW_DIP, TOPBAR_DIP, DIVIDER_DIP = 2, 28, 6
HTLEFT, HTRIGHT = 10, 11
HWND_BOTTOM = 1


def nchittest_at(hwnd: int, x: int, y: int) -> int:
    """WM_NCHITTEST 探针（SendMessageTimeoutW 防挂起）。"""
    WM_NCHITTEST, SMTO_ABORTIFHUNG = 0x0084, 0x0002
    lp = (y & 0xFFFF) << 16 | (x & 0xFFFF)
    res = wintypes.LPARAM()
    u32 = ctypes.windll.user32
    if u32.SendMessageTimeoutW(wintypes.HWND(hwnd), WM_NCHITTEST, None,
                               wintypes.LPARAM(lp), SMTO_ABORTIFHUNG, 1000,
                               ctypes.byref(res)):
        return res.value & 0xFFFF
    return -1


def edge_grab_point(hwnd: int, edge: str) -> tuple[int, int] | None:
    """缩放边抓点：在窗口竖直中线自边缘向内找 WM_NCHITTEST==HTLEFT/HTRIGHT 的第一个 x。"""
    r = wm.ext_frame_bounds(hwnd) or wm.get_window_rect(hwnd)
    y = r.Top + r.height // 2
    want = HTRIGHT if edge == "right" else HTLEFT
    rng = range(r.Right - 2, r.Right - 30, -1) if edge == "right" else range(r.Left + 2, r.Left + 30)
    for x in rng:
        if nchittest_at(hwnd, x, y) == want:
            return (x, y)
    return None


def drag(from_x: int, from_y: int, to_x: int, to_y: int, steps: int = 20) -> None:
    wm.set_cursor_pos(from_x, from_y)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.15)
    for i in range(1, steps + 1):
        wm.set_cursor_pos(from_x + int((to_x - from_x) * i / steps),
                          from_y + int((to_y - from_y) * i / steps))
        time.sleep(0.03)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(0.8)


class Sampler:
    """后台高频采样线程：截分隔条带状区域，扫描纯品红/分隔条深色/子窗白色像素，
    汇总每个样本的列直方图（列分类 M/D/W/b）。"""

    def __init__(self, x0: int, y0: int, w: int, h: int):
        self.x0, self.y0, self.w, self.h = x0, y0, w, h
        self.events: list[tuple[str, int, int, int]] = []  # (phase, t, magenta_cols, dark_cols)
        self.phase = "init"
        self.running = False
        self.last_img = None

    def set_phase(self, p: str) -> None:
        self.phase = p

    def start(self) -> None:
        import threading
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        mag = b"\xff\x00\xff"   # BGRX 品红 (255,0,255)
        dark = b"\x3c\x3c\x3c"  # BGRX #3C3C3C 分隔条
        white = b"\xff\xff\xff"
        while self.running:
            t = time.perf_counter()
            img = wm.capture_screen(self.x0, self.y0, self.w, self.h)
            self.last_img = img
            data = img.tobytes()
            mcols, dcols = set(), set()
            pos = data.find(mag)
            while pos >= 0:
                if pos % 4 == 0:
                    mcols.add((pos // 4) % self.w)
                pos = data.find(mag, pos + 1)
            pos = data.find(dark)
            while pos >= 0:
                if pos % 4 == 0:
                    dcols.add((pos // 4) % self.w)
                pos = data.find(dark, pos + 1)
            _ = data.find(white)  # 白色列在快照直方图里看，主循环不计（省时）
            self.events.append((self.phase, t, len(mcols), len(dcols)))
            if mcols:
                self.events.append((self.phase + ":M", t, sorted(mcols)[0], sorted(mcols)[-1]))

    def stop(self) -> None:
        self.running = False
        time.sleep(0.15)

    def event_groups(self) -> dict[str, list]:
        """按 phase 前缀聚合（:M 标记归属主 phase）。"""
        groups: dict[str, list] = {}
        for ev in self.events:
            key = ev[0].split(":")[0]
            groups.setdefault(key, []).append(ev)
        return groups


def column_profile(img, w: int, h: int, rows_step: int = 4) -> str:
    """按列分类快照：M=含纯品红，D=多数 #3C3C3C，W=多数纯白，b=混合。"""
    data = img.tobytes()
    mag, dark, white = b"\xff\x00\xff", b"\x3c\x3c\x3c", b"\xff\xff\xff"
    out = []
    rows = range(0, h, rows_step)
    for x in range(w):
        m = d = wht = 0
        n = 0
        for y in rows:
            off = (y * w + x) * 4
            px = data[off:off + 3]
            n += 1
            if px == mag:
                m += 1
            elif px == dark:
                d += 1
            elif px == white:
                wht += 1
        if m >= 2:
            out.append("M")
        elif d >= n * 0.5:
            out.append("D")
        elif wht >= n * 0.5:
            out.append("W")
        else:
            out.append("b")
    return "".join(out)


def children_efb() -> tuple:
    l = wm.main_windows_by_name("Notepad")
    m = wm.main_windows_by_name("mspaint")
    lefb = wm.ext_frame_bounds(l[0][1]) if l else None
    refb = wm.ext_frame_bounds(m[0][1]) if m else None
    return (lefb, refb)


def dump_state(tag: str, host: int) -> None:
    lefb, refb = children_efb()
    hr = wm.get_window_rect(host)
    print(f"[{tag}] host=({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom}) "
          f"L_efb={lefb and (lefb.Left, lefb.Right)} R_efb={refb and (refb.Left, refb.Right)}")


def probe(s: Sampler, host: int, tag: str, settle: float = 0.9) -> None:
    """静止采样 settle 秒 + 打印列分类剖面与判定线索。"""
    time.sleep(settle)
    img = s.last_img
    if img is None:
        print(f"[{tag}] NO_SAMPLE")
        return
    lefb, refb = children_efb()
    prof = column_profile(img, s.w, s.h)
    print(f"[{tag}] band_x0={s.x0} profile={prof}")
    print(f"[{tag}] host_x={wm.get_window_rect(host).Left} "
          f"L_efb.Right={lefb and lefb.Right} R_efb.Left={refb and refb.Left} "
          f"(band 内相对坐标：列号 + {s.x0})")
    SNAP_DIR.mkdir(exist_ok=True)
    p = SNAP_DIR / f"{tag}.png"
    img.save(p)
    print(f"[{tag}] snapshot={p}")


def main() -> int:
    global MARKER_PID
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    SNAP_DIR.mkdir(exist_ok=True)

    layout = wm.test_layout()
    hx, hy, hw, hh = layout["host"]
    wa = wm.pick_test_monitor().rcWork

    # 品红标记窗：盖住宿主矩形外扩（缩放位移全在覆盖内），先创建 → 天然垫底
    mx, my = max(wa.Left, hx - 100), max(wa.Top, hy - 20)
    mw = min(wa.Right - mx, hw + 200)
    mh = min(wa.Bottom - my, hh + 40)
    marker = subprocess.Popen([sys.executable,
                               str(Path(__file__).resolve().parents[1] / "targets" / "color_pad.py"),
                               "--color", "255,0,255", "--geometry", f"{mw}x{mh}+{mx}+{my}"])
    MARKER_PID = marker.pid
    time.sleep(1.2)

    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t1.write_text("seam-diag", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.2)
    subprocess.Popen(["mspaint"])
    time.sleep(1.5)
    subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    wm.set_window_pos(hm, None, hx, hy, hw, hh, wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm, True)
    time.sleep(0.4)

    lefb, refb = children_efb()
    if not lefb or not refb:
        print("NO_CHILDREN")
        return 1
    div_x = (lefb.Right + refb.Left) // 2
    mid_y = hy + TOPBAR_DIP + (hh - TOPBAR_DIP) // 2
    print(f"SETUP host=({hx},{hy},{hw},{hh}) divider~{div_x} marker=({mx},{my},{mw},{mh})")

    # 采样带：分隔条全程旅行范围（缩放 ±100px）+ 上下各留 12px 避开顶条/底边框
    s = Sampler(div_x - 110, hy + TOPBAR_DIP + 12, 240, hh - TOPBAR_DIP - 30)
    s.start()
    s.set_phase("P0_baseline")
    probe(s, hm, "P0_baseline")

    # P1 右缘外拖 +80（宽度变大，x 不动）
    s.set_phase("P1_resize_right")
    g = edge_grab_point(hm, "right")
    if g is None:
        print("NO_RIGHT_EDGE")
        return 1
    print(f"P1 grab={g}")
    drag(g[0], g[1], g[0] + 80, g[1])
    probe(s, hm, "P1_after_right")
    dump_state("P1", hm)

    # P2 左缘外拖 +80（x 与宽度都变——分隔条整体右移，最考验跟随同步）
    s.set_phase("P2_resize_left")
    g = edge_grab_point(hm, "left")
    if g is None:
        print("NO_LEFT_EDGE")
        return 1
    print(f"P2 grab={g}")
    drag(g[0], g[1], g[0] - 80, g[1])
    probe(s, hm, "P2_after_left")
    dump_state("P2", hm)

    # P3 用户路径：拖分隔条本身（恢复不透明的操作）——观察缝消失与子窗是否随之移动
    lefb, refb = children_efb()
    div_x2 = (lefb.Right + refb.Left) // 2
    s.set_phase("P3_divider_drag")
    drag(div_x2, mid_y, div_x2 + 60, mid_y)
    probe(s, hm, "P3_after_divider_drag")
    dump_state("P3", hm)

    # P4 右缘内收 -80（宽度变小：子窗被压缩的方向）
    s.set_phase("P4_shrink_right")
    g = edge_grab_point(hm, "right")
    drag(g[0], g[1], g[0] - 80, g[1])
    probe(s, hm, "P4_after_shrink")
    dump_state("P4", hm)

    s.stop()
    # 事件汇总：各 phase 出现品红的样本数
    groups = s.event_groups()
    print("---- 采样汇总（各阶段含品红样本数 / 总样本数）----")
    for ph, evs in sorted(groups.items()):
        mhits = sum(1 for e in evs if e[0].endswith(":M"))
        print(f"{ph}: magenta_samples={mhits}/{len(evs)}")

    # 清理：还原层级 + 优雅关宿主
    wm.set_topmost(hm, False)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    marker.kill()
    wm.force_kill_by_name("Notepad", "mspaint")
    print("SEAM_DIAG_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
