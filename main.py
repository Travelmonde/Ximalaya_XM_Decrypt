"""喜马拉雅 XM 解密工具 —— 统一入口。

    python main.py               启动终端界面（TUI）
    python main.py --cli -h      命令行模式（适合脚本 / 无交互终端）
    python main.py --cli -d ~/xm -o ~/out -j 4 -r
"""

from __future__ import annotations

import importlib.util
import sys

CLI_FLAGS = ("--cli", "-cli")

# .pyz 是「把代码打进一个 zip」的 zipapp，不含第三方依赖：
# wasmtime / pycryptodome 都是带 .so 的原生扩展，无法从 zip 里 import。
# 所以启动前先检查，缺了就给人话提示，而不是抛 ModuleNotFoundError 堆栈。
CORE_DEPS = (("Crypto", "pycryptodome"), ("mutagen", "mutagen"), ("wasmtime", "wasmtime"))
TUI_DEPS = (("textual", "textual"),)

HELP = """喜马拉雅 XM 解密工具

用法：
  python main.py                启动终端界面（TUI）
  python main.py --cli [参数]   命令行模式

命令行常用参数：
  -f/--file    指定 .xm 文件（可重复）
  -d/--dir     指定输入目录
  -r           扫描目录时包含子目录
  -o/--out     输出目录
  -j/--jobs    并行进程数
  --wav        keep / alac
  --name       与 -f 一一对应的自定义名称

完整参数：python main.py --cli -h
"""


def _missing(deps) -> list[tuple[str, str]]:
    """返回缺失的依赖：(import 名, pip 包名)。"""
    return [(mod, dist) for mod, dist in deps if importlib.util.find_spec(mod) is None]


def _report_missing(missing: list[tuple[str, str]]) -> int:
    packages = " ".join(dist for _, dist in missing)
    print("缺少依赖：" + "、".join(dist for _, dist in missing), file=sys.stderr)
    print(f"当前解释器：{sys.executable}", file=sys.stderr)
    print("", file=sys.stderr)
    print("安装后重试：", file=sys.stderr)
    print(f"  {sys.executable} -m pip install {packages}", file=sys.stderr)
    print("", file=sys.stderr)
    print("或用项目虚拟环境运行（推荐）：", file=sys.stderr)
    print("  python -m venv .venv", file=sys.stderr)
    print("  .venv/bin/pip install -r requirements.txt", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    wants_cli = any(flag in args for flag in CLI_FLAGS)

    # 依赖检查放在最前：xm_decrypt 在 import 期就会拉起 Crypto 等原生扩展。
    missing = _missing(CORE_DEPS + (() if wants_cli else TUI_DEPS))
    if missing:
        return _report_missing(missing)

    # 延迟导入：TUI 会拉起 textual，而 --cli 与多进程子进程都不需要它。
    if wants_cli:
        from xm_decrypt.cli import main as cli_main

        return cli_main([arg for arg in args if arg not in CLI_FLAGS])

    if args and args[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0

    from xm_decrypt.tui import run_tui

    return run_tui()


if __name__ == "__main__":
    # 冻结成单文件可执行程序（PyInstaller）时，spawn 子进程会重新执行本程序，
    # 必须由 freeze_support() 先接管，否则多进程解密会无限拉起自己。
    # 非冻结环境下这是空操作。
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
