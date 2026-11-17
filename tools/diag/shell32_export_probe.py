# -*- coding: utf-8 -*-
"""shell32 导出探针（临时诊断）：查 SHGetPropertyStoreForWindow 等导出存在性。
GetModuleHandleW/GetProcAddress 必须显式 restype=c_void_p——64 位句柄默认 c_int 截断。
"""
import ctypes

k = ctypes.windll.kernel32
k.LoadLibraryW.restype = ctypes.c_void_p
k.GetModuleHandleW.restype = ctypes.c_void_p
k.GetProcAddress.restype = ctypes.c_void_p
k.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

import struct


def exports(path):
    """读 PE 导出表名字清单（无 dumpbin 时用）。"""
    h = k.LoadLibraryW(path)
    if not h:
        return []
    k.GetModuleHandleW.restype = ctypes.c_void_p
    base = k.GetModuleHandleW(path)
    buf = ctypes.create_string_buffer(4096)
    ctypes.memmove(buf, base, 4096)
    e_lfanew = struct.unpack_from("<I", buf, 0x3C)[0]
    pe = ctypes.create_string_buffer(4096)
    ctypes.memmove(pe, base + e_lfanew, 4096)
    opt_off = 24
    magic = struct.unpack_from("<H", pe, opt_off)[0]
    dd_off = opt_off + (112 if magic == 0x20B else 96)  # PE32+/PE32 数据目录偏移
    exp_rva, exp_size = struct.unpack_from("<II", pe, dd_off)  # 第 0 项 = 导出表
    if not exp_rva:
        return []
    names_rva = struct.unpack_from("<I", ctypes.create_string_buffer(
        ctypes.string_at(base + exp_rva, 40), 40), 12)[0]
    n_names = struct.unpack_from("<I", ctypes.create_string_buffer(
        ctypes.string_at(base + exp_rva, 40), 40), 8)[0]
    names_ptr = base + names_rva
    out = []
    for i in range(n_names):
        rva = struct.unpack_from("<I", ctypes.string_at(names_ptr + i * 4, 4), 0)[0]
        s = ctypes.string_at(base + rva)
        out.append(s.decode())
    return out


for dll in (r"C:\Windows\System32\propsys.dll",):
    names = exports(dll)
    hits = [n for n in names if "PropertyStore" in n and "Window" in n]
    print(dll, len(names), "exports; window+propertystore:", hits)
    hits2 = [n for n in names if "AppUserModel" in n or "Window" in n]
    print("  appusermodel/window:", hits2[:30])

# API-set 合同直调（绕坏转发）：LoadLibrary 接受 API set 合同名
for apiset in ("ext-ms-win-shell-shell32-l1-3-0.dll", "api-ms-win-shell-shell32-l1-2-0.dll"):
    h2 = k.LoadLibraryW(apiset)
    if not h2:
        print(apiset, "LOAD_FAIL")
        continue
    p2 = k.GetProcAddress(h2, b"SHGetPropertyStoreForWindow")
    print(apiset, "proc", hex(p2) if p2 else "NOT_FOUND")

