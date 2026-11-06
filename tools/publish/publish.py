# -*- coding: utf-8 -*-
"""本地打包发布：框架依赖单文件 exe（win-x64），产出 publish\\WindowMerger-<版本>-win-x64.exe。
先 WM_CLOSE 优雅关运行实例（同正常退出路径：存配置 + 子窗口回原位），再复用
Properties\\PublishProfiles\\FolderProfile.pubxml（打包设置唯一来源）发布。
原 Publish.ps1。
用法: uv run tools/\publish\\publish.py [--version 1.2.3] [--configuration Release]
"""
import argparse
import hashlib
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

ROOT = Path(__file__).resolve().parents[2]
CSPROJ = ROOT / "WindowMerger.csproj"


def read_version_from_csproj() -> str:
    text = CSPROJ.read_text(encoding="utf-8")
    m = re.search(r"<Version>(.*?)</Version>", text)
    if not m or not m.group(1):
        raise RuntimeError("Cannot read <Version> from WindowMerger.csproj; pass --version explicitly.")
    return m.group(1)


def close_running_instances() -> None:
    """WM_CLOSE 优雅关（exe 文件锁会打断构建）；15s 不退出则报错拒绝强杀。"""
    pids = []
    for h in wm.top_windows_of_pids(wm.pids_by_name("WindowMerger")):
        pid = wm.pid_of(h)
        pids.append(pid)
        print(f"Closing running instance (pid {pid}) via WM_CLOSE ...")
        wm.post_close(h)
    if not pids:
        return
    deadline = time.monotonic() + 15
    alive = pids
    while time.monotonic() < deadline:
        alive = [p for p in pids if p in wm.pids_by_name("WindowMerger")]
        if not alive:
            return
        time.sleep(0.3)
    raise RuntimeError(f"Instance pid {alive[0]} did not exit within 15s; "
                       "refusing to force kill. Close it manually and retry.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="")
    ap.add_argument("--configuration", default="Release")
    a = ap.parse_args()

    # --- 版本：参数优先，否则读 csproj <Version> ---
    # 带 hash 后缀的显示版本（如 0.0.1.a242d884）不是合法 NuGet 版本：restore 把
    # $(Version) 当 PackageVersion 校验、第 4 段非数字即拒收（实测炸在 restore 阶段，
    # MSB4181 无具体日志）。-p:Version 传数字前缀、显示版本走 -p:InformationalVersion
    # （进 exe 的 ProductVersion）——与 CI 同款拆法
    version = (a.version or read_version_from_csproj()).removeprefix("v")
    m = re.match(r"^(\d+(?:\.\d+){0,3})", version)
    if not m:
        raise RuntimeError(f"Version '{version}' has no numeric prefix; cannot derive -p:Version.")
    msbuild_version = m.group(1)
    print(f"Version: {version} (msbuild: {msbuild_version})")

    # --- 优雅关运行实例 ---
    close_running_instances()

    # --- 经仓库内 VS 发布配置发布（FolderProfile = 单一来源：win-x64/框架依赖/单文件） ---
    pub_profile = ROOT / "Properties" / "PublishProfiles" / "FolderProfile.pubxml"
    if not pub_profile.exists():
        raise RuntimeError(f"Publish profile not found: {pub_profile}")
    r = subprocess.run(
        ["dotnet", "publish", str(CSPROJ), "-c", a.configuration,
         "-p:PublishProfile=FolderProfile", "-p:TreatWarningsAsErrors=true",
         f"-p:Version={msbuild_version}", f"-p:InformationalVersion={version}"],
        cwd=ROOT)
    if r.returncode != 0:
        raise RuntimeError(f"dotnet publish failed with exit code {r.returncode}.")

    # profile 的相对 PublishDir（publish\）按项目目录解析
    pub_exe = ROOT / "publish" / "WindowMerger.exe"
    if not pub_exe.exists():
        raise RuntimeError(f"Published exe not found: {pub_exe}")

    artifact = ROOT / "publish" / f"WindowMerger-{version}-win-x64.exe"
    # 先 copy 成 .new 再改名替换：从产物上跑着的实例持影像锁，拒绝覆写但允许改名（实测）
    artifact.with_suffix(".exe.new").write_bytes(pub_exe.read_bytes())
    artifact.with_suffix(".exe.new").replace(artifact)

    size_mb = round(artifact.stat().st_size / 1024 / 1024, 2)
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest().upper()
    print(f"ARTIFACT: {artifact} ({size_mb} MB)")
    print(f"SHA256  : {sha}")
    print("NOTE    : target machines need the .NET 10 Desktop Runtime (x64).")
    print("PUBLISH_DONE")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
