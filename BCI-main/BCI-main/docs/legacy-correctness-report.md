# 旧研究入口正确性修复记录

日期：2026-11-15（独立审查整改版）。范围对应 `docs/migration-plan.md` 任务 1。保留 `core/UI/main_UI.py`；没有修改或运行训练 `core/decoding`、`core/processing` 的计算实现，没有安装 CUDA 或任何依赖，没有使用或改写真实原始数据。整改实现待原问题限定复审，本报告不是复审通过声明。

## 结论与验证范围

完成旧 IO、DataBus、面板线程边界和真实/演示边界的针对性修复。最终回归覆盖 44 项场景；五面板隐藏窗口烟测核对了共享数据、严格样本身份、特征撤销、实际特征桥接、旧结果清空和 reset 后订阅。源码审计核对 36 个冻结目录文件（35 个源码与 1 个既有工件），SHA-256 均与修改前基线一致。

这些验证证明工程契约和失效策略，不证明模型性能、统计推断有效性或真实受试者结果；没有实际调用训练。预处理线程测试使用替代处理器，确认主线程读取参数和后台使用私有数据快照。

## 独立审查 I1–I7 整改

| 项目 | 最终处理 | 验证 |
|---|---|---|
| I1 | features=None 删除可视化 feature/features/classification_features 副本；更新或失效均关闭旧子视图 | 单阶段失效回归及实际隐藏子窗口销毁 |
| I2 | 文件和 DataBus 元信息保留 dataset_id、dataset_version、有序唯一 sample_ids；缺失身份、跨数据集、跨版本或逆序均拒绝；CSV 明确 label 列 | 正确 CSV 标签、错误版本/顺序、无 ID NPY 标签提交拦截 |
| I3 | fNIRS C×W×T 在归档/预处理入口保留；C 与通道名称、W 与 wavelengths 须匹配，axis_order 若提供须一致 | JSON/NPZ 三维往返与布局校验 |
| I4 | 14 类 Enum type/member/value 静态白名单；解码为数据描述，不导入文件指定类；支持实际 numpy 时间记录 | 默认 ECG、四模态配置、时间记录、非法 Enum 请求 |
| I5 | 所有文件 Modality/scope 一致；所选特征 Unit/Scope 必须明确且与 Definition 跨文件一致 | 单文件各自单模态、跨文件 EEG/ECG 在统计核心前拒绝 |
| I6 | 完整移除 current_backend 顶层残留与假设置日志 | plot_core 实际导入及禁止 use() 回归 |
| I7 | 支持 feature[modality] 与旧 features；只绘制范围明确的标量，不猜向量轴 | 实际流水线字典的 BarView 读取及隐藏桥接 |

复核补充：审计只读源码；宽表非法数字/NaN 立即报错，提交不再删除非 finite 观察；旧显式演示采用固定正弦或局部 default_rng(42)，不修改全局 NumPy RNG，导出水印保留。

MNE 1.13.2 当前安装文档/源码确认 `BaseRaw.get_data(units=None)` 返回类型对应的 SI 单位。EDF/EEGLAB 适配对明确电压数据通道标 V，数值不缩放；固定 RawArray 的精确二进制样本在仅替换读取器后逐点相等。刺激码等非电压/未知通道拒绝统一标 V；旧 FIFF unit 占位值不足以独立证明电压。

## 根因与最终行为

| 问题 | 根因 | 修复与可复现验证 |
|---|---|---|
| Excel 导入删除同名 CSV | 把同目录同名 CSV 当作临时文件并覆盖、删除 | 直接从 DataFrame 内存解析；临时合成 Excel 与哨兵 CSV 的字节/hash 不变 |
| NPZ/JSON 丢模态、元信息、事件或数组类型 | 保存和读取无统一 schema；JSON 列表没有归一化 | 安全 schema v2；两模态、不同采样率、通道、单位、事件、processed 数组、dtype、tuple、复数和保留键往返 |
| NPY 串用上次 NPZ 元信息 | `self.npz_meta` 持久保存 | 单次读取局部上下文；显式采样率优先，不继承前一文件 |
| 普通导入可执行 pickle | `allow_pickle=True` 和对象模型加载 | 普通 NPY/NPZ 始终 `allow_pickle=False`；显式传 True 也不放开；旧 pickle 和对象模型加载明确禁用 |
| 原始数据替换后仍使用旧下游 | 缺少版本和依赖失效策略 | raw/processed/features/labels 更新使下游失效；按请求 revision 拒绝陈旧提交；reset 保留监听 |
| 换特征文件仍用旧标签/结果 | 只在新文件带标签时赋值 | 切换立即撤销旧标签、模型、评估与结果控件；特征/标签按文件声明的 dataset_id、dataset_version、有序 sample_ids 严格绑定；缺失/逆序/跨版本拒绝 |
| 长表误把 EEG 当通道 | 默认第一列为通道 | 显式识别 Modality/Category/Channel/Feature/Value；通道取 Channel，特征键为 Category/Feature，重复观察保留 |
| 后台读取/操作 Tk、迟到回调覆写新状态 | 共用可变面板状态及跨线程 after | 主线程配置与数据快照；后台仅入队；主线程提交时检查 revision/generation，销毁后丢弃回调 |
| 异常被延迟 lambda 掩盖、控件未恢复 | 退出 except 后引用 e，或助手异常逃逸 | 捕获独立错误字符串入队；异常与过期路径恢复可操作状态 |
| 真实无数据却出现随机图 | 波形/统计/柱状/时频失败的模拟回退；fNIRS 未解析真实数据 | 波形失败直接失败；统计缺少结果显示空状态；柱状和时频转换失败不制造随机数据；旧 fNIRS 伪读取直接拒绝 |
| 预处理保存丢事件和元信息 | 面板另写简化 NPZ | 所有预处理保存统一调用 DataSaver；不支持普通对象格式 |
| 保存失败清空已有输出 | 写目标文件后才进行类型编码 | DataSaver 在隔离临时文件中写完后原子替换；失败保留既有输出 |
| 多模块抢 matplotlib 后端 | Tk/Qt 模块导入期间全局 use | 移除旧 UI/visualizer 的全局切换；使用显式 canvas；保留主线程 Qt 事件桥 |

