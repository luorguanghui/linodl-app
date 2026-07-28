# Linodl 阅读工作台与 CloakBrowser 可靠性实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 CustomTkinter 桌面端改造成连续的阅读工作台，并修复 CloakBrowser 验证误判、不可见人工验证、档案并发和参数配置问题。

**Architecture:** 核心浏览器层负责页面状态判断、启动参数和档案租约；GUI 服务层负责可见验证与任务状态；界面层只消费线程安全的任务事件。现有搜索、目录、下载、校验和导出逻辑继续复用，通过统一工作台和任务中心组织。

**Tech Stack:** Python 3.12、CustomTkinter、Playwright、vendored CloakBrowser、pytest、threading/queue。

## Global Constraints

- 不实现验证码自动破解或绕过。
- 保留现有配置字段、下载目录和浏览档案；新增配置必须有安全默认值。
- 默认下载可以无头运行，确认遇到验证页时必须改用可见 CloakBrowser。
- 单独出现 `cdn-cgi/challenge-platform` 脚本不能判定为验证页。
- 启用 GeoIP 时不强制传入 `zh-CN` locale；无代理时禁用 GeoIP。
- CloakBrowser 不传自定义 `1920×1080` viewport，使用上游指纹默认值。
- 没有合法授权密钥时继续使用公开可用的 Chromium 构建。
- 不删除浏览档案、输出目录、已下载文件或用户已有的未提交修改。
- UI 控件只能在 Tk 主线程更新。
- 验收只运行完整单元测试、编译检查、主窗口启动和 `about:blank` 浏览器冒烟检查。

---

## 文件结构

- `linodl/core/browser.py`：页面状态判断、浏览器启动参数和会话生命周期。
- `linodl/core/profile_coordinator.py`：浏览档案的进程内互斥租约。
- `linodl/gui/tasks.py`：任务快照、状态机和线程安全任务存储。
- `linodl/gui/verification.py`：使用同一档案启动可见 CloakBrowser 并复检目标页。
- `linodl/gui/workers.py`：后台任务、取消传播、任务事件和验证服务接入。
- `linodl/gui/widgets/task_center.py`：任务中心列表。
- `linodl/gui/widgets/workflow_steps.py`：连续步骤指示器。
- `linodl/gui/panels/workbench_panel.py`：统一搜索/URL 入口、最近档案和任务摘要。
- `linodl/gui/app.py`：新导航、面板组合和主线程事件分发。
- `linodl/gui/style.py`：阅读工作台的设计令牌。
- `linodl/gui/panels/settings_panel.py`：代理、GeoIP、主题和浏览档案状态。
- `linodl/config/manager.py`：兼容旧字段的批量配置写入。
- `vendor/cloakbrowser/`：同步经过校验的 CloakBrowser Python 包装层。
- `vendor/LICENSE.cloakbrowser`、`vendor/README.md`：许可证和版本来源说明。
- `tests/test_browser_helpers.py`：验证页判断与启动参数测试。
- `tests/test_profile_coordinator.py`：浏览档案租约测试。
- `tests/test_gui_tasks.py`：任务状态、取消和验证恢复测试。
- `tests/test_gui_helpers.py`：UI 路由、输入分类和任务中心辅助逻辑测试。

---

### Task 1: 修正验证页判断与 CloakBrowser 启动参数

**Files:**
- Modify: `linodl/core/browser.py`
- Modify: `tests/test_browser_helpers.py`

**Interfaces:**
- Produces: `ChallengeState(Enum)`，成员为 `NORMAL`、`CHALLENGE`、`UNKNOWN`。
- Produces: `assess_challenge(html: str | None) -> ChallengeState`。
- Preserves: `is_cloudflare_challenge(html: str | None) -> bool`，作为兼容包装。
- Produces: `BrowserSession._cloak_launch_kwargs() -> dict`。

- [ ] **Step 1: 写入验证误判和参数组合的失败测试**

