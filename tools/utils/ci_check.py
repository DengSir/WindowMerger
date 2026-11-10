# -*- coding: utf-8 -*-
"""CI 运行诊断：拉取 run 的 jobs/steps 结论 + 失败步骤日志尾部（公开仓库匿名可读，
logs 走 302 到签名 URL，urllib 自动跟随）。"""
import json
import sys
import urllib.request

RUN_URL = ("https://api.github.com/repos/DengSir/WindowMerger/"
           "actions/runs/{run}/jobs?per_page=5")
LOG_URL = "https://api.github.com/repos/DengSir/WindowMerger/actions/runs/{run}/logs"


def fetch(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "wm-ci-check"})
    return urllib.request.urlopen(req, timeout=60)


def main() -> int:
    run = sys.argv[1] if len(sys.argv) > 1 else "42741240496"
    data = json.load(fetch(RUN_URL.format(run=run)))
    print(f"total jobs: {data.get('total_count')}", flush=True)
    failed_jobs = []
    for job in data.get("jobs", []):
        print(f"JOB {job['name']} -> {job['conclusion']}", flush=True)
        for s in job.get("steps", []):
            if s["conclusion"] not in ("success", "skipped", None):
                print(f"  STEP {s['name']} -> {s['conclusion']}", flush=True)
        if job["conclusion"] == "failure":
            failed_jobs.append(job)
    if len(sys.argv) > 2 and sys.argv[2] == "--logs":
        for job in failed_jobs:
            print(f"==== LOG {job['name']} ====", flush=True)
            try:
                resp = fetch(LOG_URL.format(run=run))
                text = resp.read().decode("utf-8", errors="replace")
                lines = text.splitlines()
                # 只留失败步骤附近：含 error/fail/MISMATCH/Traceback 的行及其后 2 行
                hit = [i for i, ln in enumerate(lines)
                       if any(k in ln for k in ("##[error]", "MISMATCH", "Traceback",
                                                "FAIL", "Error:", "error:"))]
                shown = set()
                for i in hit:
                    for j in range(max(0, i - 1), min(len(lines), i + 3)):
                        shown.add(j)
                for j in sorted(shown)[-120:]:
                    print(lines[j][:240], flush=True)
            except Exception as ex:
                print(f"LOG_FETCH_FAILED {type(ex).__name__}: {ex}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
