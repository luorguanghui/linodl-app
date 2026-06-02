# linodl 搜索与 Cloudflare 问题交接文档

日期：2026-05-30  
项目目录：`C:\Users\123\Desktop\codex_temp\linodl-app`

## 当前结论

当前应用已经具备基本下载、目录解析、搜索兜底和 CloakBrowser 接入，但“直接站内搜索”仍未彻底解决。

用户最新遇到的问题是：

```text
[browser] cloudflare_retry: please complete verification in the CloakBrowser window (search-home)
```

程序会打开可见 CloakBrowser 并等待用户完成 Cloudflare 人机验证，但实际体验仍卡在验证页，后续不会稳定进入搜索结果页。这说明当前 CloakBrowser 只是被接入为浏览器外壳，还没有把“验证完成后的导航状态、cookie 持久化、重提搜索、失败恢复”完整打通。

另一个问题是：此前为了绕过 `/S6/` 搜索接口被 Cloudflare 挡住，加入了“榜单/入库列表扫描”兜底。它可以搜到例如《无止尽的冬天，毁坏的梦之国》这类近期入库作品，但不是完整搜索方案；如果作品不在扫描范围内，仍会搜不到。

## 项目结构

主要入口和模块：

- `run.bat`  
  Windows 启动脚本，安装依赖后运行 `python -m linodl %*`。

- `requirements.txt`
  当前包含 `cloudscraper`、`playwright`、`httpx`、`rich`、`ebooklib`、`pytest`。
  CloakBrowser 已内嵌至 `vendor/cloakbrowser/`，无需单独安装。

- `linodl/__main__.py`  
  批处理 CLI 入口。支持：
  - `--search <关键词>`
  - `--url <目录URL>`
  - `--volumes <1,3,5>`
  - `--output-dir <目录>`
  - `--no-login`
  - `--headed`
  - `--anti-bot auto|playwright|cloak`
  - `--proxy <URL>`

- `linodl/cli/app.py`  
  Rich 交互式 CLI，负责菜单、配置、搜索选择、下载流程和 EPUB 导出入口。

- `linodl/config/manager.py`  
  配置文件管理，默认写入 `~/.linovelib.ini`。新增配置：
  - `[download] anti_bot_mode = auto | playwright | cloak`
  - `[download] profile_dir = ~/.linodl-browser`
  - `[network] proxy =`
  - `[network] geoip = false`

- `linodl/core/browser.py`  
  统一浏览器层，当前负责：
  - 普通 Playwright 持久化 context
  - CloakBrowser 持久化 context
  - Cloudflare challenge HTML 检测
  - 遇到 challenge 时切换到可见 CloakBrowser
  - 打印提示并等待用户完成验证

- `linodl/core/search.py`  
  搜索引擎。当前策略顺序：
  1. 使用浏览器提交首页搜索表单 `/S6/`
  2. 使用 `cloudscraper` POST `/S6/`
  3. 从排行榜页做标题匹配
  4. 从公开入库列表页做标题匹配
  5. Bing site search 兜底

- `linodl/core/catalog.py`  
  目录页抓取和解析。目录页比 `/S6/` 更容易抓取，目前 `https://www.linovelib.com/novel/5105/catalog` 可解析成功。

- `linodl/core/downloader.py`  
  章节和插图下载。正文通过浏览器 page 获取，图片优先通过 Playwright/CloakBrowser 的 `context.request` 获取以复用 cookie。

- `linodl/core/auth.py`  
  登录逻辑。已接入共享浏览器 session。

- `linodl/core/epub.py`  
  从下载目录导出 EPUB。

- `linodl/models/novel.py`  
  数据模型：`NovelInfo`、`Volume`、`Chapter`、`DownloadResult`。

- `tests/`  
  当前有 `pytest` 覆盖：
  - Cloudflare 检测
  - 图片 URL 提取
  - 目录解析
  - 配置默认值
  - 搜索结果过滤和列表页解析

## 已完成的改动

1. 统一浏览器层
   - 新增 `BrowserSession`。
   - 默认使用 Playwright。
   - 检测 Cloudflare 后可切换 CloakBrowser。
   - CloakBrowser 使用持久 profile：`~/.linodl-browser/cloak`。
   - 自动兜底时使用可见窗口，方便用户点击验证。