```python
def test_generic_cloudflare_script_is_not_a_challenge():
    html = '<html><h1>正常作品页</h1><a href="/novel/1.html">作品</a><script src="/cdn-cgi/challenge-platform/x.js"></script></html>'
    assert assess_challenge(html) is ChallengeState.NORMAL


def test_blank_html_is_unknown():
    assert assess_challenge("") is ChallengeState.UNKNOWN


def test_cloak_geoip_omits_locale_and_requires_proxy(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setitem(
        sys.modules,
        "cloakbrowser",
        types.SimpleNamespace(
            launch_persistent_context=lambda path, **kwargs: captured.update(kwargs) or _LaunchContext()
        ),
    )
    BrowserSession(profile_dir=str(tmp_path), proxy="socks5://127.0.0.1:1080", geoip=True)._start_cloak()
    assert captured["geoip"] is True
    assert "locale" not in captured
    assert "viewport" not in captured
```

- [ ] **Step 2: 运行窄测试并确认失败**

Run: `python -m pytest -q tests/test_browser_helpers.py -k "generic_cloudflare or blank_html or cloak_geoip"`

Expected: FAIL，因为 `ChallengeState`、`assess_challenge` 尚未定义，且现有 kwargs 仍包含 locale/viewport。

- [ ] **Step 3: 实现三态判断和集中启动参数**

```python
class ChallengeState(str, Enum):
    NORMAL = "normal"
    CHALLENGE = "challenge"
    UNKNOWN = "unknown"


def assess_challenge(html: str | None) -> ChallengeState:
    if not html or not html.strip():
        return ChallengeState.UNKNOWN
    text = html.lower()
    strong = (
        "cf-browser-verify",
        "cf-challenge",
        "verify you are human",
        "checking your browser",
        "cf-turnstile",
    )
    if any(marker in text for marker in strong):
        return ChallengeState.CHALLENGE
    if "<html" in text or "<body" in text or "/novel/" in text:
        return ChallengeState.NORMAL
    return ChallengeState.UNKNOWN


def is_cloudflare_challenge(html: str | None) -> bool:
    return assess_challenge(html) is ChallengeState.CHALLENGE
```

`_cloak_launch_kwargs()` 返回 `headless`、稳定 fingerprint、`humanize` 和 `human_preset`；仅在 `proxy` 非空时添加 proxy，仅在 `proxy` 非空且 `geoip=True` 时添加 geoip；geoip 开启时不添加 locale。删除 CloakBrowser 的 viewport 参数，并让兼容重试只在异常信息明确指出 `humanize` 或 `human_preset` 不支持时执行。

- [ ] **Step 4: 运行浏览器辅助测试**

Run: `python -m pytest -q tests/test_browser_helpers.py`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add -- linodl/core/browser.py tests/test_browser_helpers.py
git commit -m "fix: harden browser challenge detection"
```

---

### Task 2: 增加浏览档案互斥租约

**Files:**
- Create: `linodl/core/profile_coordinator.py`
- Create: `tests/test_profile_coordinator.py`
- Modify: `linodl/core/browser.py`

**Interfaces:**
- Produces: `ProfileLeaseCancelled(RuntimeError)`。
- Produces: `BrowserProfileCoordinator.acquire(profile_path: str, cancel_event: threading.Event | None = None, wait_callback: Callable[[str], None] | None = None) -> ContextManager[None]`。
- Produces: module singleton `profile_coordinator`。
- Consumes: `BrowserSession._profile_path(engine: str) -> str`。

- [ ] **Step 1: 写入互斥、等待、取消和释放测试**

```python
def test_same_profile_waits_until_first_lease_releases(tmp_path):
    coordinator = BrowserProfileCoordinator(poll_interval=0.01)
    entered = threading.Event()

    def acquire_in_thread():
        with coordinator.acquire(str(tmp_path)):
            entered.set()

    with coordinator.acquire(str(tmp_path)):
        thread = threading.Thread(target=acquire_in_thread)
        thread.start()
        assert not entered.wait(0.05)
    assert entered.wait(0.2)
    thread.join(0.5)


