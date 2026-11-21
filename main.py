"""喜马拉雅 XM 解密工具 —— 统一入口。

    python main.py               启动终端界面（TUI）
    python main.py --cli -h      命令行模式（适合脚本 / 无交互终端）
    python main.py --cli -d ~/xm -o ~/out -j 4 -r
"""

from __future__ import annotations

import sys

CLI_FLAGS = ("--cli", "-cli")

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


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    # 延迟导入：TUI 会拉起 textual，而 --cli 与多进程子进程都不需要它。
    if any(flag in args for flag in CLI_FLAGS):
        from xm_decrypt.cli import main as cli_main

        return cli_main([arg for arg in args if arg not in CLI_FLAGS])

    if args and args[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0

    from xm_decrypt.tui import run_tui

    return run_tui()


if __name__ == "__main__":
    sys.exit(main())
