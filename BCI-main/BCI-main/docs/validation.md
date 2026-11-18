# 心澜运行验证记录

本次工作从 2026-11-14 开始，验收持续至 2026-11-15。证据目录位于工作区 `review_artifacts/migration-2026-11-14/`；目录日期表示基线建立日。

## 验证内容与来源

最终在当前稳定源码上实际运行 `scripts/verify.ps1`：后端 **41 项**、旧入口 **44 项**、隐藏五面板烟测、前端 typecheck/lint/build 均通过；前端 **17 项** E2E 全部通过。首次 Windows 测试收尾等待 Vite 退出，已仅关闭经父进程树核验的本次测试进程；新增监督器复验 17 项通过，约 1.1 分钟，退出码 0，能自行清理自己的开发服务。

固定输入兼容 **2 项**另在生成基线的原 Anaconda 环境通过，20 个 EEG 特征值逐值相等。当前 `.runtime` 与独立 `.install-check` 均不继承系统 site-packages；pip check 无冲突。最终摘要：工作区 `review_artifacts/migration-2026-11-14/final-verification.json`。

| 检查 | 证据 |
|---|---|
| 原始工程与既有文件 | baseline.json，199 文件 SHA256；original-source 备份 |
| 原有数值/归档/图像工件 | original-artifact-check.json，98 个文件未变 |
| 核心冻结 | 35 个源码 + 1 个既有工件哈希一致；未重训或修改模型 |
| 固定输入兼容 | 原备份源码生成 algorithm-baseline.json；当前 EEGFeatureExtractor 的 20 个固定特征值逐值相等 |
| 正确性修复 | legacy-review-red.log、legacy-mne-red.log、legacy-review-green.log；44 项回归，限定复审通过 |
| 新后端 | 单独建立不继承系统包的 .install-check，安装 41 个开发锁依赖；backend-clean-env.xml 首轮 35 项通过 |
| 补充边界 | 安全 JSON dtype 展开规模拒绝；schema 精确一致；历史编码绑定版本；文件模拟标记不可导为 real；改变端口前不覆盖活动实例 |
| 前端 | frontend-report.md，真实 API E2E、下载内容、过期状态、14 组 axe A/AA；后续修复按独立审查新增定向回归 |
| 中文 PDF | pdf/verification.json；草稿 2 页、长复核 3 页，嵌入中文字体，全部页模拟标记；PDFium 渲染后人工查看 |
| 启动器 | 真正隐藏子进程、空闲端口启动、重复启动不新建、身份核验与安全停止、占用端口不杀外部服务 |
| 依赖审计 | npm-audit.json，0 个已知漏洞；Vite 8.1.6、ESLint 9.39.5、定向 minimatch 11.0.8 覆盖修复。不是完整渗透测试 |

测试使用固定正弦/匿名合成数组和临时目录；没有读取人的原始信号，没有训练。少量故障注入用于提供方异常、迟到结果、取消竞态，不属于产品虚假数据来源。

## 可复现命令

从工程根目录：

```powershell
.runtime/Scripts/python.exe -m pip install -r backend/requirements-dev.lock
.runtime/Scripts/python.exe -X utf8 -m pytest tests/test_workspace_api.py tests/test_job_integrity.py tests/test_reporting_and_io.py tests/test_optional_assistant.py tests/test_review_regressions.py tests/test_json_schema_limits.py tests/test_frontend_contract.py tests/test_versioned_display_code.py tests/test_import_mode_marker.py tests/test_launcher_integration.py tests/test_launcher_port_change.py -q
```

旧入口用已有科研解释器，避免为了新工作台自动安装 CUDA/torch：

```powershell
& '<research-python.exe>' -B -X utf8 -m unittest discover -s tests -p 'test_legacy*.py' -v
& '<research-python.exe>' -B -X utf8 -m tests.legacy_hidden_smoke
```

本次旧 IO/UI 边界测试子进程使用 `NUMBA_DISABLE_JIT=1`，以避免现有 antropy 的导入编译等待。该条件没有修改用户环境、依赖或源码，也没有用来声称算法数值兼容；固定输入兼容检查在另一条原环境命令中执行。

固定数值兼容检查需要 NumPy、SciPy、networkx 与原备份证据；本次实际使用原 Anaconda 3.13 环境，与生成基线相同：

```powershell
python -X utf8 -m pytest tests/test_algorithm_compatibility.py -q
```

启动 API 后：

```powershell
cd frontend
npm run typecheck
npm run lint
npm run build
npm run test:e2e
```

Windows 推荐由监督器管理验证 Vite 的生命周期：

```powershell
.runtime/Scripts/python.exe -X utf8 scripts/frontend_e2e.py
```

它复用已有开发服务器而不结束它，或只结束自己持有 Popen 句柄的 Node 进程，避免框架收尾等待；不会管理其他 Node。`scripts/verify.ps1` 已调用此监督器。

也可执行 `scripts/verify.ps1 -ResearchPython '<research-python.exe>'`。它要求本地 API 已启动，按实际失败退出；不会把未运行的检查标成通过。

## 关键回归语义

- Excel 源文件哈希及同名哨兵 CSV 保持不变。
- NPZ/JSON 回读保持可移植元信息、数据 dtype/shape、事件和模态；读取器不串状态。
- 元信息不足、NaN/Inf、对象数组、标签样本错配、错版本和模式冲突不能提交分析。
- 同输入幂等；不同输入 key 冲突；取消、重试、进程池损坏、重启、输入更新和迟到结果均有确定状态。
- 缺少真实模型/Ollama/可靠性/电极坐标时，提供明确缺失原因，不回退真实结果到模拟。
- 复核只追加意见；缺失或低可靠性不会因点击复核变成高可靠性。
- 报告生成和下载检查版本；过期存档保留原文件并附明确过期说明。
- 主流程从实际导入、核对、演示任务、结果、复核到 PDF/JSON 导出及重新打开。

## 验证范围说明

原生 Windows 全局 DPI 没有修改。125%/150% 使用等效 CSS 视口与像素密度，属于布局验证。axe 自动检查不是完整无障碍认证。没有宣称性能压力、渗透、临床或真实模型效度验证。旧 Qt 子图的全部可见交互仍有明确边界。

独立审查初轮报告保留，修复后的限定复审另记录，不能把“原测试通过”当作发现问题已经消失的证据。
