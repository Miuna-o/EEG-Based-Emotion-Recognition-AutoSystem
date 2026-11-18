import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { demoRecord } from "./fixtures";

test("历史任务、结果与报告使用绑定版本编码，报告按旧编码检索", async ({
  page,
}) => {
  const fixture = await demoRecord(page.request);
  const newCode = fixture.code + "-NEW";
  const patched = await page.request.patch(
    `/api/v1/datasets/${fixture.dataset.id}/metadata`,
    {
      data: {
        expected_version: fixture.dataset.version,
        metadata: { display_code: newCode },
      },
    },
  );
  expect(patched.ok()).toBeTruthy();
  for (const route of ["/jobs", "/results", "/records"]) {
    await page.goto("/#" + route);
    await expect(page.getByText(fixture.code, { exact: true })).toBeVisible();
    await expect(page.getByText(newCode, { exact: true })).not.toBeAttached();
  }
  await page.getByLabel("数据编码 / 报告编号").fill(fixture.code);
  await expect(page.getByText(fixture.code, { exact: true })).toBeVisible();
  await page.getByLabel("数据编码 / 报告编号").fill(newCode);
  await expect(
    page.getByText("没有符合条件的报告", { exact: true }),
  ).toBeVisible();
});

for (const scenario of ["results-dataset", "records-review"]) {
  test(`已打开JSON预览在${scenario}变更后关闭`, async ({ page }) => {
    const fixture = await demoRecord(page.request);
    if (scenario.startsWith("results"))
      await page.goto("/#/results/" + fixture.job.assessment_id);
    else {
      await page.goto("/#/records");
      await page.getByLabel("数据编码 / 报告编号").fill(fixture.code);
    }
    await page
      .getByRole("button", { name: "预览", exact: true })
      .first()
      .click();
    await expect(
      page.getByRole("dialog", { name: "JSON报告预览" }),
    ).toBeVisible();
    await expect(page.getByRole("dialog")).toContainText(fixture.report.id);
    const changed = scenario.startsWith("results")
      ? await page.request.patch(
          `/api/v1/datasets/${fixture.dataset.id}/metadata`,
          {
            data: {
              expected_version: fixture.dataset.version,
              metadata: {
                source_description: "E2E：预览期间更新固定合成输入说明",
              },
            },
          },
        )
      : await page.request.post(
          `/api/v1/assessments/${fixture.job.assessment_id}/reviews`,
          {
            data: {
              expected_revision: 0,
              reviewer: "E2E-SNAPSHOT",
              opinion: "只验证报告预览修订保护。",
              status: "needs_followup",
              idempotency_key: randomUUID(),
            },
          },
        );
    expect(changed.ok()).toBeTruthy();
    await expect(
      page.getByRole("dialog", { name: "JSON报告预览" }),
    ).not.toBeAttached();
    await expect(
      page.getByText(
        "报告版本已变更，已关闭当前预览。请核对版本或下载历史存档。",
        { exact: true },
      ),
    ).toBeVisible();
  });
}
