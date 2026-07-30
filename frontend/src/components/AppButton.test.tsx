import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Search } from "lucide-react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppButton } from "./AppButton";

afterEach(cleanup);

describe("AppButton", () => {
  it("defaults to a primary button without submitting forms", () => {
    render(<AppButton>查找作品</AppButton>);

    const button = screen.getByRole("button", { name: "查找作品" });
    expect(button).toHaveAttribute("type", "button");
    expect(button).toHaveClass(
      "app-button",
      "app-button--primary",
      "app-button--default",
    );
  });

  it("forwards native button attributes and selected variants", () => {
    render(
      <AppButton type="submit" variant="danger" size="compact" form="settings">
        确认退出
      </AppButton>,
    );

    const button = screen.getByRole("button", { name: "确认退出" });
    expect(button).toHaveAttribute("type", "submit");
    expect(button).toHaveAttribute("form", "settings");
    expect(button).toHaveClass("app-button--danger", "app-button--compact");
  });

  it("keeps decorative icons out of the accessible name", () => {
    render(<AppButton icon={Search}>查找作品</AppButton>);

    const button = screen.getByRole("button", { name: "查找作品" });
    expect(button.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("disables repeated activation while loading", () => {
    const onClick = vi.fn();
    render(
      <AppButton loading onClick={onClick}>
        保存设置
      </AppButton>,
    );

    const button = screen.getByRole("button", { name: "保存设置" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");

    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });
});
