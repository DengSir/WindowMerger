# -*- coding: utf-8 -*-
"""读已下载 zip 里指定测试的完整日志段（诊断 CI 单项失败）。"""
import io
import os
import sys
import tempfile
import zipfile

run = sys.argv[1]
step_needle = sys.argv[2] if len(sys.argv) > 2 else "Run full regression suite"
test_needle = sys.argv[3] if len(sys.argv) > 3 else "pane_drag_rules"
zpath = os.path.join(tempfile.gettempdir(), f"wm_ci_logs_{run}.zip")
with zipfile.ZipFile(zpath) as z:
    target = next(n for n in z.namelist()
                  if n.endswith(".txt") and step_needle in n)
    text = z.read(target).decode("utf-8", errors="replace")
lines = text.splitlines()
start = next(i for i, ln in enumerate(lines) if test_needle in ln and "=====" in ln)
end = next((i for i in range(start + 1, len(lines)) if "=====" in lines[i]), len(lines))
for ln in lines[start - 1:end]:
    print(ln[:300])
