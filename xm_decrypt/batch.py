"""批量调度：单进程直跑 / spawn 多进程并行。

任务用纯元组表示，便于 multiprocessing spawn 序列化：

    (源文件, 输出目录, 自定义文件名或 None, 是否建专辑子目录,
     曲序号或 None, 曲目总数或 None, wav 处理方式)
"""

from __future__ import annotations

import contextlib
import multiprocessing
import sys

from .exporter import decrypt_xm_to

Task = tuple


@contextlib.contextmanager
def _real_stderr():
    """临时把 sys.stderr 换成带真实 fd 的流。

    Textual 在消息循环里用 redirect_stderr 把 sys.stderr 换成 _PrintCapture，
    而它的 fileno() 返回 -1。multiprocessing 启动 resource_tracker 时会取
    sys.stderr.fileno() 作为要继承的 fd，拿到 -1 就会抛
    "bad value(s) in fds_to_keep"。这里在创建进程池的瞬间还原真实 stderr。
    """
    original = sys.stderr
    try:
        broken = original is None or original.fileno() < 0
    except (AttributeError, OSError, ValueError):
        broken = True

    if not broken or sys.__stderr__ is None:
        yield
        return

    sys.stderr = sys.__stderr__
    try:
        yield
    finally:
        sys.stderr = original


def make_task(from_file, output_dir, name=None, album_subdir=False,
              track_no=None, track_total=None, wav_mode="keep") -> Task:
    return (from_file, output_dir, name, album_subdir, track_no, track_total, wav_mode)


def decrypt_task(task: Task):
    """执行单个任务，异常一律转成结果元组（子进程里不能抛给界面）。"""
    from_file, output_dir, name, album_subdir, track_no, track_total, wav_mode = task
    try:
        final_path = decrypt_xm_to(
            from_file,
            output_dir,
            name=name,
            album_subdir=album_subdir,
            track_no=track_no,
            track_total=track_total,
            wav_mode=wav_mode,
        )
        return (True, from_file, final_path, "")
    except Exception as exc:  # noqa: BLE001 - 需要把任意失败回报给调用方
        return (False, from_file, "", f"{type(exc).__name__}: {exc}")


def run_batch(tasks, process_count=1, on_result=None, should_stop=None):
    """执行任务列表，逐个回调结果。

    on_result(ok, src, out, err) 在每个任务完成后调用；
    should_stop() 返回 True 时中断（并行模式会终止进程池）。
    """
    results = []

    def handle(result):
        results.append(result)
        if on_result is not None:
            on_result(*result)

    if process_count <= 1:
        for task in tasks:
            if should_stop is not None and should_stop():
                break
            handle(decrypt_task(task))
        return results

    ctx = multiprocessing.get_context("spawn")
    with _real_stderr():
        pool = ctx.Pool(processes=process_count)
    try:
        for result in pool.imap_unordered(decrypt_task, tasks):
            handle(result)
            if should_stop is not None and should_stop():
                pool.terminate()
                break
    finally:
        try:
            pool.close()
        except ValueError:
            # 已 terminate 的进程池不能 close。
            pass
        pool.join()
    return results