def test_waiting_lease_can_be_cancelled(tmp_path):
    coordinator = BrowserProfileCoordinator(poll_interval=0.01)
    cancel = threading.Event()
    with coordinator.acquire(str(tmp_path)):
        cancel.set()
        with pytest.raises(ProfileLeaseCancelled):
            with coordinator.acquire(str(tmp_path), cancel_event=cancel):
                pass
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/test_profile_coordinator.py`

Expected: FAIL，因为模块尚不存在。

- [ ] **Step 3: 实现协调器**

使用 `threading.Condition` 和规范化后的绝对档案路径作为 key。等待循环每 `poll_interval` 检查取消事件，并最多调用一次 `wait_callback("等待浏览档案…")`。上下文管理器的 `finally` 从占用集合移除路径并 `notify_all()`。

- [ ] **Step 4: 让 BrowserSession 生命周期持有租约**

`BrowserSession.__init__` 新增 `cancel_event=None` 和 `profile_wait_callback=None`。`start()` 在启动具体引擎前获取对应档案租约；`close()` 在浏览器上下文关闭后释放租约。启动异常也必须释放租约。

- [ ] **Step 5: 运行协调器和浏览器测试**

Run: `python -m pytest -q tests/test_profile_coordinator.py tests/test_browser_helpers.py`

Expected: PASS，且测试进程正常退出，不残留等待线程。

- [ ] **Step 6: 提交**

```powershell
git add -- linodl/core/profile_coordinator.py linodl/core/browser.py tests/test_profile_coordinator.py
git commit -m "feat: coordinate persistent browser profiles"
```

---

### Task 3: 建立任务状态与可恢复输入快照

**Files:**
- Create: `linodl/gui/tasks.py`
- Create: `tests/test_gui_tasks.py`
- Modify: `linodl/gui/workers.py`

**Interfaces:**
- Produces: `TaskStatus(str, Enum)`，包含 `QUEUED`、`WAITING_FOR_PROFILE`、`RUNNING`、`WAITING_FOR_VERIFICATION`、`CANCELLING`、`CANCELLED`、`FAILED`、`COMPLETED`。
- Produces: frozen `TaskInputSnapshot`，字段为 `kind`、`query`、`url`、`selected_volumes`、`output_dir`。
- Produces: mutable `TaskRecord`，字段为 `id`、`title`、`status`、`detail`、`progress`、`input_snapshot`、`error_detail`。
- Produces: `TaskStore.create(...)`、`TaskStore.transition(...)`、`TaskStore.snapshot()`。
- Produces queue messages: `("task", TaskRecord, owner)`。

- [ ] **Step 1: 写入状态迁移、快照不可变和取消测试**

```python
def test_task_snapshot_survives_failure():
    store = TaskStore()
    inputs = TaskInputSnapshot(
        kind="download",
        query="",
        url="https://www.linovelib.com/novel/1/catalog",
        selected_volumes=("第一卷",),
        output_dir="novel_output",
    )
    task = store.create("下载 第一卷", inputs)
    store.transition(task.id, TaskStatus.RUNNING, "正在下载")
    failed = store.transition(task.id, TaskStatus.FAILED, "网络错误", error_detail="TimeoutError")
    assert failed.input_snapshot == inputs
    assert failed.error_detail == "TimeoutError"


