import {
  BadgeCheck,
  BookOpenText,
  LibraryBig,
  Search,
  Settings2,
  type LucideIcon,
} from "lucide-react";

import { EmptyState } from "../components/EmptyState";
import { ProfilePage } from "../features/profile/ProfilePage";
import { WorkbenchPage } from "../features/workbench/WorkbenchPage";

export type PageKey =
  | "workbench"
  | "search"
  | "catalog"
  | "validation"
  | "settings";

interface PageDefinition {
  key: PageKey;
  label: string;
  chapter: string;
  chapterLabel: string;
  description: string;
  emptyKicker: string;
  emptyTitle: string;
  emptyDetail: string;
  icon: LucideIcon;
}

export const PAGE_DEFINITIONS: readonly PageDefinition[] = [
  {
    key: "workbench",
    label: "阅读工作台",
    chapter: "第一章",
    chapterLabel: "开卷",
    description: "把检索、书目与校验进度收束在同一张编辑桌上。",
    emptyKicker: "尚未开卷",
    emptyTitle: "先找到一本想整理的作品",
    emptyDetail: "从作品检索开始；任务进度会持续留在右侧检查器中。",
    icon: BookOpenText,
  },
  {
    key: "search",
    label: "作品检索",
    chapter: "第二章",
    chapterLabel: "寻书",
    description: "以书名或线索定位作品，再带着结果进入书目整理。",
    emptyKicker: "等待线索",
    emptyTitle: "检索入口即将接入",
    emptyDetail: "这一页会承载作品关键词与候选结果，不会打断全局任务进度。",
    icon: Search,
  },
  {
    key: "catalog",
    label: "书目采集",
    chapter: "第三章",
    chapterLabel: "编目",
    description: "核对卷册与章节边界，为下载建立一份清楚的目录。",
    emptyKicker: "等待书目",
    emptyTitle: "选择作品后整理卷册",
    emptyDetail: "书目采集将在这里展开；页面会保留阅读式的章节层级。",
    icon: LibraryBig,
  },
  {
    key: "validation",
    label: "内容校验",
    chapter: "第四章",
    chapterLabel: "校勘",
    description: "集中检查缺章、重复与任务异常，让资料在归档前保持完整。",
    emptyKicker: "暂无待校内容",
    emptyTitle: "完成采集后在这里校验",
    emptyDetail: "发现的问题会指向具体卷册与章节，并给出可执行的处理建议。",
    icon: BadgeCheck,
  },
  {
    key: "settings",
    label: "工作室设置",
    chapter: "第五章",
    chapterLabel: "归档",
    description: "管理输出位置与采集方式，让每次整理沿用同一套工作习惯。",
    emptyKicker: "工作室偏好",
    emptyTitle: "设置面板即将接入",
    emptyDetail: "桌面偏好会集中在这里，不混入具体作品的编辑流程。",
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
  const PageIcon = definition.icon;

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
      ) : page === "settings" ? (
        <ProfilePage />
      ) : (
        <EmptyState
          icon={<PageIcon size={22} strokeWidth={1.8} />}
          kicker={definition.emptyKicker}
          title={definition.emptyTitle}
          detail={definition.emptyDetail}
        />
      )}
    </article>
  );
}
