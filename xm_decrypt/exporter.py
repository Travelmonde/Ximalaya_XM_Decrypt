"""落盘层：命名规则、写标签、wav 转 ALAC。"""

from __future__ import annotations

import os
import subprocess

import mutagen
from mutagen.id3 import TALB, TIT2, TPE1, TRCK
from mutagen.wave import WAVE

from .decryptor import find_ext, xm_decrypt
from .metadata import read_file

INVALID_CHARS = ('/', '\\', ':', '*', '?', '"', '<', '>', '|')


def replace_invalid_chars(name: str) -> str:
    for char in INVALID_CHARS:
        name = name.replace(char, " ")
    return name


def transcode_wav_to_alac(file_path: str) -> str:
    output_path = os.path.splitext(file_path)[0] + ".m4a"
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            file_path,
            "-map_metadata",
            "0",
            "-c:a",
            "alac",
            output_path,
        ],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("ffmpeg 封装 ALAC 失败，请检查 ffmpeg 是否可用")
    os.remove(file_path)
    return output_path


def decrypt_xm_to(
    from_file,
    output_dir,
    name=None,
    album_subdir=False,
    track_no=None,
    track_total=None,
    wav_mode="keep",
    log=None,
):
    """解密单个 xm 并写到指定目录，返回最终文件路径。

    name 为 None 时沿用默认规则（"NN - 标题"）；给定 name 时使用自定义文件名
    （不要带扩展名，扩展名由解密结果决定）。album_subdir 控制是否再套一层专辑目录。
    log 是可选的日志回调，缺省时不打印，便于 TUI / 并行子进程调用。
    """
    emit = log if log is not None else (lambda _msg: None)
    emit(f"正在解密 {from_file}")
    info, audio_data = xm_decrypt(read_file(from_file))
    ext = find_ext(audio_data[:0xFF])

    if name is None:
        stem = replace_invalid_chars(info.title)
        if track_no is not None and track_total is not None:
            width = len(str(track_total))
            stem = f"{track_no:0{width}d} - {stem}"
    else:
        stem = replace_invalid_chars(str(name)).strip() or "untitled"

    target_dir = output_dir
    if album_subdir:
        target_dir = os.path.join(output_dir, replace_invalid_chars(info.album))
    os.makedirs(target_dir, exist_ok=True)
    output = os.path.join(target_dir, f"{stem}.{ext}")
    with open(output, "wb") as f:
        f.write(audio_data)

    # 标签写入是尽力而为：不支持的容器不应该让解密整体失败。
    try:
        if ext in ("mp3", "flac", "m4a"):
            tags = mutagen.File(output, easy=True)
            if tags is not None:
                tags["title"] = [info.title]
                tags["album"] = [info.album]
                tags["artist"] = [info.artist]
                if track_no is not None and track_total is not None:
                    tags["tracknumber"] = [f"{track_no}/{track_total}"]
                tags.save()
        elif ext == "wav":
            wave_file = WAVE(output)
            if wave_file.tags is None:
                wave_file.add_tags()
            wave_file.tags.add(TIT2(encoding=3, text=[info.title]))
            wave_file.tags.add(TALB(encoding=3, text=[info.album]))
            wave_file.tags.add(TPE1(encoding=3, text=[info.artist]))
            if track_no is not None and track_total is not None:
                wave_file.tags.add(TRCK(encoding=3, text=[f"{track_no}/{track_total}"]))
            wave_file.save()
            if wav_mode == "alac":
                output = transcode_wav_to_alac(output)
    except Exception as exc:  # noqa: BLE001 - 打标签失败不影响音频产出
        emit(f"写入标签失败，已跳过：{exc}")

    emit(f"解密成功，文件保存至 {output}")
    return output


def decrypt_xm_file(from_file, output_path="./output", track_no=None, track_total=None, wav_mode="keep"):
    """默认规则：输出到 <output>/<专辑>/<NN - 标题>.<ext>。"""
    return decrypt_xm_to(
        from_file,
        output_path,
        name=None,
        album_subdir=True,
        track_no=track_no,
        track_total=track_total,
        wav_mode=wav_mode,
        log=print,
    )