def test_cancel_only_finishes_after_worker_exits():
    worker.cancel()
    assert worker.task.status is TaskStatus.CANCELLING
    worker.run()
    assert worker.task.status is TaskStatus.CANCELLED
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/test_gui_tasks.py`

Expected: FAIL，因为任务模型尚不存在。

- [ ] **Step 3: 实现任务模型和合法迁移**

`TaskStore` 使用 `threading.RLock`。`transition` 拒绝从终态回到运行态；每次返回 `dataclasses.replace(record)` 的快照，避免 UI 读取正在变更的对象。

- [ ] **Step 4: 接入 BackgroundWorker**

`BackgroundWorker` 创建或接收 `TaskRecord`，`start` 前为 queued，进入 `run` 后为 running；`cancel()` 先设置取消事件再转为 cancelling；`finally` 仅在工作函数退出后转为 cancelled/completed/failed。进度、结果和异常继续携带 owner，以保留当前工作区已有的多面板路由修改。

- [ ] **Step 5: 把取消事件传给浏览器和下载循环**

所有创建 `BrowserSession` 的 worker 传入 `cancel_event=self._cancel_flag`。给 `Downloader` 增加可选 `cancel_callback: Callable[[], bool]`，在卷、章节和翻页循环入口检查；为真时抛出内部 `DownloadCancelled`，worker 将其映射为 cancelled 而不是 failed。

- [ ] **Step 6: 运行任务和下载窄测试**

Run: `python -m pytest -q tests/test_gui_tasks.py tests/test_downloader_text_order.py tests/test_gui_helpers.py`

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add -- linodl/gui/tasks.py linodl/gui/workers.py linodl/core/downloader.py tests/test_gui_tasks.py tests/test_gui_helpers.py tests/test_downloader_text_order.py
git commit -m "feat: track recoverable GUI tasks"
```

---

### Task 4: 实现可见验证服务并恢复原任务

**Files:**
- Create: `linodl/gui/verification.py`
- Modify: `linodl/core/browser.py`
- Modify: `linodl/gui/workers.py`
- Modify: `tests/test_gui_tasks.py`
- Modify: `tests/test_browser_helpers.py`

**Interfaces:**
- Produces: `VerificationResult`，字段为 `passed: bool`、`cancelled: bool`、`message: str`。
- Produces: `VerificationService.verify(target_url: str, config: ConfigManager, cancel_event: threading.Event, progress: Callable[[str], None]) -> VerificationResult`。
- Produces: `BrowserSession.reopen(headless: bool, prefer_cloak: bool = False) -> BrowserSession`。

- [ ] **Step 1: 写入可见启动、复检和取消测试**

```python
def test_verification_service_uses_visible_cloak_and_rechecks_target(fake_session_factory):
    result = VerificationService(session_factory=fake_session_factory).verify(
        BASE_URL,
        config,
        threading.Event(),
        messages.append,
    )
    assert fake_session_factory.kwargs["headless"] is False
    assert fake_session_factory.kwargs["anti_bot_mode"] == "cloak"
    assert fake_session_factory.goto_urls[-1] == BASE_URL
    assert result.passed is True


def test_verification_service_returns_cancelled_without_failure(fake_session_factory):
    cancel = threading.Event()
    cancel.set()
    result = VerificationService(session_factory=fake_session_factory).verify(
        BASE_URL, config, cancel, messages.append
    )
    assert result.cancelled is True
    assert result.passed is False
```

- [ ] **Step 2: 运行窄测试并确认失败**

Run: `python -m pytest -q tests/test_gui_tasks.py -k verification`

Expected: FAIL，因为 `VerificationService` 尚不存在。

- [ ] **Step 3: 实现验证服务**

服务使用同一 `profile_dir`、proxy 和有效 GeoIP 配置创建 `BrowserSession(headless=False, anti_bot_mode="cloak")`。循环中先检查 cancel event，再检查 `assess_challenge(session.content())`；状态变为 NORMAL 后重新导航目标 URL 并再次确认 NORMAL 才返回成功。UNKNOWN 返回可重试错误，不要求存在 `cf_clearance`。

- [ ] **Step 4: 从导航流程抛出结构化验证请求**

在 `browser.py` 增加 `BrowserChallengeRequired(target_url, reason)`。无头会话发现 CHALLENGE 时不在隐藏窗口等待，而是关闭会话并抛出该异常。GUI worker 捕获后转为 `WAITING_FOR_VERIFICATION`，调用 `VerificationService`，成功后重新创建无头会话并从保存的输入快照重跑当前操作。

- [ ] **Step 5: 简化预热判定**

`perform_cloudflare_warmup` 以“目标页面复检为 NORMAL 且存在有效内容”为成功条件，删除必须等待 `cf_clearance` 的逻辑。WarmupWorker 仍直接使用可见 CloakBrowser，但共享验证服务的页面复检函数。

