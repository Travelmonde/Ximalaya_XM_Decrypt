"""把项目打包成免依赖的单文件可执行程序（PyInstaller onefile）。

和 build_pyz.py 的区别：
    .pyz  只有 50 KB，但要求运行的 Python 里已装好第三方依赖；
    exe   约 100 MB，自带 Python 解释器与全部原生库，拷到任何 Linux x86-64 机器都能直接跑。

用法：
    python tools/build_exe.py          # 输出 dist/xm-decrypt

必须在**装了依赖的解释器**下运行（PyInstaller 只收集当前环境里的包）：

    /path/to/venv/bin/python tools/build_exe.py
"""

from __future__ import annotations

import glob
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TARGET = DIST / "xm-decrypt"
# 构建中间产物放项目内的 .workbuddy/tmp（已 gitignore），避免污染根目录。
WORK = ROOT / ".workbuddy" / "tmp" / "pyinstaller"


def find_wasmtime_lib() -> Path:
    """定位 wasmtime 的平台原生库。

    这个 .so 是运行时用 ctypes 按 `wasmtime/<平台>/_libwasmtime.so` 加载的，
    PyInstaller 的 collect-all 不会把它打进归档，必须显式 add-binary，
    否则运行时报 `cannot open shared object file`。
    """
    patterns = [
        Path(sys.prefix) / "lib" / f"python{sys.version_info[0]}.{sys.version_info[1]}" / "site-packages",
        *[Path(p) for p in sys.path if p.endswith("site-packages")],
    ]
    for base in patterns:
        hits = glob.glob(str(base / "wasmtime" / "*" / "_libwasmtime.so"))
        if hits:
            return Path(hits[0])
    raise SystemExit("未找到 wasmtime 的原生库 _libwasmtime.so，请先安装 wasmtime")


def build() -> Path:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit(
            f"未安装 PyInstaller，先执行：\n  {sys.executable} -m pip install pyinstaller"
        ) from None

    lib = find_wasmtime_lib()
    workdir = WORK / "build"
    specdir = WORK / "spec"
    workdir.mkdir(parents=True, exist_ok=True)
    specdir.mkdir(parents=True, exist_ok=True)

    # onefile 运行时会解压到临时目录，构建时也要用系统临时目录；
    # 这里显式指定，避免落到容量很小的 /tmp。
    env = dict(os.environ, TMPDIR=str(WORK))

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--name",
        TARGET.name,
        "--workpath",
        str(workdir),
        "--specpath",
        str(specdir),
        "--distpath",
        str(DIST),
        # wasm 与样式都是运行时按路径读的，必须随包带进去
        "--add-data",
        f"{ROOT / 'xm_encryptor.wasm'}{os.pathsep}.",
        "--add-data",
        f"{ROOT / 'xm_decrypt' / 'tui' / 'styles.tcss'}{os.pathsep}xm_decrypt/tui",
        "--add-binary",
        f"{lib}{os.pathsep}wasmtime/{lib.parent.name}",
        # Textual 的控件是动态导入的，静态分析看不到
        "--collect-submodules",
        "textual",
        str(ROOT / "main.py"),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stdout or "")[-1500:] + (result.stderr or "")[-1500:]
        raise SystemExit(f"构建失败：\n{tail}")
    return TARGET


def main() -> int:
    target = build()
    if not target.is_file():
        print("构建结束但未找到产物")
        return 1

    data = target.read_bytes()
    print(f"产物：{target.relative_to(ROOT)}")
    print(f"大小：{len(data) / 1024 / 1024:.1f} MB")
    print(f"sha256：{hashlib.sha256(data).hexdigest()}")

    # 自检：直接跑一次 --cli -h，确认依赖（尤其 wasmtime 的 .so）都在包里。
    probe = subprocess.run(
        [str(target), "--cli", "-h"],
        capture_output=True,
        text=True,
        env=dict(os.environ, TMPDIR=str(WORK)),
    )
    if probe.returncode != 0 or "usage:" not in probe.stdout:
        print("自检失败，程序无法启动：")
        print((probe.stdout + probe.stderr)[-1000:])
        return 1
    print("自检通过：可在未安装 Python 依赖的机器上直接运行")
    print()
    print(f"  ./{target.relative_to(ROOT)}                  # TUI")
    print(f"  ./{target.relative_to(ROOT)} --cli -h         # 命令行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
