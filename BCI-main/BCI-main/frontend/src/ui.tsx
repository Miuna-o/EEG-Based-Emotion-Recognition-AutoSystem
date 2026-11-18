import { useState } from "react";
import type { ReactNode } from "react";
import {
  Badge as MantineBadge,
  Button as MantineButton,
  Modal,
  Paper,
} from "@mantine/core";
import {
  Activity, ArrowRight, AudioLines, Check, ChevronLeft, CircleHelp, CirclePlay,
  ClipboardList, Clock3, Download, File, Files, FlaskConical, LayoutDashboard,
  MessageSquare, RefreshCw, Search, Settings2, ShieldCheck, Upload, Waves, X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { describeError } from "./api";
import { photos } from "./photos";

const icons: Record<string, LucideIcon> = {
  home: LayoutDashboard,
  upload: Upload,
  jobs: ClipboardList,
  report: Files,
  tools: FlaskConical,
  settings: Settings2,
  help: CircleHelp,
  arrow: ArrowRight,
  check: Check,
  close: X,
  refresh: RefreshCw,
  shield: ShieldCheck,
  chevron: ChevronLeft,
  chat: MessageSquare,
  download: Download,
  signal: Activity,
  waveform: AudioLines,
  play: CirclePlay,
  search: Search,
  file: File,
  clock: Clock3,
};
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const Symbol = icons[name] ?? File;
  return <Symbol size={size} strokeWidth={1.7} aria-hidden="true" />;
}
export function Brand({ small = false }: { small?: boolean }) {
  return (
    <div className="brand" role="img" aria-label="心澜">
      <span className="brand-mark">
        <Waves size={29} strokeWidth={1.45} aria-hidden="true" />
      </span>
      {!small && (
        <span>
          <strong>心<span className="brand-accent">澜</span></strong>
          <small>XINLAN</small>
        </span>
      )}
    </div>
  );
}
export function Button({
  children,
  icon,
  variant = "primary",
  className = "",
  type = "button",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: string;
  variant?: "primary" | "secondary" | "quiet" | "danger";
  children: ReactNode;
}) {
  return (
    <MantineButton
      unstyled
      className={`button ${variant} ${className}`}
      classNames={{ inner: "button-content", label: "button-label" }}
      leftSection={icon && <Icon name={icon} size={17} />}
      type={type}
      {...props}
    >
      {children}
    </MantineButton>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <MantineBadge component="span" unstyled className={`badge ${tone}`}>{children}</MantineBadge>;
}
export function ModeBadge({ mode }: { mode: "real" | "demo" }) {
  return (
    <Badge tone={mode === "demo" ? "violet" : "green"}>
      {mode === "demo" ? "模拟演示" : "真实数据"}
    </Badge>
  );
}
export function Notice({
  children,
  tone = "amber",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <div className={`notice ${tone}`}>
      <Icon name="shield" size={19} />
      <div>{children}</div>
    </div>
  );
}
export function DemoNotice() {
  return (
    <Notice tone="violet">
      <strong>模拟演示，非实际筛查结果</strong>
      <p>固定合成样本与固定输出仅用于体验工作流程，不依据信号判断情绪。</p>
    </Notice>
  );
}
export function ErrorBox({
  error,
  retry,
}: {
  error?: unknown;
  retry?: () => void;
}) {
  if (!error) return null;
  return (
    <div className="error-box" role="alert">
      <p>{typeof error === "string" ? error : describeError(error)}</p>
      {retry && (
        <Button variant="secondary" onClick={retry} icon="refresh">
          重新连接
        </Button>
      )}
    </div>
  );
}
export function Empty({
  title,
  children,
  icon = "file",
}: {
  title: string;
  children?: ReactNode;
  icon?: string;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name={icon} size={28} />
      </span>
      <h3>{title}</h3>
      <div>{children}</div>
    </div>
  );
}
function ResearchPhotoCredit() {
  const [opened, setOpened] = useState(false);

  return (
    <>
      <button className="photo-credit" type="button" onClick={() => setOpened(true)}>
        脑电帽摄影 · Chris Hope · CC BY 2.0
      </button>
      <Modal
        opened={opened}
        onClose={() => setOpened(false)}
        title="脑电帽摄影授权"
        closeButtonProps={{ "aria-label": "关闭摄影授权" }}
        centered
      >
        <div className="photo-license">
          <p>Chris Hope 摄影。心澜对照片进行了缩放和界面裁切。</p>
          <dl>
            <dt>作品原页</dt>
            <dd><code>https://commons.wikimedia.org/wiki/File:EEG_Recording_Cap.jpg</code></dd>
            <dt>CC BY 2.0 授权条款</dt>
            <dd><code>https://creativecommons.org/licenses/by/2.0/</code></dd>
          </dl>
        </div>
      </Modal>
    </>
  );
}
export function PageHeading({
  title,
  description,
  children,
  photo,
}: {
  title: string;
  description: string;
  children?: ReactNode;
  photo?: Exclude<keyof typeof photos, "dashboard">;
}) {
  return (
    <div className={`page-heading${photo ? " page-heading-photo" : ""}`} data-photo={photo}>
      {photo && (
        <img className="page-photo" src={photos[photo]} alt={photo === "research" ? "佩戴中的脑电电极帽" : ""} />
      )}
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children && <div className="actions">{children}</div>}
      {photo === "research" && <ResearchPhotoCredit />}
    </div>
  );
}
export function Card({
  children,
  title,
  extra,
  className = "",
}: {
  children: ReactNode;
  title?: string;
  extra?: ReactNode;
  className?: string;
}) {
  return (
    <Paper component="section" unstyled className={`card ${className}`}>
      {title && (
        <div className="card-heading">
          <h2>{title}</h2>
          {extra}
        </div>
      )}
      {children}
    </Paper>
  );
}
export const date = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "未提供";
export const percent = (value?: number | null) =>
  value == null ? "未提供" : `${(value * 100).toFixed(1)}%`;
export const shortId = (value: string) =>
  value.length > 22 ? value.slice(0, 9) + "…" + value.slice(-7) : value;
// API display_code 来自记录绑定的 dataset_version；缺失时使用内部编号。
export const boundCode = (record: {
  display_code?: string | null;
  dataset_id: string;
}) => record.display_code || shortId(record.dataset_id);
export const jobStatus: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  cancelling: "正在取消",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};
export const reviewStatus: Record<string, string> = {
  pending: "待复核",
  reviewed: "已复核",
  needs_followup: "需跟进",
};
export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge
      tone={
        ["succeeded", "reviewed", "ready"].includes(status)
          ? "green"
          : ["failed", "interrupted"].includes(status)
            ? "red"
            : ["pending", "needs_followup", "draft"].includes(status)
              ? "amber"
              : "blue"
      }
    >
      {jobStatus[status] ??
        reviewStatus[status] ??
        (status === "draft" ? "草稿" : status === "ready" ? "可分析" : status)}
    </Badge>
  );
}
export function JsonPreview({
  opened,
  value,
  onClose,
}: {
  opened: boolean;
  value: unknown;
  onClose: () => void;
}) {
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="JSON报告预览"
      size="xl"
      centered
      closeOnClickOutside={false}
      closeButtonProps={{ "aria-label": "关闭预览" }}
      classNames={{ header: "report-preview-header", body: "report-preview-body" }}
    >
      <pre tabIndex={0}>{JSON.stringify(value, null, 2)}</pre>
    </Modal>
  );
}
