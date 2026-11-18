import { useEffect, useState } from "react";
import { go, useResource } from "./api";
import type { Capabilities, Settings } from "./api";
import { Brand, Button, Icon, PageHeading } from "./ui";
import { Dashboard } from "./pages/Dashboard";
import { ImportPage } from "./pages/ImportPage";
import { JobsPage } from "./pages/JobsPage";
import { ResultsPage } from "./pages/ResultsPage";
import { RecordsPage } from "./pages/RecordsPage";
import { ResearchPage, SettingsPage } from "./pages/SettingsPage";
import { Assistant } from "./Assistant";
import "./styles.css";
import "./theme.css";
const narrowLayout = "(max-width: 900px)";
const navigation = [
  { path: "/", name: "工作台", icon: "home" },
  { path: "/import", name: "新建筛查", icon: "upload" },
  { path: "/jobs", name: "筛查任务", icon: "jobs" },
  { path: "/results", name: "评估结果", icon: "signal" },
  { path: "/records", name: "记录与报告", icon: "report" },
  { path: "/research", name: "研究工具", icon: "tools" },
];
export function App() {
  const [route, setRoute] = useState(window.location.hash.slice(1) || "/");
  const [collapsed, setCollapsed] = useState(
    window.matchMedia(narrowLayout).matches,
  );
  const capabilities = useResource<Capabilities>("/capabilities", 15000);
  const settings = useResource<Settings>("/settings", 15000);
  useEffect(() => {
    const update = () => {
      setRoute(window.location.hash.slice(1) || "/");
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", update);
    const media = window.matchMedia(narrowLayout);
    const resize = (event: MediaQueryListEvent) => setCollapsed(event.matches);
    media.addEventListener("change", resize);
    return () => {
      window.removeEventListener("hashchange", update);
      media.removeEventListener("change", resize);
    };
  }, []);
  const url = new URL(route, window.location.origin);
  const page = url.pathname;
  const identity = page.split("/")[2];
  const title =
    [
      ...navigation,
      { path: "/settings", name: "设置与帮助" },
      { path: "/assistant", name: "文字助手" },
    ].find((item) => item.path === (identity ? "/" + page.split("/")[1] : page))
      ?.name ?? "工作台";
  return (
    <div className={`app ${collapsed ? "collapsed" : ""}`}>
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        跳到主要内容
      </a>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Brand small={collapsed} />
        </div>
        <div className="nav-section-label">工作空间</div>
        <nav aria-label="主导航">
          {navigation.map((item) => (
            <a
              href={"#" + item.path}
              key={item.path}
              className={
                (item.path === "/" ? page === "/" : page.startsWith(item.path))
                  ? "active"
                  : ""
              }
              aria-current={
                (item.path === "/" ? page === "/" : page.startsWith(item.path))
                  ? "page"
                  : undefined
              }
              aria-label={item.name}
              title={collapsed ? item.name : undefined}
            >
              <Icon name={item.icon} />
              <span>{item.name}</span>
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <a
            href="#/assistant"
            className={page === "/assistant" ? "active" : ""}
            aria-current={page === "/assistant" ? "page" : undefined}
            aria-label="文字助手"
            title="文字助手"
          >
            <Icon name="chat" />
            <span>文字助手</span>
          </a>
          <a
            href="#/settings"
            className={page === "/settings" ? "active" : ""}
            aria-current={page === "/settings" ? "page" : undefined}
            aria-label="设置与帮助"
            title="设置与帮助"
          >
            <Icon name="settings" />
            <span>设置与帮助</span>
          </a>
          <div className="local-note">
            <Icon name="shield" size={17} />
            <span>数据保存在本机</span>
          </div>
          <button
            className="collapse-button"
            aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((previous) => !previous)}
          >
            <Icon name="chevron" size={17} />
            <span>收起侧栏</span>
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            心澜 <span>/</span>
            <strong>{title}</strong>
          </div>
          <div className="topbar-right">
            <span
              className={`connection ${capabilities.data && !capabilities.error ? "online" : ""}`}
            >
              <i />
              {capabilities.error
                ? "服务连接异常"
                : capabilities.data
                  ? "本地服务已连接"
                  : "连接本地服务…"}
            </span>
            <Button variant="quiet" icon="help" aria-label="使用帮助" onClick={() => go("/settings")}>
              使用帮助
            </Button>
          </div>
        </header>
        <main id="main-content" tabIndex={-1} className="main-content">
          {page === "/import" ? (
            <ImportPage
              params={url.searchParams}
              capabilities={capabilities.data}
            />
          ) : page.startsWith("/jobs") ? (
            <JobsPage key={page} identity={identity} />
          ) : page.startsWith("/results") ? (
            <ResultsPage
              key={page}
              identity={identity}
              settings={settings.data}
            />
          ) : page === "/records" ? (
            <RecordsPage />
          ) : page === "/research" ? (
            <ResearchPage capabilities={capabilities.data} />
          ) : page === "/settings" ? (
            <SettingsPage
              capabilities={capabilities.data}
              settings={settings.data}
              error={capabilities.error ?? settings.error}
              refresh={() => {
                capabilities.refresh();
                settings.refresh();
              }}
            />
          ) : page === "/assistant" ? (
            <>
              <PageHeading title="文字助手" description="可选的本机文字服务，与评估流程独立。" />
              <Assistant />
            </>
          ) : (
            <Dashboard capabilities={capabilities.data} />
          )}
          <footer className="footer">
            <span>心澜 · 脑电支持的心理健康辅助筛查与状态评估</span>
            <span>辅助评估 · 需要专业复核</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
