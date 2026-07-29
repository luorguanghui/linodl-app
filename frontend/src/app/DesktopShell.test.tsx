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
    pendingRestartIds: [],
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

  it("returns to the workbench and activates a completed task result", () => {
    useDesktopStore.setState({
      tasks: [
        {
          id: "task-completed",
          title: "已完成目录",
          status: "completed",
          detail: "完成",
          progress: 1,
          input_snapshot: null,
          error_detail: "",
        },
      ],
      taskVersion: 1,
      operations: {
        "operation-completed": {
          id: "operation-completed",
          kind: "catalog",
          task_id: "task-completed",
          status: "completed",
          detail: "完成",
          result: [],
          error: "",
        },
      },
      operationVersion: 1,
    });
    render(<DesktopShell />);
    fireEvent.click(screen.getByRole("button", { name: "内容校验" }));

    expect(
      screen.getByRole("heading", { name: "内容校验" }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "查看已完成目录结果" }),
    );

    expect(
      screen.getByRole("heading", { name: "阅读工作台" }),
    ).toBeInTheDocument();
    expect(useDesktopStore.getState().activeOperationId).toBe(
      "operation-completed",
    );
  });

  it("opens completed verification results on the verification page", () => {
    useDesktopStore.setState({
      tasks: [
        {
          id: "task-verify",
          title: "校验下载内容",
          status: "completed",
          detail: "完成",
          progress: 1,
          input_snapshot: null,
          error_detail: "",
        },
      ],
      operations: {
        "operation-verify": {
          id: "operation-verify",
          kind: "verify",
          task_id: "task-verify",
          status: "completed",
          detail: "完成",
          result: {
            total_expected: 1,
            complete: 1,
            issue_count: 0,
            is_clean: true,
            issues: [],
          },
          error: "",
        },
      },
    });
    render(<DesktopShell />);

    fireEvent.click(
      screen.getByRole("button", { name: "查看校验下载内容结果" }),
    );

    expect(
      screen.getByRole("heading", { name: "内容校验" }),
    ).toBeInTheDocument();
    expect(useDesktopStore.getState().activeVerifyOperationId).toBe(
      "operation-verify",
    );
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
