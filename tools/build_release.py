"""构建发行版用的多平台 .pyz，并按命名规范落到 dist/。

为什么要分平台：
    .pyz 里内嵌的 `wasmtime/linux-x86_64/_libwasmtime.so`、`Crypto/Cipher/_ARC4.abi3.so`
    都是按平台编译的二进制；而且 macOS 与 Linux 的 pycryptodome 扩展**同名**
    （`_ARC4.abi3.so`），装不进同一个包。所以每个平台一份。

命名规范（沿用 wheel 的 tag 风格）：
    xm-decrypt-2.0.0-py3-none-any.pyz                 纯 Python，需目标机装依赖
    xm-decrypt-2.0.0-py3-none-linux_x86_64.pyz        内嵌依赖
    xm-decrypt-2.0.0-py3-none-linux_aarch64.pyz
    xm-decrypt-2.0.0-py3-none-win_amd64.pyz
    xm-decrypt-2.0.0-py3-none-macosx_11_0_arm64.pyz
    xm-decrypt-2.0.0-py3-none-macosx_10_13_x86_64.pyz

本机平台的包用已安装的依赖打包，可以实测；其它平台的包从 PyPI 拉对应 wheel 组装，
**只做了结构校验，没有在真机上运行过**（脚本会明确标出）。

用法：
    python tools/build_release.py                 # 全部目标
    python tools/build_release.py --only linux_x86_64 win_amd64
    python tools/build_release.py --native-only   # 只打本机平台
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pyz import DIST, ROOT, _staging_root, build  # noqa: E402

# 内嵌依赖：运行时必需的顶层模块。交叉打包时逐个下载对应平台的 wheel。
VENDOR_DISTS = (
    "pycryptodome",
    "mutagen",
    "wasmtime",
    "textual",
    "rich",
    "pygments",
    "markdown-it-py",
    "mdit-py-plugins",
    "mdurl",
    "platformdirs",
    "linkify-it-py",
    "uc-micro-py",
    "typing-extensions",
)

# (产物 tag, pip --platform 参数)
TARGETS = (
    ("linux_x86_64", "manylinux2014_x86_64"),
    ("linux_aarch64", "manylinux2014_aarch64"),
    ("win_amd64", "win_amd64"),
    ("macosx_11_0_arm64", "macosx_11_0_arm64"),
    # 注意：wasmtime 只提供 macosx_10_13_x86_64。写成 10_9 会让 pip 匹配不上，
    # 退回那个「标着 any 却只含 win32-x86_64 DLL」的废包（实测踩过）。
    ("macosx_10_13_x86_64", "macosx_10_13_x86_64"),
)

# 各平台必须存在的原生库，用来确认 wheel 真的装进去了
MARKERS = {
    "linux_x86_64": "wasmtime/linux-x86_64/_libwasmtime.so",
    "linux_aarch64": "wasmtime/linux-aarch64/_libwasmtime.so",
    "win_amd64": "wasmtime/win32-x86_64/_wasmtime.dll",
    "macosx_11_0_arm64": "wasmtime/darwin-aarch64/_libwasmtime.dylib",
    "macosx_10_13_x86_64": "wasmtime/darwin-x86_64/_libwasmtime.dylib",
}


def version() -> str:
    text = (ROOT / "xm_decrypt" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("读不到 xm_decrypt.__version__")
    return match.group(1)


def native_tag() -> str:
    machine = platform.machine().lower()
    if sys.platform.startswith("win"):
        return "win_amd64" if machine in ("amd64", "x86_64") else "win_arm64"
    if sys.platform == "darwin":
        return "macosx_11_0_arm64" if machine == "arm64" else "macosx_10_13_x86_64"
    return "linux_x86_64" if machine in ("x86_64", "amd64") else "linux_aarch64"


def download_wheels(platform_tag: str, dest: Path) -> list[Path]:
    """下载目标平台的全部依赖 wheel（只取二进制，不装）。"""
    dest.mkdir(parents=True, exist_ok=True)
    pip = [sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:", "-d", str(dest)]
    common = ["--platform", platform_tag, "--python-version", "3.12"]
    wheels: list[Path] = []
    for dist in VENDOR_DISTS:
        result = subprocess.run([*pip, *common, dist], capture_output=True, text=True)
        if result.returncode != 0:
            # 可选包（如 uc-micro-py）在个别平台没有 wheel，跳过即可
            print(f"    跳过 {dist}：{result.stderr.strip().splitlines()[-1][:100]}")
    wheels = sorted(dest.glob("*.whl"))
    if not wheels:
        raise SystemExit(f"{platform_tag}：一个 wheel 都没下到")
    return wheels


def unpack_wheels(wheels: list[Path], vendor: Path) -> None:
    """把 wheel 解压成 _vendor 布局，丢掉 dist-info 与 .data/ 里的脚本目录。"""
    vendor.mkdir(parents=True, exist_ok=True)
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as bundle:
            for info in bundle.infolist():
                name = info.filename
                if name.endswith("/") or ".dist-info/" in name or ".data/" in name:
                    continue
                out = vendor / name
                out.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)


def check_marker(target: Path, tag: str) -> bool:
    wanted = MARKERS.get(tag)
    if not wanted:
        return True
    with zipfile.ZipFile(target) as bundle:
        return f"_vendor/{wanted}" in set(bundle.namelist())


def main() -> int:
    parser = argparse.ArgumentParser(description="构建多平台发行版 .pyz")
    parser.add_argument("--only", nargs="+", metavar="TAG", help="只打指定平台")
    parser.add_argument("--native-only", action="store_true", help="只打本机平台")
    parser.add_argument("--skip-cross", action="store_true", help="跳过需要下载 wheel 的平台")
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
    built: list[tuple[str, Path, str, bool]] = []  # (tag, path, sha256, tested)

    # 1) 纯 Python 版：与平台无关，目标机需自行安装依赖
    any_target = DIST / f"xm-decrypt-{ver}-py3-none-any.pyz"
    build(target=any_target, with_deps=False)
    built.append(("any", any_target, hashlib.sha256(any_target.read_bytes()).hexdigest(), True))
    print("  ✓ any（纯 Python，需目标机装依赖）")

    # 2) 各平台内嵌依赖版
    for tag, pip_platform in selected:
        out = DIST / f"xm-decrypt-{ver}-py3-none-{tag}.pyz"
        is_native = tag == native
        if not is_native and args.skip_cross:
            print(f"  - {tag} 跳过（要求 --skip-cross）")
            continue

        if is_native:
            print(f"  … {tag}（本机，用已安装依赖）")
            build(target=out, with_deps=True)
            tested = True
        else:
            print(f"  … {tag}（交叉：从 PyPI 拉 {pip_platform} wheel）")
            work = Path(tempfile.mkdtemp(prefix=f"rel_{tag}_", dir=_staging_root()))
            try:
                wheels = download_wheels(pip_platform, work / "wheels")
                vendor = work / "vendor"
                unpack_wheels(wheels, vendor)
                build(target=out, with_deps=True, vendor_dir=vendor)
                tested = False
            finally:
                try:
                    shutil.rmtree(work, ignore_errors=True)
                except Exception:
                    print(f"    提示：暂存目录未删除：{work}")

        if not check_marker(out, tag):
            print(f"  ✗ {tag} 缺少原生库标记 {MARKERS.get(tag)}，产物不可用")
            return 1
        built.append((tag, out, hashlib.sha256(out.read_bytes()).hexdigest(), tested))
        print(f"  ✓ {tag}  {out.stat().st_size / 1024 / 1024:.1f} MB")

    # 3) 校验和清单（release 页面上的附通常配这个）
    sums = DIST / f"SHA256SUMS-{ver}.txt"
    lines = [f"{sha}  {path.name}" for _, path, sha, _ in built]
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print(f"{'平台':22s} {'大小':>10s}  {'sha256':18s} 验证")
    print("-" * 68)
    for tag, path, sha, tested in built:
        size = f"{path.stat().st_size / 1024 / 1024:.1f} MB"
        mark = "本机实测" if tested and tag != "any" else ("结构与源码一致" if tag == "any" else "仅结构校验")
        print(f"{tag:22s} {size:>10s}  {sha[:16]}  {mark}")
    print()
    print(f"校验和清单：{sums.relative_to(ROOT)}")
    print("注意：非本机平台的包没有真机运行过，首次使用请先跑 `--cli -h` 与一次解密确认。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
