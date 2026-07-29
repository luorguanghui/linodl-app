import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createDesktopStore,
  startPolling,
  stopPolling,
  useDesktopStore,
} from "./desktop";
import type { BootstrapDto, BridgeOperationResult } from "../api/types";

const snapshot: BootstrapDto = {
  task_version: 0,
  tasks: [],
  operation_version: 0,
  operations: {},
  config: {},
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function flushPromises() {
  for (let index = 0; index < 5; index += 1) {
    await Promise.resolve();
  }
}

describe("desktop store", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    stopPolling();
    useDesktopStore.setState({
      tasks: [],
      taskVersion: -1,
      operations: {},
      operationVersion: -1,
      activeOperationId: null,
      activeOperationKind: null,
      selectedVolumes: [],
      pendingCancellationIds: [],
      pendingRestartIds: [],
      profile: { status: "unknown", detail: "" },
      settings: {},
      notice: null,
    });
  });

  afterEach(() => {
    stopPolling();
    delete window.pywebview;
    vi.restoreAllMocks();
    vi.useRealTimers();
    delete document.documentElement.dataset.theme;
  });

  it("keeps existing tasks when the bridge reports no version change", async () => {
    const api = {
      poll: vi
        .fn()
        .mockResolvedValueOnce({
          task_version: 2,
          tasks: [
            {
              id: "1",
              title: "下载",
              status: "running",
              detail: "",
              progress: 0.5,
              input_snapshot: null,
              error_detail: "",
            },
          ],
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
        error: {
          code: "INVALID_QUERY",
          message: "请输入作品名。",
          action: "输入后重试。",
        },
      }),
    };
    const store = createDesktopStore(api as never);

    await store.getState().search("");

    expect(store.getState().notice).toEqual({
      code: "INVALID_QUERY",
      message: "请输入作品名。",
      action: "输入后重试。",
    });
  });

  it("deduplicates cancellation while the bridge request is pending", async () => {
    const request = deferred<{ ok: true }>();
    const cancel = vi.fn().mockReturnValue(request.promise);
    const store = createDesktopStore({ cancel } as never);

    const first = store.getState().cancelTask("task-1");
    const second = store.getState().cancelTask("task-1");

    expect(store.getState().pendingCancellationIds).toEqual(["task-1"]);
    expect(cancel).toHaveBeenCalledTimes(1);

    request.resolve({ ok: true });
    await Promise.all([first, second]);

    expect(store.getState().pendingCancellationIds).toEqual([]);
  });

  it("deduplicates restart while pending and clears the guard after failure", async () => {
    const firstRequest = deferred<BridgeOperationResult>();
    const restartTask = vi
      .fn()
      .mockReturnValueOnce(firstRequest.promise)
      .mockResolvedValueOnce({ ok: true, operation_id: "retry-operation" });
    const store = createDesktopStore({ restartTask } as never);

    const first = store.getState().restartTask("task-1");
    const duplicate = store.getState().restartTask("task-1");

    expect(store.getState().pendingRestartIds).toEqual(["task-1"]);
    expect(restartTask).toHaveBeenCalledTimes(1);

    firstRequest.resolve(Promise.reject(new Error("restart failed")) as never);
    await Promise.all([first, duplicate]);

    expect(store.getState().pendingRestartIds).toEqual([]);

    await store.getState().restartTask("task-1");

    expect(restartTask).toHaveBeenCalledTimes(2);
    expect(store.getState().pendingRestartIds).toEqual([]);
  });

  it("keeps selected volume names in the desktop store", () => {
    const store = createDesktopStore({} as never);

    store.getState().toggleVolume("第一卷");
    store.getState().toggleVolume("第二卷");
    store.getState().toggleVolume("第一卷");

    expect(store.getState().selectedVolumes).toEqual(["第二卷"]);
  });

  it("keeps the newest operation id when repeated searches resolve out of order", async () => {
    const first = deferred<BridgeOperationResult>();
    const second = deferred<BridgeOperationResult>();
    const api = {
      startSearch: vi
        .fn()
        .mockReturnValueOnce(first.promise)
        .mockReturnValueOnce(second.promise),
    };
    const store = createDesktopStore(api as never);

    const firstCommand = store.getState().search("旧查询");
    const secondCommand = store.getState().search("新查询");
    second.resolve({ ok: true, operation_id: "new-operation" });
    await secondCommand;
    first.resolve({ ok: true, operation_id: "old-operation" });
    await firstCommand;

    expect(store.getState().activeOperationId).toBe("new-operation");
    expect(store.getState().activeOperationKind).toBe("search");
  });

  it("ignores an older search error after a newer catalog command succeeds", async () => {
    const search = deferred<BridgeOperationResult>();
    const catalog = deferred<BridgeOperationResult>();
    const api = {
      startSearch: vi.fn().mockReturnValue(search.promise),
      loadCatalog: vi.fn().mockReturnValue(catalog.promise),
    };
    const store = createDesktopStore(api as never);

    const searchCommand = store.getState().search("旧查询");
    const catalogCommand = store
      .getState()
      .loadCatalog("https://www.linovelib.com/novel/42/catalog");
    catalog.resolve({ ok: true, operation_id: "catalog-operation" });
    await catalogCommand;
    search.resolve({
      ok: false,
      error: {
        code: "OLD_SEARCH_FAILED",
        message: "旧查询失败。",
        action: "不应显示。",
      },
    });
    await searchCommand;

    expect(store.getState().activeOperationId).toBe("catalog-operation");
    expect(store.getState().activeOperationKind).toBe("catalog");
    expect(store.getState().notice).toBeNull();
  });

  it("does not expose an unstructured error message in the notice", async () => {
    const store = createDesktopStore({
      poll: vi.fn().mockRejectedValue(new Error("token=secret-value")),
    } as never);

    await store.getState().pollOnce();

    expect(store.getState().notice).toMatchObject({
      code: "DESKTOP_API_UNAVAILABLE",
    });
    expect(store.getState().notice?.message).not.toContain("secret-value");
  });

  it("loads archives and tracks verify and export operations separately", async () => {
    const api = {
      listArchives: vi.fn().mockResolvedValue({
        ok: true,
        archives: [
          {
            id: "作品 A",
            title: "作品 A",
            path: "C:\\books\\作品 A",
            volume_count: 1,
            chapter_count: 12,
          },
        ],
      }),
      startVerify: vi.fn().mockResolvedValue({
        ok: true,
        operation_id: "verify-1",
      }),
      startExport: vi.fn().mockResolvedValue({
        ok: true,
        operation_id: "export-1",
      }),
    };
    const store = createDesktopStore(api as never);

    await store.getState().loadArchives();
    await store.getState().startVerify("作品 A");
    await store.getState().startExport("作品 A", true);

    expect(store.getState().archives).toHaveLength(1);
    expect(store.getState().activeVerifyOperationId).toBe("verify-1");
    expect(store.getState().activeExportOperationId).toBe("export-1");
  });

  it("loads and saves credential-safe settings through typed actions", async () => {
    const api = {
      getSettings: vi.fn().mockResolvedValue({
        ok: true,
        settings: {
          username: "reader",
          has_password: true,
          output_dir: "C:\\books",
          proxy: "",
          geoip: false,
        },
      }),
      saveSettings: vi.fn().mockResolvedValue({ ok: true }),
    };
    const store = createDesktopStore(api as never);

    await store.getState().loadSettings();
    const saved = await store.getState().saveSettings({
      ...store.getState().settings,
      clear_proxy: false,
      password: "",
      clear_password: false,
    });

    expect(saved).toBe(true);
    expect(store.getState().settings.has_password).toBe(true);
    expect(api.saveSettings).toHaveBeenCalledWith(
      expect.objectContaining({ password: "", clear_password: false }),
    );
  });

  it("applies the bootstrapped theme to the document root", async () => {
    const store = createDesktopStore({
      bootstrap: vi.fn().mockResolvedValue({
        ...snapshot,
        config: { theme: "dark" },
      }),
    } as never);

    await store.getState().bootstrap();

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });

  it("applies saved light and auto themes without retaining credentials", async () => {
    const saveSettings = vi.fn().mockResolvedValue({ ok: true });
    const store = createDesktopStore({ saveSettings } as never);

    await store.getState().saveSettings({
      theme: "light",
      proxy: "",
      clear_proxy: false,
      password: "",
      clear_password: false,
    });
    expect(document.documentElement).toHaveAttribute("data-theme", "light");

    await store.getState().saveSettings({
      theme: "auto",
      proxy: "",
      clear_proxy: false,
      password: "",
      clear_password: false,
    });
    expect(document.documentElement).toHaveAttribute("data-theme", "auto");
    expect(store.getState().settings).not.toHaveProperty("password");
  });

  it("activates completed verify and export results from the global inspector", () => {
    const store = createDesktopStore({} as never);
    store.setState({
      operations: {
        "verify-1": {
          id: "verify-1",
          kind: "verify",
          task_id: "task-verify",
          status: "completed",
          detail: "",
          result: {},
          error: "",
        },
        "export-1": {
          id: "export-1",
          kind: "export",
          task_id: "task-export",
          status: "completed",
          detail: "",
          result: [],
          error: "",
        },
      },
    });

    expect(store.getState().viewTaskResult("task-verify")).toBe(true);
    expect(store.getState().activeVerifyOperationId).toBe("verify-1");
    expect(store.getState().viewTaskResult("task-export")).toBe(true);
    expect(store.getState().activeExportOperationId).toBe("export-1");
  });

  it("does not restart polling after stop during an in-flight poll", async () => {
    const pendingPoll = deferred<typeof snapshot>();
    const poll = vi.fn().mockReturnValue(pendingPoll.promise);
    window.pywebview = { api: { bootstrap: vi.fn().mockResolvedValue(snapshot), poll } };

    startPolling();
    await flushPromises();
    vi.advanceTimersByTime(500);
    await flushPromises();
    expect(poll).toHaveBeenCalledTimes(1);

    stopPolling();
    pendingPoll.resolve(snapshot);
    await flushPromises();
    vi.advanceTimersByTime(2_001);

    expect(poll).toHaveBeenCalledTimes(1);
  });

  it("does not create a second timer when visibility changes during a poll", async () => {
    const pendingPoll = deferred<typeof snapshot>();
    const poll = vi
      .fn()
      .mockReturnValueOnce(pendingPoll.promise)
      .mockResolvedValue(snapshot);
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
    window.pywebview = { api: { bootstrap: vi.fn().mockResolvedValue(snapshot), poll } };

    startPolling();
    await flushPromises();
    vi.advanceTimersByTime(500);
    await flushPromises();
    hidden.mockReturnValue(true);
    document.dispatchEvent(new Event("visibilitychange"));
    pendingPoll.resolve(snapshot);
    await flushPromises();
    vi.advanceTimersByTime(2_000);
    await flushPromises();

    expect(poll).toHaveBeenCalledTimes(2);
  });

  it("waits for bootstrap before it starts polling", async () => {
    const pendingBootstrap = deferred<typeof snapshot>();
    const poll = vi.fn().mockResolvedValue(snapshot);
    window.pywebview = {
      api: { bootstrap: vi.fn().mockReturnValue(pendingBootstrap.promise), poll },
    };

    startPolling();
    vi.advanceTimersByTime(2_000);
    await flushPromises();

    expect(poll).not.toHaveBeenCalled();

    pendingBootstrap.resolve(snapshot);
    await flushPromises();
    vi.advanceTimersByTime(500);
    await flushPromises();

    expect(poll).toHaveBeenCalledTimes(1);
  });

  it("does not let an older poll overwrite a newer generation", async () => {
    const oldPoll = deferred<typeof snapshot>();
    const poll = vi
      .fn()
      .mockReturnValueOnce(oldPoll.promise)
      .mockResolvedValue({
        ...snapshot,
        task_version: 2,
        tasks: [
          {
            id: "new-task",
            title: "newer result",
            status: "running",
            detail: "",
            progress: 0,
            input_snapshot: null,
            error_detail: "",
          },
        ],
      });
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
    window.pywebview = { api: { bootstrap: vi.fn().mockResolvedValue(snapshot), poll } };

    startPolling();
    await flushPromises();
    vi.advanceTimersByTime(500);
    await flushPromises();
    hidden.mockReturnValue(true);
    document.dispatchEvent(new Event("visibilitychange"));
    vi.advanceTimersByTime(2_000);
    await flushPromises();
    oldPoll.resolve({
      ...snapshot,
      task_version: 1,
      tasks: [
        {
          id: "old-task",
          title: "older result",
          status: "running",
          detail: "",
          progress: 0,
          input_snapshot: null,
          error_detail: "",
        },
      ],
    });
    await flushPromises();

    expect(useDesktopStore.getState().tasks[0]?.title).toBe("newer result");
  });

  it("does not let a stopped bootstrap overwrite a later start", async () => {
    const oldBootstrap = deferred<typeof snapshot>();
    const bootstrap = vi
      .fn()
      .mockReturnValueOnce(oldBootstrap.promise)
      .mockResolvedValueOnce({ ...snapshot, config: { theme: "new" } });
    window.pywebview = {
      api: { bootstrap, poll: vi.fn().mockResolvedValue(snapshot) },
    };

    startPolling();
    stopPolling();
    startPolling();
    await flushPromises();
    oldBootstrap.resolve({ ...snapshot, config: { theme: "old" } });
    await flushPromises();

    expect(useDesktopStore.getState().settings.theme).toBe("new");
  });

  it("does not let an invalidated poll error replace the current notice", async () => {
    const oldPoll = deferred<typeof snapshot>();
    const poll = vi
      .fn()
      .mockReturnValueOnce(oldPoll.promise)
      .mockResolvedValue(snapshot);
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
    window.pywebview = { api: { bootstrap: vi.fn().mockResolvedValue(snapshot), poll } };

    startPolling();
    await flushPromises();
    vi.advanceTimersByTime(500);
    await flushPromises();
    hidden.mockReturnValue(true);
    document.dispatchEvent(new Event("visibilitychange"));
    vi.advanceTimersByTime(2_000);
    await flushPromises();
    oldPoll.resolve(Promise.reject(new Error("stale failure")) as never);
    await flushPromises();

    expect(useDesktopStore.getState().notice).toBeNull();
  });
});