- [ ] **Step 6: 运行浏览器和任务测试**

Run: `python -m pytest -q tests/test_browser_helpers.py tests/test_gui_tasks.py`

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add -- linodl/gui/verification.py linodl/core/browser.py linodl/gui/workers.py tests/test_gui_tasks.py tests/test_browser_helpers.py
git commit -m "feat: resume tasks after visible browser verification"
```

---

### Task 5: 构建阅读工作台与任务中心

**Files:**
- Create: `linodl/gui/widgets/task_center.py`
- Create: `linodl/gui/widgets/workflow_steps.py`
- Create: `linodl/gui/panels/workbench_panel.py`
- Modify: `linodl/gui/style.py`
- Modify: `linodl/gui/app.py`
- Modify: `linodl/gui/panels/search_panel.py`
- Modify: `linodl/gui/panels/download_panel.py`
- Modify: `linodl/gui/panels/export_panel.py`
- Modify: `linodl/gui/panels/verify_panel.py`
- Modify: `linodl/gui/panels/warmup_panel.py`
- Modify: `linodl/gui/widgets/progress_area.py`
- Modify: `tests/test_gui_helpers.py`

**Interfaces:**
- Produces: `classify_workbench_input(value: str) -> Literal["empty", "url", "query", "invalid_url"]`。
- Produces: `WorkflowSteps.set_active(step: str)`，合法步骤为 `search`、`volumes`、`download`、`verify_export`。
- Produces: `TaskCenter.render(records: Sequence[TaskRecord])`。
- Produces: `WorkbenchPanel.refresh_tasks(records)` 和 `WorkbenchPanel.set_profile_health(text, level)`。

- [ ] **Step 1: 写入统一输入分类和任务排序测试**

```python
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", "empty"),
        ("刀剑神域", "query"),
        ("https://www.linovelib.com/novel/1/catalog", "url"),
        ("https://example.com/novel/1", "invalid_url"),
    ],
)
def test_classify_workbench_input(value, expected):
    assert classify_workbench_input(value) == expected


def test_task_center_lists_active_before_finished():
    records = sort_task_records([completed, running, waiting])
    assert [record.status for record in records] == [
        TaskStatus.RUNNING,
        TaskStatus.WAITING_FOR_VERIFICATION,
        TaskStatus.COMPLETED,
    ]
