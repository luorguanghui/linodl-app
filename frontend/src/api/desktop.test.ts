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
      profile: { status: "unknown", detail: "" },
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

  it("maps utility commands to the stable pywebview method names", async () => {
    const listArchives = vi.fn().mockResolvedValue({ ok: true, archives: [] });
    const startVerify = vi.fn().mockResolvedValue({
      ok: true,
      operation_id: "verify-1",
    });
    const startRetry = vi.fn().mockResolvedValue({
      ok: true,
      operation_id: "retry-1",
    });
    const startExport = vi.fn().mockResolvedValue({
      ok: true,
      operation_id: "export-1",
    });
    (window as TestWindow).pywebview = {
      api: {
        list_archives: listArchives,
        start_verify: startVerify,
        start_retry: startRetry,
        start_export: startExport,
      },
    };

    await desktopApi.listArchives();
    await desktopApi.startVerify("作品 A");
    await desktopApi.startRetry("verify-1");
    await desktopApi.startExport("作品 A", true);

    expect(listArchives).toHaveBeenCalledWith();
    expect(startVerify).toHaveBeenCalledWith("作品 A");
    expect(startRetry).toHaveBeenCalledWith("verify-1");
    expect(startExport).toHaveBeenCalledWith("作品 A", true);
  });
});
