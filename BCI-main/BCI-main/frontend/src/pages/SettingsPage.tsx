import {
  Activity,
  ChartColumn,
  CircleHelp,
  ClipboardList,
  FileArchive,
  ListChecks,
  ScanLine,
  ShieldCheck,
  SlidersHorizontal,
  Terminal,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Capabilities, Settings } from "../api";
import { download, useAction } from "../api";
import { Badge, Button, Card, ErrorBox, Notice, PageHeading } from "../ui";
import "../support-workspace.css";

const quickHelp = [
  {
    title: "导入被保留为草稿",
    text: "返回元信息页核对轴定义、单位、样本编码和标签空间，保存后重新校验。",
  },
  {
    title: "任务失败或中断",
    text: "查看任务日志和错误编号，确认输入版本后重试。新尝试会保留与原任务的关联。",
  },
  {
    title: "可靠性字段缺失",
    text: "可靠性缺失时保留空值，按缺失原因记录人工复核。分类置信度与可靠性是独立字段。",
  },
  {
    title: "来源版本变更",
    text: "旧结果会标为过期。重新提交当前版本的任务，历史复核和报告仍可追溯。",
  },
];

const researchModules: Partial<
  Record<string, { Icon: LucideIcon; description: string }>
> = {
  preprocessing: {
    Icon: Activity,
    description: "在研究环境中处理原始脑电信号。",
  },
  features: {
    Icon: ScanLine,
    description: "从已准备的脑电数据中提取研究特征。",
  },
  statistics: {
    Icon: ChartColumn,
    description: "对研究数据执行统计分析。",
  },
  training: {
    Icon: Workflow,
    description: "在研究环境中训练和评估分类器。",
  },
  visualization: {
    Icon: ClipboardList,
    description: "用研究界面的图表查看和比较数据。",
  },
};

