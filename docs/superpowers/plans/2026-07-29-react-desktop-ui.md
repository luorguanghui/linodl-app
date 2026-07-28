# React Desktop UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the default CustomTkinter presentation layer with a responsive React desktop window while preserving the existing Python search, catalog, download, verification, export, configuration, and CloakBrowser behavior.

**Architecture:** A Vite-built React application is loaded inside a pywebview window. A narrow Python bridge validates commands, starts the existing background workers, serializes domain models, and exposes versioned task/operation snapshots; React owns only presentation state and responsive layout. The existing CustomTkinter application remains available through an explicit `--legacy-gui` fallback.

**Tech Stack:** Python 3.12, pywebview 6.2.x, React 19.2.x, TypeScript 7.0.x, Vite 8.1.x, Zustand 5.0.x, Lucide React 1.27.x, Vitest 4.1.x, Testing Library, pytest.

## Global Constraints

- Keep `linodl/core/`, `linodl/config/`, CloakBrowser integration, download files, browser profiles, and existing configuration semantics intact.
- Do not implement CAPTCHA solving or Cloudflare bypass.
- Do not expose proxy credentials, cookies, passwords, or raw sensitive URLs to the frontend.
- Production mode loads bundled local assets and does not open an external browser or require a development server.
- Default window size is `1280 × 820`; minimum size is `900 × 640`.
- Preserve the old CustomTkinter UI behind `python -m linodl --legacy-gui`.
- The responsive layout has three content breakpoints: wide at `>= 1400px`, standard at `980–1399px`, and compact at `< 980px`.
- Empty states size to their content; only result lists and task logs may independently scroll.
- Use test-first changes and commit after each independently testable task.

---

## File Structure

### Python desktop boundary

- `linodl/desktop/__init__.py`: public desktop package exports.
- `linodl/desktop/app.py`: pywebview window lifecycle and production/development asset selection.
- `linodl/desktop/assets.py`: resolve Vite build assets without depending on the current working directory.
- `linodl/desktop/bridge.py`: validated API exposed to `window.pywebview.api`.
- `linodl/desktop/controller.py`: start existing workers, consume their queue, and store serializable operation results.
- `linodl/desktop/serialization.py`: convert dataclasses, enums, and error payloads to frontend DTOs.
- `linodl/desktop/window_state.py`: persist normal bounds and maximized state.
- `linodl/desktop/archive.py`: scan output directories and build archive DTOs without UI dependencies.

### React application

- `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig*.json`: frontend toolchain.
- `frontend/index.html`, `frontend/src/main.tsx`: application entry.
- `frontend/src/api/desktop.ts`: typed pywebview bridge adapter with a test browser fallback.
- `frontend/src/api/types.ts`: DTO contracts matching Python serialization.
- `frontend/src/store/desktop.ts`: operation, task, profile, settings, and navigation state.
- `frontend/src/design/tokens.css`: palette, type, spacing, elevation, and motion tokens.
- `frontend/src/design/base.css`: reset, focus, form, and accessibility rules.
- `frontend/src/app/DesktopShell.tsx`: responsive desktop shell.
- `frontend/src/app/AppRouter.tsx`: in-memory navigation for five primary pages.
- `frontend/src/components/`: shared command deck, navigation, ribbon, task inspector, and state components.
- `frontend/src/features/workbench/`: search, catalog, volume selection, and download flow.
- `frontend/src/features/verify/`: local download verification page.
- `frontend/src/features/archive/`: downloaded archive and EPUB export page.
- `frontend/src/features/profile/`: browser profile health and visible verification page.
- `frontend/src/features/settings/`: settings form.

### Tests and entrypoints

- `tests/test_desktop_assets.py`
- `tests/test_desktop_serialization.py`
- `tests/test_desktop_bridge.py`
- `tests/test_desktop_controller.py`
- `tests/test_window_state.py`
- `frontend/src/**/*.test.ts(x)`
- `requirements.txt`
- `run_gui.bat`
- `linodl/__main__.py`
- `README.md`

---

### Task 1: Scaffold the Local React Desktop Shell

**Files:**
- Create: `linodl/desktop/__init__.py`
- Create: `linodl/desktop/assets.py`
- Create: `linodl/desktop/app.py`
- Create: `tests/test_desktop_assets.py`
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/DesktopShell.tsx`
- Modify: `requirements.txt`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `ConfigManager`, repository-local `frontend/dist/index.html`.
- Produces: `DesktopAssets.resolve(project_root: Path | None = None) -> DesktopAssets`; `run_desktop(config: ConfigManager, debug: bool = False) -> None`.

- [ ] **Step 1: Write the failing asset-resolution tests**

```python
# tests/test_desktop_assets.py
from pathlib import Path

import pytest

from linodl.desktop.assets import DesktopAssets


def test_resolve_uses_built_index_from_project_root(tmp_path: Path):
    index = tmp_path / "frontend" / "dist" / "index.html"
    index.parent.mkdir(parents=True)
    index.write_text("<main>linodl</main>", encoding="utf-8")

    assets = DesktopAssets.resolve(tmp_path)

    assert assets.index_file == index.resolve()
    assert assets.url.startswith("file:")


