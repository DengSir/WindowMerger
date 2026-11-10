# -*- coding: utf-8 -*-
"""精确核实各 action 的 tag：浮动 major tag（refs/tags/v7 整名存在）与最新完整版本
是两回事——setup-uv 自 v8.0.0 起只发完整版本 tag（immutable），vN 前缀匹配会误报
（v10.3.3 提取出 v10，workflow 引用 @v10 直接找不到）。"""
import re
import subprocess

REPOS = ["actions/checkout", "actions/upload-artifact",
         "astral-sh/setup-uv", "actions/setup-dotnet"]
for repo in REPOS:
    out = subprocess.run(["git", "ls-remote", "--tags", "--refs",
                          f"https://github.com/{repo}.git"],
                         capture_output=True, text=True, check=True).stdout
    tags = re.findall(r"refs/tags/(v[\d.]+)\s*$", out, re.M)
    floating = sorted({t for t in tags if re.fullmatch(r"v\d+", t)},
                      key=lambda s: int(s[1:]))
    versions = sorted({t for t in tags if "." in t},
                      key=lambda s: [int(x) for x in s[1:].split(".")])
    print(f"{repo}:")
    print(f"  floating majors = {floating[-3:]}")
    print(f"  latest full tag = {versions[-1] if versions else '(none)'}")