## 修改文件

既有文件（17 个）：

- `core/data_bus.py`、`core/io/data_io.py`。
- `core/UI/main_UI.py`。
- `core/UI/panel/ai_chat_panel.py`、`analysis_panel_tk.py`、`decoding_panel.py`、`extraction_panel.py`、`preprocessing_panel.py`、`visualization_panel.py`。
- `core/visualizer/bar_view.py`、`feature_view.py`、`plot_core.py`、`plot_dialog.py`、`signal_view.py`、`stats_view.py`、`time_frequency_view.py`、`topography_view.py`。

新增帮助与验证文件：

- `core/io/serialization.py`：安全四层序列化。
- `core/io/enum_schema.py`、`core/io/signal_layout.py`：有限 Enum 白名单与模态布局。
- `core/UI/dispatch.py`：Tk 主线程队列与计算前元信息校验。
- `core/UI/feature_summary.py`：真实通道名与全局观察的查看长表导出。
- `core/UI/sample_identity.py`：严格分类身份文件协议。
- `tests/test_legacy_regressions.py`、`tests/test_legacy_threads.py`、`tests/test_legacy_review_regressions.py`：合计 44 项回归。
- `tests/legacy_hidden_smoke.py`：显式隐藏窗口烟测。
- `tests/legacy_audit.py`：基线哈希、源差异与环境记录。
- 本报告。

临时源码替换脚本已移除，不能误当常驻转换工具运行。新增文件均为 UTF-8 无 BOM。

## 安全归档接口

`encode_npz(data)` 返回可直接传给 `np.savez_compressed` 的数组映射。`decode_npz(archive)` 接收由调用方以 `allow_pickle=False` 打开的 NpzFile 或数组映射；调用方负责关闭文件。

`__schema__` 为 Unicode JSON 字符串标量，内容为 `{format: "bci-data-dict", version: 2, payload: ...}`。ndarray 以 `{"__ndarray__": "array_0", "dtype": "<f4", "shape": [...]}` 引用纯数值/非 object 数组，读取核对 dtype 和 shape。

`encode_json(data)` 返回 JSON 可编码 dict；`decode_json(parsed_dict_or_string)` 返回归一化四层 dict。JSON ndarray 内嵌 values；tuple、复数、非有限浮点使用显式标记，用户字典中的保留键通过 `__mapping__` 转义。入口仅归一化信号数组，不猜测转置和单位。自定义 Python 对象不属于可移植契约，会明确报错。

无元信息的数值输入保留 `sampling_rate=None`、`duration=None` 草稿状态；预处理、特征提取与波形/时频入口要求采样率、单位与轴明确；普通信号为二维，fNIRS 预处理按原接口接受 C×W×T 三维。统计核心没有增加新公式或统计方法。

新增 Enum 标记为 `{"__enum__":{"type":"core.processing.preprocessing.preprocessing.FilterType","name":"BUTTERWORTH","value":"butterworth"}}`；白名单核对后返回纯数据 `{"enum_type":...,"enum_name":...,"enum_value":...}`，保留类型/成员/值语义，不恢复任意 Python 对象或自动执行配置。NumPy 时间用 `__datetime64__` 标记保留 dtype；标准时间使用有限 `__datetime__` 标记。

分类 NPZ/JSON 使用 features/X、labels/y、dataset_id、dataset_version、sample_ids；version 为兼容别名，有两个版本字段时须一致。CSV 使用 dataset_id、dataset_version、sample_id、label 与数值特征列。ID 列不计入特征或标签；顺序不一致会拒绝，用户须另行显式导出对齐文件，原文件不会被改写。

