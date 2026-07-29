import { afterEach, describe, expect, it, vi } from "vitest";

import { desktopApi } from "./desktop";

type TestWindow = Window & {
  pywebview?: { api: Record<string, (...args: unknown[]) => Promise<unknown>> };
};

describe("desktop API", () => {
  afterEach(() => {
    delete (window as TestWindow).pywebview;
  });

  it("uses empty bootstrap data in development without pywebview", async () => {
    await expect(desktopApi.bootstrap()).resolves.toEqual({
      task_version: 0,
      tasks: [],
      operation_version: 0,
      operations: {},
      config: {},
    });
  });

  it("maps poll arguments to the pywebview bridge", async () => {
    const poll = vi.fn().mockResolvedValue({
      task_version: 4,
      tasks: [],
      operation_version: 7,
      operations: {},
    });
    (window as TestWindow).pywebview = { api: { poll } };

    await expect(desktopApi.poll(3, 6)).resolves.toMatchObject({
      task_version: 4,
      operation_version: 7,
    });

    expect(poll).toHaveBeenCalledWith(3, 6);
  });
});
