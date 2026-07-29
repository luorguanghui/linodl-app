import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { stopPolling, useDesktopStore } from "../store/desktop";
import { DesktopShell } from "./DesktopShell";

const emptySnapshot = {
  task_version: 0,
  tasks: [],
  operation_version: 0,
  operations: {},
  config: {},
};

async function flushPromises() {
  for (let index = 0; index < 5; index += 1) {
    await Promise.resolve();
  }
}

afterEach(() => {
  cleanup();
  stopPolling();
  delete window.pywebview;
  vi.useRealTimers();
  useDesktopStore.setState({
    tasks: [],
    taskVersion: -1,
    operations: {},
    operationVersion: -1,
    activeOperationId: null,
    activeOperationKind: null,
    selectedVolumes: [],
    pendingCancellationIds: [],
    profile: { status: "unknown", detail: "" },
    settings: {},
    notice: null,
  });
});

describe("DesktopShell", () => {
  it("keeps the global task inspector when navigating", () => {
    render(<DesktopShell />);
    expect(
      screen.getByRole("complementary", { name: "任务检查器" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "内容校验" }));

    expect(
      screen.getByRole("heading", { name: "内容校验" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "任务检查器" }),
    ).toBeInTheDocument();
  });

  it("marks the current navigation item", () => {
    render(<DesktopShell />);

    expect(
      screen.getByRole("button", { name: "阅读工作台" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("starts polling on mount and stops scheduling work after unmount", async () => {
    vi.useFakeTimers();
    const bootstrap = vi.fn().mockResolvedValue(emptySnapshot);
    const poll = vi.fn().mockResolvedValue(emptySnapshot);
    window.pywebview = { api: { bootstrap, poll } };

    const { unmount } = render(<DesktopShell />);
    await act(flushPromises);

    expect(bootstrap).toHaveBeenCalledTimes(1);

    unmount();
    await act(async () => {
      vi.advanceTimersByTime(2_000);
      await flushPromises();
    });

    expect(poll).not.toHaveBeenCalled();
  });
});
