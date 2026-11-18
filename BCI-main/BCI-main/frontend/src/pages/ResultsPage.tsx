import { useRef, useState } from "react";
import type { Assessment, Report, Review } from "../generated/api";
import {
  download,
  go,
  idempotencyKey,
  post,
  request,
  useAction,
  useResource,
} from "../api";
import type { Settings } from "../api";
import { useReportPreview } from "../reportPreview";
import {
  Badge,
  Button,
  Card,
  DemoNotice,
  Empty,
  ErrorBox,
  JsonPreview,
  ModeBadge,
  Notice,
  PageHeading,
  StatusBadge,
  date,
  boundCode,
  percent,
} from "../ui";
import "../assessment-workspace.css";

const bands = [
  { id: "delta", label: "δ · Delta" },
  { id: "theta", label: "θ · Theta" },
  { id: "alpha", label: "α · Alpha" },
  { id: "beta", label: "β · Beta" },
  { id: "gamma", label: "γ · Gamma" },
];
function ReviewForm({
  assessment,
  onSaved,
}: {
  assessment: Assessment;
  onSaved: () => void;
}) {
  const [reviewer, setReviewer] = useState("");
  const [opinion, setOpinion] = useState("");
  const [status, setStatus] = useState("reviewed");
  const key = useRef(idempotencyKey());
  const action = useAction();
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void action.run(async (signal) => {
          await post<Review>(
            `/assessments/${assessment.id}/reviews`,
            {
              expected_revision: assessment.review_revision ?? 0,
              reviewer,
              opinion,
              status,
              idempotency_key: key.current,
            },
            signal,
          );
          onSaved();
        });
      }}
    >
      <div className="form-grid">
        <label>
          复核人编码
          <input
            value={reviewer}
            onChange={(event) => setReviewer(event.target.value)}
            maxLength={80}
            placeholder="填写匿名工作编码"
            required
          />
        </label>
        <label>
          复核状态
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="reviewed">已复核</option>
            <option value="needs_followup">需跟进</option>
          </select>
        </label>
        <label className="span-2">
          复核意见
          <textarea
            value={opinion}
            onChange={(event) => setOpinion(event.target.value)}
            maxLength={4000}
            rows={4}
            placeholder="记录证据核对、缺失信息与后续建议；避免填写身份信息。"
            required
          />
        </label>
      </div>
      <ErrorBox error={action.error} />
      <div className="form-actions">
        <Button
          icon="check"
          type="submit"
          disabled={
            action.pending ||
            !reviewer.trim() ||
            !opinion.trim() ||
            assessment.stale
          }
        >
          {action.pending ? "正在保存…" : "保存复核记录"}
        </Button>
        <span className="hint">
          当前复核修订 r{assessment.review_revision ?? 0}
          ；保存采用并发版本检查。
        </span>
      </div>
    </form>
  );
}
export function ResultsPage({
  identity,
  settings,
}: {
  identity?: string;
  settings?: Settings;
}) {
  const all = useResource<Assessment[]>(identity ? null : "/assessments", 4000);
  const assessmentQuery = useResource<Assessment>(
    identity ? "/assessments/" + identity : null,
    5000,
  );
  const reviews = useResource<Review[]>(
    identity ? `/assessments/${identity}/reviews` : null,
  );
  const reports = useResource<Report[]>(identity ? "/reports" : null, 5000);
  const action = useAction();
  const {
    preview,
    notice: previewNotice,
    openPreview,
    closePreview,
  } = useReportPreview(reports.data);
  const assessment = assessmentQuery.data;
  const exportReport = (format: "json" | "pdf") =>
    void action.run(async (signal) => {
      if (!assessment) return;
      const report = await post<Report>(
        `/assessments/${assessment.id}/reports`,
        { format, expected_revision: assessment.review_revision ?? 0 },
        signal,
      );
      reports.refresh();
      await download(
        `/reports/${report.id}/download`,
        `xinlan-${report.data_mode}-${report.id}.${format}`,
        signal,
      );
    });
  return (
    <div className="assessment-workspace">
      <PageHeading
        title="评估结果"
        description={
          identity
            ? "按样本阅读模型输出，区分置信度与可靠性，并记录人工复核意见。"
            : "结果绑定来源版本。选择记录查看输出证据、复核历史与报告。"
        }
      >
        {identity && (
          <Button variant="secondary" onClick={() => go("/results")}>
            全部结果
          </Button>
        )}
      </PageHeading>
      <ErrorBox
        error={
          all.error ?? assessmentQuery.error ?? reviews.error ?? action.error
        }
        retry={() => {
          all.refresh();
          assessmentQuery.refresh();
          reviews.refresh();
        }}
      />
      {previewNotice && <Notice>{previewNotice}</Notice>}
      {!identity && (
        <Card title="结果记录" className="workspace-register">
          {all.data?.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">数据编码</th>
                    <th scope="col">来源</th>
                    <th scope="col">置信度</th>
                    <th scope="col">可靠性</th>
                    <th scope="col">复核状态</th>
                    <th scope="col">生成时间</th>
                    <th scope="col">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {all.data.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{boundCode(item)}</strong>
                        <small className="block">
                          v{item.dataset_version}
                          {item.stale && " · 已过期"}
                        </small>
                      </td>
                      <td>
                        <ModeBadge mode={item.data_mode} />
                      </td>
                      <td className={item.confidence == null ? "muted" : "mono"}>
                        {percent(item.confidence)}
                      </td>
                      <td className={item.reliability == null ? "muted" : "mono"}>
                        {percent(item.reliability)}
                      </td>
                      <td>
                        <StatusBadge status={item.review_status ?? "pending"} />
                      </td>
                      <td>
                        <time dateTime={item.generated_at}>
                          {date(item.generated_at)}
                        </time>
                      </td>
                      <td>
                        <Button
                          variant="quiet"
                          onClick={() => go("/results/" + item.id)}
                        >
                          查看结果
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title={all.loading ? "正在读取评估记录…" : "还没有评估结果"}
              icon="signal"
            >
              <p>完成任务后，可在此查看按样本输出与证据缺失原因。</p>
              <Button variant="secondary" onClick={() => go("/jobs")}>
                查看任务
              </Button>
            </Empty>
          )}
        </Card>
      )}
      {identity && !assessment && !assessmentQuery.error && (
        <Empty title="正在读取评估结果…" />
      )}
      {assessment && (
        <>
          {assessment.data_mode === "demo" && <DemoNotice />}
          {assessment.stale && (
            <Notice tone="red">
              <strong>来源版本已变更，此结果已过期</strong>
              <p>
                结果绑定 v{assessment.dataset_version}
                。请核对最新数据版本后重新提交任务；旧复核与报告保留为历史记录。
              </p>
            </Notice>
          )}
          <Card className="assessment-overview">
            <div className="assessment-identity">
              <div className="workspace-identity-meta">
                <ModeBadge mode={assessment.data_mode} />
                <StatusBadge status={assessment.review_status ?? "pending"} />
              </div>
              <h2>{boundCode(assessment)}</h2>
              <p>
                数据 v{assessment.dataset_version} ·{" "}
                <time dateTime={assessment.generated_at}>
                  {date(assessment.generated_at)}
                </time>
              </p>
            </div>
            <dl className="assessment-metrics">
              <div>
                <dt>分类置信度</dt>
                <dd>
                  <strong>{percent(assessment.confidence)}</strong>
                  <small>
                    {assessment.data_mode === "demo"
                      ? "固定契约示例值"
                      : "提供方分类输出"}
                  </small>
                </dd>
              </div>
              <div
                className={assessment.reliability == null ? "metric-unavailable" : ""}
              >
                <dt>输出可靠性</dt>
                <dd>
                  <strong>{percent(assessment.reliability)}</strong>
                  <small>独立的可靠性证据</small>
                </dd>
              </div>
            </dl>
          </Card>
          {assessment.reliability == null && (
            <Notice>
              <strong>可靠性信息缺失，需要复核</strong>
              <p>
                {assessment.missing_reasons.reliability ??
                  "提供方未返回可靠性，不进行估算。"}
              </p>
            </Notice>
          )}
          <div className="workspace-split">
            <Card
              title="按样本情绪输出"
              className="workspace-register workspace-evidence"
              extra={
                <Badge tone="blue">{assessment.emotions.length} 个样本</Badge>
              }
            >
              <div className="table-scroll" tabIndex={0} role="region" aria-label="按样本情绪输出表格">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">样本编码</th>
                      <th scope="col">分类输出</th>
                      <th scope="col">分类置信度</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assessment.emotions.map((emotion) => (
                      <tr key={emotion.sample_id}>
                        <td className="mono">{emotion.sample_id}</td>
                        <td>
                          <strong>{emotion.label}</strong>
                        </td>
                        <td className={emotion.confidence == null ? "muted" : "mono"}>
                          {percent(emotion.confidence)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="hint">
                标签空间：{assessment.label_space.join("、")}。
                {assessment.data_mode === "demo"
                  ? "这些固定输出用于界面流程演示，没有真实情绪推理意义。"
                  : "分类输出需结合适用性与复核意见理解。"}
              </p>
            </Card>
            <Card title="可靠性与复核依据">
              <dl className="workspace-facts">
                <div>
                  <dt>可靠性</dt>
                  <dd>{percent(assessment.reliability)}</dd>
                </div>
                <div>
                  <dt>规则阈值</dt>
                  <dd>{percent(assessment.reliability_threshold)}</dd>
                </div>
                <div>
                  <dt>规则来源</dt>
                  <dd>{assessment.reliability_rule_source ?? "未提供"}</dd>
                </div>
                <div>
                  <dt>复核要求</dt>
                  <dd>
                    {assessment.review_required ? "需要人工复核" : "未要求复核"}
                  </dd>
                </div>
              </dl>
              <p className="workspace-review-reason">{assessment.review_reason}</p>
            </Card>
          </div>
          <Card title="频带证据" className="workspace-register workspace-evidence">
            <div className="table-scroll" tabIndex={0} role="region" aria-label="频带证据表格">
              <table>
                <thead>
                  <tr>
                    <th scope="col">频带</th>
                    <th scope="col">贡献度</th>
                    <th scope="col">一致性</th>
                    <th scope="col">频带后验</th>
                    <th scope="col">证据状态 / 缺失原因</th>
                  </tr>
                </thead>
                <tbody>
                  {bands.map((band) => {
                    const evidence = assessment.band_evidence.find(
                      (item) => item.band === band.id,
                    );
                    return (
                      <tr key={band.id}>
                        <td className={evidence?.contribution == null ? "muted" : "mono"}>
                          <strong>{band.label}</strong>
                        </td>
                        <td>
                          {evidence?.contribution == null
                            ? "未提供"
                            : evidence.contribution.toPrecision(4)}
                        </td>
                        <td className={evidence?.consistency == null ? "muted" : "mono"}>
                          {percent(evidence?.consistency)}
                        </td>
                        <td className={evidence?.posterior == null ? "muted" : "mono"}>
                          {evidence?.posterior
                            ?.map((value) => percent(value))
                            .join(" / ") ?? "未提供"}
                        </td>
                        <td className="muted">
                          {evidence?.missing_reason ??
                            (evidence?.contribution == null
                              ? "提供方未返回该频带证据"
                              : "提供方已返回")}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="hint">
              缺失数据保持为空；无完整证据时不绘制贡献度或后验图表。
            </p>
          </Card>
          <div className="workspace-split workspace-equal">
            <Card title="空间与质量证据">
              <div className="workspace-inline-empty">
                <h3>电极定位图不可用</h3>
                <p>
                  {assessment.missing_reasons.electrode_coordinates ??
                    "未提供当前输入的电极坐标，不绘制定位脑地形。"}
                </p>
              </div>
              <p className="hint">
                信号质量：
                {assessment.missing_reasons.signal_quality_score ??
                  "见服务端结构校验记录"}
                。
              </p>
              <details>
                <summary>查看原始质量校验字段</summary>
                <pre>{JSON.stringify(assessment.quality, null, 2)}</pre>
              </details>
            </Card>
            <Card title="来源与版本">
              <dl className="workspace-facts">
                <div>
                  <dt>数据版本</dt>
                  <dd>v{assessment.dataset_version}</dd>
                </div>
                <div>
                  <dt>配置版本</dt>
                  <dd className="mono">{assessment.config_version}</dd>
                </div>
                <div>
                  <dt>提供方版本</dt>
                  <dd className="mono">{assessment.provider_version}</dd>
                </div>
                <div>
                  <dt>适配器版本</dt>
                  <dd className="mono">{assessment.adapter_version}</dd>
                </div>
                <div>
                  <dt>契约版本</dt>
                  <dd>{assessment.schema_version ?? "未提供"}</dd>
                </div>
                <div>
                  <dt>来源状态</dt>
                  <dd>
                    <Badge tone={assessment.stale ? "red" : "green"}>
                      {assessment.stale ? "已过期" : "当前版本"}
                    </Badge>
                  </dd>
                </div>
              </dl>
              <details>
                <summary>查看完整输入哈希与记录编号</summary>
                <p className="mono wrap">{assessment.input_hash}</p>
                <p className="mono wrap">{assessment.id}</p>
                <p className="mono wrap">{assessment.job_id}</p>
              </details>
            </Card>
          </div>
          <div className="workspace-split">
            <Card
              title="人工复核"
              extra={
                <StatusBadge status={assessment.review_status ?? "pending"} />
              }
            >
              <ReviewForm
                key={`${assessment.id}/${assessment.review_revision}`}
                assessment={assessment}
                onSaved={() => {
                  assessmentQuery.refresh();
                  reviews.refresh();
                  reports.refresh();
                }}
              />
            </Card>
            <Card
              title="复核历史"
              extra={<Badge>修订 r{assessment.review_revision ?? 0}</Badge>}
            >
              {reviews.data?.length ? (
                <ol className="workspace-event-list">
                  {reviews.data.map((review) => (
                    <li key={review.id}>
                      <div className="workspace-event-heading">
                        <strong>{review.reviewer}</strong>
                        <StatusBadge status={review.status} />
                        <small className="muted">
                          r{review.revision} ·{" "}
                          <time dateTime={review.created_at}>{date(review.created_at)}</time>
                        </small>
                      </div>
                      <p className="pre-wrap">{review.opinion}</p>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="muted">
                  尚无复核记录。保存意见后会创建不可覆盖的历史条目。
                </p>
              )}
            </Card>
          </div>
          <Card title="报告与归档">
            <div className="workspace-export-controls">
              <div>
                <p className="workspace-export-state">
                  {assessment.review_status === "reviewed"
                    ? "已复核报告"
                    : "未复核报告将标为草稿"}{" "}
                  · 数据 v{assessment.dataset_version} · 复核 r
                  {assessment.review_revision ?? 0}
                </p>
                <p className="hint">
                  导出由服务端生成实际文件并保留哈希与版本；模拟报告持续带有演示声明。
                </p>
              </div>
              <div className="actions">
                <Button
                  variant="secondary"
                  icon="download"
                  disabled={action.pending || assessment.stale}
                  onClick={() => exportReport("json")}
                >
                  导出 JSON 报告
                </Button>
                <Button
                  icon="download"
                  disabled={
                    action.pending ||
                    assessment.stale ||
                    !settings?.pdf_available
                  }
                  onClick={() => exportReport("pdf")}
                >
                  导出 PDF 报告
                </Button>
              </div>
            </div>
            {settings && !settings.pdf_available && (
              <Notice>
                服务端 PDF 渲染依赖不可用，请使用 JSON 报告并查看设置诊断。
              </Notice>
            )}
            {reports.data
              ?.filter((report) => report.assessment_id === assessment.id)
              .map((report) => (
                <div className="report-row workspace-report-row" key={report.id}>
                  <div className="workspace-report-format">
                    <span className="workspace-format-tag">
                      {report.format.toUpperCase()}
                    </span>
                    <div>
                      <div className="workspace-report-status">
                        <StatusBadge status={report.status} />
                        {report.stale && <Badge tone="red">已过期</Badge>}
                      </div>
                      <small className="block">
                        <time dateTime={report.created_at}>
                          {date(report.created_at)}
                        </time>
                        {" "}· v{report.dataset_version} / r{report.review_revision}
                      </small>
                      {report.stale && (
                        <small className="block">
                          当前 v{report.current_dataset_version} / r
                          {report.current_review_revision} · {report.stale_reason}
                        </small>
                      )}
                    </div>
                  </div>
                  <ModeBadge mode={report.data_mode} />
                  <div className="actions">
                    <Button
                      variant="quiet"
                      disabled={report.stale}
                      aria-disabled={action.pending || undefined}
                      onClick={() =>
                        void action.run(async (signal) => {
                          if (report.format === "json")
                            openPreview(
                              report,
                              await request<unknown>(
                                `/reports/${report.id}/download`,
                                { signal },
                              ),
                            );
                          else
                            window.open(
                              "/api/v1/reports/" + report.id + "/download?preview=true",
                              "_blank",
                              "noopener,noreferrer",
                            );
                        })
                      }
                    >
                      预览
                    </Button>
                    <Button
                      variant="quiet"
                      disabled={action.pending || report.stale}
                      onClick={() =>
                        void action.run((signal) =>
                          download(
                            `/reports/${report.id}/download`,
                            `${report.id}.${report.format}`,
                            signal,
                          ),
                        )
                      }
                    >
                      下载
                    </Button>
                    {report.stale && (
                      <Button
                        variant="quiet"
                        disabled={action.pending}
                        onClick={() =>
                          void action.run((signal) =>
                            download(
                              `/reports/${report.id}/download?historical=true`,
                              `xinlan-historical-${report.id}.zip`,
                              signal,
                            ),
                          )
                        }
                      >
                        下载历史存档
                      </Button>
                    )}
                  </div>
                </div>
              ))}
          </Card>
          <JsonPreview opened={preview !== undefined} value={preview?.value} onClose={closePreview} />
        </>
      )}
    </div>
  );
}
