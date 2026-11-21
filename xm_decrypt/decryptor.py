"""解密算法本体：ID3 → AES-256-CBC → wasm 二次解密 → 拼接尾部数据。"""

from __future__ import annotations

import base64
import struct

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from . import wasm
from .metadata import get_xm_info

XM_KEY = b"ximalayaximalayaximalayaximalaya"


def get_printable_count(data: bytes) -> int:
    for index, byte in enumerate(data):
        if byte < 0x20 or byte > 0x7E:
            return index
    return len(data)


def get_printable_bytes(data: bytes) -> bytes:
    return data[: get_printable_count(data)]


def find_ext(data: bytes) -> str:
    """按文件头魔数判断真实音频格式。"""
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return "m4a"
    if data[:2] in (b"\xff\xf1", b"\xff\xf9"):
        return "aac"
    if data[:3] == b"ID3":
        return "mp3"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:4] == b"RIFF":
        return "wav"
    return "aac"


def xm_decrypt(raw_data):
    """解密一份完整的 xm 字节流，返回 (XMInfo, 音频字节)。"""
    runtime = wasm.get_runtime()
    store = runtime["store"]

    info = get_xm_info(raw_data)
    encrypted_data = raw_data[info.header_size:info.header_size + info.size:]

    # 第一段：AES-256-CBC。
    # 对密文再 pad 看似"错用"，但它负责容忍 TSIZ 非 16 字节对齐的样本：
    # CBC 逐块独立，多出的填充块解密后是不可打印垃圾，由下方截断丢弃；
    # 若去掉 pad，非对齐文件会在 decrypt 阶段直接抛 ValueError。
    cipher = AES.new(XM_KEY, AES.MODE_CBC, info.iv())
    stage1 = cipher.decrypt(pad(encrypted_data, 16))

    # 第二段：wasm 内的 xmDecrypt，密钥是音轨号的十进制字符串。
    stage1 = get_printable_bytes(stage1)
    track_id = str(info.tracknumber).encode()
    stack_pointer = runtime["a"](store, -16)
    data_offset = runtime["c"](store, len(stage1))
    track_offset = runtime["c"](store, len(track_id))
    memory = runtime["i"]

    memory.write(store, stage1, start=data_offset)
    memory.write(store, track_id, start=track_offset)
    runtime["g"](store, stack_pointer, data_offset, len(stage1), track_offset, len(track_id))

    meta = wasm.read_memory(memory, store, stack_pointer, 16)
    result_pointer, result_length, status_code, extra_code = struct.unpack("<4i", meta)
    if status_code != 0 or extra_code != 0:
        raise RuntimeError(f"wasm 解密失败：status={status_code}, extra={extra_code}")
    result_text = wasm.read_memory(memory, store, result_pointer, result_length).decode()

    # 第三段：base64(TSSE + wasm 结果) 再拼回尾部未加密数据。
    body = base64.b64decode(info.encoding_technology + result_text)
    return info, body + raw_data[info.header_size + info.size::]
