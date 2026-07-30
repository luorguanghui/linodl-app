import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BrandMark } from "./BrandMark";

afterEach(cleanup);

describe("BrandMark", () => {
  it("exposes a supplied accessible title", () => {
    render(<BrandMark title="linodl 品牌图标" />);

    expect(
      screen.getByRole("img", { name: "linodl 品牌图标" }),
    ).toBeVisible();
  });

  it("stays decorative when no title is supplied", () => {
    const { container } = render(<BrandMark />);

    expect(container.querySelector("svg")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });
});
