# linodl

`linodl` 是一个面向 linovelib.com / 哔哩轻小说的命令行下载工具，用于搜索小说、解析目录、下载分卷章节，并将本地章节导出为 EPUB。

## 功能

- 通过关键词搜索小说。
- 通过目录 URL 批量下载指定分卷。
- 支持章节正文、插图章节和正文内插图。
- 下载后可校验缺章、空章、截断章节和缺失图片。
- 支持将已下载的分卷导出为 EPUB。
- 使用 Playwright / CloakBrowser 处理 Cloudflare 验证和反爬页面。
- 支持交互式菜单和命令行批处理两种模式。

## 安装

需要 Python 3.12 或兼容版本。

```powershell
cd linodl-app
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## 使用

### React desktop UI

Install the Python and frontend dependencies, then build and start the default desktop UI:

```powershell
pip install -r requirements.txt
Set-Location frontend
npm install
npm run build
Set-Location ..
python -m linodl --gui
```

For frontend development only, set `LINODL_FRONTEND_URL=http://localhost:5173`
and launch `python -m linodl --gui --debug` while Vite is running. Production
launches use the built `frontend/dist` assets.

`python -m linodl --legacy-gui` remains available as a temporary fallback to
the CustomTkinter interface.

### Windows EXE

在项目根目录双击 `build_exe.bat`，或在 PowerShell 中运行：

```powershell
.\build_exe.bat
```

构建完成后，可直接运行 `release\linodl\linodl.exe`。发布时请复制整个
`release\linodl` 目录；首次使用 CloakBrowser 时，浏览器内核会下载到当前
Windows 用户的 `.cloakbrowser` 缓存目录。

交互式模式：

```powershell
python -m linodl
```

搜索小说：

```powershell
python -m linodl --search "小说关键词"
```

按目录 URL 下载：

```powershell
python -m linodl --url "https://www.linovelib.com/novel/2139/catalog" --volumes 1,2 --no-login
```

指定输出目录：

```powershell
python -m linodl --url "https://www.linovelib.com/novel/2139/catalog" --output-dir novel_output
```

预热 Cloudflare 验证：

```powershell
python -m linodl --warmup-cloudflare
```

## 账号与安全

程序会把交互式输入的站点账号配置保存到用户目录下的本机配置文件中，不应提交到 Git 仓库。

本仓库的 `.gitignore` 已排除常见缓存、下载结果、调试页面和环境变量文件：

- `.env*`
- `.pytest_cache/`
- `__pycache__/`
- `novel_output/`
- `smoke_empty_5105/`
- `debug_*.html`

请不要把真实账号、密码、cookie、token 或浏览器 profile 提交到 GitHub。

## 测试

```powershell
python -m pytest -q
python -m compileall -q linodl tests
```

## 目录结构

```text
linodl/
  cli/        交互式菜单和批处理入口
  config/     本机配置管理
  core/       搜索、目录解析、下载、EPUB 导出、浏览器会话
  models/     数据模型
tests/        单元测试和回归测试
docs/         调试记录和设计说明
```

## 说明

本项目仅用于个人学习和备份场景。使用时请遵守目标网站规则、版权要求和当地法律法规。
