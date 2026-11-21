"""喜马拉雅 xm 解密工具的核心库。

对外只需要这一层：

    from xm_decrypt import decrypt_xm_to, scan_xm_files, Settings

模块划分：
    metadata   读 ID3 元信息、扫描与排序（不解密，开销极低）
    wasm       xm_encryptor.wasm 的实例化与内存读写
    decryptor  AES-256-CBC + wasm 的解密算法本体
    exporter   命名、写标签、wav→alac、落盘
    batch      单进程 / 多进程批量调度
    settings   持久化设置
    tui        Textual 终端界面
"""

from .batch import decrypt_task, make_task, run_batch
from .decryptor import find_ext, get_printable_bytes, get_printable_count, xm_decrypt
from .exporter import decrypt_xm_file, decrypt_xm_to, replace_invalid_chars, transcode_wav_to_alac
from .metadata import (
    XMInfo,
    get_xm_info,
    get_xm_track_id,
    parse_track_number,
    read_file,
    read_xm_meta,
    scan_xm_files,
    sort_files_by_track_id,
)
from .settings import Settings, default_process_count, settings_path

# 老实点：功能只在单个样本上验证过，多音轨 / 其它载体格式都还没覆盖，
# 给个 0.x 版本号，别装成正式版。
__version__ = "0.1.0"

__all__ = [
    "XMInfo",
    "Settings",
    "decrypt_task",
    "decrypt_xm_file",
    "decrypt_xm_to",
    "default_process_count",
    "find_ext",
    "get_printable_bytes",
    "get_printable_count",
    "get_xm_info",
    "get_xm_track_id",
    "make_task",
    "parse_track_number",
    "read_file",
    "read_xm_meta",
    "replace_invalid_chars",
    "run_batch",
    "scan_xm_files",
    "settings_path",
    "sort_files_by_track_id",
    "transcode_wav_to_alac",
    "xm_decrypt",
]
