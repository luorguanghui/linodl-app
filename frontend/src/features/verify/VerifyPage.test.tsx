import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VerifyPage } from "./VerifyPage";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("VerifyPage", () => {
  it("requires an archive selection before verification starts", () => {
    render(
      <VerifyPage
        model={{
          archives: [],
          outputDir: "C:\\books",
          loadArchives: vi.fn(),
          chooseDirectory: vi.fn(),
          startVerify: vi.fn(),
        } as never}
      />,
    );

    expect(
      screen.getByRole("button", { name: "开始校验" }),
    ).toBeDisabled();
  });

  it("starts verification for the selected archive", () => {
    const startVerify = vi.fn();
    render(
      <VerifyPage
        model={{
          archives: [
            {
              id: "作品 A",
              title: "作品 A",
              path: "C:\\books\\作品 A",
              volume_count: 1,
              chapter_count: 12,
            },
          ],
          outputDir: "C:\\books",
          loadArchives: vi.fn(),
          chooseDirectory: vi.fn(),
          startVerify,
        } as never}
      />,
    );

    fireEvent.click(screen.getByRole("radio", { name: /作品 A/ }));
    fireEvent.click(screen.getByRole("button", { name: "开始校验" }));

    expect(startVerify).toHaveBeenCalledWith("作品 A");
  });

  it("renders the verification summary and issue list", () => {
    render(
      <VerifyPage
        model={{
          archives: [],
          outputDir: "C:\\books",
          loadArchives: vi.fn(),
          chooseDirectory: vi.fn(),
          startVerify: vi.fn(),
          verification: {
            total_expected: 12,
            complete: 11,
            issue_count: 1,
            is_clean: false,
            issues: [
              {
                volume_name: "第一卷",
                chapter_index: 3,
                chapter_title: "缺失章节",
                issue: "missing",
                detail: "未找到章节文件",
              },
            ],
          },
        } as never}
      />,
    );

    expect(screen.getByText("11 / 12")).toBeVisible();
    expect(screen.getByText("缺失章节")).toBeVisible();
    expect(screen.getByText("未找到章节文件")).toBeVisible();
  });

  it("retries all recoverable verification issues", () => {
    const startRetry = vi.fn();
    render(
      <VerifyPage
        model={{
          archives: [],
          outputDir: "C:\\books",
          loadArchives: vi.fn(),
          chooseDirectory: vi.fn(),
          startVerify: vi.fn(),
          startRetry,
          operation: {
            id: "verify-1",
            kind: "verify",
            task_id: "task-1",
            status: "completed",
            detail: "",
            result: {},
            error: "",
          },
          verification: {
            issue_count: 2,
            is_clean: false,
            issues: [
              {
                chapter_title: "recoverable chapter",
                chapter_url: "/novel/1/1.html",
                issue: "missing",
              },
              {
                chapter_title: "legacy chapter",
                issue: "missing",
              },
            ],
          },
        } as never}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry recoverable issues" }));

    expect(startRetry).toHaveBeenCalledWith("verify-1");
    expect(screen.getByText(/无法自动重试/)).toBeVisible();
  });
});
