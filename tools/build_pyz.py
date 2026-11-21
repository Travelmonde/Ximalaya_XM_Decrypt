"""把项目打包成单文件 .pyz（Python zipapp）。

产物结构（归档内部）：
    __main__.py            ← 由 main.py 改名而来，直接作为入口
    xm_decrypt/...         ← 整个包（含 tui/styles.tcss）
    xm_encryptor.wasm      ← wasm 必须进归档，见 wasm.py:wasm_bytes()

用法：
    python tools/build_pyz.py            # 输出 dist/xm-decrypt.pyz
    python dist/xm-decrypt.pyz --cli -h               # 运行（需已装依赖）
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TARGET = DIST / "xm-decrypt.pyz"
WASM = "xm_encryptor.wasm"

# 只带运行必需的东西；记忆、测试脚本、样本文件都不进归档。
INCLUDE_FILES = ("main.py", WASM)
INCLUDE_DIRS = ("xm_decrypt",)


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {name for name in names if name == "__pycache__" or name.endswith((".pyc", ".pyo"))}


def build(target: Path = TARGET, interpreter: str = "/usr/bin/env python3") -> Path:
    """interpreter 写进产物首行 shebang。

    默认 `/usr/bin/env python3`，分发时不绑定具体机器；
    `tools/install.py` 会传当前解释器的绝对路径，好处是双击就能用、
    且天然带着已装好的依赖（.pyz 不含第三方库，必须由解释器提供）。
    """
    # 暂存目录用系统临时目录：源文件合计约 330KB，普通 tmpfs 足够；
    # 且本项目所在的挂载点删除文件会落到 .Trash-0，建在项目内会留下垃圾。
    staging = Path(tempfile.mkdtemp(prefix="pyz_build_"))
    try:
        # main.py 直接改名为 __main__.py，避免维护两份入口。
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
        shutil.rmtree(staging, ignore_errors=True)
    return target


def main() -> int:
    target = build()
    data = target.read_bytes()
    digest = hashlib.sha256(data).hexdigest()

    print(f"产物：{target.relative_to(ROOT)}")
    print(f"大小：{len(data)} 字节 ({len(data) / 1024:.1f} KB)")
    print(f"sha256：{digest}")

    # 归档自检：入口、包、样式、wasm 都得在。
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
    missing = [name for name in required if name not in names]
    if missing:
        print(f"自检失败，归档缺少：{missing}")
        return 1
    print(f"自检通过：{len(names)} 个文件，入口 / 包 / 样式 / wasm 齐全")
    print()
    print("运行方式：")
    print(f"  python {target.relative_to(ROOT)}                 # TUI")
    print(f"  python {target.relative_to(ROOT)} --cli -h        # 命令行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
