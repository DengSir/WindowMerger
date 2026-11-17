# -*- coding: utf-8 -*-
"""提取 CI 日志包中指定时间窗的子测试输出（run_all 子测试走临时文件重定向，
主日志只剩 RESULT 行——按时间戳窗口切段落用）。用法:
  uv run tools/diag/ci_fail_window.py <日志zip路径> <HH:MM:SS> <HH:MM:SS> [标签]
"""
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

zpath, t0, t1 = sys.argv[1], sys.argv[2], sys.argv[3]
label = sys.argv[4] if len(sys.argv) > 4 else f"{t0}-{t1}"
z = zipfile.ZipFile(zpath)
name = next(n for n in z.namelist() if n.endswith(".txt") and "test" in n)
data = z.read(name).decode("utf-8", errors="replace").splitlines()
print(f"====== {label} ({t0}..{t1}) ======")
n = 0
for line in data:
    ts = line[11:19] if len(line) > 19 else ""
    if t0 <= ts <= t1:
        body = line.split(" | ", 1)[1] if " | " in line else line
        print(body[:240])
        n += 1
print(f"------ {n} lines ------")
