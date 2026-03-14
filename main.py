import base64
import io
import sys
import os
import glob
import pathlib
import struct
import mutagen
import tkinter as tk
from tkinter import filedialog
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from mutagen.id3 import TALB, TIT2, TPE1, TRCK
from mutagen.easyid3 import ID3
from mutagen.wave import WAVE
import wasmtime


_WASM_RUNTIME = None


class XMInfo:
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
        if self.ISRC != "":
            return bytes.fromhex(self.ISRC)
        return bytes.fromhex(self.encodedby)


def get_str(x):
    if x is None:
        return ""
    return x


def read_file(x):
    with open(x, "rb") as f:
        return f.read()


# return number of id3 bytes
def get_xm_info(data: bytes):
    # print(EasyID3(io.BytesIO(data)))
    id3 = ID3(io.BytesIO(data), v2_version=3)
    id3value = XMInfo()
    id3value.title = str(id3["TIT2"])
    id3value.album = str(id3["TALB"])
    id3value.artist = str(id3["TPE1"])
    id3value.tracknumber = int(str(id3["TRCK"]))
    id3value.ISRC = "" if id3.get("TSRC") is None else str(id3["TSRC"])
    id3value.encodedby = "" if id3.get("TENC") is None else str(id3["TENC"])
    id3value.size = int(str(id3["TSIZ"]))
    id3value.header_size = id3.size
    id3value.encoding_technology = str(id3["TSSE"])
    return id3value


def get_printable_count(x: bytes):
    i = 0
    for i, c in enumerate(x):
        # all pritable
        if c < 0x20 or c > 0x7e:
            return i
    return len(x)


def get_printable_bytes(x: bytes):
    return x[:get_printable_count(x)]


def get_wasm_runtime():
    global _WASM_RUNTIME
    if _WASM_RUNTIME is not None:
        return _WASM_RUNTIME

    engine = wasmtime.Engine()
    store = wasmtime.Store(engine)
    wasm_path = pathlib.Path(__file__).with_name("xm_encryptor.wasm")
    module = wasmtime.Module.from_file(engine, str(wasm_path))
    instance = wasmtime.Instance(store, module, [])
    exports = instance.exports(store)

    _WASM_RUNTIME = {
        "store": store,
        "a": exports["a"],
        "c": exports["c"],
        "g": exports["g"],
        "i": exports["i"],
    }
    return _WASM_RUNTIME


def xm_decrypt(raw_data):
    wasm_runtime = get_wasm_runtime()
    store = wasm_runtime["store"]

    # decode id3
    xm_info = get_xm_info(raw_data)
    # print("id3 header size: ", hex(xm_info.header_size))
    encrypted_data = raw_data[xm_info.header_size:xm_info.header_size + xm_info.size:]

    # Stage 1 aes-256-cbc
    xm_key = b"ximalayaximalayaximalayaximalaya"
    # print(f"decrypt stage 1 (aes-256-cbc):\n"
    #       f"    data length = {len(encrypted_data)},\n"
    #       f"    key = {xm_key},\n"
    #       f"    iv = {xm_info.iv().hex()}")
    cipher = AES.new(xm_key, AES.MODE_CBC, xm_info.iv())
    de_data = cipher.decrypt(pad(encrypted_data, 16))
    # print("success")
    # Stage 2 xmDecrypt (wasm)
    de_data = get_printable_bytes(de_data)
    track_id = str(xm_info.tracknumber).encode()
    stack_pointer = wasm_runtime["a"](store, -16)
    de_data_offset = wasm_runtime["c"](store, len(de_data))
    track_id_offset = wasm_runtime["c"](store, len(track_id))
    memory = wasm_runtime["i"]

    memory.write(store, de_data, start=de_data_offset)
    memory.write(store, track_id, start=track_id_offset)
    wasm_runtime["g"](store, stack_pointer, de_data_offset, len(de_data), track_id_offset, len(track_id))

    result_meta = bytes(memory.read(store, stack_pointer, stack_pointer + 16))
    result_pointer, result_length, status_code, extra_code = struct.unpack("<4i", result_meta)
    if status_code != 0 or extra_code != 0:
        raise RuntimeError(f"wasm decrypt failed: status={status_code}, extra={extra_code}")
    result_data = bytes(memory.read(store, result_pointer, result_pointer + result_length)).decode()
    # Stage 3 combine
    # print(f"Stage 3 (base64)")
    decrypted_data = base64.b64decode(xm_info.encoding_technology + result_data)
    final_data = decrypted_data + raw_data[xm_info.header_size + xm_info.size::]
    # print("success")
    return xm_info, final_data