def test_resolve_explains_missing_frontend_build(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="npm run build"):
        DesktopAssets.resolve(tmp_path)
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest -q tests/test_desktop_assets.py`  
Expected: FAIL because `linodl.desktop.assets` does not exist.

- [ ] **Step 3: Implement asset resolution and the pywebview window**

```python
# linodl/desktop/assets.py
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DesktopAssets:
    index_file: Path

    @property
    def url(self) -> str:
        return self.index_file.as_uri()

    @classmethod
    def resolve(cls, project_root: Path | None = None) -> "DesktopAssets":
        root = project_root or Path(__file__).resolve().parents[2]
        index_file = (root / "frontend" / "dist" / "index.html").resolve()
        if not index_file.is_file():
            raise FileNotFoundError(
                "React desktop assets are missing. Run: cd frontend; npm install; npm run build"
            )
        return cls(index_file=index_file)
```

```python
# linodl/desktop/app.py
from __future__ import annotations

import os

import webview

from ..config.manager import ConfigManager
from .assets import DesktopAssets


def run_desktop(config: ConfigManager, debug: bool = False) -> None:
    from .bridge import DesktopBridge

    development_url = os.environ.get("LINODL_FRONTEND_URL", "").strip()
    url = development_url or DesktopAssets.resolve().url
    bridge = DesktopBridge(config=config, debug=debug)
    window = webview.create_window(
        "linodl · 轻小说资料库",
        url=url,
        js_api=bridge,
        width=1280,
        height=820,
        min_size=(900, 640),
    )
    bridge.attach_window(window)
    webview.start(debug=debug)
```

Create the Vite app with React and TypeScript, render a temporary `DesktopShell` heading, and use relative asset paths:

```json
{
  "name": "linodl-desktop",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "typecheck": "tsc -b --pretty false",
    "test": "vitest"
  },
  "dependencies": {
    "lucide-react": "^1.27.0",
    "react": "^19.2.8",
    "react-dom": "^19.2.8",
    "zustand": "^5.0.14"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^7.0.0",
    "@testing-library/react": "^16.3.2",
    "@types/react": "^19.2.17",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^6.0.4",
    "jsdom": "^30.0.0",
    "typescript": "^7.0.2",
    "vite": "^8.1.5",
    "vitest": "^4.1.10"
  }
}
```

```ts
// frontend/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  test: { environment: "jsdom", setupFiles: "./src/test/setup.ts" },
});
```

Add `pywebview>=6.2,<7` to `requirements.txt`, and ignore `frontend/node_modules/`, `frontend/dist/`, and `frontend/coverage/`.

- [ ] **Step 4: Install, build, and run the focused tests**

Run: `npm install` in `frontend`  
Run: `npm run build` in `frontend`  
Run: `python -m pytest -q tests/test_desktop_assets.py`  
Expected: build succeeds and both pytest tests pass.

- [ ] **Step 5: Commit**

```powershell
git add .gitignore requirements.txt linodl/desktop frontend tests/test_desktop_assets.py
git commit -m "feat: scaffold React desktop shell"
```

---

### Task 2: Add Versioned Task Snapshots and Stable DTO Serialization

**Files:**
- Modify: `linodl/gui/tasks.py`
- Create: `linodl/desktop/serialization.py`
- Create: `tests/test_desktop_serialization.py`
- Modify: `tests/test_gui_tasks.py`
- Create: `frontend/src/api/types.ts`

**Interfaces:**
- Consumes: `TaskRecord`, `TaskInputSnapshot`, `NovelInfo`, `Volume`, `Chapter`, `VerificationResult`.
- Produces: `TaskStore.snapshot_versioned(after_version: int = -1) -> tuple[int, list[TaskRecord] | None]`; `to_primitive(value: object) -> JSONPrimitive`; matching TypeScript DTO types.

- [ ] **Step 1: Write failing version and serialization tests**

```python
# tests/test_desktop_serialization.py
from linodl.desktop.serialization import to_primitive
from linodl.gui.tasks import TaskInputSnapshot, TaskStatus, TaskStore
from linodl.models.novel import Chapter, Volume


def test_task_store_returns_none_when_version_is_unchanged():
    store = TaskStore()
    first_version, first_records = store.snapshot_versioned()
    same_version, unchanged = store.snapshot_versioned(first_version)

    assert same_version == first_version
    assert first_records == []
    assert unchanged is None


def test_task_version_changes_after_create_and_transition():
    store = TaskStore()
    version_0, _ = store.snapshot_versioned()
    task = store.create("读取目录", TaskInputSnapshot(kind="catalog", url="https://example.test"))
    version_1, _ = store.snapshot_versioned(version_0)
    store.transition(task.id, TaskStatus.RUNNING, "正在读取", progress=0.25)
    version_2, records = store.snapshot_versioned(version_1)

    assert version_0 < version_1 < version_2
    assert records[0].progress == 0.25


