import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TaskDto } from "../api/types";
import { useDesktopStore } from "../store/desktop";
import { TaskInspector } from "./TaskInspector";

function task(overrides: Partial<TaskDto>): TaskDto {
  return {
    id: "task-1",
    title: "读取目录",
    status: "running",
    detail: "",
    progress: 0.2,
    input_snapshot: null,
    error_detail: "",
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

afterEach(() => {
  cleanup();
  delete window.pywebview;
  useDesktopStore.setState({
    tasks: [],
    taskVersion: -1,
    pendingCancellationIds: [],
    notice: null,
  });
  vi.restoreAllMocks();
});

describe("TaskInspector", () => {
  it("shows a verification action for a waiting task", () => {
    render(
      <TaskInspector
        tasks={[
          task({
            status: "waiting_for_verification",
            detail: "等待用户验证",
          }),
        ]}
      />,
    );

    expect(
      screen.getByRole("button", { name: "打开人工验证" }),
    ).toBeInTheDocument();
  });

  it("disables cancellation immediately and prevents duplicate requests", async () => {
    const pending = deferred<{ ok: true }>();
    const cancel = vi.fn().mockReturnValue(pending.promise);
    window.pywebview = { api: { cancel } };

    render(<TaskInspector tasks={[task({ status: "running" })]} />);
    const button = screen.getByRole("button", { name: "取消读取目录" });

    fireEvent.click(button);
    fireEvent.click(button);
    await act(async () => {
      await Promise.resolve();
    });

    expect(button).toBeDisabled();
    expect(cancel).toHaveBeenCalledTimes(1);

    await act(async () => {
      pending.resolve({ ok: true });
      await pending.promise;
    });

    expect(button).not.toBeDisabled();
  });

  it("shows restart and result actions only for recoverable task states", async () => {
    const restartTask = vi.fn().mockResolvedValue({
      ok: true,
      operation_id: "restarted-operation",
    });
    window.pywebview = { api: { restart_task: restartTask } };
    render(
      <TaskInspector
        tasks={[
          task({ id: "failed", status: "failed" }),
          task({ id: "done", title: "已完成", status: "completed" }),
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: "重新开始读取目录" })).toBeVisible();
    expect(screen.getByRole("button", { name: "查看已完成结果" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "取消读取目录" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "重新开始读取目录" }));
    await waitFor(() => expect(restartTask).toHaveBeenCalledWith("failed"));
  });
});
