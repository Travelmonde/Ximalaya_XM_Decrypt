<h1 align="center">喜马拉雅xm文件解密工具</h1>
## 说明
本工具用于解密喜马拉雅官方客户端下载的加密音频文件，本工具在[sld272](https://github.com/sld272/Ximalaya-XM-Decrypt.git)工作基础上进行维护工作，包括修复bug,替换老旧的库并且增加多核支持。具体解密原理请详阅@aynakeya的[博文](https://www.aynakeya.com/2023/03/15/ctf/xi-ma-la-ya-xm-wen-jian-jie-mi-ni-xiang-fen-xi/)。

在使用该软件时，请确保xm_encryptor.wasm文件与主程序文件处在同一目录下。

目前该工具已在Mac os 26.3和python 3.10中测试通过

## 简介

本开源项目提供了一个简单易用的工具，用于将喜马拉雅的xm解密并输出为其原本对应的音频格式(.mp3，.aac，.flac，etc.)。支持批量转换并且提供多核优化

无论你是需要将单个文件转换，还是需要处理大量文件，本工具都能满足你的需求。

### 功能特点
- 批量转换：支持一次性转换多个 xm 文件  
- 多核优化：支持多核并行处理（max 8 cores）  
- 格式支持：支持包括 mp3、aac、flac 在内的多种无损或有损格式. 对于 wav 格式，本工具提供转码为 alac 无损格式以减小体积


## 使用方法
> ⚠️ 需要 Python 3.10
### 1. 克隆仓库
```bash
git clone https://github.com/Travelmonde/Ximalaya_XM_Decrypt.git
```
### 2. 进入项目目录
在本地文件夹打开Terminal (Mac)或者cmd（windows）
```bash
cd Ximalaya-XM-Decrypt
```
### 3. 安装所需的依赖包
安装依赖：进入项目目录，安装所需的依赖包。
```bash
pip install -r requirements.txt
```
### 4. 运行工具
```bash
python main_parallel.py
```

## 注意事项
请确保你拥有合法的xm文件下载和转换权限。
仅限于学习交流使用，严禁商业使用，本工具作者不负任何其他责任。
转换过程中可能会占用较多系统资源，建议在空闲时间进行批量操作。
