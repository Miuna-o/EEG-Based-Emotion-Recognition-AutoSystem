import { test, expect } from "@playwright/test";
import { readFile, mkdir } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";

test("演示导入 → 任务 → 结果 → 复核 → JSON/PDF报告 → 重载恢复", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "脑电数据工作台" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "体验演示", exact: true }).click();
  await expect(
    page.getByText("模拟演示，非实际筛查结果", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "导入固定合成样本" }).click();
  await expect(
    page.getByText("DEMO-001", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "继续预览" }).click();
  await expect(page.getByRole("heading", { name: "数据预览" })).toBeVisible();
  await expect(page.getByRole("img", { name: /脑电波形/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "继续确认" })).toBeEnabled();
  await mkdir("screenshots", { recursive: true });
  await page.screenshot({
    path: "screenshots/import-preview-1440x900.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "采样散点", exact: true }).click();
  await expect(page.getByRole("img", { name: /脑电采样散点/ })).toBeVisible();
  await page.getByRole("button", { name: "通道对比", exact: true }).click();
  await expect(page.getByRole("heading", { name: "各通道的幅值大小" })).toBeVisible();
  await expect(page.getByText("8.49 μV", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "头皮电极", exact: true }).click();
  await page.getByRole("button", { name: /电极 F4/ }).click();
  await expect(page.getByRole("img", { name: /脑电波形.*F4/ })).toBeVisible();
  await expect(page.getByRole("img", { name: /脑电波形.*F3/ })).toHaveCount(0);
  await page.getByRole("button", { name: "继续确认" }).click();
  await page
    .getByRole("checkbox", { name: "我已核对数据来源、轴定义与标签空间" })
    .check();
  await page.getByRole("button", { name: "提交演示任务" }).click();
  await expect(
    page.getByRole("button", { name: "查看评估结果" }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "查看评估结果" }).click();
  await expect(
    page.getByRole("heading", { name: "评估结果", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("可靠性信息缺失，需要复核", { exact: false }).first(),
  ).toBeVisible();
  await page.getByLabel("复核人编码").fill("E2E-REVIEWER");
  await page
    .getByLabel("复核意见")
    .fill("已核对固定合成演示样本。此记录仅用于流程验证，不用于实际筛查。");
  await page.getByRole("button", { name: "保存复核记录" }).click();
  await expect(page.getByText("E2E-REVIEWER", { exact: true })).toBeVisible();
  await mkdir("screenshots", { recursive: true });
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    (document.activeElement as HTMLElement | null)?.blur();
  });
  await page.screenshot({
    path: "screenshots/result-detail-1440x900.png",
    fullPage: true,
  });
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    axe.violations,
    JSON.stringify(
      axe.violations.map((item) => ({
        id: item.id,
        nodes: item.nodes.map((node) => node.target),
      })),
    ),
  ).toEqual([]);
  const jsonDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 JSON 报告" }).click();
  const jsonFile = await jsonDownload;
  expect(jsonFile.suggestedFilename()).toMatch(/demo.*\.json$/);
  const snapshot = JSON.parse(
    await readFile((await jsonFile.path())!, "utf-8"),
  );
  expect(snapshot.data_mode).toBe("demo");
  expect(snapshot.watermark).toBe("模拟演示，非实际筛查结果");
  expect(snapshot.assessment.reliability).toBeNull();
  expect(snapshot.reviews.at(-1).reviewer).toBe("E2E-REVIEWER");
  const pdfDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 PDF 报告" }).click();
  const pdfFile = await pdfDownload;
  expect(pdfFile.suggestedFilename()).toMatch(/demo.*\.pdf$/);
  const pdf = await readFile((await pdfFile.path())!);
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
  expect(pdf.byteLength).toBeGreaterThan(2000);
  const jsonPreviewButton = page
    .locator(".report-row")
    .filter({ hasText: "JSON" })
    .first()
    .getByRole("button", { name: "预览", exact: true });
  await jsonPreviewButton.focus();
  await jsonPreviewButton.press("Enter");
  await expect(
    page.getByRole("dialog", { name: "JSON报告预览" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("dialog", { name: "JSON报告预览" }),
  ).not.toBeAttached();
  await expect(jsonPreviewButton).toBeFocused();
  await page.reload();
  await expect(page.getByText("E2E-REVIEWER", { exact: true })).toBeVisible();
  const update = await page.request.patch(
    `/api/v1/datasets/${snapshot.dataset.id}/metadata`,
    {
      data: {
        expected_version: snapshot.dataset.version,
        metadata: {
          source_description: "E2E：更新合成演示来源说明以验证历史版本保护",
        },
      },
    },
  );
  expect(update.ok()).toBeTruthy();
  await expect(
    page.getByText("来源版本已变更，此结果已过期", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "导出 JSON 报告" }),
  ).toBeDisabled();
  const reportRow = page
    .locator(".report-row")
    .filter({ hasText: "JSON" })
    .first();
  await expect(
    reportRow.getByRole("button", { name: "下载", exact: true }),
  ).toBeDisabled();
  await expect(reportRow.getByText("已过期", { exact: true })).toBeVisible();
  const oldDownload = await page.request.get(
    `/api/v1/reports/${snapshot.report_id}/download`,
  );
  expect(oldDownload.status()).toBe(409);
  const historicalDownload = page.waitForEvent("download");
  await reportRow.getByRole("button", { name: "下载历史存档" }).click();
  const historical = await historicalDownload;
  expect(historical.suggestedFilename()).toMatch(/\.zip$/);
  expect(
    (await readFile((await historical.path())!)).subarray(0, 2).toString(),
  ).toBe("PK");
});

test("草稿不能提交，真实模型缺失不会自动切换为演示", async ({ page }) => {
  await page.goto("/#/import?mode=real");
  await page.getByLabel("选择数据文件").setInputFiles({
    name: "draft.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("feature_a,feature_b,feature_c\n1,2,3\n4,5,6\n"),
  });
  await expect(page.getByText("草稿", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "继续预览" }).click();
  await expect(page.getByRole("table", { name: /数值预览.*2 行 × 3 列/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "头皮电极" })).toHaveCount(0);
  await page.getByRole("button", { name: "继续确认" }).click();
  await page
    .getByRole("checkbox", { name: "我已核对数据来源、轴定义与标签空间" })
    .check();
  await expect(
    page.getByRole("button", { name: "提交筛查任务" }),
  ).toBeDisabled();
  await expect(
    page.getByText("未发现 PACER 推理实现", { exact: false }).first(),
  ).toBeVisible();
});