def test_to_primitive_serializes_nested_dataclasses_and_enums():
    volume = Volume(
        name="第一卷",
        chapters=[Chapter(index=1, url="/1.html", title="序章", is_illustration=False)],
    )

    payload = to_primitive(volume)

    assert payload["name"] == "第一卷"
    assert payload["text_count"] == 1
    assert payload["chapters"][0]["title"] == "序章"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m pytest -q tests/test_desktop_serialization.py`  
Expected: FAIL because the versioned method and serializer do not exist.

- [ ] **Step 3: Implement monotonic versioning and serialization**

Increment `TaskStore._version` inside `create()` and `transition()`. Add:

```python
def snapshot_versioned(
    self,
    after_version: int = -1,
) -> tuple[int, list[TaskRecord] | None]:
    with self._lock:
        if after_version == self._version:
            return self._version, None
        return self._version, [replace(record) for record in self._records.values()]
```

Implement `to_primitive()` recursively with dataclasses, enums, dictionaries, tuples/lists, and computed `Volume.text_count`, `Volume.illus_count`, `VerificationResult.is_clean`, and `VerificationResult.issue_count`. Pass every string through `redact_sensitive_text()`.

Define exact TypeScript contracts:

```ts
export type TaskStatus =
  | "queued"
  | "waiting_for_profile"
  | "running"
  | "waiting_for_verification"
  | "cancelling"
  | "cancelled"
  | "failed"
  | "completed";

export interface TaskDto {
  id: string;
  title: string;
  status: TaskStatus;
  detail: string;
  progress: number;
  input_snapshot: TaskInputDto | null;
  error_detail: string;
}

export interface VersionedTasksDto {
  version: number;
  tasks: TaskDto[] | null;
}
```

- [ ] **Step 4: Run task and serialization tests**

Run: `python -m pytest -q tests/test_desktop_serialization.py tests/test_gui_tasks.py`  
Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add linodl/gui/tasks.py linodl/desktop/serialization.py frontend/src/api/types.ts tests/test_desktop_serialization.py tests/test_gui_tasks.py
git commit -m "feat: expose versioned desktop task DTOs"
```

---

### Task 3: Build the Worker Controller and Bridge Command Boundary

**Files:**
- Create: `linodl/desktop/controller.py`
- Create: `linodl/desktop/bridge.py`
- Create: `tests/test_desktop_controller.py`
- Create: `tests/test_desktop_bridge.py`
- Modify: `linodl/desktop/app.py`

**Interfaces:**
- Consumes: existing `SearchWorker`, `CatalogWorker`, `DownloadWorker`, `VerifyWorker`, `ExportWorker`, `WarmupWorker`, `cancel_task`, `TaskStore`.
- Produces: `DesktopController.start(kind: str, **payload) -> str`; `DesktopController.operations(after_version: int) -> dict`; `DesktopController.poll(task_version: int, operation_version: int) -> dict`; `DesktopBridge.bootstrap()`, `start_search()`, `load_catalog()`, `start_download()`, `cancel()`, `poll()`.

- [ ] **Step 1: Write failing controller tests with injected workers**

```python
# tests/test_desktop_controller.py
import queue

from linodl.desktop.controller import DesktopController
from linodl.gui.tasks import TaskStore


class FinishedWorker:
    def __init__(self, message_queue, owner):
        self._queue = message_queue
        self._owner = owner
        self.task = type("Task", (), {"id": "task-1"})()

    def start(self):
        self._queue.put(("result", [{"title": "作品 A"}], self._owner))
        self._queue.put(("done", None, self._owner))


def test_controller_keeps_result_after_worker_finishes():
    controller = DesktopController(
        task_store=TaskStore(),
        worker_factories={"search": lambda payload, q, owner: FinishedWorker(q, owner)},
    )

    operation_id = controller.start("search", query="作品 A")
    controller.drain_events()
    payload = controller.operations(-1)

    assert payload["operations"][operation_id]["status"] == "completed"
    assert payload["operations"][operation_id]["result"][0]["title"] == "作品 A"
```

```python
# tests/test_desktop_bridge.py
from linodl.config.manager import ConfigManager
from linodl.desktop.bridge import DesktopBridge


class FakeController:
    def start(self, kind, **payload):
        self.last = (kind, payload)
        return "op-1"

    def poll(self, task_version, operation_version):
        return {"task_version": 0, "tasks": [], "operation_version": 0, "operations": {}}


def test_bridge_rejects_blank_search(tmp_path):
    bridge = DesktopBridge(
        ConfigManager(str(tmp_path / "settings.ini")),
        controller=FakeController(),
    )

    response = bridge.start_search("   ")

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_QUERY"


def test_bridge_starts_valid_search(tmp_path):
    controller = FakeController()
    bridge = DesktopBridge(
        ConfigManager(str(tmp_path / "settings.ini")),
        controller=controller,
    )

    response = bridge.start_search("刀剑神域")

    assert response == {"ok": True, "operation_id": "op-1"}
    assert controller.last == ("search", {"query": "刀剑神域"})
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `python -m pytest -q tests/test_desktop_controller.py tests/test_desktop_bridge.py`  
Expected: FAIL because the controller and bridge do not exist.

- [ ] **Step 3: Implement the controller**

Use one `queue.Queue`, an `OperationOwner(operation_id)` token, a locked operation dictionary, and a monotonically increasing operation version. `drain_events()` maps:

- `progress` to `running` and `detail`.
- `result` to a serialized `result`.
- `error` to `failed`, with `redact_sensitive_text()`.
- `done` to `completed` unless already failed or cancelled.

Worker factories receive `(payload, queue, owner)` and construct existing workers. Cache catalog results in the controller by operation ID so `start_download(catalog_operation_id, selected_volumes)` passes original Python `Volume` and `NovelInfo` objects to `DownloadWorker` without round-tripping them through JavaScript.

```python
def start(self, kind: str, **payload) -> str:
    operation_id = uuid.uuid4().hex
    owner = OperationOwner(operation_id)
    worker = self._worker_factories[kind](payload, self._queue, owner)
    with self._lock:
        self._operations[operation_id] = OperationRecord(
            id=operation_id,
            kind=kind,
            task_id=worker.task.id,
            status="running",
        )
        self._workers[operation_id] = worker
        self._operation_version += 1
    worker.start()
    return operation_id
