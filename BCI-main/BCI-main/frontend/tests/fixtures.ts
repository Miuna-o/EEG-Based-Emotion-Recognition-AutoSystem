import { expect } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";
import { randomUUID } from "node:crypto";
import type { Dataset, Job, Report } from "../src/generated/api";

/** 实际API创建固定合成样本与演示输出，测试自身不替代模型或服务契约。 */
export async function demoRecord(api: APIRequestContext) {
  const code = "E2E-SNAPSHOT-" + randomUUID().slice(0, 8);
  const sample = await (await api.get("/api/v1/demo/sample")).json();
  sample.metadata.display_code = code;
  const imported = await api.post("/api/v1/datasets/import", {
    multipart: {
      data_mode: "demo",
      file: {
        name: "snapshot.json",
        mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify(sample)),
      },
    },
  });
  expect(imported.ok()).toBeTruthy();
  const dataset = (await imported.json()) as Dataset;
  const submitted = await api.post("/api/v1/jobs", {
    data: {
      dataset_id: dataset.id,
      dataset_version: dataset.version,
      provider: "demo",
      idempotency_key: randomUUID(),
    },
  });
  expect(submitted.ok()).toBeTruthy();
  let job = (await submitted.json()) as Job;
  await expect
    .poll(async () => {
      job = (await (await api.get("/api/v1/jobs/" + job.id)).json()) as Job;
      return job.status;
    })
    .toBe("succeeded");
  expect(job.assessment_id).toBeTruthy();
  const exported = await api.post(
    `/api/v1/assessments/${job.assessment_id}/reports`,
    { data: { format: "json", expected_revision: 0 } },
  );
  expect(exported.ok()).toBeTruthy();
  const report = (await exported.json()) as Report;
  return { code, dataset, job, report };
}