export function SettingsPage({
  capabilities,
  settings,
  error,
  refresh,
}: {
  capabilities?: Capabilities;
  settings?: Settings;
  error?: unknown;
  refresh: () => void;
}) {
  const action = useAction();
  const availability = [
    {
      label: "真实模型推理",
      available: capabilities?.real.available,
      unavailable: "未接入",
    },
    {
      label: "模拟演示",
      available: capabilities?.demo.available,
      unavailable: "不可用",
    },
    {
      label: "硬件采集",
      available: capabilities?.acquisition.available,
      unavailable: "未接入",
    },
    {
      label: "电极坐标",
      available: capabilities?.electrode_coordinates.available,
      unavailable: "未提供",
    },
    {
      label: "中文 PDF 报告",
      available: settings?.pdf_available,
      unavailable: "依赖不可用",
    },
  ];

  return (
    <>
      <PageHeading
        title="设置与帮助"
        description="查看本地服务的运行能力、有效配置与常见问题。"
        photo="settings"
      >
        <Button variant="secondary" icon="refresh" onClick={refresh}>
          刷新服务状态
        </Button>
        <Button
          icon="download"
          disabled={action.pending}
          onClick={() =>
            void action.run((signal) =>
              download("/diagnostics/download", "xinlan-diagnostics.zip", signal),
            )
          }
        >
          导出诊断包
        </Button>
      </PageHeading>
      <ErrorBox error={error ?? action.error} retry={refresh} />
      <div className="settings-overview">
        <Card className="support-panel">
          <div className="support-panel-heading">
            <span className="support-icon">
              <Activity size={20} aria-hidden="true" />
            </span>
            <h2>运行能力</h2>
          </div>
          <dl className="support-facts">
            {availability.map(({ label, available, unavailable }) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>
                  <Badge tone={available ? "green" : "neutral"}>
                    {available === undefined
                      ? "正在读取"
                      : available
                        ? "可用"
                        : unavailable}
                  </Badge>
                </dd>
              </div>
            ))}
            <div>
              <dt>应用版本</dt>
              <dd className="mono">{settings?.version ?? "正在读取"}</dd>
            </div>
            <div>
              <dt>配置版本</dt>
              <dd className="mono">{settings?.config_version ?? "正在读取"}</dd>
            </div>
          </dl>
          {capabilities && (
            <Notice>
              <strong>真实模型接入边界</strong>
              <p>{capabilities.real.reason}</p>
            </Notice>
          )}
        </Card>
        <div className="settings-side">
          <Card className="support-panel">
            <div className="support-panel-heading">
              <span className="support-icon">
                <ShieldCheck size={20} aria-hidden="true" />
              </span>
              <h2>数据与使用边界</h2>
            </div>
            <div className="support-text-list">
              <div>
                <h3>隐私与本地运行</h3>
                <p>{settings?.privacy ?? "正在读取本地服务隐私说明。"}</p>
              </div>
              <div>
                <h3>数据编码</h3>
                <p>导入和复核使用匿名编码，避免在来源说明和复核意见中填写身份信息。</p>
              </div>
              <div>
                <h3>辅助评估</h3>
                <p>结果需结合信号质量、模型适用性及专业复核，不能替代临床诊断或专业心理评估。</p>
              </div>
            </div>
          </Card>
          <Card className="support-panel">
            <div className="support-panel-heading">
              <span className="support-icon">
                <FileArchive size={20} aria-hidden="true" />
              </span>
              <h2>诊断包内容</h2>
            </div>
            <p className="support-description">
              包含服务能力、配置版本与任务状态。原始信号、复核意见和助手会话不会随诊断包导出。
            </p>
          </Card>
        </div>
      </div>
      <Card className="support-panel">
        <div className="support-panel-heading">
          <span className="support-icon">
            <SlidersHorizontal size={20} aria-hidden="true" />
          </span>
          <h2>有效配置</h2>
        </div>
        <p className="support-description">{settings?.priority ?? "正在读取配置优先级。"}</p>
        <div className="table-scroll support-settings-table">
          <table>
            <thead>
              <tr>
                <th scope="col">配置项</th>
                <th scope="col">有效值</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(settings?.effective ?? {}).map(([key, value]) => (
                <tr key={key}>
                  <td className="mono">{key}</td>
                  <td className="mono">
                    {typeof value === "string" ? value : JSON.stringify(value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card className="support-panel">
        <div className="support-panel-heading">
          <span className="support-icon">
            <CircleHelp size={20} aria-hidden="true" />
          </span>
          <h2>快速帮助</h2>
        </div>
        <div className="settings-help-grid">
          {quickHelp.map(({ title, text }) => (
            <div key={title}>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}

export function ResearchPage({ capabilities }: { capabilities?: Capabilities }) {
  return (
    <>
      <PageHeading
        title="研究工具"
        description="查看预处理、特征提取、统计分析等功能在旧版研究桌面中的入口。"
        photo="research"
      />
      <div className="research-tools-layout">
        <section aria-labelledby="research-tools-title">
          <div className="research-tools-heading">
            <h2 id="research-tools-title">研究功能</h2>
            <p>以下模块目前从独立的研究桌面启动。</p>
          </div>
          {capabilities ? (
            <div className="research-tools-grid">
              {capabilities.research.map((tool) => {
                const details = researchModules[tool.id];
                const ToolIcon = details?.Icon ?? ListChecks;
                return (
                  <Card key={tool.id} className="support-panel research-tool">
                    <span className="support-icon">
                      <ToolIcon size={20} aria-hidden="true" />
                    </span>
                    <h3>{tool.name}</h3>
                    {details && (
                      <p className="support-description">{details.description}</p>
                    )}
                    <div className="research-tool-entry">
                      <span>桌面入口</span>
                      <code>{tool.entry}</code>
                    </div>
                  </Card>
                );
              })}
            </div>
          ) : (
            <Card className="support-panel">
              <p role="status">正在读取研究工具入口…</p>
            </Card>
          )}
        </section>
        <Card className="support-panel research-launcher">
          <div className="support-panel-heading">
            <span className="support-icon">
              <Terminal size={20} aria-hidden="true" />
            </span>
            <h2>启动研究桌面</h2>
          </div>
          <p className="support-description">
            在项目根目录执行，将占位文字替换为已安装研究依赖的 Python 解释器路径。
          </p>
          <pre>
            <code>
              {'powershell -ExecutionPolicy Bypass -File scripts/start-legacy.ps1 -Python "<研究环境的 python.exe>"'}
            </code>
          </pre>
          <p className="support-description">
            界面入口位于 <code>core/UI/main_UI.py</code>。
          </p>
        </Card>
      </div>
    </>
  );
}
