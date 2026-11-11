# -*- coding: utf-8 -*-
"""CI 运行状态速查：最近 N 次 run 的 sha/状态/结论/链接。"""
import json
import sys
import urllib.request

n = sys.argv[1] if len(sys.argv) > 1 else "3"
req = urllib.request.Request(
    f"https://api.github.com/repos/DengSir/WindowMerger/actions/runs?per_page={n}",
    headers={"User-Agent": "wm-ci-check"})
for r in json.load(urllib.request.urlopen(req, timeout=30)).get("workflow_runs", []):
    print(r["head_sha"][:7], r["status"], r["conclusion"], r["html_url"])
