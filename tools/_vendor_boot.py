"""把归档内 `_vendor/` 的第三方依赖解压到缓存目录，并挂到 sys.path。

为什么需要它：`.pyz` 是 zip 归档，`zipimport` **只能导入纯 Python 模块**，
无法加载 `wasmtime/_libwasmtime.so`、`Crypto/Cipher/_raw_aes.abi3.so` 这类原生扩展。
所以内嵌依赖不能直接 import，必须先解压到真实文件系统。

缓存策略：用归档自身的 sha256 前 16 位作目录名，归档变了自然换目录，
旧目录可随时删除，不会读到半新半旧的库。解压用「临时目录 + 原子改名」，
多个进程同时首启也不会互相踩。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import zipfile

MARKER = ".ready"
VENDOR_DIR = "_vendor"


def _archive_path() -> str | None:
    """取当前 zip 归档的绝对路径；源码运行时返回 None。"""
    loader = globals().get("__loader__")
    return getattr(loader, "archive", None)


def _cache_root() -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "xm-decrypt")


def _digest(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _extract(archive: str, dest: str) -> None:
    parent = os.path.dirname(dest)
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".tmp-", dir=parent)
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = [n for n in bundle.namelist() if n.startswith(VENDOR_DIR + "/")]
            if not names:
                raise RuntimeError("归档里没有 _vendor/，这不是带依赖的构建")
            bundle.extractall(staging, members=names)
        source = os.path.join(staging, VENDOR_DIR)
        with open(os.path.join(source, MARKER), "w", encoding="utf-8") as marker:
            marker.write("ok\n")
        try:
            os.replace(source, dest)
        except OSError:
            # 并发首启时别的进程刚装好，直接用现成的
            if not os.path.exists(os.path.join(dest, MARKER)):
                raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def install() -> str | None:
    """解压并挂载依赖，返回实际使用的目录（未打包依赖时返回 None）。"""
    archive = _archive_path()
    if not archive or not os.path.isfile(archive):
        return None

    try:
        dest = os.path.join(_cache_root(), "libs-" + _digest(archive))
        if not os.path.exists(os.path.join(dest, MARKER)):
            _extract(archive, dest)
    except OSError:
        # 家目录不可写（只读镜像、CI 容器等）时退化为进程级临时目录
        dest = tempfile.mkdtemp(prefix="xm-decrypt-libs-")
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(dest, members=[n for n in bundle.namelist() if n.startswith(VENDOR_DIR + "/")])
        dest = os.path.join(dest, VENDOR_DIR)

    if dest not in sys.path:
        sys.path.insert(0, dest)
    return dest
