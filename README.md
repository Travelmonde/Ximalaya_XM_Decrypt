<h1 align="center">喜马拉雅xm文件解密工具</h1>

## 说明
本工具用于解密喜马拉雅官方客户端下载的加密音频文件，本工具在 [sld272](https://github.com/sld272/Ximalaya-XM-Decrypt.git) 工作基础上进行维护工作，包括修复 bug、替换老旧的库、增加多核支持与终端界面。具体解密原理请详阅 @aynakeya 的[博文](https://www.aynakeya.com/2023/03/15/ctf/xi-ma-la-ya-xm-wen-jian-jie-mi-ni-xiang-fen-xi/)。

使用前请确保 `xm_encryptor.wasm` 与 `main.py` 位于同一目录（放在 `xm_decrypt/` 包目录下也能被找到）。

## 功能特点
- **终端界面（TUI）**：全键盘操作，不依赖 tkinter，服务器 / SSH 环境同样可用
- **多选解密 + 逐个改名**：一次选中多个 `.xm`，每个文件都能单独指定输出名
- **目录批量解密**：可选是否包含子目录，支持多进程并行
- **设置持久化**：默认输入/输出目录、是否含子目录、WAV 处理方式、并行数都会记住
- **格式支持**：mp3、aac、flac、m4a、wav；wav 可选转为 ALAC 无损 `.m4a` 以减小体积

## 安装

有两种用法，按需选择：

**A. 直接跑单文件可执行程序（免安装 Python 依赖）**

从 Release 下载 `xm-decrypt`（Linux x86-64），加执行权限后直接运行：

```bash
chmod +x xm-decrypt
./xm-decrypt            # 终端界面
./xm-decrypt --cli -h   # 命令行
```

**B. 从源码运行**

```bash
git clone https://github.com/taally666/Ximalaya_XM_Decrypt_TUI.git
cd Ximalaya_XM_Decrypt_TUI
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> 需要 Python 3.9 及以上（已在 3.12 / 3.13 上验证）。仅在把 wav 转成 ALAC 时需要系统里有 `ffmpeg`。

启动时会先检查依赖，缺哪一个会直接提示对应的 `pip install` 命令，不会抛一堆堆栈。

## 使用
```bash
python main.py
```

启动后进入主界面，左侧为功能入口，右侧显示当前设置：

| 按键 | 作用 |
| --- | --- |
| `F` | 解密 `.xm` 文件（可多选、可改名） |
| `D` | 解密整个目录 |
| `S` | 设置 |
| `Q` | 退出 |

### 文件选择页
| 按键 | 作用 |
| --- | --- |
| `↑` `↓` | 移动光标 |
| `空格` | 选中 / 取消当前文件 |
| `Enter` | 进入目录 / 切换选中 |
| `A` | 全选当前目录 |
| `C` | 清空选择 |
| `Ctrl+S` | 确定 |
| `Esc` | 取消 |

选好文件后进入“命名确认”页：可以修改输出目录，并逐个修改输出文件名（不用写扩展名，程序按解密结果自动补全）。默认名取自 ID3 标题，多选时自动加 `1 - `、`2 - ` 顺序前缀；重名或留空会被拦下并提示。

### 目录解密
确认页会显示扫描到的文件数，可临时切换是否包含子目录、调整并行进程数。输出规则：

```
<输出目录>/<专辑>/<曲序 - 标题>.<扩展名>
```

运行页有进度条与逐条日志，失败项会显示原因；`停止` 会在当前文件处理完后中断。

### 设置项
| 设置 | 说明 |
| --- | --- |
| 默认输入目录 | 打开文件 / 目录选择器时的起始位置 |
| 默认输出目录 | 命名页与目录解密页的预填值 |
| 扫描目录时包含子目录 | 目录解密时是否递归 |
| WAV 处理 | 保留 WAV / 封装为 ALAC |
| 并行进程数 | `0` 表示自动（CPU 核心数，上限 8） |

设置保存在 `~/.config/xm-decrypt/settings.json`（Windows 为 `%APPDATA%\xm-decrypt\settings.json`），设置页底部会显示实际路径。

### 命令行模式
适合脚本、cron 或无交互终端的环境：

```bash
python main.py --cli -h                                  # 查看全部参数
python main.py --cli                                     # 用设置里的默认目录
python main.py --cli -d ~/xm -o ~/out -j 4 -r            # 目录 + 4 进程 + 含子目录
python main.py --cli -f a.xm -f b.xm --name 第一集 --name 第二集
python main.py --cli --settings                          # 打印当前设置
```

## 项目结构
```
.
├── main.py                  统一入口：默认启动 TUI，--cli 走命令行
├── xm_encryptor.wasm        wasm 解密模块（必需）
├── requirements.txt
├── tools/                   开发与发布脚本（不参与运行）
│   ├── build_pyz.py         打包成单文件 .pyz
│   ├── build_exe.py         打包成免依赖可执行程序
│   ├── verify_baseline.py   解密产物哈希回归
│   └── test_tui.py          界面端到端测试（Textual pilot）
└── xm_decrypt/              核心库
    ├── metadata.py          读 ID3 元信息、扫描与排序（不解密，开销极低）
    ├── wasm.py              wasm 实例化、内存读写、地址空间受限时的降级
    ├── decryptor.py         解密算法：AES-256-CBC → wasm → base64 拼接
    ├── exporter.py          命名规则、写标签、wav→ALAC、落盘
    ├── batch.py             单进程 / spawn 多进程调度
    ├── settings.py          设置持久化
    ├── cli.py               命令行模式
    └── tui/                 Textual 终端界面
        ├── app.py           应用与主界面
        ├── picker.py        文件 / 目录选择器（多选与选目录共用）
        ├── screens.py       命名确认 / 目录确认 / 设置 / 运行页
        └── styles.tcss      样式
```

分层原则：`metadata` 只读文件头，`decryptor` 只算字节，`exporter` 只负责落盘，`batch` 只负责调度，界面层不碰解密细节。要在其他脚本里复用，直接 `from xm_decrypt import decrypt_xm_to` 即可。

仓库只包含运行代码与 `tools/` 脚本。开发过程中的本地笔记、构建中间产物放在 `.workbuddy/`，已在 `.gitignore` 中排除，不会提交。

## 打包与分发

两种产物各有取舍：

| | `.pyz` | 可执行程序 |
| --- | --- | --- |
| 体积 | 约 53 KB | 约 100 MB |
| 构建工具 | 标准库 `zipapp` | PyInstaller |
| 运行前提 | 目标机器已装好依赖 | 无，自带解释器和原生库 |
| 适用 | 自己有 Python 环境 / 内部分发 | 给不想装环境的人 |

### 单文件 .pyz

```bash
python tools/build_pyz.py
```

产物 `dist/xm-decrypt.pyz`，把 `main.py`、`xm_decrypt/`、`styles.tcss` 和 `xm_encryptor.wasm` 全部封进一个压缩归档：

```bash
python xm-decrypt.pyz              # TUI
python xm-decrypt.pyz --cli -h     # 命令行
```

**它不含第三方依赖**——zipapp 只是把代码打成一个 zip，`wasmtime`、`pycryptodome` 是带 `.so` 的原生扩展，无法从 zip 里 import。所以换机器跑之前仍要 `pip install -r requirements.txt`，缺依赖时程序会提示装哪些包。

两个实现细节（改代码时别踩）：

- **wasm 必须打进归档**。`wasm.py` 先用磁盘候选路径找 `xm_encryptor.wasm`，找不到就通过 zipimporter 的 `archive` 属性从归档内部读字节，交给 `wasmtime.Module(engine, bytes)`。所以单独拷一个 `.pyz` 出去也能跑，不必附带 wasm。
- **样式不能再用 `CSS_PATH`**。Textual 会用 `inspect.getfile()` 拼出 `.../xm-decrypt.pyz/xm_decrypt/tui/styles.tcss` 这种磁盘上不存在的路径。现在磁盘上有文件时仍走 `CSS_PATH`（保留开发期热重载），打包运行时改为从归档读文本塞进 `CSS`。两种方式加载的样式规则数都是 135 条，外观一致。

### 免依赖可执行程序

```bash
python tools/build_exe.py     # 输出 dist/xm-decrypt
./xm-decrypt                  # 直接运行，不需要 Python 环境
```

用 PyInstaller onefile 打包，自带解释器、`wasmtime` 原生库和 Textual，拷到任何同架构 Linux 上都能跑。两个必须显式处理的点：

- `wasmtime` 的原生库 `_libwasmtime.so` 是运行时用 `ctypes` 按路径加载的，PyInstaller 的 `--collect-all` **不会**把它收进归档，必须 `--add-binary` 显式指定。漏了会在启动时报 `cannot open shared object file`。
- 冻结后多进程 spawn 会重新执行自身，入口处必须调用 `multiprocessing.freeze_support()`（非冻结环境是空操作）。

脚本末尾会自动跑一次 `--cli -h` 自检，确认依赖真的在包里。

## 注意事项
请确保你拥有合法的 xm 文件下载和转换权限。
仅限于学习交流使用，严禁商业使用，本工具作者不负任何其他责任。
转换过程中可能会占用较多系统资源，建议在空闲时间进行批量操作。
