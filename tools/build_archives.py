"""构建非 .pyz 的发行包：目录式归档（解压即用）与源码归档。

为什么要它：
    `.pyz` 是 zipapp，首启要把内嵌依赖解压到 `~/.cache`，也容易被杀软 / 企业策略拦住。
    目录式归档把代码与依赖放在同一个目录里，解压即可运行，**不写缓存、不碰家目录**，
    还能直接改代码看效果。

产出（平台表与 build_release.py 一致，默认全打；Windows 目标用 .zip）：
    dist/xm-decrypt-0.1.0-py310-none-linux_x86_64.tar.gz      目录式，含第三方依赖
    dist/xm-decrypt-0.1.0-py310-none-linux_aarch64.tar.gz
    dist/xm-decrypt-0.1.0-py310-none-win_amd64.zip
    dist/xm-decrypt-0.1.0-py310-none-macosx_11_0_arm64.tar.gz
    dist/xm-decrypt-0.1.0-py310-none-macosx_10_13_x86_64.tar.gz
    dist/xm-decrypt-0.1.0-py310-none-any.tar.gz               源码，需自行装依赖

目录式归档结构：
    xm-decrypt-0.1.0/
        xm-decrypt          启动器（POSIX sh；Windows 目标为 xm-decrypt.bat）
        main.py
        xm_encryptor.wasm
        xm_decrypt/...      代码
        _vendor/...         第三方依赖，与 .pyz 内嵌的是同一份
        README.md
        requirements.txt

用法：
    python tools/build_archives.py                 # 全部平台目录式 + 通用源码包
    python tools/build_archives.py --native-only   # 只打本机平台
    python tools/build_archives.py --only win_amd64 macosx_11_0_arm64
    python tools/build_archives.py --skip-dir      # 只出源码包
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pyz import DIST, ROOT, _ignore, _staging_root, update_sums  # noqa: E402
from build_release import (  # noqa: E402
    MARKERS,
    PYTHON_TAG,
    TARGETS,
    download_wheels,
    native_tag,
    unpack_wheels,
    version,
)

WASM = "xm_encryptor.wasm"

# 启动器：先确认解释器版本够用，再把自带的依赖挂到 PYTHONPATH 上。
# `${PYTHONPATH:+:$PYTHONPATH}` 在 `set -u` 下对未定义变量也安全。
LAUNCHER_SH = """#!/bin/sh
# XM 解密工具 —— 免安装启动器
#   ./xm-decrypt              终端界面
#   ./xm-decrypt --cli -h     命令行
# 换解释器：XM_DECRYPT_PYTHON=/usr/bin/python3.12 ./xm-decrypt
set -eu
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
PY=${XM_DECRYPT_PYTHON:-python3}
if ! command -v "$PY" >/dev/null 2>&1; then
    echo "找不到 $PY。请安装 Python 3.10+，或用 XM_DECRYPT_PYTHON 指定解释器。" >&2
    exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    echo "$($PY -V 2>&1) 版本过低，本工具需要 Python 3.10 及以上。" >&2
    exit 1