```

`poll(task_version, operation_version)` first calls `drain_events()`, then combines `TaskStore.snapshot_versioned(task_version)` and `operations(operation_version)` into one response. This is the method consumed by `DesktopBridge.poll()`.

- [ ] **Step 4: Implement the bridge response contract**

Every public bridge method returns one of:

```python
{"ok": True, "operation_id": operation_id}
```

```python
{
    "ok": False,
    "error": {
        "code": "INVALID_QUERY",
        "message": "请输入作品名。",
        "action": "输入作品名后重新查找。",
    },
}
```

Expose these exact methods:

```python
bootstrap() -> dict
poll(task_version: int, operation_version: int) -> dict
start_search(query: str) -> dict
load_catalog(url: str) -> dict
start_download(catalog_operation_id: str, selected_volumes: list[str]) -> dict
cancel(task_id: str) -> dict
```

`poll()` calls `controller.drain_events()` before producing DTOs. Do not expose Python exceptions to JavaScript.

- [ ] **Step 5: Run focused and existing worker tests**

Run: `python -m pytest -q tests/test_desktop_controller.py tests/test_desktop_bridge.py tests/test_gui_tasks.py tests/test_gui_helpers.py`  
Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add linodl/desktop tests/test_desktop_controller.py tests/test_desktop_bridge.py
git commit -m "feat: bridge React UI to desktop workers"
```

---

### Task 4: Add the Typed Frontend API and Versioned Desktop Store

**Files:**
- Create: `frontend/src/api/desktop.ts`
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/store/desktop.ts`
- Create: `frontend/src/store/desktop.test.ts`
- Create: `frontend/src/test/setup.ts`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: Task 3 bridge methods and Task 2 DTOs.
- Produces: `desktopApi`; `useDesktopStore`; `startPolling()` and `stopPolling()`.

- [ ] **Step 1: Write failing store tests**

```ts
// frontend/src/store/desktop.test.ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createDesktopStore } from "./desktop";

describe("desktop store", () => {
  beforeEach(() => vi.useFakeTimers());

  it("keeps existing tasks when the bridge reports no version change", async () => {
    const api = {
      poll: vi
        .fn()
        .mockResolvedValueOnce({
          task_version: 2,
          tasks: [{ id: "1", title: "下载", status: "running", detail: "", progress: 0.5 }],
          operation_version: 0,
          operations: {},
        })
        .mockResolvedValueOnce({
          task_version: 2,
          tasks: null,
          operation_version: 0,
          operations: null,
        }),
    };
    const store = createDesktopStore(api as never);

    await store.getState().pollOnce();
    await store.getState().pollOnce();

    expect(store.getState().tasks).toHaveLength(1);
  });

  it("surfaces an actionable bridge error", async () => {
    const api = {
      startSearch: vi.fn().mockResolvedValue({
        ok: false,
        error: { code: "INVALID_QUERY", message: "请输入作品名。", action: "输入后重试。" },
      }),
    };
    const store = createDesktopStore(api as never);

    await store.getState().search("");

    expect(store.getState().notice?.message).toBe("请输入作品名。");
  });
});
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `npm run test -- --run src/store/desktop.test.ts` in `frontend`  
Expected: FAIL because the store does not exist.

- [ ] **Step 3: Implement the pywebview adapter**

Declare the pywebview API on `window` and wait for `pywebviewready` before the first command. Keep a development fallback that returns empty bootstrap data only when `import.meta.env.DEV` is true.

```ts
export async function invoke<T>(method: string, ...args: unknown[]): Promise<T> {
  await waitForPywebview();
  const api = window.pywebview?.api as Record<string, (...values: unknown[]) => Promise<T>>;
  if (!api?.[method]) throw new Error(`Desktop API method is unavailable: ${method}`);
  return api[method](...args);
}
```

- [ ] **Step 4: Implement the Zustand store**

Store:

- `tasks`, `taskVersion`
- `operations`, `operationVersion`
- `activeOperationId`
- `profile`
- `settings`
- `notice`
- `pollOnce()`, `search()`, `loadCatalog()`, `startDownload()`, `cancelTask()`

