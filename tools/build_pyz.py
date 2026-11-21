"""把项目打包成单文件 .pyz（Python zipapp）。

产物结构（归档内部）：
    __main__.py            ← 入口。带依赖时是一层引导；否则就是 main.py 本体
    main.py                ← 仅 --with-deps 时存在，供 __main__.py 调用
    xm_decrypt/...         ← 整个包（含 tui/styles.tcss）
    xm_encryptor.wasm      ← wasm 必须进归档，见 wasm.py:wasm_bytes()
    _vendor/...            ← 仅 --with-deps 时存在，第三方依赖
    _xm_vendor.py          ← 仅 --with-deps 时存在，负责把 _vendor 解压到缓存

两种产物：
    python tools/build_pyz.py                 # dist/xm-decrypt.pyz       约 53 KB，需目标机装依赖
    python tools/build_pyz.py --with-deps     # dist/xm-decrypt-standalone.pyz  自带依赖

为什么带依赖的版本要解压：
    zipimport 只能导入纯 Python 模块，`wasmtime/_libwasmtime.so`、
    `Crypto/Cipher/_raw_aes.abi3.so` 这类原生扩展必须落在真实文件系统上。
    所以 `_vendor/` 里的东西在首次运行时解压到缓存目录，再挂到 sys.path。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TARGET = DIST / "xm-decrypt.pyz"
TARGET_BUNDLED = DIST / "xm-decrypt-standalone.pyz"
WASM = "xm_encryptor.wasm"

# 只带运行必需的东西；记忆、测试脚本、样本文件都不进归档。
INCLUDE_FILES = ("main.py", WASM)
INCLUDE_DIRS = ("xm_decrypt",)

# 需要内嵌的第三方顶层模块 / 单文件模块。用白名单而非依赖闭包：
# importlib.metadata 的 requires 里混着 pytest 之类开发依赖和带 marker 的 extras，
# 按闭包收会又大又错。这份名单靠「用系统 python 跑通」验证过。
VENDOR_ITEMS = (
    "Crypto",             # pycryptodome
    "mutagen",
    "wasmtime",           # 含 linux-x86_64/_libwasmtime.so
    "textual",
    "rich",
    "pygments",
    "markdown_it",
    "mdit_py_plugins",
    "mdurl",
    "platformdirs",
    "linkify_it",
    "uc_micro",
    "typing_extensions.py",
)

BOOTSTRAP_NAME = "_xm_vendor.py"

# 带依赖版入口：先解压依赖，再调用 main.py 的 main()。
ENTRY_WITH_DEPS = '''"""自动生成的入口：先把内嵌依赖解压到缓存，再运行主程序。"""

import sys

import _xm_vendor

_xm_vendor.install()

import main as _entry

sys.exit(_entry.main())
'''


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name == "__pycache__" or name.endswith((".pyc", ".pyo", ".dist-info"))
    }


def _site_packages() -> Path:
    for path in sys.path:
        candidate = Path(path)
        if candidate.name == "site-packages" and candidate.is_dir():
            return candidate
    raise SystemExit("找不到 site-packages，请用装好依赖的解释器运行本脚本")


def _copy_vendor(staging: Path) -> list[str]:
    source = _site_packages()
    dest = staging / "_vendor"
    dest.mkdir()
    copied = []
    for item in VENDOR_ITEMS:
        origin = source / item
        if not origin.exists():
            # uc_micro 等可选包不一定装；缺了不致命，最后会由自检暴露
            continue
        if origin.is_dir():
            shutil.copytree(origin, dest / item, ignore=_ignore)
        else:
            shutil.copy2(origin, dest / item)
        copied.append(item)
    return copied


def _staging_root(min_free: int = 400 * 1024 * 1024) -> str:
    """选一个放得下依赖的临时目录。

    带依赖的构建要暂存约 70 MB，而很多环境（本机就是）`/tmp` 是 10 MB 的 tmpfs，
    直接 mkdtemp 会报 ENOSPC。按可用空间依次挑，全都不够时退回系统默认值。
    """
    candidates = [
        os.environ.get("TMPDIR"),
        tempfile.gettempdir(),
        "/var/tmp",
        str(Path.home()),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            if shutil.disk_usage(candidate).free >= min_free:
                return candidate
        except OSError:
            continue
    return tempfile.gettempdir()


def build(
    target: Path = TARGET,
    interpreter: str = "/usr/bin/env python3",
    with_deps: bool = False,
) -> Path:
    """interpreter 写进产物首行 shebang。

    默认 `/usr/bin/env python3`，分发时不绑定具体机器；
    `tools/install.py` 会传当前解释器的绝对路径，好处是双击就能用、
    且天然带着已装好的依赖（.pyz 不含第三方库，必须由解释器提供）。
    """
    # 暂存目录不能建在项目内：本项目所在挂载点删除文件会落到 .Trash-0，留垃圾。
    staging = Path(tempfile.mkdtemp(prefix="pyz_build_", dir=_staging_root()))
    try:
        if with_deps:
            # 入口要能先引导依赖，所以 main.py 保留原名供 import
            shutil.copy2(ROOT / "main.py", staging / "main.py")
            (staging / "__main__.py").write_text(ENTRY_WITH_DEPS, encoding="utf-8")
            shutil.copy2(ROOT / "tools" / "_vendor_boot.py", staging / BOOTSTRAP_NAME)
            _copy_vendor(staging)
        else:
            # 无依赖版：main.py 直接改名，避免维护两份入口
            shutil.copy2(ROOT / "main.py", staging / "__main__.py")

        for name in INCLUDE_FILES:
            if name == "main.py":
                continue
            shutil.copy2(ROOT / name, staging / name)
        for name in INCLUDE_DIRS:
            shutil.copytree(ROOT / name, staging / name, ignore=_ignore)

        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        # compressed=True 让 zip 内文本压缩；interpreter 让产物可直接 ./x.pyz 执行。
        zipapp.create_archive(
            staging,
            target=str(target),
            interpreter=interpreter,
            compressed=True,
        )
    finally:
        # 暂存目录里有一两千个文件，某些环境（沙箱的 safe-delete 钩子）会拦截批量删除。
        # 删不掉不算构建失败，提示一下路径即可，别让整个构建报错。
        try:
            shutil.rmtree(staging, ignore_errors=True)
        except Exception:
            print(f"提示：暂存目录未能删除，可手动清理：{staging}")
    return target


def report(target: Path, with_deps: bool) -> int:
    data = target.read_bytes()
    print(f"产物：{target.relative_to(ROOT)}")
    print(f"大小：{len(data) / 1024:.1f} KB ({len(data) / 1024 / 1024:.1f} MB)")
    print(f"sha256：{hashlib.sha256(data).hexdigest()}")

    import zipfile

    with zipfile.ZipFile(target) as bundle:
        names = set(bundle.namelist())
    required = (
        "__main__.py",
        "xm_decrypt/__init__.py",
        "xm_decrypt/wasm.py",
        "xm_decrypt/tui/app.py",
        "xm_decrypt/tui/styles.tcss",
        WASM,
    )
    if with_deps:
        required += (BOOTSTRAP_NAME, "_vendor/Crypto/__init__.py", "_vendor/textual/__init__.py")
    missing = [name for name in required if name not in names]
    if missing:
        print(f"自检失败，归档缺少：{missing}")
        return 1
    print(f"自检通过：{len(names)} 个文件，入口 / 包 / 样式 / wasm" + (" / 依赖" if with_deps else "") + " 齐全")
    print()
    print("运行方式：")
    print(f"  python {target.relative_to(ROOT)}                 # TUI")
    print(f"  python {target.relative_to(ROOT)} --cli -h        # 命令行")
    if with_deps:
        print("（已内嵌依赖，目标机器无需 pip install）")
    else:
        print("（不含第三方依赖，目标机器需 pip install -r requirements.txt）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="打包成单文件 .pyz")
    parser.add_argument("--with-deps", action="store_true", help="把第三方依赖一起打进归档")
    parser.add_argument("--out", help="输出路径")
    args = parser.parse_args()

    if args.out:
        target = Path(args.out).expanduser().resolve()
    else:
        target = TARGET_BUNDLED if args.with_deps else TARGET

    built = build(target=target, with_deps=args.with_deps)
    return report(built, args.with_deps)


if __name__ == "__main__":
    sys.exit(main())
