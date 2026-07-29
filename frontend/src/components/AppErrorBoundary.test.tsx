import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppErrorBoundary } from "./AppErrorBoundary";

let shouldThrow = true;

function UnstablePage() {
  if (shouldThrow) {
    throw new Error("render failed");
  }

  return <h1>页面已恢复</h1>;
}

afterEach(() => {
  shouldThrow = true;
  vi.restoreAllMocks();
});

describe("AppErrorBoundary", () => {
  it("replaces only the failed page and retries it on request", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <>
        <nav aria-label="书脊导航">导航仍在</nav>
        <AppErrorBoundary>
          <UnstablePage />
        </AppErrorBoundary>
        <aside aria-label="任务检查器">任务仍在</aside>
      </>,
    );

    expect(
      screen.getByRole("heading", { name: "此页面暂时无法显示" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "书脊导航" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "任务检查器" }),
    ).toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith(
      "页面渲染失败",
      expect.any(Error),
      expect.any(Object),
    );

    shouldThrow = false;
    fireEvent.click(screen.getByRole("button", { name: "重新加载页面" }));

    expect(
      screen.getByRole("heading", { name: "页面已恢复" }),
    ).toBeInTheDocument();
  });
});
