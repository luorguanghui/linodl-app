import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ArchivePage } from "./ArchivePage";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ArchivePage", () => {
  it("shows compact archive counts and starts export", () => {
    const startExport = vi.fn();
    render(
      <ArchivePage
        model={{
          archives: [
            {
              id: "作品 A",
              title: "作品 A",
              path: "C:\\books\\作品 A",
              volume_count: 2,
              chapter_count: 24,
            },
          ],
          startExport,
          openDirectory: vi.fn(),
          loadArchives: vi.fn(),
        } as never}
      />,
    );

    expect(screen.getByText("2 卷")).toBeVisible();
    expect(screen.getByText("24 章")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "导出作品 A" }));

    expect(startExport).toHaveBeenCalledWith("作品 A", true);
  });

  it("opens only the selected archive row", () => {
    const openDirectory = vi.fn();
    render(
      <ArchivePage
        model={{
          archives: [
            {
              id: "作品 A",
              title: "作品 A",
              path: "C:\\books\\作品 A",
              volume_count: 1,
              chapter_count: 8,
            },
          ],
          startExport: vi.fn(),
          openDirectory,
          loadArchives: vi.fn(),
        } as never}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "打开作品 A目录" }));

    expect(openDirectory).toHaveBeenCalledWith("C:\\books\\作品 A");
  });
});
