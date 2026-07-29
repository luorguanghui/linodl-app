import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "./SettingsPage";

const settings = {
  username: "reader",
  has_password: true,
  output_dir: "C:\\books",
  profile_dir: "C:\\profile",
  proxy: "",
  has_proxy: false,
  proxy_has_credentials: false,
  geoip: false,
  headless: true,
  anti_bot_mode: "cloak",
  theme: "auto",
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SettingsPage", () => {
  it("disables GeoIP until a proxy is entered", () => {
    render(
      <SettingsPage
        model={{ settings: { proxy: "", geoip: false } } as never}
      />,
    );

    expect(
      screen.getByRole("checkbox", { name: "根据代理匹配地理位置" }),
    ).toBeDisabled();
  });

  it("keeps an existing password when the password field stays empty", async () => {
    const saveSettings = vi.fn().mockResolvedValue(true);
    render(
      <SettingsPage
        model={{ settings, saveSettings } as never}
      />,
    );

    expect(screen.getByText("已保存登录密码")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(saveSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          password: "",
          clear_password: false,
        }),
      ),
    );
  });

  it("forces GeoIP off when the proxy is explicitly cleared", async () => {
    const saveSettings = vi.fn().mockResolvedValue(true);
    render(
      <SettingsPage
        model={{
          settings: {
            ...settings,
            proxy: "socks5://127.0.0.1:1080",
            has_proxy: true,
            geoip: true,
          },
          saveSettings,
        } as never}
      />,
    );

    fireEvent.change(screen.getByLabelText("代理地址"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "清除已保存代理" }));
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(saveSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          proxy: "",
          clear_proxy: true,
          geoip: false,
        }),
      ),
    );
  });

  it("uses the desktop directory picker for the output directory", async () => {
    const chooseDirectory = vi.fn().mockResolvedValue("D:\\library");
    render(
      <SettingsPage
        model={{ settings, chooseDirectory } as never}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "选择输出目录" }));

    await waitFor(() =>
      expect(screen.getByLabelText("输出目录")).toHaveValue("D:\\library"),
    );
    expect(chooseDirectory).toHaveBeenCalledTimes(1);
  });

  it("does not submit a masked credential proxy when it was not edited", async () => {
    const saveSettings = vi.fn().mockResolvedValue(true);
    render(
      <SettingsPage
        model={{
          settings: {
            ...settings,
            proxy: "socks5://***:***@127.0.0.1:1080",
            has_proxy: true,
            proxy_has_credentials: true,
            geoip: true,
          },
          saveSettings,
        } as never}
      />,
    );

    expect(screen.getByText("已保存带凭据代理")).toBeVisible();
    expect(
      screen.getByRole("checkbox", { name: "根据代理匹配地理位置" }),
    ).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(saveSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          proxy: "",
          clear_proxy: false,
          geoip: true,
        }),
      ),
    );
  });

  it("submits an explicit proxy clear separately from an empty edit", async () => {
    const saveSettings = vi.fn().mockResolvedValue(true);
    render(
      <SettingsPage
        model={{
          settings: {
            ...settings,
            proxy: "socks5://***:***@127.0.0.1:1080",
            has_proxy: true,
            proxy_has_credentials: true,
          },
          saveSettings,
        } as never}
      />,
    );

    fireEvent.click(screen.getByRole("checkbox", { name: "清除已保存代理" }));
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(saveSettings).toHaveBeenCalledWith(
        expect.objectContaining({ proxy: "", clear_proxy: true }),
      ),
    );
  });
});
