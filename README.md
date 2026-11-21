<h1 align="center">喜马拉雅xm文件解密工具</h1>

## 说明
本工具用于解密喜马拉雅官方客户端下载的加密音频文件，本工具在 [sld272](https://github.com/sld272/Ximalaya-XM-Decrypt.git) 工作基础上进行维护工作，包括修复 bug、替换老旧的库、增加多核支持与终端界面。具体解密原理请详阅 @aynakeya 的[博文](https://www.aynakeya.com/2023/03/15/ctf/xi-ma-la-ya-xm-wen-jian-jie-mi-ni-xiang-fen-xi/)。

使用前请确保 `xm_encryptor.wasm` 与 `main.py` 位于同一目录（放在 `xm_decrypt/` 包目录下也能被找到）。

> **版本状态：0.1.0（Alpha）。** 当前仅在单一测试样本上完成端到端验证；带 `N/M` 音轨号的多音轨文件，以及 wav / flac / mp3 载体的 xm 文件尚未覆盖。处理前请备份原始 `.xm`。在上述场景验证通过之前，版本号保持在 0.x。

## 功能特点
- **终端界面（TUI）**：DOS 风格单线框 + 键盘菜单，全键盘操作，不依赖 tkinter，服务器 / SSH 环境同样可用
- **多选解密 + 逐个改名**：一次选中多个 `.xm`，每个文件都能单独指定输出名
- **目录批量解密**：可选是否包含子目录，支持多进程并行
- **设置持久化**：默认输入/输出目录、是否含子目录、WAV 处理方式、并行数都会记住
- **格式支持**：mp3、aac、flac、m4a、wav；wav 可选转为 ALAC 无损 `.m4a` 以减小体积

## 环境要求

| 项目 | 要求 |
| --- | --- |
| Python | **3.10 及以上**（已在 3.10 / 3.12 / 3.13 上实测） |
| ffmpeg | 可选，只在把 WAV 转成 ALAC 时需要 |

该下限由两处约束决定：

- 源码使用 `zip(..., strict=)`，该参数自 Python 3.10 起提供；
- 随包内嵌的 mutagen 1.48 在包元数据中声明 `Requires-Python >=3.10`。

发行包文件名中的 `py310` 对应这一约束。`.pyz` 不含 pyc 与包元数据，pip 无法读取版本要求，
版本信息只能通过文件名传达。以 3.9 运行会在启动校验阶段被终止，并输出明确的版本提示。

## 安装

按目标机器是否需要安装 Python 依赖选择：

| 形式 | 文件 | 目标机器需要 |
| --- | --- | --- |
| 目录式归档（推荐） | `xm-decrypt-0.1.0-py310-none-<平台>.tar.gz`（Windows 为 `.zip`） | 能跑 Python 3.10+，依赖已随包 |
| 单文件 `.pyz` | `xm-decrypt-0.1.0-py310-none-<平台>.pyz` | 同上，但首启要解压依赖到缓存 |
| 免依赖可执行文件 | `xm-decrypt` | 什么都不需要（目前只有 Linux x86-64） |
| 源码 | 仓库，或 `...-py310-none-any.tar.gz` | Python 3.10+ 和 `pip install -r requirements.txt` |

`<平台>` 取 `linux_x86_64` / `linux_aarch64` / `win_amd64` / `macosx_11_0_arm64` /
`macosx_10_13_x86_64` 之一，两种形式都是五个平台齐全。

**A. 目录式归档（免安装，不写用户缓存）**

```bash
tar xzf xm-decrypt-0.1.0-py310-none-linux_x86_64.tar.gz
cd xm-decrypt-0.1.0
./xm-decrypt              # 终端界面
./xm-decrypt --cli -h     # 命令行
```

Windows 对应为同名 `.zip`，解压后执行 `xm-decrypt.bat`。默认使用 PATH 中的 `python3`
（Windows 为 `python`）；如需指定解释器，设置环境变量：

```bash
XM_DECRYPT_PYTHON=/usr/bin/python3.12 ./xm-decrypt
```

第三方依赖位于目录内的 `_vendor/`，**不会写入 `~/.cache`**。整个目录可整体迁移，删除后无残留。
与 `.pyz` 相比，该形式适用于受安全软件策略限制、家目录不可写，或需要直接修改代码的场景。

**B. 单文件 `.pyz`（免安装 Python 依赖）**

从 Release 下载对应平台的 `.pyz`，例如 Linux x86-64：

```bash
python3 xm-decrypt-0.1.0-py310-none-linux_x86_64.pyz            # 终端界面
python3 xm-decrypt-0.1.0-py310-none-linux_x86_64.pyz --cli -h   # 命令行
```

首次运行时将内置依赖解压至 `~/.cache/xm-decrypt/`（约 53 MB），后续运行直接复用。
如需更改缓存位置（例如路径包含非 ASCII 字符），设置环境变量 `XDG_CACHE_HOME`。

**C. 从源码运行**

```bash
git clone https://github.com/taally666/Ximalaya_XM_Decrypt_TUI.git
cd Ximalaya_XM_Decrypt_TUI
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

启动前会检查依赖；缺失时输出对应的 `pip install` 命令，而非抛出异常堆栈。

**D. 装成系统命令 `xm-decrypt`（推荐）**

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
│   ├── build_release.py     多平台 .pyz 发行版 + 校验和清单
│   ├── build_archives.py    目录式归档（解压即用）与源码包
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

分层原则：`metadata` 只读文件头，`decryptor` 只算字节，`exporter` 只负责落盘，`batch` 只负责调度，界面层不碰解密细节。在其他脚本中复用可直接 `from xm_decrypt import decrypt_xm_to`。

仓库只包含运行代码与 `tools/` 脚本。开发过程中的本地笔记、构建中间产物放在 `.workbuddy/`，已在 `.gitignore` 中排除，不会提交。

## 打包与分发

按目标机器是否需要安装依赖选择产物：

| 产物 | 体积 | 构建 | 目标机器要求 |
| --- | --- | --- | --- |
| `-py310-none-linux_x86_64.tar.gz`（目录式） | 14 MB | `build_archives.py` | 只需 `python3` 3.10+，依赖在目录里 |
| `-py310-none-any.pyz` | 57 KB | `build_release.py` / `build_pyz.py` | 已装好依赖 |
| `-py310-none-<平台>.pyz` | 12–15 MB | `build_release.py` | 只需 `python3` 3.10+，按平台分发 |
| `-py310-none-any.tar.gz`（源码） | 57 KB | `build_archives.py` | Python 3.10+ 与 `pip install` |
| `xm-decrypt`（可执行） | 81 MB | `build_exe.py` | 无需 Python 环境 |

发布用 `build_release.py`（一次产出全部平台的 `.pyz` + 校验和清单）与
`build_archives.py`（目录式归档 + 源码包）。`build_pyz.py` 是二者的基础模块，用于构建单个包。

### 目录式归档 / 源码包

```bash
python tools/build_archives.py                 # 全部平台目录式 + 源码包
python tools/build_archives.py --native-only   # 只打本机平台
python tools/build_archives.py --only win_amd64 macosx_11_0_arm64
python tools/build_archives.py --skip-dir      # 只出源码包
```

平台表与产物命名沿用 `build_release.py`，一次产出六份：五个平台的目录式归档
（Windows 目标为 `.zip`，其余 `.tar.gz`）加一份与平台无关的源码包：

```
dist/xm-decrypt-0.1.0-py310-none-linux_x86_64.tar.gz
dist/xm-decrypt-0.1.0-py310-none-linux_aarch64.tar.gz
dist/xm-decrypt-0.1.0-py310-none-win_amd64.zip
dist/xm-decrypt-0.1.0-py310-none-macosx_11_0_arm64.tar.gz
dist/xm-decrypt-0.1.0-py310-none-macosx_10_13_x86_64.tar.gz
dist/xm-decrypt-0.1.0-py310-none-any.tar.gz
```

本机平台的依赖从已安装的 site-packages 取，其余平台用
`pip download --platform ... --only-binary=:all:` 拉对应 wheel 解压成 `_vendor/`，
并在归档中校验各平台的原生库标记（`wasmtime/linux-x86_64/_libwasmtime.so` 等），
缺失即中止。归档内容为单一目录：

```
xm-decrypt-0.1.0/
├── xm-decrypt            启动器：检查解释器版本、把 _vendor 挂到 PYTHONPATH、再 exec main.py
├── main.py
├── xm_encryptor.wasm
├── xm_decrypt/           代码
├── _vendor/              第三方依赖，和 .pyz 内嵌的是同一份
├── README.md
└── requirements.txt
```

与 `.pyz` 的唯一区别是依赖的存放方式：`.pyz` 首次运行时将 `_vendor/` 解压至
`~/.cache/xm-decrypt/libs-<哈希>/`，目录式归档则**就地加载**，不写用户家目录，也不产生缓存。
启动器在执行前校验 `sys.version_info >= (3, 10)`，不满足时输出明确的版本提示。

源码包不含 `_vendor/`，用之前需要 `pip install -r requirements.txt`。

### 单文件 .pyz（含内置依赖）

```bash
python tools/build_pyz.py --with-deps     # → dist/xm-decrypt-standalone.pyz
```

```bash
python xm-decrypt-standalone.pyz              # TUI
python xm-decrypt-standalone.pyz --cli -h     # 命令行
```

**`.pyz` 是 zip，无法直接 import 原生扩展**（`wasmtime/_libwasmtime.so`、`Crypto/**/*.so`），
因此内嵌依赖需在首次运行时解压至缓存并加入 `sys.path`：

- 依赖放在归档的 `_vendor/`，入口 `__main__.py` 先调用 `_xm_vendor.install()`；
- 解压目标为 `~/.cache/xm-decrypt/libs-<pyz 的 sha256 前 16 位>/`，归档内容变化时目录随之变化，避免读到不一致的依赖；
- 解压采用临时目录 + 原子改名，多进程同时首次启动不会冲突；家目录不可写时退化为进程级临时目录；
- 首次运行约 7 秒（解压 54 MB），后续启动不足 1 秒。

已在**未安装任何第三方依赖**的系统 Python 3.12 上实测：解密产物 sha256 `c5ebb5d1…` 与源码运行一致，
`-j 2` 并行正常，TUI 渲染出的样式规则数仍是 108。

### 精简版 .pyz

```bash
python tools/build_pyz.py                  # → dist/xm-decrypt.pyz（53 KB）
```

只含 `main.py`、`xm_decrypt/`、`styles.tcss` 和 `xm_encryptor.wasm`，**不含第三方依赖**。
zipapp 仅将代码打包为 zip，而 `wasmtime`、`pycryptodome` 属于带 `.so` 的原生扩展，无法从 zip 直接导入。
更换机器前仍需 `pip install -r requirements.txt`；依赖缺失时程序会列出所需包名。

两种 `.pyz` 共用的两项实现约束：

- **wasm 必须打进归档**。`wasm.py` 先用磁盘候选路径找 `xm_encryptor.wasm`，找不到就通过 zipimporter 的 `archive` 属性从归档内部读字节，交给 `wasmtime.Module(engine, bytes)`。因此单独分发 `.pyz` 时无需附带 wasm 文件。
- **样式不能再用 `CSS_PATH`**。Textual 会用 `inspect.getfile()` 拼出 `.../xm-decrypt.pyz/xm_decrypt/tui/styles.tcss` 这种磁盘上不存在的路径。磁盘上存在该文件时仍使用 `CSS_PATH`（保留开发期热重载）；打包运行时改为从归档读取文本注入 `CSS`。两种方式加载的样式规则数都是 108 条，外观一致。

### 发行版（多平台）

```bash
python tools/build_release.py            # 全部平台
python tools/build_release.py --native-only    # 只打本机
```

产物命名沿用 wheel 的 tag 风格 `xm-decrypt-<版本>-py310-none-<平台>.pyz`
（`py310` = 要求 Python 3.10+，见前面的「环境要求」）：

| 文件 | 平台 | 大小 |
| --- | --- | --- |
| `...-py310-none-any.pyz` | 通用（纯 Python） | 57 KB |
| `...-py310-none-linux_x86_64.pyz` | Linux x86-64 | 14.6 MB |
| `...-py310-none-linux_aarch64.pyz` | Linux ARM64 | 13.2 MB |
| `...-py310-none-win_amd64.pyz` | Windows x64 | 11.9 MB |
| `...-py310-none-macosx_11_0_arm64.pyz` | macOS Apple Silicon | 12.1 MB |
| `...-py310-none-macosx_10_13_x86_64.pyz` | macOS Intel | 12.8 MB |

同时生成 `dist/SHA256SUMS-<版本>.txt`，发布时一并附上。

**各平台须分别打包**：包内的 `wasmtime/linux-x86_64/_libwasmtime.so`、
`Crypto/Cipher/_ARC4.pyd` 都是按平台编译的二进制；而且 macOS 与 Linux 的 pycryptodome
扩展**同名**（都叫 `_ARC4.abi3.so`），装不进同一个包。

本机平台用已安装的依赖打包并实测；其它平台由脚本从 PyPI 下载对应 wheel 组装，
**只做了结构校验**（确认原生库文件名、架构目录正确），没有真机运行过。
构建日志会标注每个产物的验证级别（本机实测 / 仅结构校验），后者不应视为已验证。

交叉打包的已知限制：macOS Intel 必须使用 `macosx_10_13_x86_64`（wasmtime 提供的最低版本）。
写成 `macosx_10_9_x86_64` 时 pip 无法匹配，会回退到标记为 `any` 但仅含 Windows DLL 的无效包，
产物在 Mac 上必然启动失败。脚本因此内置原生库存在性校验，缺失时直接报错终止。

### 免依赖可执行程序

```bash
python tools/build_exe.py     # 输出 dist/xm-decrypt
./xm-decrypt                  # 直接运行，不需要 Python 环境
```

使用 PyInstaller onefile 打包，内置解释器、`wasmtime` 原生库与 Textual，可在同架构 Linux 上直接运行。构建时需显式处理两点：

- `wasmtime` 的原生库 `_libwasmtime.so` 是运行时用 `ctypes` 按路径加载的，PyInstaller 的 `--collect-all` **不会**把它收进归档，必须 `--add-binary` 显式指定。遗漏时启动阶段会报 `cannot open shared object file`。
- 冻结后多进程 spawn 会重新执行自身，入口处必须调用 `multiprocessing.freeze_support()`（非冻结环境是空操作）。

脚本结束前会自动执行一次 `--cli -h` 自检，确认依赖已打入归档。

## 注意事项
请确保你拥有合法的 xm 文件下载和转换权限。
仅限于学习交流使用，严禁商业使用，本工具作者不负任何其他责任。
转换过程中可能会占用较多系统资源，建议在空闲时间进行批量操作。