def find_ext(data):
    if len(data) >= 8 and data[4:8] == b'ftyp':
        return "m4a"
    if data[:2] in [b'\xff\xf1', b'\xff\xf9']:
        return "aac"
    if data[:3] == b'ID3':
        return "mp3"
    if data[:4] == b'fLaC':
        return "flac"
    if data[:4] == b'RIFF':
        return "wav"
    return "aac"


def get_xm_track_id(from_file):
    id3 = ID3(from_file, v2_version=3)
    trck = str(id3["TRCK"])
    return int(trck.split("/")[0])


def sort_files_by_track_id(files_to_decrypt):
    def sort_key(path):
        try:
            return (get_xm_track_id(path), path)
        except Exception:
            # Keep undecodable files at the end but deterministic by path.
            return (sys.maxsize, path)

    return sorted(files_to_decrypt, key=sort_key)


def decrypt_xm_file(from_file, output_path='./output', track_no=None, track_total=None):
    print(f"正在解密{from_file}")
    data = read_file(from_file)
    info, audio_data = xm_decrypt(data)
    ext = find_ext(audio_data[:0xff])
    safe_title = replace_invalid_chars(info.title)
    if track_no is not None and track_total is not None:
        width = len(str(track_total))
        safe_title = f"{track_no:0{width}d} - {safe_title}"
    output = f"{output_path}/{replace_invalid_chars(info.album)}/{safe_title}.{ext}"
    if not os.path.exists(f"{output_path}/{replace_invalid_chars(info.album)}"):
        os.makedirs(f"{output_path}/{replace_invalid_chars(info.album)}")
    with open(output, "wb") as f:
        f.write(audio_data)

    # Best-effort metadata writing: do not fail decryption when tagging is unsupported.
    try:
        if ext in ["mp3", "flac", "m4a"]:
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
    except Exception as e:
        print(f"写入标签失败，已跳过：{e}")

    print(f"解密成功，文件保存至{output}！")


def replace_invalid_chars(name):
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in invalid_chars:
        if char in name:
            name = name.replace(char, " ")
    return name


def select_file():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename()
    root.destroy()
    return file_path


def select_directory():
    root = tk.Tk()
    root.withdraw()
    directory_path = filedialog.askdirectory()
    root.destroy()
    return directory_path


if __name__ == "__main__":
    while True:
        print("欢迎使用喜马拉雅音频解密工具")
        print("本工具仅供学习交流使用，严禁用于商业用途")
        print("请选择您想要使用的功能：")
        print("1. 解密单个文件")
        print("2. 批量解密文件")
        print("3. 退出")
        choice = input()
        if choice == "1" or choice == "2":
            if choice == "1":
                files_to_decrypt = [select_file()]
                if files_to_decrypt == [""]:
                    print("检测到文件选择窗口被关闭")
                    continue
            elif choice == "2":
                dir_to_decrypt = select_directory()
                if dir_to_decrypt == "":
                    print("检测到目录选择窗口被关闭")
                    continue
                files_to_decrypt = glob.glob(os.path.join(dir_to_decrypt, "*.xm"))
            files_to_decrypt = sort_files_by_track_id(files_to_decrypt)
            track_total = len(files_to_decrypt)
            print("请选择是否需要设置输出路径：（不设置默认为本程序目录下的output文件夹）")
            print("1. 设置输出路径")
            print("2. 不设置输出路径")
            choice = input()
            if choice == "1":
                output_path = select_directory()
                if output_path == "":
                    print("检测到目录选择窗口被关闭")
                    continue
            elif choice == "2":
                output_path = "./output"
            for i, file in enumerate(files_to_decrypt, start=1):
                decrypt_xm_file(file, output_path, i, track_total)
        elif choice == "3":
            sys.exit()
        else:
            print("输入错误，请重新输入！")
