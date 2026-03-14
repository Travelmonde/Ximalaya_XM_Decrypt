<h1 align="center">喜马拉雅xm文件解密工具</h1>
<h4 align="center">Ximalaya-XM-Decrypt</h4>

### 说明

由于喜马拉雅官方客户端下载的音频文件为加密格式，无法在普通播放器中播放，所以我写了这个小工具来解密喜马拉雅下载的音频文件。本工具参考@aynakeya的[博文](https://www.aynakeya.com/2023/03/15/ctf/xi-ma-la-ya-xm-wen-jian-jie-mi-ni-xiang-fen-xi/)，并加入了批量解密的功能。我还写了一个程序[Ximalaya-Downloader](https://github.com/Diaoxiaozhang/Ximalaya-Downloader)，用于直接爬取未加密的喜马拉雅音频文件。本工具作为Ximalaya-Downloader的补充，当每日下载vip音频达到上限时，可以使用客户端下载加密的xm文件并使用本工具解密。

在使用该软件时，请确保xm_encryptor.wasm文件与主程序文件处在同一目录下，最好是一个单独的文件夹。


喜马拉雅xm文件转mp3/m4a工具
简介
本开源项目提供了一个简单易用的工具，用于将喜马拉雅的xm文件转换为mp3或m4a格式，并支持批量转换和批量下载。无论你是需要将单个文件转换，还是需要处理大量文件，本工具都能满足你的需求。

功能特点
批量转换：支持一次性转换多个xm文件为mp3或m4a格式。
批量下载：支持从喜马拉雅平台批量下载xm文件，并自动转换为所需格式。
格式支持：支持将xm文件转换为mp3或m4a格式，满足不同设备和播放器的需求。
使用方法
克隆仓库：首先，克隆本仓库到你的本地环境。
git clone https://github.com/your-repo-url.git

安装依赖：进入项目目录，安装所需的依赖包。
cd your-repo-directory
pip install -r requirements.txt

运行工具：根据需要运行相应的脚本进行文件转换或下载。
python convert_xm_to_mp3.py

注意事项
请确保你拥有合法的xm文件下载和转换权限。
转换过程中可能会占用较多系统资源，建议在空闲时间进行批量操作。
