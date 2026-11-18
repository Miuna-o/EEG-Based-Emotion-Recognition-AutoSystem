import { test, expect } from "@playwright/test";

test("频带输入重新选择并保存后保持EEG模态且元信息就绪", async ({ page }) => {
  const fixture = {
    data: [
      [
        [1, 2, 3, 4, 5],
        [6, 7, 8, 9, 10],
      ],
      [
        [2, 3, 4, 5, 6],
        [7, 8, 9, 10, 11],
      ],
    ],
    metadata: {
      display_code: "E2E-BAND-001",
      kind: "band_features",
      modality: "EEG",
      axes: ["sample", "channel", "band"],
      sampling_rate: 128,
      channels: ["F3", "F4"],
      bands: ["delta", "theta", "alpha", "beta", "gamma"],
      unit: "uV^2",
      sample_ids: ["demo-band-001", "demo-band-002"],
      label_space: ["模拟平静", "模拟波动"],
      source_description: "固定三维合成频带数值，仅用于元信息UI验证。",
    },
    provenance: { data_mode: "demo", generator: "fixed-band-ui-fixture/1.0" },
  };
  await page.goto("/#/import?mode=demo");
  await page
    .getByLabel("选择数据文件")
    .setInputFiles({
      name: "band-fixture.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(fixture)),
    });
  await expect(page.getByText("E2E-BAND-001", { exact: true })).toBeVisible();
  await expect(page.getByText("可分析", { exact: true })).toBeVisible();
  await page.getByLabel("输入类型").selectOption("features");
  await page.getByLabel("输入类型").selectOption("band_features");
  const savedResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response.url().endsWith("/metadata"),
  );
  await page.getByRole("button", { name: "保存元信息并重新校验" }).click();
  const response = await savedResponse;
  expect(response.ok()).toBeTruthy();
  const dataset = await response.json();
  expect(dataset.metadata.kind).toBe("band_features");
  expect(dataset.metadata.modality).toBe("EEG");
  expect(dataset.shape).toEqual([2, 2, 5]);
  expect(dataset.validation_errors).toEqual([]);
  expect(dataset.validation_status).toBe("ready");
  await expect(page.getByText("可分析", { exact: true })).toBeVisible();
});
