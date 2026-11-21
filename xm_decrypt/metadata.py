"""ID3 元信息解析与 .xm 文件发现。

这一层只碰"文件头和文件名"，不做任何解密，因此开销极低，
可以放心在界面预览、排序、扫描时反复调用。
"""

from __future__ import annotations

import io
import pathlib
import sys

from mutagen.easyid3 import ID3


class XMInfo:
    """xm 文件头里携带的元信息（解密所需参数也从这里来）。"""

    def __init__(self):
        self.title = ""
        self.artist = ""
        self.album = ""
        self.tracknumber = 0
        self.size = 0
        self.header_size = 0
        self.ISRC = ""
        self.encodedby = ""
        self.encoding_technology = ""

    def iv(self):
        """AES-CBC 的 IV：优先 TSRC，退回 TENC。"""
        if self.ISRC != "":
            return bytes.fromhex(self.ISRC)
        return bytes.fromhex(self.encodedby)


def parse_track_number(value):
    """按 "N" 或 "N/M" 两种常见写法解析音轨号，返回整数。

    ID3 的 TRCK 帧允许 "N/M" 形式（当前曲目/总曲目），旧实现在
    get_xm_info 中直接 int() 会抛 ValueError，这里统一解析规则。
    """
    text = str(value).strip()
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    return int(text)


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


def _info_from_id3(id3) -> XMInfo:
    info = XMInfo()
    info.title = str(id3["TIT2"])
    info.album = str(id3["TALB"])
    info.artist = str(id3["TPE1"])
    info.tracknumber = parse_track_number(id3["TRCK"])
    info.ISRC = "" if id3.get("TSRC") is None else str(id3["TSRC"])
    info.encodedby = "" if id3.get("TENC") is None else str(id3["TENC"])
    info.size = int(str(id3["TSIZ"]))
    info.header_size = id3.size
    info.encoding_technology = str(id3["TSSE"])
    return info


def get_xm_info(data: bytes) -> XMInfo:
    """从内存字节解析元信息（解密主流程使用）。"""
    return _info_from_id3(ID3(io.BytesIO(data), v2_version=3))


def read_xm_meta(path):
    """只读 ID3 解析元信息（不读整个文件），失败返回 None。

    用 mutagen 直接打开文件是惰性的，只会读标签区；
    对单个几十 MB 的 xm 文件做批量预览时这点很关键。
    """
    try:
        return _info_from_id3(ID3(str(path), v2_version=3))
    except Exception:
        return None


def get_xm_track_id(path) -> int:
    return parse_track_number(ID3(str(path), v2_version=3)["TRCK"])


def sort_files_by_track_id(files):
    def sort_key(path):
        try:
            return (get_xm_track_id(path), path)
        except Exception:
            # 解析不了的文件放到最后，但仍按路径保持稳定顺序。
            return (sys.maxsize, path)

    return sorted(files, key=sort_key)


def scan_xm_files(directory, recursive=False):
    """扫描目录下的 .xm 文件（可选递归），并按音轨号排序。"""
    root = pathlib.Path(directory).expanduser()
    if not root.is_dir():
        return []
    candidates = root.rglob("*") if recursive else root.glob("*")
    files = [str(p) for p in candidates if p.is_file() and p.suffix.lower() == ".xm"]
    return sort_files_by_track_id(files)
