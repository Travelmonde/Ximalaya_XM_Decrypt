"""把工具安装成一条可直接调用的命令 `xm-decrypt`。

做的事：用**当前解释器**（必须已装好依赖）打包 .pyz，装到 `~/.local/bin/xm-decrypt`。
之所以不写 `#!/usr/bin/env python3`，是因为 .pyz 只含本项目代码，第三方库得靠解释器
提供；把解释器绝对路径写进 shebang，才能保证 `xm-decrypt` 一敲就跑，不会因为
系统 python 缺 pycryptodome 而报 `No module named 'Crypto'`。

用法：
    python tools/install.py              # 安装 / 覆盖升级
    python tools/install.py --uninstall  # 卸载
    python tools/install.py --dir ~/bin  # 装到别处
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pyz import ROOT, build  # noqa: E402

DEFAULT_DIR = Path.home() / ".local" / "bin"
COMMAND = "xm-decrypt"


def check_interpreter() -> None:
    """安装用的解释器必须能 import 全部依赖，否则装完也跑不起来。"""
    missing = []
    for module, dist in (("Crypto", "pycryptodome"), ("mutagen", "mutagen"), ("wasmtime", "wasmtime"), ("textual", "textual")):
        try:
            __import__(module)
        except ImportError:
            missing.append(dist)
    if missing:
        raise SystemExit(
            f"当前解释器缺少依赖：{'、'.join(missing)}\n"
            f"  {sys.executable} -m pip install {' '.join(missing)}"
        )


def on_path(directory: Path) -> bool:
    return str(directory) in os.environ.get("PATH", "").split(os.pathsep)


def install(directory: Path) -> int:
    check_interpreter()
    shebang = f"#!{sys.executable}"
    if len(shebang) > 127:
        # 内核 shebang 上限 127 字节，超了会静默失败
        raise SystemExit(f"解释器路径过长（{len(shebang)} > 127），请把虚拟环境放到更短的路径下")

    directory.mkdir(parents=True, exist_ok=True)
    target = directory / COMMAND

    # 直接产出带绝对 shebang 的 pyz，装的就是它本身，不是包装脚本
    build(target=target, interpreter=sys.executable)
    target.chmod(0o755)

    data = target.read_bytes()
    print(f"已安装：{target}")
    print(f"大小：{len(data) / 1024:.1f} KB")
    print(f"sha256：{hashlib.sha256(data).hexdigest()[:16]}")
    print(f"解释器：{sys.executable}")

    # 自检：直接执行装好的文件，走真实 shebang 路径
    probe = subprocess.run([str(target), "--cli", "-h"], capture_output=True, text=True)
    if probe.returncode != 0 or "usage:" not in probe.stdout:
        print("\n自检失败：")
        print((probe.stdout + probe.stderr)[-800:])
        return 1
    print("自检通过（--cli -h 正常）")

    if not on_path(directory):
        print(f"\n注意：{directory} 不在 PATH 中，需要加一行：")
        print(f'  export PATH="{directory}:$PATH"')
    else:
        print(f"\n现在可以直接用：{COMMAND}          # 终端界面")
        print(f"                  {COMMAND} --cli -h   # 命令行")
    return 0


def uninstall(directory: Path) -> int:
    target = directory / COMMAND
    if not target.exists():
        print(f"{target} 不存在，无需卸载")
        return 0
    target.unlink()
    print(f"已删除：{target}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="安装 xm-decrypt 命令")
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="安装目录（默认 ~/.local/bin）")
    parser.add_argument("--uninstall", action="store_true", help="卸载")
    args = parser.parse_args()

    directory = Path(args.dir).expanduser()
    if args.uninstall:
        return uninstall(directory)
    print(f"源目录：{ROOT}")
    return install(directory)


if __name__ == "__main__":
    sys.exit(main())
