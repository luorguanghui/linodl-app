import { FolderOpen, Save, Settings2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import type {
  DesktopSettingsDto,
  SaveSettingsDto,
} from "../../api/types";
import { AppButton } from "../../components/AppButton";
import { useDesktopStore } from "../../store/desktop";
import "../utility.css";

export interface SettingsModel {
  settings: DesktopSettingsDto;
  loadSettings?(): void | Promise<void>;
  saveSettings?(settings: SaveSettingsDto): boolean | Promise<boolean>;
  chooseDirectory?(): string | null | Promise<string | null>;
}

interface SettingsPageProps {
  model?: SettingsModel;
}

const defaults = {
  username: "",
  has_password: false,
  output_dir: "",
  profile_dir: "",
  proxy: "",
  has_proxy: false,
  proxy_has_credentials: false,
  geoip: false,
  headless: true,
  anti_bot_mode: "cloak",
  theme: "auto",
};

function ConnectedSettingsPage() {
  const settings = useDesktopStore((state) => state.settings);
  const loadSettings = useDesktopStore((state) => state.loadSettings);
  const saveSettings = useDesktopStore((state) => state.saveSettings);
  const chooseDirectory = useDesktopStore((state) => state.chooseDirectory);

  return (
    <SettingsView
      model={{ settings, loadSettings, saveSettings, chooseDirectory }}
    />
  );
}

function SettingsView({ model }: { model: SettingsModel }) {
  const [form, setForm] = useState({
    ...defaults,
    ...model.settings,
    proxy: model.settings.proxy_has_credentials
      ? ""
      : model.settings.proxy ?? "",
    password: "",
    clear_password: false,
    clear_proxy: false,
  });
  const [saving, setSaving] = useState(false);
  const storedProxyConfigured = form.has_proxy && !form.clear_proxy;
  const proxyConfigured =
    Boolean(form.proxy.trim()) || storedProxyConfigured;

  useEffect(() => {
    void model.loadSettings?.();
  }, [model.loadSettings]);

  useEffect(() => {
    setForm((current) => ({
      ...current,
      ...model.settings,
      proxy: model.settings.proxy_has_credentials
        ? ""
        : model.settings.proxy ?? "",
      password: "",
      clear_password: false,
      clear_proxy: false,
    }));
  }, [model.settings]);

  function update<K extends keyof typeof form>(
    key: K,
    value: (typeof form)[K],
  ) {
    setForm((current) => {
      const update = { ...current, [key]: value };
      if (key === "clear_proxy" && value === true) {
        return { ...update, geoip: false };
      }
      if (
        key === "proxy" &&
        !String(value).trim() &&
        !(current.has_proxy && !current.clear_proxy)
      ) {
        return { ...update, geoip: false };
      }
      return update;
    });
  }

  async function chooseFor(key: "output_dir" | "profile_dir") {
    const path = await model.chooseDirectory?.();
    if (path) update(key, path);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await model.saveSettings?.({
        username: form.username,
        has_password: form.has_password,
        password: form.password,
        clear_password: form.clear_password,
        output_dir: form.output_dir,
        profile_dir: form.profile_dir,
        proxy: form.proxy.trim(),
        clear_proxy: form.clear_proxy,
        geoip: proxyConfigured && form.geoip,
        headless: form.headless,
        anti_bot_mode: form.anti_bot_mode,
        theme: form.theme,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="utility-page" aria-label="工作室设置">
      <form className="utility-card settings-form" onSubmit={submit}>
        <header className="utility-card-heading">
          <div>
            <h2>
              <Settings2 size={18} aria-hidden="true" />
              桌面偏好
            </h2>
            <p>路径、浏览方式与账号状态只保存在本机。</p>
          </div>
        </header>

        <div className="settings-grid">
          <div className="settings-field-with-action settings-span">
            <label className="utility-field">
              <span>输出目录</span>
              <input
                aria-label="输出目录"
                value={form.output_dir}
                onChange={(event) => update("output_dir", event.target.value)}
              />
            </label>
            <AppButton
              className="utility-button"
              variant="secondary"
              icon={FolderOpen}
              aria-label="选择输出目录"
              onClick={() => void chooseFor("output_dir")}
            >
              选择
            </AppButton>
          </div>

          <div className="settings-field-with-action settings-span">
            <label className="utility-field">
              <span>浏览档案目录</span>
              <input
                aria-label="浏览档案目录"
                value={form.profile_dir}
                onChange={(event) => update("profile_dir", event.target.value)}
              />
            </label>
            <AppButton
              className="utility-button"
              variant="secondary"
              icon={FolderOpen}
              aria-label="选择浏览档案目录"
              onClick={() => void chooseFor("profile_dir")}
            >
              选择
            </AppButton>
          </div>

          <label className="utility-field">
            <span>账号</span>
            <input
              aria-label="账号"
              value={form.username}
              onChange={(event) => update("username", event.target.value)}
            />
          </label>

          <label className="utility-field">
            <span>密码</span>
            <input
              aria-label="密码"
              type="password"
              autoComplete="new-password"
              value={form.password}
              placeholder={
                form.has_password ? "留空以保留当前密码" : "尚未保存密码"
              }
              onChange={(event) => update("password", event.target.value)}
            />
          </label>

          <div className="settings-credential settings-span">
            <div>
              <p>凭据状态</p>
              <strong>
                {form.has_password ? "已保存登录密码" : "未保存登录密码"}
              </strong>
            </div>
            <label className="utility-checkbox">
              <input
                type="checkbox"
                checked={form.clear_password}
                disabled={!form.has_password}
                onChange={(event) =>
                  update("clear_password", event.target.checked)
                }
              />
              清除已保存密码
            </label>
          </div>

          <label className="utility-field settings-span">
            <span>代理地址</span>
            <input
              aria-label="代理地址"
              placeholder={
                form.proxy_has_credentials
                  ? "留空以保留当前带凭据代理"
                  : "例如 socks5://127.0.0.1:1080"
              }
              value={form.proxy}
              onChange={(event) => update("proxy", event.target.value)}
            />
          </label>

          <div className="settings-credential settings-span">
            <div>
              <p>代理状态</p>
              <strong>
                {form.proxy_has_credentials
                  ? "已保存带凭据代理"
                  : form.has_proxy
                    ? "已保存代理"
                    : "未保存代理"}
              </strong>
            </div>
            <label className="utility-checkbox">
              <input
                type="checkbox"
                checked={form.clear_proxy}
                disabled={!form.has_proxy}
                onChange={(event) =>
                  update("clear_proxy", event.target.checked)
                }
              />
              清除已保存代理
            </label>
          </div>

          <label className="utility-field">
            <span>反爬模式</span>
            <select
              aria-label="反爬模式"
              value={form.anti_bot_mode}
              onChange={(event) =>
                update("anti_bot_mode", event.target.value)
              }
            >
              <option value="auto">自动</option>
              <option value="cloak">CloakBrowser</option>
              <option value="playwright">Playwright</option>
            </select>
          </label>

          <label className="utility-field">
            <span>主题</span>
            <select
              aria-label="主题"
              value={form.theme}
              onChange={(event) => update("theme", event.target.value)}
            >
              <option value="auto">跟随系统</option>
              <option value="light">浅色</option>
              <option value="dark">深色</option>
            </select>
          </label>

          <label className="utility-checkbox">
            <input
              type="checkbox"
              checked={form.headless}
              onChange={(event) => update("headless", event.target.checked)}
            />
            使用无头浏览器
          </label>

          <label className="utility-checkbox">
            <input
              type="checkbox"
              aria-label="根据代理匹配地理位置"
              checked={proxyConfigured && form.geoip}
              disabled={!proxyConfigured}
              onChange={(event) => update("geoip", event.target.checked)}
            />
            根据代理匹配地理位置
          </label>
        </div>

        <footer className="settings-actions">
          <AppButton
            className="utility-button"
            type="submit"
            icon={Save}
            loading={saving}
          >
            {saving ? "正在保存" : "保存设置"}
          </AppButton>
        </footer>
      </form>
    </section>
  );
}

export function SettingsPage({ model }: SettingsPageProps) {
  return model ? <SettingsView model={model} /> : <ConnectedSettingsPage />;
}
