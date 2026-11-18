import { test, expect } from "@playwright/test";

for (const changed of ["version", "file"]) {
  test(`同输入重试复用幂等键，切换${changed}生成新键`, async ({ page }) => {
    const keys: string[] = [];
    const createdIds: string[] = [];
    // 实际转发至服务端创建任务，仅将前两次HTTP响应替换为测试失败，模拟响应中断。
    await page.route("**/api/v1/jobs", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      keys.push(route.request().postDataJSON().idempotency_key);
      const response = await route.fetch();
      if (keys.length <= 2) {
        expect(response.ok()).toBeTruthy();
        createdIds.push((await response.json()).id);
        await route.fulfill({
          status: 503,
          json: {
            code: "test_response_failure",
            message: "测试响应中断",
            details: null,
            request_id: "test-only-response",
          },
        });
      } else await route.fulfill({ response });
    });
    await page.goto("/#/import?mode=demo");
    await page.getByRole("button", { name: "导入固定合成样本" }).click();
    await page.getByRole("button", { name: "继续预览" }).click();
    await page.getByRole("button", { name: "继续确认" }).click();
    await page
      .getByRole("checkbox", { name: "我已核对数据来源、轴定义与标签空间" })
      .check();
    await page.getByRole("button", { name: "提交演示任务" }).click();
    await expect(page.getByRole("alert")).toContainText("测试响应中断");
    await page.getByRole("button", { name: "提交演示任务" }).click();
    await expect.poll(() => keys.length).toBe(2);
    await expect(
      page.getByRole("button", { name: "提交演示任务" }),
    ).toBeEnabled();
    expect(keys[0]).toBe(keys[1]);
    expect(createdIds[0]).toBe(createdIds[1]);
    await page.getByRole("button", { name: "返回核对" }).click();
    if (changed === "version") {
      await page.getByLabel("来源说明").fill("E2E：新版本独立任务幂等键验证");
      const patch = page.waitForResponse(
        (response) =>
          response.request().method() === "PATCH" &&
          response.url().endsWith("/metadata"),
      );
      await page.getByRole("button", { name: "保存元信息并重新校验" }).click();
      expect((await patch).ok()).toBeTruthy();
      await expect(
        page.getByText("数据版本 v2", { exact: true }),
      ).toBeVisible();
    } else {
      await page.getByRole("button", { name: "重新选择文件" }).click();
      await page.getByRole("button", { name: "导入固定合成样本" }).click();
    }
    await page.getByRole("button", { name: "继续预览" }).click();
    await page.getByRole("button", { name: "继续确认" }).click();
    await page
      .getByRole("checkbox", { name: "我已核对数据来源、轴定义与标签空间" })
      .check();
    await page.getByRole("button", { name: "提交演示任务" }).click();
    await expect.poll(() => keys.length).toBe(3);
    expect(keys[2]).not.toBe(keys[0]);
    await expect(page.getByRole("heading", { name: "任务详情" })).toBeVisible();
  });
}
