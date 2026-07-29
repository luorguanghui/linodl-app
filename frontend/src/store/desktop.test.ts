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
});
