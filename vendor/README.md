# Vendored Dependencies

本目录包含项目内嵌的第三方依赖源码，避免依赖系统级 pip 安装。

## CloakBrowser v0.3.31

- **来源**: https://github.com/CloakHQ/CloakBrowser
- **许可证**: MIT License (Copyright (c) 2026 CloakHQ)
- **用途**: 提供反检测 Chromium 浏览器，用于绕过 Cloudflare 反爬验证
- **依赖**: `httpx`、`playwright`（仍需通过 pip 安装）

### 更新方法

```bash
pip install --upgrade cloakbrowser
# 然后将新版本源码复制到 vendor/cloakbrowser/
```

源码位于 Python site-packages 的 `cloakbrowser/` 目录中。
