# -*- coding: utf-8 -*-
"""列出四个 GitHub Actions 的浮动 major tag（决定 workflow 升级目标）。"""
import re
import subprocess

REPOS = ["actions/checkout", "actions/upload-artifact",
         "astral-sh/setup-uv", "actions/setup-dotnet"]
for repo in REPOS:
    out = subprocess.run(["git", "ls-remote", "--tags", "--refs",
                          f"https://github.com/{repo}.git"],
                         capture_output=True, text=True, check=True).stdout
    tags = sorted({m for m in re.findall(r"refs/tags/(v\d+)\b", out)},
                  key=lambda s: int(s[1:]))
    print(f"{repo}: majors={tags[-4:]}")
