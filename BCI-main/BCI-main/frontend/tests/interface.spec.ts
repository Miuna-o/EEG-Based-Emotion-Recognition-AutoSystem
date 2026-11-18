import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";

test("错误可读并包含请求编号，未配置助手不阻断工作台", async ({ page }) => {
  await page.goto("/#/import?mode=real");
  await page
    .getByLabel("选择数据文件")
    .setInputFiles({
      name: "invalid.json",
      mimeType: "application/json",
      buffer: Buffer.from("{not-json"),
    });
  await expect(page.getByRole("alert")).toContainText("请求编号：");
  await page.getByRole("link", { name: "文字助手" }).click();
  await expect(
    page.getByText("assistant_enabled", { exact: false }),
  ).toBeVisible();
  await page.getByRole("link", { name: "工作台", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "脑电数据工作台" }),
  ).toBeVisible();
});

test("多尺寸与等效缩放布局没有水平溢出；主要页面通过 WCAG AA 自动检查", async ({
  browser,
}) => {
  await mkdir("screenshots", { recursive: true });
  const cases = [
    { name: "dashboard-1280x800", width: 1280, height: 800, scale: 1 },
    { name: "dashboard-1440x900", width: 1440, height: 900, scale: 1 },
    { name: "dashboard-1920x1080", width: 1920, height: 1080, scale: 1 },
    { name: "dashboard-1024x800", width: 1024, height: 800, scale: 1 },
    {
      name: "dashboard-equivalent-125pct",
      width: 1152,
      height: 720,
      scale: 1.25,
    },
    {
      name: "dashboard-equivalent-150pct",
      width: 960,
      height: 600,
      scale: 1.5,
    },
  ];
  for (const size of cases) {
    const context = await browser.newContext({
      viewport: { width: size.width, height: size.height },
      deviceScaleFactor: size.scale,
    });
    const page = await context.newPage();
    await page.goto("/");
    await expect(page.getByText("本地服务已连接")).toBeAttached();
    await expect(
      page.getByRole("heading", { name: "脑电数据工作台" }),
    ).toBeVisible();
    const layout = await page.evaluate(() => ({
      available: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    }));
    expect(layout.content).toBeLessThanOrEqual(layout.available);
    await page.screenshot({
      path: `screenshots/${size.name}.png`,
      fullPage: false,
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
    await context.close();
  }
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  for (const route of [
    "/import?mode=demo",
    "/jobs",
    "/results",
    "/records",
    "/research",
    "/settings",
    "/assistant",
  ]) {
    await page.goto("/#" + route);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.screenshot({
      path: "screenshots/page-" + route.split("?")[0].replace("/", "") + ".png",
      fullPage: true,
    });
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      axe.violations,
      route +
        ": " +
        JSON.stringify(
          axe.violations.map((item) => ({
            id: item.id,
            nodes: item.nodes.map((node) => node.target),
          })),
        ),
    ).toEqual([]);
  }
  await context.close();
});

test("侧栏可用键盘收起与展开，导航保持可访问名称", async ({ page }) => {
  await page.goto("/");
  const collapse = page.getByRole("button", { name: "收起侧栏" });
  await collapse.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "展开侧栏" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  await page.getByRole("link", { name: "新建筛查", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "新建筛查" })).toBeVisible();
  await page.getByRole("button", { name: "展开侧栏" }).click();
  await expect(page.getByRole("button", { name: "收起侧栏" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
});