## 实际运行记录

已确认两个 Python 路径均存在；实际验证使用 `E:/conda/conda_env/bci-app/python.exe`，版本 3.11.18。NumPy 2.4.6、pandas 3.1.1、SciPy 1.17.1。没有声称另一个 Anaconda 环境也完成了依赖验证。

当前环境 antropy 0.2.3、numba 0.68.1、MNE 1.13.2；本任务未安装/修改依赖。此前 antropy 可用状态没有记录，不能推断它是本轮新安装。一次超时堆栈显示 antropy.fractal 导入时正在 numba 编译；后续仅 IO/UI 边界回归与隐藏初始化子进程设置 NUMBA_DISABLE_JIT=1。未改变用户持久环境；该条件不用于真实算法计算兼容性声明。

从工程根目录运行：

```powershell
$legacyPreviousJit = $env:NUMBA_DISABLE_JIT
try {
    $env:NUMBA_DISABLE_JIT='1' # 仅边界验证，未调用研究计算
    & 'E:/conda/conda_env/bci-app/python.exe' -B -X utf8 -m unittest discover -s tests -p 'test_legacy*.py' -v
    & 'E:/conda/conda_env/bci-app/python.exe' -B -X utf8 -m tests.legacy_hidden_smoke
} finally {
    $env:NUMBA_DISABLE_JIT=$legacyPreviousJit
}
& 'E:/conda/conda_env/bci-app/python.exe' -B -X utf8 -m tests.legacy_audit
```

回归初始 12 项在原缺陷上全部失败；扩展后确认了真实图随机回退、助手异常、特殊元信息、非数值列和保存失败的失败证据，再实施修复。最终结果与退出码以实际日志为准：

- `review_artifacts/migration-2026-11-14/legacy-tests.log`。
- `review_artifacts/migration-2026-11-14/legacy-hidden-smoke.log`。
- `review_artifacts/migration-2026-11-14/legacy-validation.json`。
- `review_artifacts/migration-2026-11-14/legacy-correctness.diff`。
- `review_artifacts/migration-2026-11-14/legacy-review-red.log`：整改前 14 个新增用例，16 个失败（含子用例）。
- `review_artifacts/migration-2026-11-14/legacy-review-green.log`：当前 44 项完整回归。
- `review_artifacts/migration-2026-11-14/legacy-mne-red.log`：在隔离进程回放备份 IO 方法的 SI 单位 RED 证据。

另以 Python `compile()` 核对 IO、DataBus、UI、visualizer 的 27 个 Python 文件；未产生新 pycache。上述日志及差异位于 AIC 根目录下的 review_artifacts。

## 明确限制

- 旧图片/绝对定位界面仍保留；没有完成可见图窗、高 DPI、键盘可达性和响应式布局验收。隐藏烟测没有打开 Qt 子图；事件桥的持续可见交互需另行检查。
- 旧 CSV/NPY 没有新增元信息编辑器；缺少采样率或单位时仅能查看草稿信息。可用新工作台补齐或通过明确参数/安全归档进入研究流程。
- fNIRS 旧 SNIRF/NIRS 随机伪读取已禁用，没有在本任务中重新实现真实解析；可信对象模型/旧 object NPZ 的离线迁移工具也未实现。
- fNIRS 三维归档/预处理已可达；旧二维波形与特征视图仍须明确选择波长或血红蛋白信号，不自动合并 C/W/T。
- 分类特征与标签必须声明相同 dataset_id、dataset_version 和有序 sample_ids。无 ID 标签、逆序、不同数据集或版本均不能提交训练；本轮未实现无 ID 人工绑定 UI，旧 NPY 标签须另行导出协议文件。
- 统计仍采用操作者显式选择的组文件。长表多模态混用、不适用的通道/特征组合和非有限值会拒绝；全局与通道观察可同表保留，未知轴向量留在 NPZ，不能按长度猜成通道独立观察；没有新增原先不存在的效应量/置信区间，也未评价统计核心的检验前提。
- 未声明 Modality/Unit/Scope 的旧宽表/摘要不能直接进入组统计；需要研究者补齐声明。元信息一致不等于已经证明实验独立性或统计检验前提成立。
- MNE 电压入口只接受明确 EEG/EOG/ECG/EMG/SEEG/ECoG/DBS 电压通道；混合刺激码及未知单位须显式分离/映射，不能整体标 V。
- DataBus 与旧面板任务仍为进程内状态；旧计算无法即时中止，迟到结果被丢弃。任务持久化、取消/重试和报告版本属于新服务任务，不由旧入口声称已实现。
- 模板电极布局持续标为示意；显式三维通道坐标才标为输入坐标。演示波形及派生图保留模拟来源，不把模板坐标称为个体实际电极位置。