fi
PYTHONPATH="$HERE/_vendor${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
exec "$PY" "$HERE/main.py" "$@"
"""

LAUNCHER_BAT = """@echo off
rem XM decrypt tool - portable launcher (Windows)
rem   xm-decrypt.bat              TUI
rem   xm-decrypt.bat --cli -h     CLI
rem Override interpreter: set XM_DECRYPT_PYTHON=C:\\Python312\\python.exe
rem ASCII only: cmd.exe runs under the OEM codepage (GBK on zh-CN),
rem so UTF-8 text here would be garbled.
setlocal
set "HERE=%~dp0"
if "%XM_DECRYPT_PYTHON%"=="" (set "PY=python") else (set "PY=%XM_DECRYPT_PYTHON%")
"%PY%" -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ or set XM_DECRYPT_PYTHON.
    exit /b 1
)
"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo Python 3.10 or newer is required.
    exit /b 1
)
set "PYTHONPATH=%HERE%_vendor;%HERE%"
"%PY%" "%HERE%main.py" %*
"""


def _copy_sources(dest: Path) -> None:
    """拷代码本体。__pycache__ / .pyc 一律不进归档。"""
    shutil.copy2(ROOT / "main.py", dest / "main.py")
    shutil.copy2(ROOT / WASM, dest / WASM)
    shutil.copy2(ROOT / "README.md", dest / "README.md")
    shutil.copy2(ROOT / "requirements.txt", dest / "requirements.txt")
    shutil.copytree(ROOT / "xm_decrypt", dest / "xm_decrypt", ignore=_ignore)
    # 源文件挂在 777 的挂载点上，copy2 会把可执行位一起带过来。
    # 归档里只留启动器可执行，其余统一 644 / 755，免得看着像脚本。
    for path in [dest, *dest.rglob("*")]:
        if path.is_dir():
            path.chmod(0o755)
        elif path.is_file():
            path.chmod(0o644)


def _copy_vendor(vendor_dir: Path, dest: Path) -> int:
    """把已解压好的依赖目录整个搬进归档，返回文件数。"""
    total = 0
    for path in vendor_dir.rglob("*"):
        out = dest / path.relative_to(vendor_dir)
        if path.is_dir():
            out.mkdir(parents=True, exist_ok=True)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, out)
            total += 1
    return total


def _stage_onedir(payload: Path, root_name: str, tag: str, vendor_dir: Path | None) -> Path:
    """组装目录式包的顶层目录。返回 `.../<root_name>`。"""
    top = payload / root_name
    top.mkdir(parents=True)
    _copy_sources(top)
    if vendor_dir is not None and vendor_dir.is_dir():
        _copy_vendor(vendor_dir, top / "_vendor")
    elif tag != "any":
        # 本机平台：直接取已安装的依赖
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from build_pyz import _copy_vendor as copy_installed

        copy_installed(top)

    if tag.startswith("win"):
        (top / "xm-decrypt.bat").write_text(LAUNCHER_BAT, encoding="utf-8", newline="\r\n")
    else:
        launcher = top / "xm-decrypt"
        launcher.write_text(LAUNCHER_SH, encoding="utf-8", newline="\n")
        launcher.chmod(0o755)
    return top


def _stage_source(payload: Path, root_name: str) -> Path:
    top = payload / root_name
    top.mkdir(parents=True)
    _copy_sources(top)
    return top


def _add_tree_tar(tar: tarfile.TarFile, root: Path, arc_root: str) -> None:
    """按固定 uid/gid 写入，让产物可复现（同一份源码两次打包哈希一致）。"""
    entries = [root, *sorted(root.rglob("*"))]
    for path in entries:
        arcname = arc_root if path == root else f"{arc_root}/{path.relative_to(root).as_posix()}"
        info = tar.gettarinfo(str(path), arcname=arcname)
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        if path.is_file():
            with open(path, "rb") as handle:
                tar.addfile(info, handle)
        else:
            info.mode = 0o755
            tar.addfile(info)


def _make_targz(top: Path, target: Path) -> None:
    with tarfile.open(target, "w:gz", compresslevel=9) as tar:
        _add_tree_tar(tar, top, top.name)


def _make_zip(top: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in [top, *sorted(top.rglob("*"))]:
            arcname = top.name if path == top else f"{top.name}/{path.relative_to(top).as_posix()}"
            if path.is_dir():
                bundle.writestr(zipfile.ZipInfo(arcname + "/"), b"")
                continue
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            # 启动器需要可执行位；其余文件普通权限
            info.external_attr = (0o755 if os.access(path, os.X_OK) else 0o644) << 16
            bundle.writestr(info, path.read_bytes())


def _size(path: Path) -> str:
    kb = path.stat().st_size / 1024
    return f"{kb:.0f} KB" if kb < 1024 else f"{kb / 1024:.1f} MB"


def _names_in(archive: Path) -> set[str]:
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            return set(bundle.namelist())
    with tarfile.open(archive, "r:gz") as tar:
        return {info.name for info in tar.getmembers()}


def _check_marker(archive: Path, tag: str, root_name: str) -> bool:
    """确认目标平台的原生库真的进了归档。"""
    wanted = MARKERS.get(tag)
    if not wanted:
        return True
    return f"{root_name}/_vendor/{wanted}" in _names_in(archive)


def main() -> int:
    parser = argparse.ArgumentParser(description="构建目录式 / 源码发行包")
    parser.add_argument("--only", nargs="+", metavar="TAG", help="只打指定平台")
    parser.add_argument("--native-only", action="store_true", help="只打本机平台")
    parser.add_argument("--skip-cross", action="store_true", help="跳过需要下载 wheel 的平台")
    parser.add_argument("--skip-dir", action="store_true", help="跳过目录式包（只出源码包）")
    parser.add_argument("--keep-staging", action="store_true", help="保留暂存目录便于排查")
    args = parser.parse_args()

    ver = version()
    native = native_tag()
    print(f"版本 {ver}，本机平台 {native}")

    selected = list(TARGETS)
    if args.only:
        selected = [t for t in TARGETS if t[0] in args.only]
    elif args.native_only:
        selected = [t for t in TARGETS if t[0] == native]

    DIST.mkdir(parents=True, exist_ok=True)
    root_name = f"xm-decrypt-{ver}"
    built: list[tuple[str, Path, str, bool]] = []  # (tag, path, sha256, tested)

    staging = Path(tempfile.mkdtemp(prefix="arc_build_", dir=_staging_root()))
    try:
        # 1) 各平台目录式包：解压即用，含依赖
        if not args.skip_dir:
            for tag, pip_platform in selected:
                is_native = tag == native
                if not is_native and args.skip_cross:
                    print(f"  - {tag} 跳过（要求 --skip-cross）")
                    continue
                payload = staging / f"payload_{tag}"
                payload.mkdir()
                vendor_dir: Path | None = None
                work: Path | None = None
                try:
                    if is_native:
                        print(f"  … {tag}（本机，用已安装依赖）")
                        tested = True
                    else:
                        print(f"  … {tag}（交叉：从 PyPI 拉 {pip_platform} wheel）")
                        work = Path(tempfile.mkdtemp(prefix=f"arc_{tag}_", dir=_staging_root()))
                        wheels = download_wheels(pip_platform, work / "wheels")
                        vendor_dir = work / "vendor"
                        unpack_wheels(wheels, vendor_dir)
                        tested = False

                    top = _stage_onedir(payload, root_name, tag, vendor_dir)
                    suffix = ".zip" if tag.startswith("win") else ".tar.gz"
                    target = DIST / f"xm-decrypt-{ver}-{PYTHON_TAG}-none-{tag}{suffix}"
                    target.unlink(missing_ok=True)
                    if suffix == ".zip":
                        _make_zip(top, target)
                    else:
                        _make_targz(top, target)

                    if not _check_marker(target, tag, root_name):
                        print(f"  ✗ {tag} 缺少原生库标记 {MARKERS.get(tag)}，产物不可用")
                        return 1
                    built.append(
                        (tag, target, hashlib.sha256(target.read_bytes()).hexdigest(), tested)
                    )
                    print(f"  ✓ {target.name}  {_size(target)}")
                finally:
                    shutil.rmtree(payload, ignore_errors=True)
                    if work is not None:
                        shutil.rmtree(work, ignore_errors=True)

        # 2) 源码包：与平台无关，目标机自己装依赖
        print("  … any（源码，需目标机装依赖）")
        payload = staging / "payload_any"
        payload.mkdir()
        top = _stage_source(payload, root_name)
        target = DIST / f"xm-decrypt-{ver}-{PYTHON_TAG}-none-any.tar.gz"
        target.unlink(missing_ok=True)
        _make_targz(top, target)
        built.append(("any", target, hashlib.sha256(target.read_bytes()).hexdigest(), True))
        print(f"  ✓ {target.name}  {_size(target)}")
        shutil.rmtree(payload, ignore_errors=True)
    finally:
        if args.keep_staging:
            print(f"暂存目录保留：{staging}")
        else:
            shutil.rmtree(staging, ignore_errors=True)

    sums = update_sums(ver, {path.name: digest for _, path, digest, _ in built})

    print()
    print(f"{'平台':22s} {'大小':>10s}  {'sha256':18s} 验证")
    print("-" * 68)
    for tag, path, digest, tested in built:
        if tag == "any":
            mark = "源码，无二进制"
        else:
            mark = "本机实测" if tested else "仅结构校验"
        print(f"{tag:22s} {_size(path):>10s}  {digest[:16]}  {mark}")
    print()
    print(f"校验和清单：{sums.relative_to(ROOT)}")
    print("用法（Linux / macOS）：")
    print(f"  tar xzf xm-decrypt-{ver}-{PYTHON_TAG}-none-<平台>.tar.gz && cd {root_name} && ./xm-decrypt --cli -h")
    print("用法（Windows）：解压 .zip 后执行 xm-decrypt.bat")
    print("注意：非本机平台的包没有真机运行过，首次使用请先跑 `--cli -h` 与一次解密确认。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
