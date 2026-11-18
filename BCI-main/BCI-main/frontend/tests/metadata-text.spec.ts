import { test, expect } from "@playwright/test";

test("列表逐字符输入保留逗号和换行，保存仅发送变更并撤销旧样本标签", async ({
  page,
}) => {
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
      display_code: "E2E-LIST-001",
      kind: "band_features",
      modality: "EEG",
      axes: ["sample", "channel", "band"],
      sampling_rate: 128,
      channels: ["F3", "F4"],
      bands: ["delta", "theta", "alpha", "beta", "gamma"],
      unit: "uV^2",
      sample_ids: ["old-band-001", "old-band-002"],
      label_space: ["模拟平静", "模拟波动"],
      labels: ["模拟平静", "模拟波动"],
      label_sample_ids: ["old-band-001", "old-band-002"],
    },
    provenance: { data_mode: "demo", generator: "fixed-list-ui-fixture/1.0" },
  };
  await page.goto("/#/import?mode=demo");
  await page
    .getByLabel("选择数据文件")
    .setInputFiles({
      name: "lists.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(fixture)),
    });
  await expect(page.getByText("E2E-LIST-001", { exact: true })).toBeVisible();
  const axes = page.getByLabel("轴定义（按数组顺序）");
  await axes.fill("");
  await axes.pressSequentially("channel,");
  await expect(axes).toHaveValue("channel,");
  await axes.pressSequentially("time");
  await expect(axes).toHaveValue("channel,time");
  await axes.fill("");
  await axes.pressSequentially("sample,channel,band");
  const channels = page.getByLabel("通道名称");
  await channels.fill("");
  await channels.pressSequentially("F3");
  await channels.press("Enter");
  await channels.pressSequentially("F4");
  await expect(channels).toHaveValue("F3\nF4");
  const bands = page.getByLabel("频带名称");
  await bands.fill("");
  await bands.pressSequentially("delta,theta,alpha,beta,gamma");
  const ids = page.getByLabel("样本编码");
  await ids.fill("");
  await ids.pressSequentially("new-band-001,new-band-002");
  const labels = page.getByLabel("标签空间（不自动推断）");
  await labels.fill("");
  await labels.pressSequentially("模拟平静,模拟波动");
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response.url().endsWith("/metadata"),
  );
  await page.getByRole("button", { name: "保存元信息并重新校验" }).click();
  const response = await saved;
  const patch = response.request().postDataJSON().metadata;
  expect(patch).toEqual({ sample_ids: ["new-band-001", "new-band-002"] });
  expect(response.ok()).toBeTruthy();
  const dataset = await response.json();
  expect(dataset.metadata.axes).toEqual(["sample", "channel", "band"]);
  expect(dataset.metadata.channels).toEqual(["F3", "F4"]);
  expect(dataset.metadata.bands).toEqual([
    "delta",
    "theta",
    "alpha",
    "beta",
    "gamma",
  ]);
  expect(dataset.metadata.label_space).toEqual(["模拟平静", "模拟波动"]);
  expect(dataset.metadata.sample_ids).toEqual(["new-band-001", "new-band-002"]);
  expect(dataset.metadata.labels).toBeNull();
  expect(dataset.metadata.label_sample_ids).toBeNull();
  expect(dataset.validation_status).toBe("ready");
});

test("特征名称逐字符输入在保存时形成数组，不重传旧标签", async ({ page }) => {
  const fixture = {
    data: [
      [1, 2],
      [3, 4],
    ],
    metadata: {
      display_code: "E2E-LIST-002",
      kind: "features",
      modality: "FEATURES",
      axes: ["sample", "feature"],
      feature_names: ["old-a", "old-b"],
      unit: "dimensionless",
      sample_ids: ["feature-001", "feature-002"],
      label_space: ["模拟平静", "模拟波动"],
      labels: ["模拟平静", "模拟波动"],
      label_sample_ids: ["feature-001", "feature-002"],
    },
    provenance: { data_mode: "demo", generator: "fixed-list-ui-fixture/1.0" },
  };
  await page.goto("/#/import?mode=demo");
  await page
    .getByLabel("选择数据文件")
    .setInputFiles({
      name: "feature-lists.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(fixture)),
    });
  await expect(page.getByText("E2E-LIST-002", { exact: true })).toBeVisible();
  const names = page.getByLabel("特征名称");
  await names.fill("");
  await names.pressSequentially("new-a,new-b");
  await expect(names).toHaveValue("new-a,new-b");
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response.url().endsWith("/metadata"),
  );
  await page.getByRole("button", { name: "保存元信息并重新校验" }).click();
  const response = await saved;
  expect(response.request().postDataJSON().metadata).toEqual({
    feature_names: ["new-a", "new-b"],
  });
  expect(response.ok()).toBeTruthy();
  const dataset = await response.json();
  expect(dataset.metadata.feature_names).toEqual(["new-a", "new-b"]);
  expect(dataset.metadata.labels).toBeNull();
  expect(dataset.metadata.label_sample_ids).toBeNull();
  expect(dataset.validation_status).toBe("ready");
});
