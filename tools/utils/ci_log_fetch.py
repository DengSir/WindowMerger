# -*- coding: utf-8 -*-
"""CI 日志拉取：urllib 带 Authorization 握手被本机网络掐断（SSL EOF 实测），
改走 curl.exe；凭据写临时 curl 配置文件（不落命令行/输出），302 签名 URL 由
curl -L 跟随且跨主机自动摘除 Authorization。"""
import io
import os
import subprocess
import sys
import tempfile
import zipfile

API = "https://api.github.com/repos/DengSir/WindowMerger/actions/runs/{run}/logs"


def gcm_token() -> str:
    p = subprocess.run(["git", "credential", "fill"],
                       input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, check=True)
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):]
    raise OSError("GCM 未提供 token")


def main() -> int:
    run = sys.argv[1]
    token = gcm_token()
    cfg = os.path.join(tempfile.gettempdir(), "wm_ci_curl.cfg")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(f'header = "Authorization: token {token}"\n'
                'header = "User-Agent: wm-ci-check"\n')
    try:
        p = subprocess.run(["curl.exe", "-sSL", "--max-time", "180",
                            "-K", cfg, "-o", os.path.join(tempfile.gettempdir(),
                                                          f"wm_ci_logs_{run}.zip"),
                            "-w", "%{http_code}", API.format(run=run)],
                           capture_output=True, text=True)
        code = p.stdout.strip()
        if code != "200":
            print(f"HTTP {code} stderr={p.stderr[:200]}")
            return 1
    finally:
        os.unlink(cfg)
    zpath = os.path.join(tempfile.gettempdir(), f"wm_ci_logs_{run}.zip")
    with zipfile.ZipFile(zpath) as z:
        target = None
        for name in z.namelist():
            if name.endswith(".txt") and "Run full regression suite" in name:
                target = name
                break
        if target is None:
            print(f"NO_STEP_LOG names={z.namelist()[:30]}")
            return 1
        text = z.read(target).decode("utf-8", errors="replace")
        print(f"==== {target} ====")
        lines = text.splitlines()
        keys = ("FAIL", "TIMEOUT", "SUMMARY", "::error", "UNKNOWN")
        hit = [i for i, ln in enumerate(lines) if any(k in ln for k in keys)]
        shown = set()
        for i in hit:
            for j in range(max(0, i - 3), min(len(lines), i + 6)):
                shown.add(j)
        for j in sorted(shown):
            print(lines[j][:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
