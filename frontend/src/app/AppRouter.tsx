import {
  BadgeCheck,
  BookOpenText,
  LibraryBig,
  Settings2,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

import { ArchivePage } from "../features/archive/ArchivePage";
import { ProfilePage } from "../features/profile/ProfilePage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { VerifyPage } from "../features/verify/VerifyPage";
import { WorkbenchPage } from "../features/workbench/WorkbenchPage";

export type PageKey =
  | "workbench"
  | "profile"
  | "catalog"
  | "validation"
  | "settings";

interface PageDefinition {
  key: PageKey;
  label: string;
  chapter: string;
  chapterLabel: string;
  description: string;
  icon: LucideIcon;
}

export const PAGE_DEFINITIONS: readonly PageDefinition[] = [
  {
    key: "workbench",
    label: "阅读工作台",
    chapter: "第一章",
    chapterLabel: "开卷",
    description: "把检索、书目与校验进度收束在同一张编辑桌上。",
    icon: BookOpenText,
  },
  {
    key: "profile",
    label: "浏览档案",
    chapter: "第二章",
    chapterLabel: "寻书",
    description: "检查浏览档案健康状态，或在可见浏览器中完成站点人工验证。",
    icon: ShieldCheck,
  },
  {
    key: "catalog",
    label: "归档与导出",
    chapter: "第三章",
    chapterLabel: "归档",
    description: "浏览本地作品、核对卷章数量，并沿用现有导出流程生成 EPUB。",
    icon: LibraryBig,
  },
  {
    key: "validation",
    label: "内容校验",
    chapter: "第四章",
    chapterLabel: "校勘",
    description: "集中检查缺章、重复与任务异常，让资料在归档前保持完整。",
    icon: BadgeCheck,
  },
  {
    key: "settings",
    label: "工作室设置",
    chapter: "第五章",
    chapterLabel: "偏好",
    description: "管理输出位置与采集方式，让每次整理沿用同一套工作习惯。",
    icon: Settings2,
  },
] as const;

export function getPageDefinition(page: PageKey): PageDefinition {
  return (
    PAGE_DEFINITIONS.find((definition) => definition.key === page) ??
    PAGE_DEFINITIONS[0]
  );
}

interface AppRouterProps {
  page: PageKey;
}

export function AppRouter({ page }: AppRouterProps) {
  const definition = getPageDefinition(page);

  return (
    <article className="studio-page">
      <header className="stage-heading">
        <div>
          <p className="stage-chapter">
            {definition.chapter} · {definition.chapterLabel}
          </p>
          <h1 className="stage-title">{definition.label}</h1>
          <p className="stage-description">{definition.description}</p>
        </div>
        <span className="stage-folio">LINODL / {definition.chapter}</span>
      </header>

      {page === "workbench" ? (
        <WorkbenchPage />
      ) : page === "profile" ? (
        <ProfilePage />
      ) : page === "catalog" ? (
        <ArchivePage />
      ) : page === "validation" ? (
        <VerifyPage />
      ) : page === "settings" ? (
        <SettingsPage />
      ) : (
        null
      )}
    </article>
  );
}
