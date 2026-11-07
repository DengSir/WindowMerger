# -*- coding: utf-8 -*-
"""CI 发布辅助（GitHub Actions windows-latest 自带 Python，纯 stdlib 零依赖）。
取代 workflow 里的 pwsh 内联脚本，与仓库 Python 工具链同栈、可本地 dry-run 测试。

子命令：
  resolve   解析版本/tag/是否发版 → 写 GITHUB_OUTPUT（key=value 行）
  stage     把 publish\\WindowMerger.exe 打包成 zip
  release   gh 发版（tag 推送 / dispatch 两路），--dry-run 只打印

环境变量：GITHUB_EVENT_NAME / GITHUB_REF_TYPE / GITHUB_REF_NAME / GITHUB_SHA /
INPUT_VERSION / INPUT_PRERELEASE / GITHUB_OUTPUT / VERSION / TAG / PRERELEASE。
"""
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLISH_DIR = ROOT / "publish"


def _output(key: str, value: str) -> None:
    """写 GITHUB_OUTPUT（Actions 步骤输出）。"""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")
    print(f"{key}={value}")


def _run(cmd: list[str], dry: bool) -> int:
    print("+", " ".join(cmd))
    if dry:
        return 0
    return subprocess.run(cmd, cwd=ROOT).returncode


def resolve() -> int:
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    ref_type = os.environ.get("GITHUB_REF_TYPE", "")
    ref_name = os.environ.get("GITHUB_REF_NAME", "")
    sha = os.environ.get("GITHUB_SHA", "")
    input_version = os.environ.get("INPUT_VERSION", "").strip()
    # 注意写小写：消费方按字符串比较
    prerelease = os.environ.get("INPUT_PRERELEASE", "") == "true"

    if event == "push" and ref_type == "tag":
        version = ref_name.removeprefix("v")           # tag 推送：从 tag 本身发版
        tag = ref_name
        should_release = True
    elif input_version:
        version = input_version.removeprefix("v")      # dispatch 带版本：分支 HEAD 发版
        tag = f"v{version}"
        should_release = True
    else:
        import xml.etree.ElementTree as ET            # dispatch 无版本：只出工件
        root = ET.parse(ROOT / "WindowMerger.csproj").getroot()
        version = (root.find("PropertyGroup/Version").text or "").strip()
        tag = ""
        should_release = False

    if not version:
        raise SystemExit("Cannot resolve version (tag name, input or csproj).")
    # NuGet restore 把 $(Version) 当 PackageVersion 校验：第 4 段非数字（hash 后缀）
    # 直接拒收——-p:Version 传数字前缀，显示版本走 -p:InformationalVersion
    m = re.match(r"^(\d+(?:\.\d+){0,3})", version)
    if not m:
        raise SystemExit(f"Version '{version}' has no numeric prefix.")
    msbuild_version = m.group(1)
    print(f"Version: {version} | MSBuild: {msbuild_version} | Tag: {tag} "
          f"| Release: {should_release} | Prerelease: {prerelease}")
    _output("version", version)
    _output("msbuild_version", msbuild_version)
    _output("tag", tag)
    _output("should_release", "true" if should_release else "false")
    _output("prerelease", "true" if prerelease else "false")
    return 0


def stage() -> int:
    version = os.environ["VERSION"]
    src = PUBLISH_DIR / "WindowMerger.exe"
    if not src.exists():
        raise SystemExit(f"Published exe not found: {src}")
    asset = PUBLISH_DIR / f"WindowMerger-{version}-win-x64.zip"
    with zipfile.ZipFile(asset, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(src, "WindowMerger.exe")  # zip 内固定名，不随版本改名
    print(f"STAGED {asset.name} ({asset.stat().st_size} bytes) <- {src.name} ({src.stat().st_size} bytes)")
    return 0


def release(dry: bool) -> int:
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    ref_type = os.environ.get("GITHUB_REF_TYPE", "")
    sha = os.environ.get("GITHUB_SHA", "")
    version = os.environ["VERSION"]
    tag = os.environ["TAG"]
    prerelease = os.environ.get("PRERELEASE", "") == "true"
    asset = f"publish\\WindowMerger-{version}-win-x64.zip"

    args = ["gh", "release", "create", tag, asset]
    if event == "push" and ref_type == "tag":
        # tag 推送：tag 已存在，校验指向本次构建的提交
        args += ["--verify-tag", "--title", f"WindowMerger {tag}", "--generate-notes"]
    else:
        # dispatch 发版：tag 建在本次构建的确切提交
        args += ["--target", sha, "--title", f"WindowMerger {tag}", "--generate-notes"]
    if prerelease:
        args.append("--prerelease")
    rc = _run(args, dry)
    if rc != 0:
        return rc
    print(f"Release created: {tag}")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "resolve":
        return resolve()
    if cmd == "stage":
        return stage()
    if cmd == "release":
        return release("--dry-run" in sys.argv)
    print(f"usage: release.py resolve|stage|release [--dry-run], got: {sys.argv[1:]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
