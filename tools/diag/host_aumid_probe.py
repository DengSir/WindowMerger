# -*- coding: utf-8 -*-
"""窗口级 AUMID 读回验证（多扇宿主独立任务栏按钮的机制层证据）：无参起首实例 →
第二实例唤起开新扇 → ctypes 走 SHGetPropertyStoreForWindow + IPropertyStore::GetValue
读回两扇 hwnd 的 System.AppUserModel.ID，断言互不相同且以 DengSir.WindowMerger.host- 开头。
本机任务栏图标若被收纳进溢出 flyout（主任务栏树读不到按钮），按钮数黑盒不可行——
读回 property store 是 shell 实际生效值的直接证据。
若启动前检测到已运行的 WindowMerger 实例（可能是用户开着的）→ SKIP 不动它。
用法: uv run tools/diag/host_aumid_probe.py [--exe 路径]
警告: 无已运行实例时会强杀 WindowMerger 残留。
"""
import argparse
import ctypes
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia

PKEY_AUMID_FMTID = ctypes.c_buffer(
    b"\x55\x28\x4C\x9F\xDB\x9F\x4B\x46\x81\x29\x29\xB3\xD3\x1E\x2C\x5A")  # GUID 小端
VT_LPWSTR = 31


def read_window_aumid(hwnd: int, debug: bool = False) -> str | None:
    """SHGetPropertyStoreForWindow + IPropertyStore::GetValue 读回窗口 AppUserModel.ID。
    裸 vtable：槽位 5=GetValue 7=Release(store)。debug=True 打每步 HRESULT。"""
    shell32 = ctypes.windll.shell32
    iid = ctypes.c_buffer(
        b"\xEB\x8E\x6D\x88\xF2\x8C\x46\x44\x8D\x02\xCD\xBA\x1D\xBD\xCF\x4C")  # IPropertyStore
    store = ctypes.c_void_p()
    hr = shell32.SHGetPropertyStoreForWindow(
        ctypes.c_void_p(hwnd), ctypes.byref(iid), ctypes.byref(store))
    if debug:
        print(f"  GetStore(IPropertyStore) hr=0x{hr & 0xFFFFFFFF:08X} store={store.value}")
    if hr != 0 or not store.value:
        # 定性：连 IID_IUnknown 都拿不到 = 转发 stub/入口本身坏；能拿到 = iid 特定问题
        iid_unk = ctypes.c_buffer(
            b"\x00\x00\x00\x00\xC0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
        unk = ctypes.c_void_p()
        hr_unk = shell32.SHGetPropertyStoreForWindow(
            ctypes.c_void_p(hwnd), ctypes.byref(iid_unk), ctypes.byref(unk))
        if debug:
            print(f"  GetStore(IUnknown) hr=0x{hr_unk & 0xFFFFFFFF:08X} store={unk.value}")
        if unk.value:  # IUnknown 拿到了：QI 回 IPropertyStore
            vtbl = ctypes.c_void_p.from_address(unk.value).value
            qi = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_void_p, ctypes.c_void_p)(
                vtbl + 0 * ctypes.sizeof(ctypes.c_void_p))
            store2 = ctypes.c_void_p()
            hr_qi = qi(unk, ctypes.byref(iid), ctypes.byref(store2))
            if debug:
                print(f"  QI(IPropertyStore) hr=0x{hr_qi & 0xFFFFFFFF:08X} store={store2.value}")
            ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtbl + 2 * ctypes.sizeof(ctypes.c_void_p))(unk)
            if hr_qi == 0 and store2.value:
                store = store2
            else:
                return None
        else:
            return None
    try:
        key = ctypes.c_buffer(20)  # PROPERTYKEY: GUID(16) + pid(4)
        ctypes.memmove(key, PKEY_AUMID_FMTID.value, 16)
        struct.pack_into("<I", key, 16, 5)  # pid
        prop = ctypes.c_buffer(24)  # PROPVARIANT: vt(2)+pad(6)+union(8)+对齐
        struct.pack_into("<H", prop, 0, VT_LPWSTR)
        # GetValue 槽位 5：vtable = [QI, AddRef, Release, GetCount, GetAt, GetValue, ...]
        vtbl = ctypes.c_void_p.from_address(store.value).value
        fn = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
            ctypes.cast(vtbl + 5 * ctypes.sizeof(ctypes.c_void_p), ctypes.c_void_p).value)
        hr2 = fn(store, ctypes.addressof(key), ctypes.addressof(prop))
        if debug:
            print(f"  GetValue hr=0x{hr2 & 0xFFFFFFFF:08X}")
        if hr2 != 0:
            return None
        vt = struct.unpack_from("<H", prop, 0)[0]
        if debug:
            print(f"  vt={vt}")
        if vt != VT_LPWSTR:
            return None
        pwsz = ctypes.c_void_p.from_address(
            ctypes.addressof(prop) + 8).value  # union 偏移 8
        if not pwsz:
            return None
        return ctypes.wstring_at(pwsz)
    finally:
        # Release(store) 槽位 2
        vtbl = ctypes.c_void_p.from_address(store.value).value
        rel = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p)(
            ctypes.cast(vtbl + 2 * ctypes.sizeof(ctypes.c_void_p), ctypes.c_void_p).value)
        rel(store)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    if wm.pids_by_name("WindowMerger"):
        print("SKIP_USER_INSTANCE 已有 WindowMerger 在运行（可能是你自己开着的），不动它")
        return 0

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.8)

    try:
        subprocess.Popen([a.exe], env=dict(os.environ, WM_TRACE="1"))
        if not wm.wait_until(lambda: bool(wm.host_hwnd()), 8000, 200):
            print("FAIL_FIRST_HOST")
            return 1
        subprocess.Popen([a.exe], env=dict(os.environ, WM_TRACE="1"))  # 第二实例 → 唤起开新扇
        wm.wait_until(lambda: len(wm.host_hwnds()) == 2, 8000, 200)
        time.sleep(1.0)

        hosts = wm.host_hwnds()
        aumids = [read_window_aumid(h, debug=True) for h in hosts]
        print(f"HOSTS={len(hosts)} AUMIDS={aumids}")
        ok = (len(hosts) == 2
              and all(v and v.startswith("DengSir.WindowMerger.host-") for v in aumids)
              and aumids[0] != aumids[1])
        print(f"RESULT {'PASS' if ok else 'FAIL'}")
        # C# 侧写入/读回诊断（宿主 WM_TRACE=1）
        trace_log = Path(__import__("tempfile").gettempdir(), "wm_trace.log")
        try:
            for ln in trace_log.read_text(encoding="utf-8", errors="replace").splitlines():
                if "SetWindowAumid" in ln:
                    print(ln)
        except OSError:
            pass
        return 0 if ok else 1
    finally:
        wm.graceful_close_by_name("WindowMerger")
        time.sleep(1.0)
        wm.force_kill_by_name("WindowMerger")


if __name__ == "__main__":
    sys.exit(main())
