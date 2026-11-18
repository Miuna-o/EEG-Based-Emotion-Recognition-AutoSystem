# 心澜 Web 工作台

React + TypeScript + Vite 前端，服务端 API 为 `/api/v1`。界面包含工作台、四步导入、筛查任务、评估与复核、记录报告、研究工具入口、设置帮助及可选文字助手。

## 启动

需要 Node.js ≥ 22.12；本次实际使用 22.14.0。项目根目录先按 `scripts/start.ps1` 启动本地服务。前端开发：

```powershell
cd frontend
npm ci
npm run dev
```

开发页面为 `http://127.0.0.1:5173`，Vite 将 `/api` 转发至 `http://127.0.0.1:8765`。生产构建执行 `npm run build`，然后重启本地服务，通过 `http://127.0.0.1:8765` 使用 FastAPI 同源发布的页面与 API。

## 验证

```powershell
npm run typecheck
npm run lint
npm run build
npm run test:e2e
```

`test:e2e` 使用 `scripts/frontend_e2e.py` 监督器，避免 Windows 测试框架等待 Vite 子进程退出。它只清理自己启动的开发进程；已有 Vite 会复用并保持运行。本地 API 需先启动。

端到端测试使用实际本地服务，导入固定合成演示样本和匿名 CSV 草稿。测试包含：导入与预览、任务重载恢复、复核、JSON/PDF 实际下载与内容检查、结果及报告过期、历史 ZIP 下载、错误编号、键盘导航、多尺寸和 WCAG AA 自动检查，以及生产同源页面烟测。

测试优先使用本机已有 Chromium；可设置 `XINLAN_CHROMIUM` 为浏览器可执行文件路径。若本机没有该文件，则使用 Playwright 默认浏览器，执行 `npx playwright install chromium` 安装。截图存储于 `screenshots/`，HTML 测试报告存储于 `playwright-report/`。

## 契约生成

从项目根目录执行：

```powershell
.runtime/Scripts/python.exe frontend/scripts/generate_types.py
```

生成 `src/generated/openapi.json` 与 `src/generated/api.ts`。脚本直接调用真实 FastAPI `create_app(start_worker=False).openapi()`，不会启动 worker。领域实体以此生成契约为准；当前未声明 `response_model` 的能力、设置及预览返回形状见 `src/api.ts`，依据服务端真实序列化函数定义。

## 实施边界

- 真实推理能力取自 `/capabilities`。当前真实模型缺失时，保留导入及核对功能，并禁用真实任务提交。
- 模拟演示由用户主动选择。固定合成样本、任务、评估和导出持续标为模拟演示。
- 可靠性、频带证据或电极坐标缺失时，展示服务端缺失原因。分类置信度与可靠性分别呈现。
- 元信息采用 `expected_version`，复核及报告采用 `expected_revision`。任务提交、重试和复核采用幂等标识。
- 列表字段保留自由文本草稿，保存时按逗号或换行解析，PATCH 仅提交实际变化字段。样本或特征映射变化时，旧标签由服务端按契约撤销。
- 任务、结果、报告和工作台历史记录使用绑定版本的 `display_code`；缺失时显示内部编号。JSON 预览单独轮询绑定报告，发现版本过期后关闭并提示。
- 提交幂等键绑定数据 ID、版本与来源模式；同输入响应失败重试复用，新版本或新文件生成新键。
- 查询使用包含数据 ID 和版本的路径作为键，并采用 AbortController 处理卸载与版本变化；提交期间禁用操作。
- 过期报告禁用普通预览及下载，独立的“下载历史存档”获取含过期说明和当前版本信息的 ZIP。
- ECharts 在预览页按需加载。助手独立且可选，界面只发送用户明确输入的文字。
- 助手等待中支持取消和清空；迟到回复采用请求代次与会话代次保护。历史按 `max_history` 完整轮次有界；配置为零时发送空历史并仅显示当前回复。
- 研究工具展示服务端返回的既有桌面入口；具体算法继续在原研究环境运行。

实际验证记录与截图说明见 `../docs/frontend-report.md`。
