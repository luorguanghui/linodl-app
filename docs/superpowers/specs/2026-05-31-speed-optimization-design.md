# linodl 性能优化与搜索修复 设计文档

日期：2026-05-31

## 目标

1. 修复搜索返回大量无关结果的问题
2. 大幅提升下载速度（200章小说从 ~15分钟 → ~2-3分钟）
3. 浏览器操作在后台无头运行，仅在人工验证时才弹出窗口

---

## 一、搜索过滤修复（Bug）

**根因：** `search()` 方法中，`_try_browser_form()` 和 `_try_cloudscraper_post()` 返回 HTML 解析后，没有调用 `_filter_results_by_keyword()` 过滤。而 `_try_browser_direct()` 和 `_try_public_listing_pages()` 正确调用了过滤。

**修复：** `search.py` 第 32-41 行，解析结果后增加 `_filter_results_by_keyword()` 调用。

---

## 二、延迟削减

所有延迟参数调整（可覆盖配置）：

| 位置 | 文件 | 当前值 | 优化后 |
|---|---|---|---|
| 章节间延迟 (`_delay`) | downloader.py | 2.0-3.5s | **0.3-1.0s** |
| `_load_page` 硬等 | downloader.py | 1.5s | 移除，用 `wait_for_load_state("domcontentloaded")` |
| 翻页延迟 | downloader.py | 1.5-2.5s | **0.3-0.6s** |
| 换卷延迟 | downloader.py | 3-5s | **0.5-1.0s** |
| 错误重试延迟 | downloader.py | 5-8s | **2-3s** |
| 搜索导航后硬等 | search.py | 5s | 移除（已有 networkidle 等待） |
| 搜索重试循环 | search.py | 5×1s | **3×0.5s** |
| 登录提交后等待 | auth.py | 3s+1.2s+0.5s | **0.5s+0.3s+0.5s** |
| CF 挑战初始等待 | browser.py | 3s sleep | 移除，用 `wait_for_load_state` |
| CF 轮询间隔 | browser.py | 2s | **1s** |

---

## 三、并行下载

### 3.1 图片并行下载

`downloader.py` 中插图章节图片使用 `ThreadPoolExecutor(max_workers=5)` 并行下载。
图片下载使用 HTTP（urllib/context.request），不涉及 Playwright greenlet API，线程安全。

> **注意：** 章节下载保持串行。章节下载依赖 Playwright sync API (greenlet)，不能跨线程。
> 搜索的公开列表页抓取也保持串行，因为其内部可能回退到浏览器。

---

## 四、浏览器后台运行修复

`browser.py` 中 `_start_cloak()` 不再通过 `_prefer_cloak_headed` 强制可见窗口：
- `headless=True` 时 CloakBrowser 保持无头
- 仅在 Cloudflare 挑战进入用户交互等待阶段（`wait_for_challenge_clear`）时，才临时开可见窗口

---

## 五、涉及文件

| 文件 | 改动内容 |
|---|---|
| `linodl/core/search.py` | 过滤修复 + 延迟优化 |
| `linodl/core/downloader.py` | 延迟削减 + 并行图片下载 |
| `linodl/core/browser.py` | 后台运行修复 + 延迟优化 |
| `linodl/core/auth.py` | 延迟削减 |
| `linodl/config/manager.py` | 默认延迟值调整 |

---

## 六、验证方案

```powershell
# 1. 单元测试
python -m pytest -q

# 2. 编译检查
python -m compileall -q .

# 3. 搜索功能测试（验证过滤修复 + 速度）
python -m linodl --search "义妹" --debug --anti-bot playwright

# 4. 目录解析 + 下载测试（验证速度提升）
python -m linodl --url https://www.linovelib.com/novel/5105/catalog --volumes 1 --no-login

# 5. 浏览器后台运行验证
python -m linodl --search "无止尽的冬天" --debug --anti-bot cloak
# 确认：不应弹出可见窗口（除非遇到 Cloudflare 挑战）
```

## 2026-06-01 状态更新

本设计中的搜索过滤、延迟削减和图片并行下载已经完成并进入当前代码基线。后续下载稳定性的重点已经从“尽快读取正文”调整为“等正文脚本稳定后再按浏览器渲染顺序提取正文”。

章节乱序修复结论：

- 正文页必须给站点脚本一个稳定窗口，否则可能读到 `#TextContent` 的中间态。
- 仅等待还不够，部分章节页存在 DOM 顺序混淆，需要按渲染后的字符行位置重建文本顺序。
- 章节下载仍保持串行，因为 Playwright sync API 不适合跨线程共享；并行优化目前只用于插图下载。
- 已下载过的错误 txt 不会自动覆盖，需要删除后重新下载。

当前验证基线：

```text
python -m pytest -q
22 passed

python -m compileall -q linodl tests
passed
```
