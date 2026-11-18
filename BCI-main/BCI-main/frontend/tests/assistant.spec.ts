import { test, expect } from "@playwright/test";

// 仅在测试中 stub 助手 HTTP，验证客户端竞态；产品仍请求真实本机服务。
test("助手取消和清空中止等待，迟到回复不能写入新会话", async ({ page }) => {
  await page.route("**/api/v1/assistant/status", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        available: true,
        model: "test-stub",
        reason: "",
        max_history: 4,
        timeout_seconds: 20,
      },
    }),
  );
  const pending: (() => Promise<void>)[] = [];
  await page.route(
    "**/api/v1/assistant/chat",
    (route) =>
      new Promise<void>((resolve) => {
        pending.push(async () => {
          await route
            .fulfill({ json: { reply: "迟到的旧回复", model: "test-stub" } })
            .catch(() => undefined);
          resolve();
        });
      }),
  );
  await page.goto("/#/assistant");
  await page.getByLabel("您的问题").fill("旧会话问题");
  await page.getByRole("button", { name: "发送文字" }).click();
  await expect(page.getByRole("button", { name: "取消等待" })).toBeVisible();
  await expect.poll(() => pending.length).toBe(1);
  await page.getByRole("button", { name: "取消等待" }).click();
  await page.getByLabel("您的问题").fill("第二个问题");
  await page.getByRole("button", { name: "发送文字" }).click();
  await expect.poll(() => pending.length).toBe(2);
  await pending[0]();
  await expect(page.getByRole("button", { name: "取消等待" })).toBeVisible();
  await page.getByRole("button", { name: "清空本次会话" }).click();
  await expect(page.getByLabel("您的问题")).toHaveValue("");
  await pending[1]();
  await expect(
    page.getByText("迟到的旧回复", { exact: true }),
  ).not.toBeAttached();
  await expect(page.locator(".chat-message")).toHaveCount(0);
  await page.unroute("**/api/v1/assistant/chat");
  await page.route("**/api/v1/assistant/chat", (route) =>
    route.fulfill({ json: { reply: "新会话有效回复", model: "test-stub" } }),
  );
  await page.getByLabel("您的问题").fill("新会话问题");
  await page.getByRole("button", { name: "发送文字" }).click();
  await expect(page.getByText("新会话有效回复", { exact: true })).toBeVisible();
  await expect(
    page.getByText("迟到的旧回复", { exact: true }),
  ).not.toBeAttached();
});

test("助手本地历史与发送快照按上限保留完整轮次", async ({ page }) => {
  await page.route("**/api/v1/assistant/status", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        available: true,
        model: "test-stub",
        reason: "",
        max_history: 1,
        timeout_seconds: 20,
      },
    }),
  );
  const snapshots: { role: string; content: string }[][] = [];
  await page.route("**/api/v1/assistant/chat", (route) => {
    const body = route.request().postDataJSON();
    snapshots.push(body.messages);
    return route.fulfill({
      json: { reply: "回答：" + body.text, model: "test-stub" },
    });
  });
  await page.goto("/#/assistant");
  for (const input of ["问题一", "问题二", "问题三"]) {
    await page.getByLabel("您的问题").fill(input);
    await page.getByRole("button", { name: "发送文字" }).click();
    await expect(
      page.getByText("回答：" + input, { exact: true }),
    ).toBeVisible();
  }
  await expect(page.locator(".chat-message")).toHaveCount(2);
  expect(snapshots.map((items) => items.map((item) => item.role))).toEqual([
    [],
    ["user", "assistant"],
    ["user", "assistant"],
  ]);
  expect(snapshots[2][0].content).toBe("问题二");
});

test("助手零历史配置保留本次回复且发送空历史", async ({ page }) => {
  await page.route("**/api/v1/assistant/status", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        available: true,
        model: "test-stub",
        reason: "",
        max_history: 0,
        timeout_seconds: 20,
      },
    }),
  );
  const history: unknown[] = [];
  await page.route("**/api/v1/assistant/chat", (route) => {
    history.push(route.request().postDataJSON().messages);
    return route.fulfill({
      json: { reply: "无历史的当前回复", model: "test-stub" },
    });
  });
  await page.goto("/#/assistant");
  await page.getByLabel("您的问题").fill("没有历史的问题");
  await page.getByRole("button", { name: "发送文字" }).click();
  await expect(
    page.getByText("无历史的当前回复", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".chat-message")).toHaveCount(0);
  expect(history).toEqual([[]]);
  await page.getByRole("button", { name: "清空本次会话" }).click();
  await expect(
    page.getByText("无历史的当前回复", { exact: true }),
  ).not.toBeAttached();
});
