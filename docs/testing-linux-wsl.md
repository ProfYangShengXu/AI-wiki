# 使用 Linux/WSL 运行测试

当前 Windows 助手环境无法执行 shell，但项目已经准备好 Linux/WSL 测试脚本。

## 1. 确认 WSL

在 Windows PowerShell 或 CMD 中执行：

```powershell
wsl -l -v
```

如果未安装：

```powershell
wsl --install -d Ubuntu
```

安装后重启电脑，Ubuntu 首次启动时设置用户名和密码。

## 2. 进入项目目录

在 WSL 中：

```bash
cd /mnt/c/Users/45140/OneDrive/Desktop/code/AIwiki2.0
```

> 建议把项目复制到 Linux 文件系统，避免 OneDrive/`/mnt/c` 的 IO 开销：
>
> ```bash
> mkdir -p ~/code
> cp -r /mnt/c/Users/45140/OneDrive/Desktop/code/AIwiki2.0 ~/code/AIwiki2.0
> cd ~/code/AIwiki2.0
> ```

## 3. 安装测试环境

```bash
bash scripts/linux_setup.sh
```

该脚本会：

- 安装 Python、venv、pip、Tesseract OCR
- 创建 `.venv-linux`
- 安装 `requirements.txt`
- 下载前端 vendor 资源

## 4. 运行测试

快速测试（推荐）：

```bash
bash scripts/run_tests_linux.sh
```

全量测试：

```bash
bash scripts/run_tests_linux.sh full
```

## 5. 启动服务（可选）

```bash
.venv-linux/bin/python main.py
```

浏览器打开 `http://127.0.0.1:8000`。

## 常见问题

| 问题 | 处理 |
| --- | --- |
| `wsl` 不是内部或外部命令 | 管理员 PowerShell 运行 `wsl --install -d Ubuntu` |
| apt 下载慢 | 更换 Ubuntu 软件源或配置代理 |
| 测试访问不到 Windows 后端 | 在 WSL 中直接启动 Linux 后端，或使用 Windows 宿主 IP |
| sentence-transformers 下载慢 | 提前在 Windows 侧准备模型缓存，或设置 HF 镜像 |
