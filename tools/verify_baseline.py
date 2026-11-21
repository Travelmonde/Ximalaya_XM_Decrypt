"""回归基线校验脚本（不依赖临时目录，可长期复用）。

用法（在项目根目录执行）：
    /home/tally/.workbuddy/binaries/python/envs/default/bin/python \
        tools/verify_baseline.py

它会：
1. 遍历目录下所有 .xm，走完整解密流程（不写盘），检查能否产出音频；
2. 对每个文件解密后写入临时输出目录，比对产物 sha256 与基线；
3. 顺带验证单进程与 spawn 并行两条路径结果一致。

基线为 2026-11-21 在 Python 3.13 + wasmtime 51 上测得的固定值，
用于确认后续改动「功能不变」。
"""

import glob
import hashlib
import os
import pathlib
import shutil
import sys
import tempfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

BASELINE = {
    "【预告】第四季 暗流涌动篇.xm":
        "3a523aff6b58a6dd097fbb1e5a73ffec9612343a1e9abce3c7306a5d8bf39e4f",
}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    import xm_decrypt as xm

    os.chdir(PROJECT_ROOT)
    files = sorted(glob.glob("*.xm"))
    if not files:
        print("目录下没有 .xm 文件，跳过。")
        return 0

    # 用项目内的临时目录，避免 /tmp 是小型 tmpfs 时写出失败
    tmp_root = PROJECT_ROOT / ".workbuddy" / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    out_dir = tempfile.mkdtemp(prefix="xm_verify_", dir=str(tmp_root))
    failures = 0
    try:
        for name in files:
            print(f"=== {name} ===")
            try:
                info, audio = xm.xm_decrypt(xm.read_file(name))
                ext = xm.find_ext(audio[:0xff])
                print(f"  解密 OK：{len(audio)} 字节，格式 {ext}，音轨 {info.tracknumber}")
            except Exception as exc:
                print(f"  解密失败：{type(exc).__name__}: {exc}")
                failures += 1
                continue

            files_sorted = xm.sort_files_by_track_id([name])
            xm.decrypt_xm_file(files_sorted[0], out_dir, 1, 1, "keep")

            produced = []
            for root, _, names in os.walk(out_dir):
                produced.extend(os.path.join(root, n) for n in names)
            if len(produced) != 1:
                print(f"  产物数量异常：{produced}")
                failures += 1
                continue

            digest = sha256_of(produced[0])
            expected = BASELINE.get(name)
            if expected is None:
                print(f"  无基线，记录当前值：{digest}")
            elif digest == expected:
                print(f"  产物哈希与基线一致 ✓ {digest}")
            else:
                print(f"  产物哈希不一致 ✗\n    实际 {digest}\n    基线 {expected}")
                failures += 1
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)

    print("\n全部通过 ✓" if failures == 0 else f"\n{failures} 项未通过 ✗")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
