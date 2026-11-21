"""xm_encryptor.wasm 的运行时管理。

只负责"把 wasm 跑起来"和"安全读写它的线性内存"，不掺解密业务逻辑。
"""

from __future__ import annotations

import pathlib
import zipfile

import wasmtime

_RUNTIME = None

WASM_FILENAME = "xm_encryptor.wasm"


def _search_paths():
    """按 包目录 → 项目根目录 → 当前目录 的顺序给出候选路径。"""
    package_dir = pathlib.Path(__file__).resolve().parent
    return (
        package_dir / WASM_FILENAME,
        package_dir.parent / WASM_FILENAME,
        pathlib.Path.cwd() / WASM_FILENAME,
    )


def wasm_path() -> pathlib.Path:
    """定位磁盘上的 wasm 文件。

    打包成 .pyz 后磁盘上并没有这个文件，那种场景请用 wasm_bytes()。
    """
    for candidate in _search_paths():
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"未找到 {WASM_FILENAME}，已尝试：{[str(c) for c in _search_paths()]}")


def wasm_bytes() -> bytes:
    """读取 wasm 内容：优先磁盘，其次从运行中的 .pyz 归档内部取。

    zipapp 运行时 __file__ 形如 /path/app.pyz/xm_decrypt/wasm.py，磁盘上
    并没有该目录，只能通过 zipimporter 的 archive 属性回到归档里读。
    """
    for candidate in _search_paths():
        if candidate.is_file():
            return candidate.read_bytes()

    loader = globals().get("__loader__")
    archive = getattr(loader, "archive", None)
    if archive:
        try:
            with zipfile.ZipFile(archive) as bundle:
                return bundle.read(WASM_FILENAME)
        except (KeyError, OSError, zipfile.BadZipFile):
            pass
    raise FileNotFoundError(f"未找到 {WASM_FILENAME}，已尝试：{[str(c) for c in _search_paths()]}")


def instantiate(wasm_source, memory_reservation=None):
    """创建 Engine/Store 并实例化模块，返回 (store, exports)。

    wasm_source 可为 bytes（归档内读取）或路径。
    memory_reservation 为 None 时沿用 wasmtime 默认值（4GiB 静态预留）；
    为 0 时改为动态内存，供地址空间受限的环境降级使用。
    """
    if memory_reservation is None:
        engine = wasmtime.Engine()
    else:
        config = wasmtime.Config()
        config.memory_reservation = memory_reservation
        engine = wasmtime.Engine(config)

    store = wasmtime.Store(engine)
    if isinstance(wasm_source, (bytes, bytearray)):
        module = wasmtime.Module(engine, bytes(wasm_source))
    else:
        module = wasmtime.Module.from_file(engine, str(wasm_source))

    # 使用 wasmtime 当前推荐的 Linker 实例化路径。
    # 旧写法 wasmtime.Instance(store, module, []) 属于早期低层 API，
    # 其构造签名与 exports 的取值形式在 wasmtime-py 版本迭代中多次变动，
    # Linker 路径是官方文档的稳定入口。
    linker = wasmtime.Linker(engine)
    instance = linker.instantiate(store, module)
    return store, instance.exports(store)


def get_runtime():
    """进程级单例：store 的生命周期必须与导出函数一致。

    保留模块级缓存（而非每次都实例化）是有意为之：wasm 实例化在
    受限环境下有明显开销，且导出函数句柄绑定在 store 上。
    """
    global _RUNTIME
    if _RUNTIME is not None:
        return _RUNTIME

    wasm_data = wasm_bytes()
    try:
        store, exports = instantiate(wasm_data)
    except wasmtime.WasmtimeError:
        # 容器 / CI 等场景常用 ulimit -v 限制地址空间，此时默认的 4GiB
        # 静态内存预留会 mmap 失败。改为动态内存后功能一致，只是少了
        # 越界访问的 guard page 保护（本项目由 read_memory 自行校验）。
        store, exports = instantiate(wasm_data, memory_reservation=0)

    _RUNTIME = {
        "store": store,
        "a": exports["a"],
        "c": exports["c"],
        "g": exports["g"],
        "i": exports["i"],
    }
    return _RUNTIME


def read_memory(memory, store, start, length):
    """按起止偏移读取 wasm 线性内存，并显式校验越界。

    wasmtime 各版本对越界读取抛出的异常类型并不统一（Python 异常 / wasm trap），
    这里用稳定的 data_len() 先做边界检查，保证失败时给出可读的错误信息。
    """
    if start < 0 or length < 0:
        raise RuntimeError(f"wasm 内存读取参数非法：start={start}, length={length}")
    end = start + length
    capacity = memory.data_len(store)
    if end > capacity:
        raise RuntimeError(f"wasm 内存越界：请求 [{start}, {end}) 超出容量 {capacity}")
    return bytes(memory.read(store, start, end))
