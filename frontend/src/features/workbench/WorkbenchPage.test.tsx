import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { deriveWorkbenchModel, WorkbenchPage } from "./WorkbenchPage";

const actions = {
  search: vi.fn(),
  loadCatalog: vi.fn(),
  startDownload: vi.fn(),
  toggleVolume: vi.fn(),
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("WorkbenchPage", () => {
  it("submits a title through the unified command field", () => {
    const search = vi.fn();
    render(
      <WorkbenchPage
        model={{ ...actions, state: "empty", search } as never}
      />,
    );

    fireEvent.change(screen.getByLabelText("作品名或目录地址"), {
      target: { value: "刀剑神域" },
    });
    fireEvent.click(screen.getByRole("button", { name: "查找作品" }));

    expect(search).toHaveBeenCalledWith("刀剑神域");
  });

  it("loads a supported catalog URL through the same command field", () => {
    const loadCatalog = vi.fn();
    render(
      <WorkbenchPage
        model={{ ...actions, state: "empty", loadCatalog } as never}
      />,
    );

    fireEvent.change(screen.getByLabelText("作品名或目录地址"), {
      target: {
        value: "https://www.linovelib.com/novel/1/catalog",
      },
    });
    fireEvent.submit(screen.getByRole("form", { name: "查找作品或目录" }));

    expect(loadCatalog).toHaveBeenCalledWith(
      "https://www.linovelib.com/novel/1/catalog",
    );
  });

  it("normalizes a supported novel URL before loading its catalog", () => {
    const loadCatalog = vi.fn();
    render(
      <WorkbenchPage
        model={{ ...actions, state: "empty", loadCatalog } as never}
      />,
    );

    fireEvent.change(screen.getByLabelText("作品名或目录地址"), {
      target: {
        value: "http://m.linovelib.com/novel/42/",
      },
    });
    fireEvent.submit(screen.getByRole("form", { name: "查找作品或目录" }));

    expect(loadCatalog).toHaveBeenCalledWith(
      "https://www.linovelib.com/novel/42/catalog",
    );
  });

  it("rejects unsupported HTTP sources inline without calling the backend", () => {
    const search = vi.fn();
    const loadCatalog = vi.fn();
    render(
      <WorkbenchPage
        model={{ ...actions, state: "empty", search, loadCatalog } as never}
      />,
    );

    fireEvent.change(screen.getByLabelText("作品名或目录地址"), {
      target: { value: "https://example.com/novel/1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "查找作品" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "目前仅支持 linovelib.com 的作品或目录链接。",
    );
    expect(search).not.toHaveBeenCalled();
    expect(loadCatalog).not.toHaveBeenCalled();
  });

  it.each([
    "https://www.linovelib.com/",
    "https://www.linovelib.com/help",
  ])("rejects a non-novel linovelib URL inline: %s", (url) => {
    const search = vi.fn();
    const loadCatalog = vi.fn();
    render(
      <WorkbenchPage
        model={{ ...actions, state: "empty", search, loadCatalog } as never}
      />,
    );

    fireEvent.change(screen.getByLabelText("作品名或目录地址"), {
      target: { value: url },
    });
    fireEvent.click(screen.getByRole("button", { name: "查找作品" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "目前仅支持 linovelib.com 的作品或目录链接。",
    );
    expect(search).not.toHaveBeenCalled();
    expect(loadCatalog).not.toHaveBeenCalled();
  });

  it("opens a result catalog and does not render catalog content at the same time", () => {
    const loadCatalog = vi.fn();
    render(
      <WorkbenchPage
        model={{
          ...actions,
          state: "results",
          loadCatalog,
          results: [
            {
              novel_id: "1",
              title: "刀剑神域",
              author: "川原砾",
              description: "浮游城艾恩葛朗特的生存冒险。",
              catalog_url: "https://www.linovelib.com/novel/1/catalog",
            },
          ],
          volumes: [{ name: "不应出现", text_count: 1, illus_count: 0 }],
        } as never}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "读取《刀剑神域》目录" }));

    expect(loadCatalog).toHaveBeenCalledWith(
      "https://www.linovelib.com/novel/1/catalog",
    );
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("keeps selected volume names when the layout changes", () => {
    const startDownload = vi.fn();
    const model = {
      ...actions,
      startDownload,
      state: "catalog",
      catalogOperationId: "catalog-1",
      selectedVolumes: ["第一卷"],
      novel: {
        novel_id: "1",
        title: "刀剑神域",
        author: "川原砾",
        description: "浮游城艾恩葛朗特的生存冒险。",
        catalog_url: "https://www.linovelib.com/novel/1/catalog",
      },
      volumes: [
        { name: "第一卷", text_count: 12, illus_count: 2 },
        { name: "第二卷", text_count: 11, illus_count: 1 },
      ],
    };
    const { rerender } = render(<WorkbenchPage model={model as never} />);
    rerender(<WorkbenchPage model={model as never} />);

    expect(screen.getByRole("checkbox", { name: /第一卷/ })).toBeChecked();
    expect(screen.getByRole("button", { name: "下载所选" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "下载所选" }));
    expect(startDownload).toHaveBeenCalledWith("catalog-1", ["第一卷"]);
  });

  it("disables download until at least one volume is selected", () => {
    render(
      <WorkbenchPage
        model={{
          ...actions,
          state: "catalog",
          catalogOperationId: "catalog-1",
          selectedVolumes: [],
          novel: { title: "刀剑神域" },
          volumes: [{ name: "第一卷", text_count: 12, illus_count: 2 }],
        } as never}
      />,
    );

    expect(screen.getByRole("button", { name: "下载所选" })).toBeDisabled();
  });

  it("shows actionable failures while keeping technical details collapsed", () => {
    render(
      <WorkbenchPage
        model={{
          ...actions,
          state: "failed",
          error: {
            message: "目录读取失败。",
            action: "检查地址后重试。",
            detail: "HTTP 503 from upstream",
          },
        } as never}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("目录读取失败。");
    expect(screen.getByRole("alert")).toHaveTextContent("检查地址后重试。");
    expect(screen.getByText("HTTP 503 from upstream")).not.toBeVisible();
  });

  it("does not let a global notice replace an active operation result", () => {
    const model = deriveWorkbenchModel(
      {
        activeOperationId: "search-1",
        activeOperationKind: "search",
        selectedVolumes: ["旧选择"],
        notice: {
          code: "DESKTOP_API_UNAVAILABLE",
          message: "桌面轮询暂时失败。",
          action: "稍后重试。",
        },
        operations: {
          "search-1": {
            id: "search-1",
            kind: "search",
            task_id: "task-1",
            status: "completed",
            detail: "",
            error: "",
            result: [
              {
                novel_id: "1",
                title: "刀剑神域",
                catalog_url:
                  "https://www.linovelib.com/novel/1/catalog",
              },
            ],
          },
        },
      },
      actions,
    );

    expect(model.state).toBe("results");
    expect(model.results).toHaveLength(1);
    expect(model.volumes).toBeUndefined();
  });

  it("derives catalog without retaining stale search results", () => {
    const model = deriveWorkbenchModel(
      {
        activeOperationId: "catalog-1",
        activeOperationKind: "catalog",
        selectedVolumes: ["第一卷"],
        notice: null,
        operations: {
          "catalog-1": {
            id: "catalog-1",
            kind: "catalog",
            task_id: "task-2",
            status: "completed",
            detail: "",
            error: "",
            result: [
              [{ name: "第一卷", text_count: 12, illus_count: 2 }],
              { title: "刀剑神域" },
            ],
          },
        },
      },
      actions,
    );

    expect(model.state).toBe("catalog");
    expect(model.selectedVolumes).toEqual(["第一卷"]);
    expect(model.results).toBeUndefined();
  });
});