Poll every 500 ms while the window is active and every 2 seconds while hidden. Merge only non-null snapshots.

- [ ] **Step 5: Run tests and type checking**

Run: `npm run test -- --run` in `frontend`  
Run: `npm run typecheck` in `frontend`  
Expected: all tests and TypeScript checks pass.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/api frontend/src/store frontend/src/test frontend/package.json
git commit -m "feat: add typed desktop frontend store"
```

---

### Task 5: Implement the Responsive Visual System and Desktop Shell

**Files:**
- Create: `frontend/src/design/tokens.css`
- Create: `frontend/src/design/base.css`
- Create: `frontend/src/app/AppRouter.tsx`
- Modify: `frontend/src/app/DesktopShell.tsx`
- Create: `frontend/src/app/DesktopShell.test.tsx`
- Create: `frontend/src/components/BookRail.tsx`
- Create: `frontend/src/components/CommandDeck.tsx`
- Create: `frontend/src/components/ChapterRibbon.tsx`
- Create: `frontend/src/components/TaskInspector.tsx`
- Create: `frontend/src/components/EmptyState.tsx`
- Create: `frontend/src/components/AppErrorBoundary.tsx`
- Create: `frontend/src/components/AppErrorBoundary.test.tsx`
- Modify: `frontend/src/main.tsx`

**Interfaces:**
- Consumes: `useDesktopStore`, React Router-free page key state.
- Produces: five-page shell and responsive layout classes used by all feature pages.

- [ ] **Step 1: Write failing shell behavior tests**

```tsx
// frontend/src/app/DesktopShell.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DesktopShell } from "./DesktopShell";

describe("DesktopShell", () => {
  it("keeps the global task inspector when navigating", () => {
    render(<DesktopShell />);
    expect(screen.getByRole("complementary", { name: "任务检查器" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "内容校验" }));

    expect(screen.getByRole("heading", { name: "内容校验" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "任务检查器" })).toBeInTheDocument();
  });

  it("marks the current navigation item", () => {
    render(<DesktopShell />);
    const workbench = screen.getByRole("button", { name: "阅读工作台" });
    expect(workbench).toHaveAttribute("aria-current", "page");
  });
});
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `npm run test -- --run src/app/DesktopShell.test.tsx` in `frontend`  
Expected: FAIL because the responsive shell components do not exist.

- [ ] **Step 3: Implement design tokens**

Define semantic variables for:

- ink/navigation
- canvas/surface/elevated surface
- primary/action
- warning/success/danger
- text/muted text/borders
- spacing from 4 to 32 px
- radii from 6 to 16 px
- one restrained shadow
- transition durations with `prefers-reduced-motion`

Bundle offline body and mono fonts under `frontend/src/assets/fonts/` with their licenses under `frontend/src/assets/fonts/LICENSES.md`. If no redistributable font is added, use the Windows system stack and do not download a font at runtime.

- [ ] **Step 4: Implement the shell from the approved visualization**

CSS requirements:

```css
.desktop-shell {
  display: grid;
  grid-template-columns: 196px minmax(0, 1fr);
  min-width: 0;
  min-height: 100%;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(720px, 1fr) minmax(320px, 420px);
  gap: var(--space-4);
  width: min(100%, 1680px);
  margin-inline: auto;
}

@media (max-width: 1399px) {
  .desktop-shell { grid-template-columns: 76px minmax(0, 1fr); }
  .workspace-grid { grid-template-columns: minmax(0, 1fr); }
  .task-inspector { display: grid; grid-template-columns: 1fr 1fr; }
}

@media (max-width: 979px) {
  .task-inspector { grid-template-columns: 1fr; }
  .command-deck { grid-template-columns: minmax(0, 1fr); }
}
```

Use Lucide icons, visible focus states, semantic buttons, and no fixed-height empty result panels.

Wrap routed content in `AppErrorBoundary`. On an unknown rendering exception it keeps the book rail and task inspector mounted, replaces only the failed page with “此页面暂时无法显示” and a “重新加载页面” button, and logs the technical error to the development console.

- [ ] **Step 5: Run component tests and build**

Run: `npm run test -- --run src/app/DesktopShell.test.tsx` in `frontend`  
Run: `npm run build` in `frontend`  
Expected: tests and build pass.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src
git commit -m "feat: build responsive reading studio shell"
```

---

### Task 6: Migrate the Search, Catalog, and Download Workbench

**Files:**
- Create: `frontend/src/features/workbench/WorkbenchPage.tsx`
- Create: `frontend/src/features/workbench/WorkbenchPage.test.tsx`
- Create: `frontend/src/features/workbench/NovelResults.tsx`
- Create: `frontend/src/features/workbench/NovelSummary.tsx`
- Create: `frontend/src/features/workbench/VolumeList.tsx`
- Create: `frontend/src/features/workbench/workbench.css`
- Modify: `frontend/src/app/AppRouter.tsx`
- Modify: `frontend/src/store/desktop.ts`

**Interfaces:**
- Consumes: `desktopStore.search(query)`, `loadCatalog(url)`, `startDownload(catalogOperationId, selectedVolumes)`.
- Produces: one mutually exclusive workbench state: `empty | searching | results | catalog | downloading | completed | failed`.

- [ ] **Step 1: Write failing workbench flow tests**

```tsx
// frontend/src/features/workbench/WorkbenchPage.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WorkbenchPage } from "./WorkbenchPage";

