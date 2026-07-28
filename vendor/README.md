# Vendored dependencies

本目录保存项目内嵌的第三方 Python 源码，使应用不依赖系统中偶然安装的同名包。

## CloakBrowser 0.5.2

- 上游项目：<https://github.com/CloakHQ/CloakBrowser>
- 同步来源：PyPI 官方 `cloakbrowser==0.5.2` wheel
- Python 包目录：`vendor/cloakbrowser/`
- 许可证：MIT，完整文本见 `vendor/LICENSE.cloakbrowser`
- Python 运行依赖：`cryptography`、`httpx`、`playwright`
- GeoIP/SOCKS 依赖：`geoip2`、`socksio`

项目通过 `linodl/core/browser.py` 将 `vendor/` 放到导入路径最前方，因此 `pip install -U cloakbrowser` 不会直接更新应用实际使用的包装层。

### Chromium 构建策略

未提供合法的 CloakBrowser 授权密钥时，应用继续使用上游公开可用的 Chromium 146 构建。应用不会写入、生成或代替用户获取授权密钥，也不会自动切换到需要授权的 Pro 构建。

### 同步方法

1. 从 PyPI 下载指定版本的官方 wheel。
2. 核对 wheel metadata 中的版本、依赖和许可证。
3. 只同步 wheel 内的 `cloakbrowser/**/*.py`，不复制缓存、浏览档案或二进制。
4. 更新本说明和 `vendor/LICENSE.cloakbrowser`。
5. 运行浏览器辅助测试与 `about:blank` 冒烟检查。
