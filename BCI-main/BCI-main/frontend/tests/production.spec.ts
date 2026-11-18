import { test, expect } from "@playwright/test";
test("FastAPI生产同源加载静态资源、导入、按需图表与诊断下载", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("http://127.0.0.1:8765/");
  await expect(page.getByText("本地服务已连接")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "脑电数据工作台" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "体验演示", exact: true }).click();
  await page.getByRole("button", { name: "导入固定合成样本" }).click();
  await expect(
    page.getByText("DEMO-001", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "继续预览" }).click();
  await expect(page.locator(".waveform canvas")).toBeVisible();
  await page.getByRole("button", { name: "前 1 秒", exact: true }).click();
  await page.getByRole("button", { name: "重置缩放", exact: true }).click();
  await page.getByRole("button", { name: "头皮电极", exact: true }).click();
  await expect(page.getByRole("button", { name: /电极 F3/ })).toBeVisible();
  const cap = page.locator(".scalp-image");
  await expect(cap).toBeVisible();
  await expect.poll(() => cap.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  expect(new URL(await cap.evaluate((image: HTMLImageElement) => image.currentSrc)).origin).toBe("http://127.0.0.1:8765");
  await page.getByRole("link", { name: "设置与帮助", exact: true }).click();
  await expect(page.getByRole("heading", { name: "设置与帮助" })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出诊断包" }).click();
  expect((await download).suggestedFilename()).toBe("xinlan-diagnostics.zip");
  expect(errors).toEqual([]);
});

test("工作台与操作指南的照片和中文字体可由本机加载", async ({ page }) => {
  const origin = "http://127.0.0.1:8765";
  const externalRequests: string[] = [];
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin === origin) return route.continue();
    externalRequests.push(url.origin);
    return route.abort();
  });

  const pages = [
    { path: "/", title: "脑电数据工作台" },
    { path: "/import", title: "新建筛查" },
    { path: "/research", title: "研究工具" },
    { path: "/settings", title: "设置与帮助" },
  ];
  const photoUrls = new Set<string>();
  for (const { path, title } of pages) {
    await page.goto(origin + "/#" + path);
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
    const photo = page.locator("main img.page-photo");
    await expect(photo).toHaveJSProperty("complete", true);
    const { source, width } = await photo.evaluate((image: HTMLImageElement) => ({
      source: image.currentSrc,
      width: image.naturalWidth,
    }));
    expect(width).toBeGreaterThan(0);
    expect(new URL(source).origin).toBe(origin);
    photoUrls.add(source);
  }
  expect(photoUrls.size).toBe(pages.length);

  await page.goto(origin + "/#/research");
  const credit = page.getByRole("button", { name: /脑电帽摄影.*Chris Hope/ });
  await credit.click();
  const license = page.getByRole("dialog", { name: "脑电帽摄影授权" });
  await expect(license).toContainText("https://creativecommons.org/licenses/by/2.0/");
  await page.keyboard.press("Escape");
  await expect(credit).toBeFocused();

  expect(await page.evaluate(async () => {
    await document.fonts.ready;
    return [...document.fonts].some(
      (font) => font.family.includes("Noto Sans SC") && font.status === "loaded",
    );
  })).toBe(true);
  for (const name of ["noto-sans-sc", "noto-serif-sc", "ibm-plex-mono"]) {
    const notice = await page.request.get(origin + "/assets/licenses/" + name + ".txt");
    expect(notice.ok()).toBe(true);
    expect(await notice.text()).toContain("SIL OPEN FONT LICENSE");
  }
  expect(externalRequests).toEqual([]);
});