describe("WorkbenchPage", () => {
  it("submits a title through the unified command field", async () => {
    const search = vi.fn();
    render(<WorkbenchPage model={{ state: "empty", search } as never} />);

    fireEvent.change(screen.getByLabelText("作品名或目录地址"), {
      target: { value: "刀剑神域" },
    });
    fireEvent.click(screen.getByRole("button", { name: "查找作品" }));

    expect(search).toHaveBeenCalledWith("刀剑神域");
  });

  it("keeps selected volume names when the layout changes", () => {
    const model = {
      state: "catalog",
      selectedVolumes: ["第一卷"],
      volumes: [
        { name: "第一卷", text_count: 12, illus_count: 2 },
        { name: "第二卷", text_count: 11, illus_count: 1 },
      ],
    };
    const { rerender } = render(<WorkbenchPage model={model as never} />);
    rerender(<WorkbenchPage model={model as never} />);

    expect(screen.getByRole("checkbox", { name: /第一卷/ })).toBeChecked();
  });
});
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `npm run test -- --run src/features/workbench/WorkbenchPage.test.tsx` in `frontend`  
Expected: FAIL because the workbench components do not exist.

- [ ] **Step 3: Implement the workbench state selector**

Derive state from the active operation and never render search results and a catalog simultaneously. A selected search result calls `loadCatalog(result.catalog_url)`. A URL input calls `loadCatalog()` directly; other HTTP URLs return an inline invalid-source message.

- [ ] **Step 4: Implement the approved workbench UI**

- Keep the command deck at the top.
- Show a compact instructional empty state.
- Render results as book rows with title, author, description, and a clear “读取目录” action.
- Render catalog as a book summary plus virtualizable volume list.
- Keep selected volume names in Zustand, not component-local layout state.
- Disable “下载所选” when nothing is selected.
- Display operation errors with `message` and `action`; keep technical details collapsed.

- [ ] **Step 5: Run frontend and Python bridge tests**

Run: `npm run test -- --run` in `frontend`  
Run: `npm run build` in `frontend`  
Run: `python -m pytest -q tests/test_desktop_bridge.py tests/test_desktop_controller.py`  
Expected: all tests and build pass.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/features/workbench frontend/src/app/AppRouter.tsx frontend/src/store/desktop.ts
git commit -m "feat: migrate reading workbench to React"
```

---

### Task 7: Connect Task Recovery and Browser Profile Verification

**Files:**
- Modify: `linodl/desktop/bridge.py`
- Modify: `linodl/desktop/controller.py`
- Create: `linodl/desktop/profile.py`
- Modify: `tests/test_desktop_bridge.py`
- Modify: `frontend/src/components/TaskInspector.tsx`
- Create: `frontend/src/components/TaskInspector.test.tsx`
- Create: `frontend/src/features/profile/ProfilePage.tsx`
- Create: `frontend/src/features/profile/ProfilePage.test.tsx`
- Modify: `frontend/src/store/desktop.ts`

**Interfaces:**
- Consumes: `cancel_task`, `VerificationService`, persistent profile coordinator, task input snapshots.
- Produces: `check_profile()`, `start_manual_verification(target_url)`, `restart_task(task_id)`, and profile health DTO.

- [ ] **Step 1: Write failing bridge and component tests**

```python
def test_bootstrap_never_reports_unknown_profile_as_healthy(tmp_path):
    bridge = DesktopBridge(
        ConfigManager(str(tmp_path / "settings.ini")),
        controller=FakeController(),
    )

    payload = bridge.bootstrap()

    assert payload["profile"]["status"] in {"unknown", "checking", "healthy", "needs_verification", "busy", "error"}
    assert payload["profile"]["status"] != "healthy"
