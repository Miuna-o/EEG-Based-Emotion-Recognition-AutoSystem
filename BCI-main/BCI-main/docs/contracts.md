# 心澜应用契约与版本规则

领域 schema `1.0`，API `/api/v1`，实现为 `backend/app/domain/models.py`。OpenAPI 由服务实际生成，前端实体类型位于 `frontend/src/generated/api.ts`。数值不作为大型 JSON 响应返回。

| 实体 | 身份与用途 |
|---|---|
| Dataset | id、version、schema_version、real/demo、source_hash、格式、形状、轴/单位/采样率/通道/频带、sample_ids、label_space、工件引用、验证状态 |
| Session | 独立会话 ID、数据集 ID、来源模式与创建时间 |
| Artifact | 内部 ID、SHA256、shape/dtype/大小；仅后端通过 ID 映射路径 |
| Job | 输入数据集/版本/哈希、提供方、attempt/retry_of、状态、阶段、已处理数、耗时、事件日志 |
| Assessment | 输入和任务身份、配置/适配器/提供方版本、原始情绪输出、confidence、reliability、五频带实际证据与缺失原因 |
| Review | 追加写；复核人编码、意见、时间、结果和数据版本、revision；不改变算法可靠性 |
| Report | 不可变生成快照、格式与 SHA256；读取时另计算当前数据/复核版本和 stale 状态 |

## 数据语义

- `eeg`：二维、明确 channel/time 两轴，单位 V/mV/uV、采样率与通道数量一致，一个明确时间窗 ID。
- `features`：二维 sample/feature，逐样本 ID、特征名、单位与标签空间。
- `band_features`：三维 sample/channel/band，完整明确五频带顺序、原始采样率与通道。
- 轴可以由操作者明确声明顺序。预览按声明读取；不猜测、转置保存或归一化原数组。
- EEG 预览返回原始轴长度 `channel_count`、`sample_count`。前 8 个通道的 `series` 同时提供有界波形点和基于该通道全部原始采样点的均方根幅值 `rms`，单位与原始记录一致。头皮电极图按可匹配的通道名称显示示意位置。
- 标签必须按 sample_id 和当前版本绑定。缺失/错误信息不得通过补零、截断或默认参数隐藏。
- 各实体保留 real/demo。文件内明确模拟来源不可重新标为 real。演示分类器仅返回固定界面契约示例，与信号情绪无推理关系。
- `confidence`、`reliability` 与结构质量检查互相独立。可靠性缺失、阈值/来源规则缺失均不能自动免除人工复核。

## 版本与事务

`PATCH datasets/{id}/metadata` 必须携带 `expected_version`；成功生成新版本，旧元信息和数值工件保持。样本/特征映射变化撤销未同时显式提交的旧标签。

任务提交使用 dataset_id/version/idempotency_key；相同 key 同输入返回同一任务，不同输入返回 409。重试生成新的 attempt 并保留原任务。执行完成后再次校验状态及当前输入版本，取消或过期结果不发布。

```text
queued -> running | cancelled | interrupted
running -> cancelling | succeeded | failed | interrupted
cancelling -> cancelled | interrupted
终态：succeeded / failed / cancelled / interrupted
```

独立进程不支持立即停止时保持 cancelling，等待安全边界再丢弃结果。重启将失联任务变为 interrupted，要求显式重试；不声称透明续算。损坏进程池会终结已认领任务并重建单工作进程池。

复核提交使用 expected_revision 和幂等 key，追加保存修订，竞争提交返回 409。报告生成要求最新结果/复核版本；既有报告过期后常规下载返回 409，`historical=true` 是明确的历史 ZIP，包含原文件、过期说明和当前上下文。

## 安全工件与错误

普通 NumPy 使用 allow_pickle=False。上传首先在 ASGI 层有界接收，再校验格式、压缩条目路径、解压规模、NumPy 声明头、dtype、shape 和有限值。无需且不允许提供服务器文件路径。

工件使用隔离临时写入、fsync、原子提交，再发布数据库记录；失败不生成成功记录。原用户文件与同名文件不覆盖。数据库使用 SQLite WAL 和事务。

错误结构：`code/message/details/request_id`。常见代码：invalid_input、unsupported_format、upload_limit、mode_conflict、provider_unavailable、version_conflict、queue_full、not_found、assistant_unavailable。日志只保存内部任务 ID、阶段、错误码与耗时。

## 源数据格式

心澜简单 JSON：`{"data": [[...]], "metadata": {...}, "provenance": {...}}`。

简单 NPZ：纯数值 `data`，可选 Unicode JSON 字符串标量 `metadata`，内容可含 metadata/provenance 对象。

旧四层安全归档 v2 使用 `__schema__` 字符串和纯数值数组引用；JSON 使用相同 format/version/payload。工程适配不改变算法。复杂多模态归档、旧 object 文件和缺失样本语义需通过研究入口显式核对，不开放对象上传。
