# 心澜本地工作台启动与使用

应用根目录是工作区中的 `BCI-main/BCI-main/BCI-main`。心澜以独立 Windows 窗口运行，无登录账号。完整桌面说明见 [desktop.md](desktop.md)。

## 当前电脑日常使用

按[本机启动命令](../../../../AGENTS.md#在本机启动)打开桌面窗口。关闭窗口会结束本次应用创建的服务。原先已运行的服务可继续使用。环境检查使用 `诊断心澜.bat`。从源码重建桌面应用执行 `scripts/build-desktop.ps1`。

以下为保留的网页开发/调试入口，日常使用不需要执行。在工程根目录打开 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

启动器检查端口和服务健康，在隐藏窗口启动自己的 Python 服务，再打开 `http://127.0.0.1:8765`。服务已运行时可直接打开该地址。只需一个 API 服务，构建后的前端由它同源提供。

停止和诊断：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop.ps1
powershell -ExecutionPolicy Bypass -File scripts/diagnose.ps1
```

启动器核验 PID、创建时间、父子进程关系与本次实例令牌，只管理自己启动的服务。端口被占用或身份不符会解释原因；不强杀其他 Python/Node 进程。

## 首次在新环境安装

已验证平台：Windows x64，Python 3.13.5，Node.js 22.14.0。Python 依赖锁针对 3.13，前端要求 Node ≥22.12。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

安装器在工程内创建 `.runtime/`，从 `backend/requirements.lock` 安装 35 个固定版本依赖，再执行前端 `npm ci` 和构建。交付到其他电脑时按锁文件重建 Python 与 Node.js 依赖。

重新安装前请先停止 Vite 开发服务器；Windows 会锁住正在使用的原生模块。安装器发现 5173 端口在用会提前提示，不会强杀 Node 或继续清理依赖。

本机独立环境验证曾遇到 pip 系统证书/缓存处理停滞；关闭缓存并使用 certifi 的传统证书模式后完成，TLS 校验保持启用。`安装心澜.bat` 已使用此模式；PowerShell 安装可加 `-LegacyCertificates`。单独修复依赖可执行：

```powershell
.runtime/Scripts/python.exe -m pip install -r backend/requirements.lock --no-cache-dir --use-deprecated=legacy-certs --index-url https://pypi.org/simple --timeout 15 --retries 1
```

## 首次体验

1. 工作台选择“体验演示”。这是用户主动选择的模拟流程。
2. 导入固定合成样本，核对通道、轴、128 Hz、uV、时间窗与模拟标签空间。
3. 查看波形预览及质量缺失说明，确认提交。
4. 进入任务详情；刷新页面仍能从后端恢复任务。
5. 查看固定演示情绪输出、分类置信度、缺失可靠性及五频带缺失原因。
6. 输入复核人编码与意见，保存复核记录。
7. 导出真实 JSON/PDF。所有演示页面与文件持续保留模拟标记。

真实模式可以导入、核对和暂存草稿；当前缺少已训练筛查提供方，不能执行真实情绪推理。它不会自动变成演示。

## 导入要求

- 支持 NPY、数值 NPZ、心澜 metadata NPZ、已修复旧四层安全 NPZ/JSON、数值 CSV/TSV、XLSX。
- 普通上传不接受 pickle、对象数组、任意服务器路径、多文件 EEG 格式或多模态归档。新工作台的四层导入首版仅接受单一 EEG；多模态研究仍使用旧入口。
- CSV/TSV/XLSX 首行必须是非数值、非空且唯一的文字列名。无表头文件须显式添加表头，避免静默丢掉首行。
- 文件默认 ≤32 MiB，实数数组 ≤4,000,000 元素；解压规模、数组头与有限值均校验。
- 轴顺序、采样率、通道、单位、样本/时间窗 ID 和标签空间须明确。不从文件名猜结果，不默认 1000 Hz。
- 信息不足只能保存草稿。更改元信息产生新版本，旧任务与报告显示过期。

## 研究工具回退

五项原研究功能仍保留于 `core/UI/main_UI.py`：预处理、特征提取、统计分析、分类训练评估、通用图表。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-legacy.ps1 -Python "你的研究环境/python.exe"
```

使用已有安装科研依赖的解释器；不要分发绑定他人电脑路径的虚拟环境。新 Web 运行环境不强制安装 torch、mne 或 Qt。此电脑已有研究环境的位置记录在验证报告，不写死在启动脚本中。

## 开发模式

工程根目录启动 API：

```powershell
.runtime/Scripts/python.exe -X utf8 -m backend.app
```

另一个终端：

```powershell
cd frontend
npm ci
npm run dev
```

开发地址 `http://127.0.0.1:5173`，精确限定 CORS；生产使用同源 8765。重建前端后重启 API，保证 assets 挂载存在。API 文档：`http://127.0.0.1:8765/docs`。

## 配置、存储与备份

单一配置入口 `config/xinlan.json`，优先级：代码默认值 < 配置文件 < `XINLAN_字段名` 环境变量。修改后重启生效。设置页面展示实际生效值及版本。

默认存储 `.xinlan-data/`：SQLite 元信息、`artifacts/` 数值工件、`reports/` 不可变报告、服务日志和启动器实例记录。源码修改前备份在工作区 `review_artifacts/migration-2026-11-14/original-source/`，原文件哈希清单为 `baseline.json`。

备份应用数据时先停止服务，再完整复制 `.xinlan-data/`。不要单独复制 SQLite 的某一张表或移动工件。原始用户文件不会被新导入流程覆盖。诊断 ZIP 不包含原始信号、复核意见或助手会话。

助手默认关闭。需要使用时在配置中设置本机地址、模型名和 enabled；只发送用户明确输入的文字。连接超时、重试与历史数量有上限；等待时可取消或清空。
