<h1 align="center">喜马拉雅xm文件解密工具</h1>

## 说明
本工具用于解密喜马拉雅官方客户端下载的加密音频文件，本工具在 [sld272](https://github.com/sld272/Ximalaya-XM-Decrypt.git) 工作基础上进行维护工作，包括修复 bug、替换老旧的库、增加多核支持与终端界面。具体解密原理请详阅 @aynakeya 的[博文](https://www.aynakeya.com/2023/03/15/ctf/xi-ma-la-ya-xm-wen-jian-jie-mi-ni-xiang-fen-xi/)。

使用前请确保 `xm_encryptor.wasm` 与 `main.py` 位于同一目录（放在 `xm_decrypt/` 包目录下也能被找到）。

> **版本状态：0.1.0。** 完整流程只在单个样本上验证过——真机上带 `N/M` 音轨号的多音轨文件、wav/flac/mp3 载体的 xm 都没测过。操作前请自行备份原始 `.xm`。版本号保持 0.x，直到覆盖面补上来。

## 功能特点
- **终端界面（TUI）**：DOS 风格单线框 + 键盘菜单，全键盘操作，不依赖 tkinter，服务器 / SSH 环境同样可用
- **多选解密 + 逐个改名**：一次选中多个 `.xm`，每个文件都能单独指定输出名
- **目录批量解密**：可选是否包含子目录，支持多进程并行
- **设置持久化**：默认输入/输出目录、是否含子目录、WAV 处理方式、并行数都会记住
- **格式支持**：mp3、aac、flac、m4a、wav；wav 可选转为 ALAC 无损 `.m4a` 以减小体积

## 安装

有两种用法，按需选择：

**A. 直接跑单文件可执行程序（免安装 Python 依赖）**

从 Release 下载对应平台的 `.pyz`，例如 Linux x86-64 用
`xm-decrypt-0.1.0-py3-none-linux_x86_64.pyz`：

```bash
python3 xm-decrypt-0.1.0-py3-none-linux_x86_64.pyz            # 终端界面
python3 xm-decrypt-0.1.0-py3-none-linux_x86_64.pyz --cli -h   # 命令行
```

首次运行会把内置依赖解压到 `~/.cache/xm-decrypt/`（约 53 MB，1 秒左右），之后直接复用。
路径含中文、想换个地方时，设置 `XDG_CACHE_HOME` 即可。

**B. 从源码运行**

```bash
git clone https://github.com/taally666/Ximalaya_XM_Decrypt_TUI.git
cd Ximalaya_XM_Decrypt_TUI
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> 需要 Python 3.9 及以上（已在 3.12 / 3.13 上验证）。仅在把 wav 转成 ALAC 时需要系统里有 `ffmpeg`。

启动时会先检查依赖，缺哪一个会直接提示对应的 `pip install` 命令，不会抛一堆堆栈。

**C. 装成系统命令 `xm-decrypt`（推荐）**

源码和环境就绪后，一条命令装到 `~/.local/bin`：

```bash
python tools/install.py              # 安装 / 覆盖升级
python tools/install.py --uninstall  # 卸载
```

之后在任何目录直接敲：

```bash
xm-decrypt            # 终端界面
xm-decrypt --cli -h   # 命令行
```

默认装的是**内嵌依赖**的版本（15 MB）：第三方库都在归档里，shebang 只用系统 `python3`，
首次运行解压到 `~/.cache/xm-decrypt/`。好处是换机器、删虚拟环境都不受影响。
装完脚本会自动跑一次 `--cli -h` 自检。

想省空间可以用 `python tools/install.py --minimal`，装 53 KB 版本，
此时 shebang 指向当前解释器的绝对路径，要求该解释器已装好依赖。

## 使用
```bash
python main.py
```

启动后进入主界面：顶部是程序名与主机名，下面是黄底的常驻提示条，
正文分四块——**操作**（键盘菜单）、**当前设置**、**状态 / 消息**、**日志**。
菜单用 `↑` `↓` 移动、`Enter` 确认，也可以直接按下面的字母键：

| 按键 | 作用 |
| --- | --- |
| `F` | 解密 `.xm` 文件（可多选、可改名） |
| `D` | 解密整个目录 |
| `S` | 设置 |
| `Q` | 退出 |

界面配色只有黑 / 白 / 灰 / 青 / 黄五种，当前项用黄色加粗和 `>>` 标记，不依赖 256 色终端。

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
│   ├── install.py           打包并安装成 `xm-decrypt` 命令
│   ├── build_release.py     多平台发行版 + 校验和清单
│   ├── build_pyz.py         打包单个 .pyz（可内嵌依赖）
│   ├── build_exe.py         打包成免依赖可执行程序
│   ├── _vendor_boot.py      带依赖的 .pyz 首启解压逻辑
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
        ├── app.py           应用与主界面（标题栏 + 菜单 + 状态 + 日志）
        ├── widgets.py       自绘控件：标题栏、提示条、键盘菜单、[x] 复选框
        ├── picker.py        文件 / 目录选择器（多选与选目录共用）
        ├── screens.py       命名确认 / 目录确认 / 设置 / 运行页
        └── styles.tcss      样式（黑底单线框，配色集中在这一处）
```

分层原则：`metadata` 只读文件头，`decryptor` 只算字节，`exporter` 只负责落盘，`batch` 只负责调度，界面层不碰解密细节。要在其他脚本里复用，直接 `from xm_decrypt import decrypt_xm_to` 即可。

仓库只包含运行代码与 `tools/` 脚本。开发过程中的本地笔记、构建中间产物放在 `.workbuddy/`，已在 `.gitignore` 中排除，不会提交。

## 打包与分发

按「要不要在目标机器装依赖」选产物：

| 产物 | 体积 | 构建 | 目标机器要求 |
| --- | --- | --- | --- |
| `-py3-none-any.pyz` | 53 KB | `build_release.py` / `build_pyz.py` | 已装好依赖 |
| `-py3-none-<平台>.pyz` | 12–15 MB | `build_release.py` | 只需 `python3`（3.9+），按平台分发 |
| `xm-decrypt`（可执行） | 81 MB | `build_exe.py` | 什么都不用，连 Python 都不需要 |

发布用 `build_release.py`（一次产出全部平台 + 校验和清单）；`build_pyz.py` 是它的底层，
只打单个包，想改打包细节时用。

### 单文件 .pyz（含内置依赖）

```bash
python tools/build_pyz.py --with-deps     # → dist/xm-decrypt-standalone.pyz
```

```bash
python xm-decrypt-standalone.pyz              # TUI
python xm-decrypt-standalone.pyz --cli -h     # 命令行
```

**`.pyz` 是 zip，无法直接 import 原生扩展**（`wasmtime/_libwasmtime.so`、`Crypto/**/*.so`），
所以内嵌依赖不是「塞进 zip 就能用」，而是首启时解压到缓存再挂到 `sys.path`：

- 依赖放在归档的 `_vendor/`，入口 `__main__.py` 先调用 `_xm_vendor.install()`；
- 解压目标 `~/.cache/xm-decrypt/libs-<pyz 的 sha256 前 16 位>/`，归档变了就换目录，不会读到半新半旧的库；
- 解压用「临时目录 + 原子改名」，多进程同时首启不会互相踩；家目录不可写时退化为进程级临时目录；
- 首次运行约 7 秒（解压 54 MB），之后不到 1 秒。

实测在**完全没装依赖**的系统 Python 3.12 上：解密产物 sha256 `c5ebb5d1…` 与源码一致，
`-j 2` 并行正常，TUI 渲染出的样式规则数仍是 106。

### 精简版 .pyz

```bash
python tools/build_pyz.py                  # → dist/xm-decrypt.pyz（53 KB）
```

只含 `main.py`、`xm_decrypt/`、`styles.tcss` 和 `xm_encryptor.wasm`，**不含第三方依赖**——
zipapp 只是把代码打成 zip，`wasmtime`、`pycryptodome` 是带 `.so` 的原生扩展，无法从 zip 里 import。
换机器跑之前仍要 `pip install -r requirements.txt`；缺依赖时程序会提示装哪些包。

上面两种 `.pyz` 共用的两个实现细节（改代码时别踩）：

- **wasm 必须打进归档**。`wasm.py` 先用磁盘候选路径找 `xm_encryptor.wasm`，找不到就通过 zipimporter 的 `archive` 属性从归档内部读字节，交给 `wasmtime.Module(engine, bytes)`。所以单独拷一个 `.pyz` 出去也能跑，不必附带 wasm。
- **样式不能再用 `CSS_PATH`**。Textual 会用 `inspect.getfile()` 拼出 `.../xm-decrypt.pyz/xm_decrypt/tui/styles.tcss` 这种磁盘上不存在的路径。现在磁盘上有文件时仍走 `CSS_PATH`（保留开发期热重载），打包运行时改为从归档读文本塞进 `CSS`。两种方式加载的样式规则数都是 106 条，外观一致。

### 发行版（多平台）

```bash
python tools/build_release.py            # 全部平台
python tools/build_release.py --native-only    # 只打本机
```

产物命名沿用 wheel 的 tag 风格 `xm-decrypt-<版本>-py3-none-<平台>.pyz`：

| 文件 | 平台 | 大小 |
| --- | --- | --- |
| `...-py3-none-any.pyz` | 通用（纯 Python） | 53 KB |
| `...-py3-none-linux_x86_64.pyz` | Linux x86-64 | 14.6 MB |
| `...-py3-none-linux_aarch64.pyz` | Linux ARM64 | 13.2 MB |
| `...-py3-none-win_amd64.pyz` | Windows x64 | 11.9 MB |
| `...-py3-none-macosx_11_0_arm64.pyz` | macOS Apple Silicon | 12.1 MB |
| `...-py3-none-macosx_10_13_x86_64.pyz` | macOS Intel | 12.8 MB |

同时生成 `dist/SHA256SUMS-<版本>.txt`，发布时一并附上。

**必须按平台分开打包，不能一个包通吃**：包里的 `wasmtime/linux-x86_64/_libwasmtime.so`、
`Crypto/Cipher/_ARC4.pyd` 都是按平台编译的二进制；而且 macOS 与 Linux 的 pycryptodome
扩展**同名**（都叫 `_ARC4.abi3.so`），装不进同一个包。

本机平台用已安装的依赖打包并实测；其它平台由脚本从 PyPI 下载对应 wheel 组装，
**只做了结构校验**（确认原生库文件名、架构目录正确），没有真机运行过。
脚本会打印每个产物是「本机实测」还是「仅结构校验」，别把后者当已验证。

交叉打包踩过的一个坑：macOS Intel 必须写 `macosx_10_13_x86_64`（wasmtime 提供的最低版本）。
写成 `macosx_10_9_x86_64` 会让 pip 匹配不上，退回到一个「标着 `any` 却只含 Windows DLL」的
废包，打出来的产物在 Mac 上必然启动失败——所以脚本里有原生库存在性校验，缺了直接报错。

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
