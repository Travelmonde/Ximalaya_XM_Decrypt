"""命令行模式（无 TUI 环境 / 脚本化批处理时的入口）。

    python main.py --cli                    # 用设置里的默认输入目录
    python main.py --cli -d ~/xm -o ~/out -j 4 -r
    python main.py --cli -f a.xm -f b.xm --name 第一集 --name 第二集
"""

from __future__ import annotations

import argparse
import os
import sys

from .batch import make_task, run_batch
from .metadata import scan_xm_files, sort_files_by_track_id
from .settings import Settings, settings_path


def build_parser() -> argparse.ArgumentParser:
    # 用实际的启动方式作为程序名：源码运行显示 main.py，打包后显示 xm-decrypt.pyz。
    invoked = os.path.basename(sys.argv[0]) or "main.py"
    parser = argparse.ArgumentParser(
        prog=f"{invoked} --cli",
        description="喜马拉雅 xm 解密工具（命令行模式）",
    )
    parser.add_argument("-f", "--file", dest="files", action="append", default=[],
                        help="要解密的 .xm 文件，可重复指定")
    parser.add_argument("-d", "--dir", dest="directory", help="要扫描的目录")
    parser.add_argument("-r", "--recursive", action="store_true", help="扫描目录时包含子目录")
    parser.add_argument("-o", "--out", dest="output_dir", help="输出目录（默认取设置）")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="并行进程数（默认 1）")
    parser.add_argument("--wav", choices=("keep", "alac"), default=None, help="wav 处理方式")
    parser.add_argument("--name", nargs="+", default=None,
                        help="与 --file 一一对应的自定义名称（不含扩展名）")
    parser.add_argument("--settings", action="store_true", help="打印设置文件位置与当前值后退出")
    return parser


def _collect_files(args, settings: Settings) -> list[str]:
    if args.files:
        return sort_files_by_track_id([os.path.abspath(p) for p in args.files])
    directory = args.directory or settings.resolved_input_dir()
    recursive = args.recursive or settings.include_subdirs
    return scan_xm_files(directory, recursive=recursive)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.load()

    if args.settings:
        print(f"设置文件：{settings_path()}")
        print(f"  默认输入目录：{settings.resolved_input_dir()}")
        print(f"  默认输出目录：{settings.resolved_output_dir()}")
        print(f"  含子目录：{settings.include_subdirs}")
        print(f"  WAV 处理：{settings.wav_mode}")
        print(f"  并行进程：{settings.effective_processes()}")
        return 0

    files = _collect_files(args, settings)
    if not files:
        print("没有找到 .xm 文件。可用 -f 指定文件，或 -d 指定目录。")
        return 1

    output_dir = args.output_dir or settings.resolved_output_dir()
    wav_mode = args.wav or settings.wav_mode
    jobs = max(1, args.jobs)

    names = args.name
    if names is not None and len(names) != len(files):
        print(f"--name 数量（{len(names)}）与文件数（{len(files)}）不一致。")
        return 2

    total = len(files)
    tag_total = total if total > 1 else None
    tasks = []
    for index, path in enumerate(files):
        tasks.append(
            make_task(
                path,
                output_dir,
                name=names[index] if names else None,
                album_subdir=names is None,
                track_no=index + 1 if tag_total else None,
                track_total=tag_total,
                wav_mode=wav_mode,
            )
        )

    print(f"共 {total} 个文件，并行 {jobs}，输出到 {output_dir}")
    counter = {"done": 0, "ok": 0}

    def on_result(ok, src, out, err):
        counter["done"] += 1
        if ok:
            counter["ok"] += 1
            print(f"[{counter['done']}/{total}] ✓ {os.path.basename(src)} -> {os.path.basename(out)}")
        else:
            print(f"[{counter['done']}/{total}] ✗ {os.path.basename(src)}: {err}")

    run_batch(tasks, jobs, on_result=on_result)

    failed = total - counter["ok"]
    print(f"完成：成功 {counter['ok']}，失败 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
