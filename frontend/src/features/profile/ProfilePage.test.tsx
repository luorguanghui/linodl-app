import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useDesktopStore } from "../../store/desktop";
import { ProfilePage } from "./ProfilePage";

afterEach(() => {
  cleanup();
  delete window.pywebview;
  useDesktopStore.setState({
    profile: { status: "unknown", detail: "" },
    notice: null,
  });
  vi.restoreAllMocks();
});

describe("ProfilePage", () => {
  it("does not describe an unchecked profile as healthy", () => {
    useDesktopStore.setState({
      profile: { status: "unknown", detail: "" },
    });

    render(<ProfilePage />);

    expect(screen.getByText("尚未检查")).toBeVisible();
    expect(screen.queryByText("档案健康")).toBeNull();
  });

  it("starts an explicit background profile check", async () => {
    const checkProfile = vi.fn().mockResolvedValue({ ok: true });
    window.pywebview = { api: { check_profile: checkProfile } };
    render(<ProfilePage />);

    fireEvent.click(screen.getByRole("button", { name: "检查浏览档案" }));

    await waitFor(() => expect(checkProfile).toHaveBeenCalledTimes(1));
  });

  it("passes the requested linovelib page to visible manual verification", async () => {
    const startManualVerification = vi.fn().mockResolvedValue({ ok: true });
    window.pywebview = {
      api: { start_manual_verification: startManualVerification },
    };
    render(<ProfilePage />);

    fireEvent.change(screen.getByRole("textbox", { name: "验证页面地址" }), {
      target: { value: "https://www.linovelib.com/novel/1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "打开人工验证" }));

    await waitFor(() =>
      expect(startManualVerification).toHaveBeenCalledWith(
        "https://www.linovelib.com/novel/1",
      ),
    );
  });

  it("only enables manual verification for HTTP(S) linovelib.com targets", () => {
    render(<ProfilePage />);
    const input = screen.getByRole("textbox", { name: "验证页面地址" });
    const button = screen.getByRole("button", { name: "打开人工验证" });

    fireEvent.change(input, {
      target: { value: "https://example.com/novel/1" },
    });
    expect(button).toBeDisabled();

    fireEvent.change(input, {
      target: { value: "ftp://www.linovelib.com/novel/1" },
    });
    expect(button).toBeDisabled();

    fireEvent.change(input, {
      target: { value: "http://linovelib.com/novel/1" },
    });
    expect(button).toBeEnabled();
  });
});