```

- [ ] **Step 2: 运行 UI 辅助测试并确认失败**

Run: `python -m pytest -q tests/test_gui_helpers.py -k "classify_workbench or task_center"`

Expected: FAIL，因为工作台和排序函数尚不存在。

- [ ] **Step 3: 建立设计令牌与可复用组件**

`style.py` 定义墨蓝侧栏、青蓝主操作、卡片表面、边框、成功/警告/危险色，以及 `display_font()`、`body_font()`、`meta_font()`。`WorkflowSteps` 用编号、文字和连接线表达四个阶段；`TaskCenter` 每项显示标题、状态文案、详情和进度，等待验证与失败状态提供重试/打开验证动作回调。

- [ ] **Step 4: 实现 WorkbenchPanel**

顶部为标题、浏览档案健康 badge 和四步指示器；中部为单一输入框与主按钮；下部左右两列为最近阅读档案和任务中心。输入分类为 query 时启动搜索，为 url 时加载目录，为 invalid_url 时显示本地错误。复用 SearchPanel 的结果卡和 DownloadPanel 的目录/下载逻辑，不复制核心业务。

- [ ] **Step 5: 重构主窗口导航与事件分发**

导航改为：阅读工作台、内容校验、阅读档案、浏览档案、设置。保留已有 owner-tagged queue 路由和并行任务提示。`("task", record, owner)` 事件刷新工作台任务中心；当前操作变化时同步 WorkflowSteps。修复所有触及文件中的乱码 UI 文案。

- [ ] **Step 6: 调整旧面板为工作台内部组件**

SearchPanel 提供 `start_from_input(value)`；DownloadPanel 提供 `snapshot_input()` 和真实 cancelling 状态；Export/Verify/Warmup 保留独立入口但统一卡片、标题、按钮和空状态样式。窗口最小尺寸保持 `800×600`，主尺寸保持 `1024×768`。

- [ ] **Step 7: 运行 UI 与核心流程测试**

Run: `python -m pytest -q tests/test_gui_helpers.py tests/test_catalog.py tests/test_search.py tests/test_epub_export_flow.py`

Expected: PASS。

- [ ] **Step 8: 提交**

```powershell
git add -- linodl/gui/style.py linodl/gui/app.py linodl/gui/panels linodl/gui/widgets tests/test_gui_helpers.py
git commit -m "feat: redesign GUI as reading workbench"
```

---

### Task 6: 完善设置、依赖和 vendored CloakBrowser

**Files:**
- Modify: `linodl/config/manager.py`
- Modify: `linodl/gui/panels/settings_panel.py`
- Modify: `requirements.txt`
- Modify: `vendor/cloakbrowser/`
- Create: `vendor/LICENSE.cloakbrowser`
- Modify: `vendor/README.md`
- Modify: `.gitignore`
- Modify: `tests/test_config_manager.py`
- Modify: `tests/test_browser_helpers.py`

**Interfaces:**
- Produces: `ConfigManager.update_settings(*, output_dir, headless, anti_bot_mode, profile_dir, proxy, geoip, theme) -> None`。
- Produces: `effective_geoip(proxy: str, requested: bool) -> bool`。

- [ ] **Step 1: 写入批量保存与 GeoIP 有效值测试**

```python
def test_update_settings_writes_one_consistent_snapshot(tmp_path):
    config = ConfigManager(str(tmp_path / "config.ini"))
    config.update_settings(
        output_dir="books",
        headless=True,
        anti_bot_mode="cloak",
        profile_dir="profile",
        proxy="",
        geoip=True,
        theme="dark",
    )
    reloaded = ConfigManager(str(tmp_path / "config.ini"))
    assert reloaded.output_dir == "books"
    assert reloaded.geoip is False
    assert reloaded.theme == "dark"