2. 搜索修正
   - 修掉“无论搜什么都返回同一份榜单”的 bug。
   - 榜单页不再无条件返回前 30 个结果，只返回标题匹配项。
   - 直接站内搜索已经调整为第一策略。
   - 入库列表扫描只作为兜底。
   - 《无止尽的冬天，毁坏的梦之国》可通过公开入库列表搜到，ID 为 `5105`。

3. 下载修正
   - 章节正文通过浏览器上下文获取。
   - 图片下载复用浏览器 context request。
   - 输出失败章节 URL。
   - EPUB 兼容新旧插图目录名。

4. 安全修正
   - `download_novel.py` 中原先的硬编码账号密码已移除，改为只读 `LINOVELIB_USER` / `LINOVELIB_PASS` 环境变量。

## 当前可复现命令

基础测试：

```powershell
cd C:\Users\123\Desktop\codex_temp\linodl-app
python -m pytest -q
python -m compileall -q .
```

已验证通过：

```powershell
python -m linodl --search "无止尽的冬天" --debug --anti-bot playwright
```

当前输出可返回：

```text
[1] 无止尽的冬天，毁坏的梦之国 (ID: 5105) 作者: 八目迷
```

目录解析已验证通过：

```powershell
python -m linodl --url https://www.linovelib.com/novel/5105/catalog --volumes 999 --no-login
```

当前问题复现：

```powershell
python -m linodl --search "<某些触发 Cloudflare 的搜索词>" --debug
```

可能输出：

```text
[browser] cloudflare_retry: opening visible CloakBrowser (search-home)
[browser] cloudflare_retry: please complete verification in the CloakBrowser window (search-home)
```

之后程序仍可能等待到超时或搜索失败。

## 根因分析

### 1. CloakBrowser 不是验证码自动求解器

CloakBrowser 的作用是提供更接近真实用户的 Chromium 指纹、持久化 profile、人类化输入等能力。它不能保证自动通过 Cloudflare 的点击验证。

所以正确使用方式应该是：

1. 第一次遇到 Cloudflare 时打开可见 CloakBrowser。
2. 用户手动点击验证。
3. 程序检测 challenge 消失。
4. 保存 cookie/localStorage 到持久 profile。
5. 回到原始目标页或重新提交搜索表单。
6. 之后复用同一 profile，尽量不再触发验证。

当前代码只完成了 1、2、部分 3；第 4-6 步不够可靠。

### 2. `/S6/` 搜索接口是重点拦截对象

实测：

- 首页和榜单页较容易访问。
- 小说详情页和目录页较容易访问。
- `/S6/` 搜索结果页经常直接返回 Cloudflare challenge。
- `/wenku/` 类列表页也可能被 challenge。

因此，直接搜索必须能处理：

- 首页无 challenge，但提交后 `/S6/` challenge。
- 首页就 challenge。
- challenge 通过后停在中间页，没有自动回到 `/S6/`。
- challenge 通过后 cookie 有效，但当前 page 内容仍是旧 challenge，需要重新导航或重提搜索。

### 3. 当前等待逻辑还不够强

`BrowserSession.wait_for_challenge_clear()` 当前只轮询 `page.content()` 判断 challenge 是否消失。问题是：

- Cloudflare 页面可能长时间保留标题/脚本，即使 cookie 已更新。
- 用户点击验证后可能需要重新加载原目标 URL。
- 当前搜索代码有重提表单逻辑，但没有明确保存“原始动作”并在验证后强制重放。
- 如果验证窗口没有真正通过，程序只能等待，无法自动解决。

## 下次继续的建议方案

### 优先方案：把搜索动作封装成可重放任务

在 `linodl/core/search.py` 中不要只写“一次性提交表单”，而是做成：

```text
perform_search(keyword):
  open_home()
  submit_form(keyword)
  wait_result_or_challenge()
  if challenge:
    ensure_cloak_headed()
    wait_user_verification()
    reload_home()
    submit_form(keyword) again
    wait_result()
```

关键是：验证通过后必须重新执行搜索动作，而不是继续读取 challenge 页。

### 浏览器层需要新增的接口

建议在 `linodl/core/browser.py` 增加：

- `ensure_cloak(reason) -> bool`
  - 如果不是 CloakBrowser，切换到可见 CloakBrowser。

- `wait_for_access(url, reason, timeout_ms=300000) -> bool`
  - 导航到目标 URL。
  - 如果 challenge，等待人工验证。
  - 验证后重新打开目标 URL。
  - 直到页面不再是 challenge。

- `run_with_challenge_retry(action, reason) -> result`
  - action 是一个可重放函数。
  - 如果 action 结果是 challenge，切 CloakBrowser、等验证、再执行 action。

