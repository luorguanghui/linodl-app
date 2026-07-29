import { useState } from "react";
import { ExternalLink, ShieldCheck } from "lucide-react";

import type { ProfileStatus } from "../../api/types";
import { useDesktopStore } from "../../store/desktop";

const profileLabels: Record<ProfileStatus, string> = {
  unknown: "尚未检查",
  checking: "正在检查",
  healthy: "档案健康",
  needs_verification: "需要人工验证",
  busy: "档案正忙",
  error: "检查失败",
};

function isValidVerificationTarget(value: string): boolean {
  try {
    const target = new URL(value.trim());
    const hostname = target.hostname.toLowerCase().replace(/\.$/, "");
    return (
      (target.protocol === "http:" || target.protocol === "https:") &&
      !target.username &&
      !target.password &&
      (hostname === "linovelib.com" || hostname.endsWith(".linovelib.com"))
    );
  } catch {
    return false;
  }
}

export function ProfilePage() {
  const profile = useDesktopStore((state) => state.profile);
  const checkProfile = useDesktopStore((state) => state.checkProfile);
  const startManualVerification = useDesktopStore(
    (state) => state.startManualVerification,
  );
  const [targetUrl, setTargetUrl] = useState("https://www.linovelib.com");
  const targetIsValid = isValidVerificationTarget(targetUrl);
  const operationPending =
    profile.status === "checking" || profile.status === "busy";

  return (
    <section className="profile-page" aria-label="浏览档案">
      <div className="profile-health-card" data-status={profile.status}>
        <span className="profile-health-icon" aria-hidden="true">
          <ShieldCheck size={24} strokeWidth={1.8} />
        </span>
        <div>
          <p className="profile-health-kicker">浏览档案状态</p>
          <h2 className="profile-health-title">
            {profileLabels[profile.status]}
          </h2>
          <p className="profile-health-detail">
            {profile.detail ||
              "档案只会在你主动检查后标记为健康，目录存在并不代表可用。"}
          </p>
        </div>
        <button
          className="profile-primary-action"
          type="button"
          disabled={operationPending}
          onClick={() => void checkProfile()}
        >
          检查浏览档案
        </button>
      </div>

      <div className="profile-manual-card">
        <div>
          <p className="profile-health-kicker">人工验证</p>
          <h2 className="profile-health-title">用可见浏览器完成页面验证</h2>
          <p className="profile-health-detail">
            程序会打开 CloakBrowser 并等待你操作，不会自动破解 CAPTCHA。
          </p>
        </div>
        <label className="profile-url-field">
          <span>验证页面地址</span>
          <input
            type="url"
            aria-label="验证页面地址"
            value={targetUrl}
            onChange={(event) => setTargetUrl(event.target.value)}
          />
        </label>
        <button
          className="profile-secondary-action"
          type="button"
          disabled={operationPending || !targetIsValid}
          onClick={() => void startManualVerification(targetUrl.trim())}
        >
          <ExternalLink size={16} aria-hidden="true" />
          打开人工验证
        </button>
      </div>
    </section>
  );
}
