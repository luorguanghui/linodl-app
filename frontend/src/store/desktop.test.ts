import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createDesktopStore,
  startPolling,
  stopPolling,
  useDesktopStore,
} from "./desktop";
import type { BootstrapDto } from "../api/types";

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
      profile: "unknown",
      settings: {},
      notice: null,
    });
  });

  afterEach(() => {
    stopPolling();
    delete window.pywebview;
    vi.restoreAllMocks();
    vi.useRealTimers();
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

  it("keeps selected volume names in the desktop store", () => {
    const store = createDesktopStore({} as never);

    store.getState().toggleVolume("第一卷");
    store.getState().toggleVolume("第二卷");
    store.getState().toggleVolume("第一卷");

    expect(store.getState().selectedVolumes).toEqual(["第二卷"]);
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
