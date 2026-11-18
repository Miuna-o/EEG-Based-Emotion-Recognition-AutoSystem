import { useState } from "react";
import { NativeSelect } from "@mantine/core";
import type { Assessment, Job } from "../generated/api";
import { go, useResource } from "../api";
import type { Capabilities } from "../api";
import { photos } from "../photos";
import {
  Button,
  Card,
  Empty,
  ErrorBox,
  Icon,
  ModeBadge,
  StatusBadge,
  boundCode,
  date,
} from "../ui";

export function Dashboard({ capabilities }: { capabilities?: Capabilities }) {
  const jobs = useResource<Job[]>("/jobs", 4000);
  const assessments = useResource<Assessment[]>("/assessments", 4000);
  const [mode, setMode] = useState("all");
  const realJobs = jobs.data?.filter((job) => job.data_mode === "real");
  const realAssessments = assessments.data?.filter((result) => result.data_mode === "real");
  const demoJobs = jobs.data?.filter((job) => job.data_mode === "demo");
  const pending = assessments.data?.filter((result) => result.review_status !== "reviewed");
  const recent = jobs.data?.filter((job) => mode === "all" || job.data_mode === mode).slice(0, 5);
  const metrics = [
    { title: "真实筛查任务", value: realJobs?.length, icon: "jobs", tone: "leaf" },
    { title: "已完成真实评估", value: realAssessments?.length, icon: "signal", tone: "ice" },
    {
      title: "真实记录待复核",
      value: pending?.filter((result) => result.data_mode === "real").length,
      icon: "clock",
      tone: "sand",
    },
    { title: "模拟演示任务", value: demoJobs?.length, icon: "play", tone: "lilac" },
  ];

  return (
    <>
      <section className="workspace-hero" aria-labelledby="dashboard-title">
        <img className="page-photo" src={photos.dashboard} alt="" fetchPriority="high" />
        <div>
          <h1 id="dashboard-title">脑电数据工作台</h1>
          <p>导入脑电数据、核对波形、复核评估记录。</p>
          <div className="actions">
            <Button icon="upload" onClick={() => go("/import?mode=real")}>
              新建筛查
            </Button>
            <Button variant="secondary" icon="play" onClick={() => go("/import?mode=demo")}>
              体验演示
            </Button>
          </div>
        </div>
      </section>
      <ErrorBox
        error={jobs.error ?? assessments.error}
        retry={() => {
          jobs.refresh();
          assessments.refresh();
        }}
      />
      <section className="dashboard-metrics" aria-label="工作台概览">
        {metrics.map((metric) => (
          <Card key={metric.title} className="dashboard-metric">
            <span className={`dashboard-symbol ${metric.tone}`}>
              <Icon name={metric.icon} size={17} />
            </span>
            <h2>{metric.title}</h2>
            <strong>{metric.value ?? "—"}</strong>
          </Card>
        ))}
      </section>
      <div className="dashboard-panels">
        <Card
          title="最近任务"
          extra={
            <NativeSelect
              aria-label="筛选数据来源"
              value={mode}
              onChange={(event) => setMode(event.currentTarget.value)}
              data={[
                { label: "全部来源", value: "all" },
                { label: "真实数据", value: "real" },
                { label: "模拟演示", value: "demo" },
              ]}
              size="xs"
              className="dashboard-filter"
            />
          }
        >
          {recent?.length ? (
            <ul className="dashboard-tasks">
              {recent.map((job) => (
                <li key={job.id}>
                  <a href={`#/jobs/${job.id}`} className="dashboard-task">
                    <span className={`dashboard-symbol ${job.data_mode === "demo" ? "lilac" : "leaf"}`}>
                      <Icon name="waveform" size={17} />
                    </span>
                    <span className="dashboard-task-info">
                      <span>
                        <strong>{boundCode(job)}</strong>
                        <ModeBadge mode={job.data_mode} />
                      </span>
                      <time dateTime={job.created_at}>{date(job.created_at)}</time>
                    </span>
                    <StatusBadge status={job.status} />
                    <Icon name="arrow" size={16} />
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <Empty
              title={jobs.loading ? "正在读取最近任务…" : "没有符合条件的任务"}
              icon="jobs"
            />
          )}
          <a href="#/jobs" className="dashboard-link">
            查看全部任务 <Icon name="arrow" size={15} />
          </a>
        </Card>
        <div className="dashboard-aside">
          <Card title="当前可用能力">
            <div className="dashboard-capability">
              <Icon name="check" size={17} />
              <div>
                <h3>真实数据导入</h3>
                <p>核对元信息、预览波形、保存草稿。</p>
              </div>
            </div>
            <div className="dashboard-capability">
              <Icon name="signal" size={17} />
              <div>
                <h3>
                  {capabilities
                    ? capabilities.real.available ? "真实筛查已接入" : "真实筛查模型待接入"
                    : "正在读取模型能力…"}
                </h3>
                {capabilities?.real.reason && <p>{capabilities.real.reason}</p>}
              </div>
            </div>
          </Card>
          {!!pending?.length && (
            <Card title="待复核记录">
              <ul className="dashboard-tasks">
                {pending.slice(0, 4).map((result) => (
                  <li key={result.id}>
                    <a href={`#/results/${result.id}`} className="dashboard-review">
                      <strong>{boundCode(result)}</strong>
                      <ModeBadge mode={result.data_mode} />
                      <Icon name="arrow" size={16} />
                    </a>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