### 搜索层建议改造

在 `linodl/core/search.py` 中：

- 保留当前顺序：
  1. 直接站内搜索
  2. HTTP 搜索
  3. 榜单标题匹配
  4. 入库列表扫描
  5. Bing 兜底

- 直接站内搜索需要改为：
  - 优先用 CloakBrowser profile 中已有 cookie。
  - 如果 `anti_bot_mode=auto` 且 `/S6/` challenge，切可见 CloakBrowser。
  - 等用户验证后，重新打开首页并重新提交搜索。
  - 如果搜索结果页仍 challenge，给出明确提示：验证未完成或 Cloudflare 拦截仍在。

### 用户体验建议

终端提示应更明确，例如：

```text
Cloudflare 验证已在 CloakBrowser 窗口打开。
请在浏览器里完成“验证您是真人”。
完成后不要关闭浏览器窗口，程序会自动继续。
最长等待 5 分钟。
```

如果超时：

```text
Cloudflare 验证仍未通过。
你可以重新运行命令，已保存的 CloakBrowser profile 会继续复用：
C:\Users\123\.linodl-browser\cloak
```

### 可选增强：增加手动预热命令

新增命令：

```powershell
python -m linodl --warmup-cloudflare
```

行为：

1. 打开可见 CloakBrowser 到 `https://www.linovelib.com/`。
2. 如果出现验证，等待用户完成。
3. 再访问 `/S6/` 或搜索一个测试词。
4. 保存 profile。
5. 提示用户下次搜索会复用该 profile。

这比在搜索流程中临时处理验证更直观。

## 重要文件状态

建议下次优先看这些文件：

1. `linodl/core/browser.py`
   - 当前 Cloudflare 检测和 CloakBrowser 使用都在这里。
   - 重点看 `restart_with_cloak()` 和 `wait_for_challenge_clear()`。

2. `linodl/core/search.py`
   - 当前搜索策略和 `/S6/` 表单提交都在这里。
   - 重点看 `_try_browser_form()`、`_open_search_home()`、`_submit_search_form()`、`_content_after_navigation()`。

3. `linodl/__main__.py`
   - 如果要加 `--warmup-cloudflare`，从这里加批处理参数。

4. `linodl/cli/app.py`
   - 如果要在交互菜单里加“预热 Cloudflare 验证”，从设置或主菜单加。

5. `tests/test_search.py`
   - 已有搜索顺序、标题过滤、入库列表解析测试。
   - 下次应新增“challenge 后重放搜索动作”的测试。

## 当前测试基线

最后一次已通过：

```text
python -m pytest -q
11 passed

python -m compileall -q .
passed
```

如果下次改搜索/浏览器层，至少跑：

```powershell
python -m pytest -q
python -m compileall -q .
python -m linodl --search "无止尽的冬天" --debug --anti-bot playwright
```

如果要验证 CloakBrowser：

```powershell
python -m linodl --search "无止尽的冬天" --debug --anti-bot auto
```

注意：该命令可能打开可见 CloakBrowser 并等待人工验证，不能作为无人值守测试。

## 2026-06-01 项目状态更新

项目已经初始化为 Git 仓库，并推送到私有 GitHub 仓库：

```text
https://github.com/luorguanghui/linodl-app
```

仓库目前包含源码、测试和文档；生成的下载内容、缓存、调试 HTML、虚拟环境和 `.env` 类文件已通过 `.gitignore` 排除。不要把账号、密码、cookie、token 或浏览器 profile 写入仓库。

当前功能状态：

- CLI、交互式下载、搜索、目录解析、章节下载、插图下载和 EPUB 导出已经可用。
- 搜索的 Cloudflare 问题仍属于外部站点拦截风险；CloakBrowser 能保存和复用浏览器状态，但不能自动解决验证码。
- 章节 txt 乱序问题已经修复：下载器会等待 `#TextContent` 被站点脚本重排稳定，然后按浏览器实际渲染出来的字符行位置重建正文顺序，避免直接使用混淆后的 DOM 顺序。
- 问题样例页 `https://www.linovelib.com/novel/2139/209975_3.html` 已用于手动验收，关键段落顺序已恢复。
- 已下载过的旧乱序 txt 不会自动改写；需要删除对应章节文件后重新下载。

当前测试基线已更新为：

```text
python -m pytest -q
22 passed

python -m compileall -q linodl tests
passed
```
