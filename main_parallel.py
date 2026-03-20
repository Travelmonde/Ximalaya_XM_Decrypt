import glob
import multiprocessing
import os
import sys

import main as xm_main


def decrypt_task(args):
    from_file, output_path, track_no, track_total, wav_mode = args
    try:
        xm_main.decrypt_xm_file(from_file, output_path, track_no, track_total, wav_mode)
        return True, from_file, ""
    except Exception as e:
        return False, from_file, str(e)


def get_process_count():
    cpu_count = os.cpu_count() or 1
    print(f"请输入并行进程数（1-{cpu_count}，输入 1 表示单进程）：")
    value = input().strip()
    try:
        process_count = int(value)
    except ValueError:
        return None
    if 1 <= process_count <= cpu_count:
        return process_count
    return None


def run_batch(files_to_decrypt, output_path, wav_mode, process_count):
    track_total = len(files_to_decrypt)
    tasks = [
        (file_path, output_path, i, track_total, wav_mode)
        for i, file_path in enumerate(files_to_decrypt, start=1)
    ]

    if process_count == 1:
        for task in tasks:
            success, from_file, error_message = decrypt_task(task)
            if not success:
                print(f"处理失败：{from_file}")
                print(f"错误信息：{error_message}")
        return

    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(processes=process_count) as pool:
        for success, from_file, error_message in pool.imap_unordered(decrypt_task, tasks):
            if not success:
                print(f"处理失败：{from_file}")
                print(f"错误信息：{error_message}")


if __name__ == "__main__":
    multiprocessing.freeze_support()

    while True:
        print("欢迎使用喜马拉雅音频解密工具（并行版）")
        print("本工具仅供学习交流使用，严禁用于商业用途")
        print("请选择您想要使用的功能：")
        print("1. 解密单个文件")
        print("2. 批量解密文件")
        print("3. 退出")
        choice = input().strip()

        if choice == "1":
            files_to_decrypt = [xm_main.select_file()]
            if files_to_decrypt == [""]:
                print("检测到文件选择窗口被关闭")
                continue
            files_to_decrypt = xm_main.sort_files_by_track_id(files_to_decrypt)
        elif choice == "2":
            dir_to_decrypt = xm_main.select_directory()
            if dir_to_decrypt == "":
                print("检测到目录选择窗口被关闭")
                continue
            files_to_decrypt = glob.glob(os.path.join(dir_to_decrypt, "*.xm"))
            files_to_decrypt = xm_main.sort_files_by_track_id(files_to_decrypt)
        elif choice == "3":
            sys.exit()
        else:
            print("输入错误，请重新输入！")
            continue

        print("请选择是否需要设置输出路径：（不设置默认为本程序目录下的output文件夹）")
        print("1. 设置输出路径")
        print("2. 不设置输出路径")
        output_choice = input().strip()
        if output_choice == "1":
            output_path = xm_main.select_directory()
            if output_path == "":
                print("检测到目录选择窗口被关闭")
                continue
        elif output_choice == "2":
            output_path = "./output"
        else:
            print("输入错误，请重新输入！")
            continue

        print("如果解密结果中包含 WAV，请选择处理方式：")
        print("1. 保留 WAV")
        print("2. 封装为 ALAC (.m4a) 并保留 metadata")
        wav_choice = input().strip()
        if wav_choice == "1":
            wav_mode = "keep"
        elif wav_choice == "2":
            wav_mode = "alac"
        else:
            print("输入错误，请重新输入！")
            continue

        process_count = 1
        if choice == "2":
            process_count = get_process_count()
            if process_count is None:
                print("输入错误，请重新输入！")
                continue

        run_batch(files_to_decrypt, output_path, wav_mode, process_count)
