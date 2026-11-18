# 心澜 Windows 桌面应用

## 打开与关闭

从工程根目录启动 `desktop/dist/心澜.exe`。本机的 .NET 运行时位于项目内，请使用[本机启动命令](../../../../AGENTS.md#在本机启动)。应用使用独立 Windows 窗口，重复启动会唤起同一窗口。

关闭窗口会自动结束本次应用启动的本地服务。若之前已有网页开发服务在运行，桌面应用会复用它，退出时保留该服务。要停止旧服务，可使用 `停止心澜.bat`。配置修改后应停止旧服务再重新打开。

移动项目时保留完整工程目录，桌面程序依赖同目录的运行文件以及工程中的 Python 环境、前端资源和配置。移动后按实际路径核对 Python 环境和重新生成的快捷方式。

## 操作

界面、配色、布局与原工作台一致。首次体验：工作台 → 体验演示 → 导入固定合成样本 → 继续预览 → 继续确认 → 勾选核对声明 → 提交演示任务 → 查看评估结果 → 保存复核记录 → 导出报告。

JSON、PDF 与 ZIP 使用系统保存对话框，选择目标文件后保存；取消对话框不删除服务端报告。PDF“预览”在心澜自己的预览窗口中打开。研究工具仍为原桌面科研入口，具体操作见 quickstart.md。

桌面化没有新增筛查模型或临床能力：真实模型仍未接入，固定演示持续标记为模拟来源。

## 数据与环境

沿用 `config/xinlan.json` 和 `.xinlan-data/`，已有记录不用迁移。窗口缓存单独保存到存储目录下 `desktop-profile/`。备份时先关闭应用和本地服务，然后复制完整数据目录。

当前交付为 Windows x64 本机版，使用已有 .NET 10 Desktop Runtime、Microsoft Edge WebView2 Runtime 和工程 `.runtime/` Python 环境。日常运行不需要 Node.js、.NET SDK 或联网下载。

## 开发构建

构建需要 .NET 10 SDK、Node.js、已配置的 `.runtime` 环境。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop.ps1
```

构建输出为 `desktop/dist/` 并生成工程根目录的 `心澜.lnk`。WebView2 SDK 固定为 1.0.4314.35，NuGet 内容哈希记录于 desktop/packages.lock.json。构建缓存位于 `.desktop-build/`；首次构建从官方 NuGet 下载 SDK。

底层网页调试仍可使用 `scripts/start.ps1`，仅日常启动入口改为桌面 APP。

## 验证方式

```powershell
.runtime/Scripts/python.exe -B -X utf8 -m pytest tests/test_desktop_service.py tests/test_desktop_reports.py tests/test_launcher_integration.py tests/test_launcher_port_change.py -q
node scripts/desktop_e2e.cjs
```

自动化启动真实 EXE 和 WebView2，用隔离合成数据验证。受工具环境限制，自动化子进程通过临时环境变量关闭嵌套 Chromium 沙箱并使用软件渲染；这些参数不写入交付应用、快捷方式或全局环境。正常 Windows 桌面启动仍保留 WebView2 默认安全策略。截图、报告和检查记录保留在 `.desktop-build/e2e-*`。