```

- [ ] **Step 2: 运行配置测试并确认失败**

Run: `python -m pytest -q tests/test_config_manager.py -k update_settings`

Expected: FAIL，因为 `update_settings` 尚不存在。

- [ ] **Step 3: 实现原子式批量配置和设置提示**

一次更新内先规范化全部值，再写入临时文件并用 `os.replace` 替换配置文件。无代理且请求 geoip 时存储 false。设置界面在 GeoIP 开关旁显示“需要 HTTP/SOCKS 代理”，无代理时禁用开关；浏览档案卡展示路径、CloakBrowser 包装层版本和浏览器二进制状态。

- [ ] **Step 4: 同步 CloakBrowser 0.5.2 包装层**

使用 PyPI 官方 wheel 下载到项目内明确的临时目录，核对包版本为 `0.5.2`，然后机械同步 `cloakbrowser/` 到 `vendor/cloakbrowser/`。同步后运行 import 测试确认 `linodl.core.browser` 仍从 vendor 加载。保留公开 Chromium 146 配置，不写入授权密钥。

Run:

```powershell
python -m pip download --no-deps cloakbrowser==0.5.2 --dest .tmp-cloakbrowser-wheel
python -m zipfile -e .tmp-cloakbrowser-wheel\cloakbrowser-0.5.2-py3-none-any.whl .tmp-cloakbrowser-wheel\expanded
```

- [ ] **Step 5: 补齐许可证、依赖和版本说明**

从 CloakBrowser `v0.5.2` 官方发行物复制完整 MIT License 到 `vendor/LICENSE.cloakbrowser`。`vendor/README.md` 使用 UTF-8 中文说明来源、版本、同步方式、公开 Chromium 构建限制。根据 0.5.2 wheel metadata 将运行依赖加入 `requirements.txt`；GeoIP 与 SOCKS 明确包含 `geoip2`、`socksio`。`.gitignore` 增加 `.superpowers/` 和本次明确临时目录 `.tmp-cloakbrowser-wheel/`。

- [ ] **Step 6: 删除已验证的临时 wheel 目录**

先解析仓库根目录和临时目录，确认临时目录严格位于仓库内，再删除：

```powershell
$cloakTempPath = (Resolve-Path '.tmp-cloakbrowser-wheel').Path
$repositoryPath = (Resolve-Path '.').Path
if (-not $cloakTempPath.StartsWith($repositoryPath + [IO.Path]::DirectorySeparatorChar)) {
    throw "Refusing to remove path outside repository: $cloakTempPath"
}
Remove-Item -LiteralPath $cloakTempPath -Recurse -Force
```

- [ ] **Step 7: 运行配置、浏览器和 vendor 测试**

Run: `python -m pytest -q tests/test_config_manager.py tests/test_browser_helpers.py`

Expected: PASS，且版本断言为 `0.5.2`，实际 import 路径位于仓库 `vendor`。

- [ ] **Step 8: 提交**

```powershell
git add -- linodl/config/manager.py linodl/gui/panels/settings_panel.py requirements.txt vendor .gitignore tests/test_config_manager.py tests/test_browser_helpers.py
git commit -m "chore: update CloakBrowser integration metadata"
```

---

### Task 7: 基础验收与交付修整

**Files:**
- Modify only if verification finds a defect: files already listed in Tasks 1–6 and their direct tests.

**Interfaces:**
- Consumes all interfaces from Tasks 1–6.
- Produces no new public interface.

- [ ] **Step 1: 运行完整测试**

Run: `python -m pytest -q`

Expected: all tests PASS。

- [ ] **Step 2: 修复测试发现的最小缺陷并重跑相关窄测试**

仅修改失败行为对应的实现和直接测试；每个修复先添加能够重现失败的断言，再修改实现，直到相关测试 PASS。

- [ ] **Step 3: 运行 Python 编译检查**

Run: `python -m compileall -q linodl tests`

Expected: exit code 0，无输出。

- [ ] **Step 4: 主窗口启动冒烟检查**

Run:

```powershell
@'
from linodl.config.manager import ConfigManager
from linodl.gui.app import MainWindow

app = MainWindow(ConfigManager())
app.update_idletasks()
assert app.winfo_exists()
assert app._current_panel is not None
app.destroy()
print("gui-smoke: ok")
'@ | python -
```

Expected: 输出 `gui-smoke: ok`，进程正常退出。

- [ ] **Step 5: CloakBrowser about:blank 冒烟检查**

Run:

```powershell
@'
import tempfile
from linodl.core.browser import BrowserSession

with tempfile.TemporaryDirectory(prefix="linodl-cloak-smoke-") as profile:
    session = BrowserSession(headless=True, anti_bot_mode="cloak", profile_dir=profile)
    try:
        session.start()
        session.goto("about:blank")
        assert session.engine == "cloak"
        assert session.page is not None
    finally:
        session.close()
print("cloak-smoke: ok")
'@ | python -
```

Expected: 输出 `cloak-smoke: ok`，浏览器上下文创建并关闭。

- [ ] **Step 6: 检查提交范围和敏感信息**

Run:

```powershell
git status --short
git diff --check
git diff --name-only HEAD~6..HEAD
rg -n --hidden -g '!vendor/cloakbrowser/**' -g '!.git/**' "(password\\s*=\\s*['\\\"][^'\\\"]+|cf_clearance|api[_-]?key\\s*=)" .
```

Expected: 不包含浏览档案、cookie、代理密码、授权密钥或 `.superpowers/` 临时产物；用户原有未纳入本次范围的修改仍保留。

- [ ] **Step 7: 提交验收阶段的直接修整**

仅在 Step 2–6 产生必要修改时执行：

```powershell
git add -- linodl tests requirements.txt vendor .gitignore
git commit -m "fix: resolve final workbench verification issues"
```

提交前使用 `git diff --cached --name-only` 检查暂存区；如果验收阶段只修改了其中一部分文件，则从命令中删除未修改路径，确保不纳入设计文档、浏览档案或临时目录。
