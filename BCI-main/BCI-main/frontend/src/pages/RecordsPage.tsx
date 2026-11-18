import { useState } from "react";
import type { Report } from "../generated/api";
import { download, go, request, useAction, useResource } from "../api";
import {
  Button,
  Badge,
  Card,
  Empty,
  ErrorBox,
  Icon,
  JsonPreview,
  ModeBadge,
  Notice,
  PageHeading,
  StatusBadge,
  date,
  boundCode,
  shortId,
} from "../ui";
import { useReportPreview } from "../reportPreview";
import "../assessment-workspace.css";

export function RecordsPage() {
  const reports = useResource<Report[]>("/reports", 5000);
  const action = useAction();
  const [text, setText] = useState("");
  const [status, setStatus] = useState("all");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const {
    preview,
    notice: previewNotice,
    openPreview,
    closePreview,
  } = useReportPreview(reports.data);
  const filtered = reports.data?.filter(
    (report) =>
      (!text ||
        boundCode(report).toLowerCase().includes(text.toLowerCase()) ||
        report.id.includes(text)) &&
      (status === "all" ||
        (status === "stale" ? report.stale : report.status === status)) &&
      (!start ||
        new Date(report.created_at) >= new Date(start + "T00:00:00")) &&
      (!end || new Date(report.created_at) <= new Date(end + "T23:59:59")),
  );
  return (
    <div className="assessment-workspace">
      <PageHeading
        title="记录与报告"
        description="按数据编码、日期与复核状态查找归档报告，保留来源版本和文件哈希。"
      >
        <Button variant="secondary" icon="refresh" onClick={reports.refresh}>
          刷新记录
        </Button>
      </PageHeading>
      <ErrorBox error={reports.error ?? action.error} retry={reports.refresh} />
      {previewNotice && <Notice>{previewNotice}</Notice>}
      <Card title="归档报告" className="workspace-register">
        <div className="workspace-archive-filters">
          <label className="search-field">
            数据编码 / 报告编号
            <span className="workspace-search">
              <Icon name="search" size={17} />
              <input
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder="搜索匿名数据编码"
              />
            </span>
          </label>
          <label>
            报告状态
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="all">全部状态</option>
              <option value="draft">草稿</option>
              <option value="reviewed">已复核</option>
              <option value="stale">已过期</option>
            </select>
          </label>
          <label>
            开始日期
            <input
              type="date"
              value={start}
              onChange={(event) => setStart(event.target.value)}
            />
          </label>
          <label>
            结束日期
            <input
              type="date"
              value={end}
              min={start}
              onChange={(event) => setEnd(event.target.value)}
            />
          </label>
        </div>
        {filtered?.length ? (
          <div className="table-scroll">
            <table className="workspace-archive-table">
              <thead>
                <tr>
                  <th scope="col">数据编码</th>
                  <th scope="col">报告</th>
                  <th scope="col">来源</th>
                  <th scope="col">状态 / 版本</th>
                  <th scope="col">归档时间</th>
                  <th scope="col">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((report) => (
                  <tr key={report.id}>
                    <td>
                      <strong>{boundCode(report)}</strong>
                    </td>
                    <td>
                      <div className="workspace-report-format">
                        <span className="workspace-format-tag">
                          {report.format.toUpperCase()}
                        </span>
                        <small className="mono" title={report.sha256}>
                          {shortId(report.id)}
                        </small>
                      </div>
                    </td>
                    <td>
                      <ModeBadge mode={report.data_mode} />
                    </td>
                    <td>
                      <div className="workspace-report-status">
                        <StatusBadge status={report.status} />
                        {report.stale && <Badge tone="red">已过期</Badge>}
                      </div>
                      <small className="block">
                        数据 v{report.dataset_version} / 复核 r
                        {report.review_revision}
                      </small>
                      {report.stale && (
                        <small
                          className="block"
                          title={report.stale_reason ?? undefined}
                        >
                          当前 v{report.current_dataset_version} / r
                          {report.current_review_revision} ·{" "}
                          {report.stale_reason}
                        </small>
                      )}
                    </td>
                    <td>
                      <time dateTime={report.created_at}>
                        {date(report.created_at)}
                      </time>
                    </td>
                    <td>
                      <div className="actions workspace-archive-actions">
                        <Button
                          variant="quiet"
                          onClick={() => go("/results/" + report.assessment_id)}
                        >
                          查看结果
                        </Button>
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
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={reports.loading ? "正在读取归档记录…" : "没有符合条件的报告"}
            icon="report"
          >
            <p>在评估结果页完成复核并导出报告后，可在这里查找和下载。</p>
          </Empty>
        )}
      </Card>
      <JsonPreview opened={preview !== undefined} value={preview?.value} onClose={closePreview} />
    </div>
  );
}
