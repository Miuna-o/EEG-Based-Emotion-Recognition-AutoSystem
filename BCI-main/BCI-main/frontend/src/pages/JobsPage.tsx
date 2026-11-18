import { useRef, useState } from "react";
import type { Job } from "../generated/api";
import { go, idempotencyKey, post, useAction, useResource } from "../api";
import {
  Button,
  Card,
  DemoNotice,
  Empty,
  ErrorBox,
  ModeBadge,
  PageHeading,
  StatusBadge,
  boundCode,
  date,
  jobStatus,
  shortId,
} from "../ui";
import "../assessment-workspace.css";

const activeStates = ["queued", "running", "cancelling"];
const retryStates = ["failed", "interrupted", "cancelled"];

function QueueSummary({ jobs }: { jobs: Job[] }) {
  const counts = [
    { label: "全部任务", value: jobs.length },
    {
      label: "排队与处理中",
      value: jobs.filter((job) => activeStates.includes(job.status)).length,
    },
    {
      label: "已完成",
      value: jobs.filter((job) => job.status === "succeeded").length,
    },
    {
      label: "失败、取消或中断",
      value: jobs.filter((job) => retryStates.includes(job.status)).length,
    },
  ];

  return (
    <dl className="queue-summary" aria-label="任务汇总">
      {counts.map(({ label, value }) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function JobsPage({ identity }: { identity?: string }) {
  const jobs = useResource<Job[]>(identity ? null : "/jobs", 2500);
  const jobQuery = useResource<Job>(identity ? "/jobs/" + identity : null, 1600);
  const action = useAction();
  const retryKey = useRef(idempotencyKey());
  const [filter, setFilter] = useState("all");
  const job = jobQuery.data;
  const filteredJobs = jobs.data?.filter(
    (item) => filter === "all" || item.status === filter,
  );
  const refresh = () => {
    jobs.refresh();
    jobQuery.refresh();
  };

  return (
    <div className="assessment-workspace">
      <PageHeading
        title={identity ? "任务详情" : "筛查任务"}
        description={
          identity
            ? "查看任务进度、处理日志和绑定的输入版本。"
            : "跟踪任务状态，查看结果或处理失败任务。"
        }
      >
        <Button variant="secondary" icon="refresh" onClick={refresh}>
          刷新状态
        </Button>
        <Button icon="upload" onClick={() => go("/import?mode=real")}>
          新建筛查
        </Button>
      </PageHeading>
      <ErrorBox
        error={jobs.error ?? jobQuery.error ?? action.error}
        retry={refresh}
      />
      {!identity && (
        <>
          {jobs.data && <QueueSummary jobs={jobs.data} />}
          <Card
            title="任务记录"
            className="workspace-register"
            extra={
              <label className="inline-label">
                状态筛选
                <select
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                >
                  <option value="all">全部状态</option>
                  {Object.entries(jobStatus).map(([status, label]) => (
                    <option key={status} value={status}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            }
          >
            {filteredJobs?.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">数据编码 / 任务编号</th>
                      <th scope="col">来源 / 版本</th>
                      <th scope="col">状态</th>
                      <th scope="col">处理进度</th>
                      <th scope="col">创建时间</th>
                      <th scope="col">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredJobs.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <strong>{boundCode(item)}</strong>
                          <small className="block mono" title={item.id}>
                            {shortId(item.id)}
                          </small>
                        </td>
                        <td>
                          <ModeBadge mode={item.data_mode} />
                          <small className="block mono">
                            v{item.dataset_version}
                          </small>
                        </td>
                        <td>
                          <StatusBadge status={item.status} />
                        </td>
                        <td>
                          <div className="queue-row-progress">
                            <span className="mono">
                              {item.processed_count ?? 0} / {item.total_count}
                            </span>
                            <progress
                              value={item.processed_count ?? 0}
                              max={Math.max(1, item.total_count)}
                              aria-label={boundCode(item) + "任务处理进度"}
                            />
                          </div>
                        </td>
                        <td>
                          <time dateTime={item.created_at}>
                            {date(item.created_at)}
                          </time>
                        </td>
                        <td>
                          <Button
                            variant="quiet"
                            onClick={() => go("/jobs/" + item.id)}
                          >
                            查看详情
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title={jobs.loading ? "正在读取任务…" : "没有符合条件的任务"}
                icon="jobs"
              >
                <p>
                  {filter === "all"
                    ? "新建筛查并提交后，可在这里跟踪任务。"
                    : "选择其他状态以查看任务。"}
                </p>
              </Empty>
            )}
          </Card>
        </>
      )}
      {identity && !job && !jobQuery.error && <Empty title="正在读取任务…" />}
      {job && (
        <>
          {job.data_mode === "demo" && <DemoNotice />}
          <div className="workspace-split">
            <div>
              <Card
                title={boundCode(job)}
                className="job-overview"
                extra={<StatusBadge status={job.status} />}
              >
                <div className="workspace-identity-meta">
                  <ModeBadge mode={job.data_mode} />
                  <span>
                    数据 v{job.dataset_version} · 第 {job.attempt ?? 1} 次尝试
                  </span>
                </div>
                <div className="job-overview-progress">
                  <p className="job-stage">{job.stage}</p>
                  <div className="job-progress-label">
                    <span>已处理样本</span>
                    <strong>
                      {job.processed_count ?? 0} / {job.total_count}
                    </strong>
                  </div>
                  <progress
                    value={job.processed_count ?? 0}
                    max={Math.max(1, job.total_count)}
                    aria-label="任务处理进度"
                  />
                </div>
                {job.error_code && (
                  <ErrorBox
                    error={`任务未完成：${job.error_code}。请查看下方处理日志；允许重试时会创建新的任务尝试。`}
                  />
                )}
                <div className="actions">
                  {job.assessment_id && (
                    <Button
                      icon="arrow"
                      onClick={() => go("/results/" + job.assessment_id)}
                    >
                      查看评估结果
                    </Button>
                  )}
                  {["queued", "running"].includes(job.status) && (
                    <Button
                      variant="danger"
                      disabled={action.pending}
                      onClick={() =>
                        void action.run(async (signal) => {
                          await post<Job>(
                            "/jobs/" + job.id + "/cancel",
                            {},
                            signal,
                          );
                          jobQuery.refresh();
                        })
                      }
                    >
                      取消任务
                    </Button>
                  )}
                  {retryStates.includes(job.status) && (
                    <Button
                      disabled={action.pending}
                      onClick={() =>
                        void action.run(async (signal) => {
                          const next = await post<Job>(
                            "/jobs/" + job.id + "/retry",
                            { idempotency_key: retryKey.current },
                            signal,
                          );
                          go("/jobs/" + next.id);
                        })
                      }
                    >
                      重试任务
                    </Button>
                  )}
                  <Button variant="secondary" onClick={() => go("/jobs")}>
                    返回任务列表
                  </Button>
                </div>
              </Card>
              <Card title="处理日志">
                {job.logs?.length ? (
                  <ol className="workspace-event-list">
                    {job.logs.map((log, index) => (
                      <li key={index}>
                        <div className="workspace-event-heading">
                          {log.stage && <StatusBadge status={log.stage} />}
                          <time dateTime={log.time ?? log.at}>
                            {date(log.time ?? log.at)}
                          </time>
                        </div>
                        <p>{log.message ?? log.stage ?? JSON.stringify(log)}</p>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="muted">暂无处理日志。</p>
                )}
              </Card>
            </div>
            <Card title="任务与输入">
              <dl className="workspace-facts">
                <div>
                  <dt>任务编号</dt>
                  <dd>
                    <code>{job.id}</code>
                  </dd>
                </div>
                <div>
                  <dt>提供方</dt>
                  <dd>
                    {job.provider === "demo" ? "模拟演示提供方" : "真实提供方"}
                  </dd>
                </div>
                <div>
                  <dt>创建时间</dt>
                  <dd>
                    <time dateTime={job.created_at}>{date(job.created_at)}</time>
                  </dd>
                </div>
                <div>
                  <dt>完成时间</dt>
                  <dd>
                    {job.finished_at ? (
                      <time dateTime={job.finished_at}>{date(job.finished_at)}</time>
                    ) : (
                      "未提供"
                    )}
                  </dd>
                </div>
                <div>
                  <dt>已运行时间</dt>
                  <dd>
                    {job.elapsed_seconds == null
                      ? "未提供"
                      : job.elapsed_seconds.toFixed(1) + " 秒"}
                  </dd>
                </div>
                <div>
                  <dt>预计剩余时间</dt>
                  <dd>
                    {job.remaining_seconds == null
                      ? "未提供"
                      : job.remaining_seconds.toFixed(1) + " 秒"}
                  </dd>
                </div>
                <div>
                  <dt>输入哈希</dt>
                  <dd>
                    <code>{job.input_hash}</code>
                  </dd>
                </div>
                {job.retry_of && (
                  <div>
                    <dt>重试来源</dt>
                    <dd>
                      <code>{job.retry_of}</code>
                    </dd>
                  </div>
                )}
              </dl>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