```

```tsx
it("shows a verification action for a waiting task", () => {
  render(
    <TaskInspector
      tasks={[{
        id: "1",
        title: "读取目录",
        status: "waiting_for_verification",
        detail: "等待用户验证",
        progress: 0.2,
      }] as never}
    />,
  );

  expect(screen.getByRole("button", { name: "打开人工验证" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m pytest -q tests/test_desktop_bridge.py -k profile`  
Run: `npm run test -- --run src/components/TaskInspector.test.tsx src/features/profile/ProfilePage.test.tsx` in `frontend`  
Expected: FAIL because profile and recovery methods do not exist.

- [ ] **Step 3: Implement profile commands**

The default bootstrap profile state is `unknown`. `check_profile()` starts a background operation that opens CloakBrowser headlessly and verifies a normal target page. `start_manual_verification()` uses the existing visible `VerificationService`; it does not solve CAPTCHA automatically.

- [ ] **Step 4: Implement task recovery commands**

`restart_task(task_id)` reads `TaskInputSnapshot` and dispatches:

- `search` with `query`
- `catalog` with `url`
- `download` only when cached catalog data still exists; otherwise return `CATALOG_RELOAD_REQUIRED`
- `warmup` without additional input

Return an actionable error for unsupported or missing snapshots.

- [ ] **Step 5: Implement task inspector and profile page**

Show active, waiting, failed, and recently completed tasks. Actions are status-specific:

- running → cancel
- waiting for verification → open verification
- failed/cancelled → restore input or restart
- completed → view result

Do not rerender unchanged tasks; select by `taskVersion`.

- [ ] **Step 6: Run focused and complete task tests**

Run: `python -m pytest -q tests/test_desktop_bridge.py tests/test_desktop_controller.py tests/test_gui_tasks.py tests/test_browser_helpers.py`  
Run: `npm run test -- --run` in `frontend`  
Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add linodl/desktop frontend/src/components frontend/src/features/profile frontend/src/store tests/test_desktop_bridge.py
git commit -m "feat: add desktop task recovery and profile verification"
```

---

### Task 8: Migrate Verification, Archive, Export, and Settings Pages

**Files:**
- Create: `linodl/desktop/archive.py`
- Modify: `linodl/desktop/bridge.py`
- Create: `tests/test_desktop_archive.py`
- Modify: `tests/test_desktop_bridge.py`
- Create: `frontend/src/features/verify/VerifyPage.tsx`
- Create: `frontend/src/features/archive/ArchivePage.tsx`
- Create: `frontend/src/features/settings/SettingsPage.tsx`
- Create: `frontend/src/features/settings/SettingsPage.test.tsx`
- Modify: `frontend/src/app/AppRouter.tsx`
- Modify: `frontend/src/store/desktop.ts`

**Interfaces:**
- Consumes: `scan_download_directories`, `VerifyWorker`, `ExportWorker`, `ConfigManager.update_settings`.
- Produces: `list_archives()`, `start_verify()`, `start_export()`, `get_settings()`, `save_settings()`, `choose_directory()`, `open_directory()`.

- [ ] **Step 1: Write failing archive and settings tests**

```python
# tests/test_desktop_archive.py
from linodl.desktop.archive import scan_archives


def test_scan_archives_ignores_files_and_reports_chapter_count(tmp_path):
    book = tmp_path / "作品 A"
    volume = book / "第一卷"
    volume.mkdir(parents=True)
    (volume / "001 序章.txt").write_text("正文", encoding="utf-8")
    (tmp_path / "note.txt").write_text("ignore", encoding="utf-8")

    archives = scan_archives(tmp_path)

    assert archives == [{
        "id": "作品 A",
        "title": "作品 A",
        "path": str(book),
        "volume_count": 1,
        "chapter_count": 1,
    }]
```

```tsx
it("disables GeoIP until a proxy is entered", () => {
  render(<SettingsPage model={{ settings: { proxy: "", geoip: false } } as never} />);
  expect(screen.getByRole("checkbox", { name: "根据代理匹配地理位置" })).toBeDisabled();
});
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m pytest -q tests/test_desktop_archive.py tests/test_desktop_bridge.py -k settings`  
Run: `npm run test -- --run src/features/settings/SettingsPage.test.tsx` in `frontend`  
Expected: FAIL because archive and settings APIs do not exist.

- [ ] **Step 3: Implement safe desktop utility methods**

- `choose_directory()` uses the attached pywebview window dialog.
- `open_directory()` resolves the target, requires it to be the configured output directory or a descendant, and then opens it with `os.startfile`.
- `get_settings()` never returns the password; return `has_password: bool`.
- `save_settings()` accepts an empty password as “keep existing password” unless `clear_password` is true.
- `list_archives()` returns only directories below the configured output directory.

- [ ] **Step 4: Implement the three pages**

- Verification page: directory picker, archive selection, verification result summary, issue list.
- Archive page: compact archive rows, chapter/volume counts, export action, open folder.
- Settings page: output/profile directories, proxy, GeoIP, headless mode, anti-bot mode, theme, credential presence.

Use the same task inspector for verify and export progress.

- [ ] **Step 5: Run tests and build**

Run: `python -m pytest -q tests/test_desktop_archive.py tests/test_desktop_bridge.py tests/test_config_manager.py`  
Run: `npm run test -- --run` in `frontend`  
Run: `npm run build` in `frontend`  
Expected: all tests and build pass.

- [ ] **Step 6: Commit**

```powershell
git add linodl/desktop frontend/src/features frontend/src/app/AppRouter.tsx frontend/src/store tests/test_desktop_archive.py tests/test_desktop_bridge.py
git commit -m "feat: migrate desktop utility pages to React"
```

---

### Task 9: Make React the Default GUI and Persist Window State

**Files:**
- Create: `linodl/desktop/window_state.py`
- Create: `tests/test_window_state.py`
- Modify: `linodl/desktop/app.py`
- Modify: `linodl/__main__.py`
- Modify: `run_gui.bat`
- Modify: `README.md`

**Interfaces:**
- Consumes: pywebview window lifecycle, `ConfigManager`.
- Produces: `WindowStateStore.load() -> WindowState`; `WindowStateStore.save(WindowState) -> None`; `--gui` React entry and `--legacy-gui` fallback.

- [ ] **Step 1: Write failing window-state tests**

```python
# tests/test_window_state.py
from linodl.desktop.window_state import WindowState, WindowStateStore


def test_window_state_clamps_invalid_saved_bounds(tmp_path):
    store = WindowStateStore(tmp_path / "window.json")
    store.save(WindowState(width=300, height=200, x=-99999, y=-99999, maximized=False))

    state = store.load()

    assert state.width >= 900
    assert state.height >= 640
    assert state.x is None
    assert state.y is None


def test_window_state_round_trips_maximized_state(tmp_path):
    store = WindowStateStore(tmp_path / "window.json")
    store.save(WindowState(width=1280, height=820, x=50, y=50, maximized=True))

    assert store.load().maximized is True
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m pytest -q tests/test_window_state.py`  
Expected: FAIL because the store does not exist.

- [ ] **Step 3: Implement atomic window-state persistence**

Store JSON beside the existing INI file as `~/.linodl-window.json`. Save normal bounds, not maximized screen bounds. Use a temporary file and `os.replace()`. Clamp width and height to the minimum and discard positions far outside reasonable desktop coordinates.

- [ ] **Step 4: Update entrypoints**

`python -m linodl --gui` imports and calls `run_desktop()`.  
`python -m linodl --legacy-gui` imports and runs `MainWindow`.  
`run_gui.bat` checks Python requirements, builds the frontend only when `frontend/dist/index.html` is missing, and then runs `python -m linodl --gui`.

Do not run `npm install` on every launch.

Register a `window.events.closing` handler. When `task_store.snapshot()` contains a non-terminal task, cancel the native close event and call `window.evaluate_js("window.linodlConfirmClose()")`. The React handler presents “仍有任务正在运行” with “继续等待” and “确认退出”; the confirmed action calls `DesktopBridge.force_close()`, which marks the next native closing event as allowed. When no active task exists, close immediately.

- [ ] **Step 5: Document development and production launch**

README commands:

```powershell
pip install -r requirements.txt
Set-Location frontend
npm install
npm run build
Set-Location ..
python -m linodl --gui
```

Document `--legacy-gui` as a temporary fallback and `LINODL_FRONTEND_URL=http://localhost:5173` for development only.

- [ ] **Step 6: Run entrypoint and state tests**

Run: `python -m pytest -q tests/test_window_state.py tests/test_desktop_assets.py`  
Run: `npm run build` in `frontend`  
Run: `python -m linodl --gui` and close the window normally after confirming it appears.  
Expected: React desktop window opens at valid saved bounds.

- [ ] **Step 7: Commit**

```powershell
git add linodl/desktop/window_state.py linodl/desktop/app.py linodl/__main__.py run_gui.bat README.md tests/test_window_state.py
git commit -m "feat: make React the default desktop UI"
```

---

### Task 10: Final Responsive and Regression Verification

**Files:**
- Modify only files required by failures found in this task.
- Test: complete Python and frontend suites.

**Interfaces:**
- Consumes: completed Tasks 1–9.
- Produces: verified desktop build with no known basic windowed or maximized layout failure.

- [ ] **Step 1: Run the complete automated suites**

Run: `python -m pytest -q`  
Expected: all Python tests pass.

Run: `python -m compileall -q linodl tests`  
Expected: exit code 0 with no output.

Run: `npm run typecheck` in `frontend`  
Run: `npm run test -- --run` in `frontend`  
Run: `npm run build` in `frontend`  
Expected: type check, tests, and production build pass.

- [ ] **Step 2: Run desktop smoke checks**

Launch: `python -m linodl --gui`

Verify at normal size:

- navigation switches all five pages;
- search field, primary action, and task inspector are visible;
- no unexpected external browser opens.

Maximize the same window and verify:

- content remains centered and bounded;
- the main stage and inspector remain readable;
- no input or empty state stretches across the entire screen;
- no horizontal scroll bar or clipped action appears.

Restore to normal size and verify the layout returns without restarting.

- [ ] **Step 3: Run business smoke checks**

- Enter a search query and confirm a task appears.
- Cancel before completion and confirm the task reaches cancelled state.
- Open the browser profile page without starting manual verification.
- Run the existing isolated CloakBrowser `about:blank` smoke script.

Do not perform a full novel download for basic acceptance.

- [ ] **Step 4: Check change scope**

Run: `git diff --check`  
Run: `git status --short`  
Run: `git diff --stat bd2ad93..HEAD`  
Expected: no whitespace errors; only planned UI, bridge, tests, docs, and dependency files are changed. Existing user-owned untracked files remain untouched.

- [ ] **Step 5: Commit verification fixes if needed**

If Step 1–4 required code changes:

```powershell
git add -- frontend linodl/desktop linodl/__main__.py run_gui.bat README.md requirements.txt tests
git commit -m "fix: resolve final React desktop verification issues"
```

If no files changed, do not create an empty commit.
