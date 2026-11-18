# 心澜迁移能力审计

审计日期：2026-11-14。工程根目录：`D:/Users/15611/Desktop/AIC/BCI-main/BCI-main/BCI-main`。

本次仅新增本文档。逐文件读取范围内源文件的全部文本，使用 AST 清点定义、调用和返回路径，逐段核对关键公开接口；未导入或执行算法，未训练模型、连接设备或访问 Ollama，未加载 pickle、权重或人的信号数据。数据文件仅记录路径、扩展名、字节数与修改时间。源码存在不符合 UTF-8 的 GBK 占位文件，清点时明确标注，未转换原文件。本文是静态能力审计，不是运行验证或科学效度验证。

## 结论与证据等级

**现有项目提供通用 BCI 算法实现，但没有可证明已部署、已训练且具有心理筛查标签契约的推理提供方。** 应保留 SVM、EEGNet、多模态融合以及全部预处理、特征、统计模块；迁移层不得用随机输出、初始化模型、频带功率或概率最大值填充心理状态、PACER 可靠性或模型频带贡献。

| 核对项 | 可证明事实 | 证据与限制 |
|---|---|---|
| SVM | `SVMDecoder` 有 fit/predict/predict_proba/evaluate/grid_search/save/load；初始化未拟合 | `core/decoding/classifiers/svm_decoder.py:63`、89、114、185、201；classes_ 来自训练数据，不是固定心理标签 |
| EEGNet | 有可配置卷积架构及训练/推理/特征提取/持久化 | `core/decoding/deep_learning/eegnet.py:168`、249、356、395、403；初始化 model=None、is_fitted=False |
| 多模态分类 | early、attention、late 三种实现；需先 fit | `core/decoding/classifiers/deep_learning/multimodal_nn.py:139`、155；无公开 save/load 接口 |
| 已训练权重 | 排除虚拟环境/运行环境/依赖目录后，按常见权重扩展名扫描，未发现 .pt/.pth/.h5/.hdf5/.keras/.onnx/.joblib/.safetensors/.ckpt/.bin 模型文件 | .venv 中同名扩展 .pth 为解释器路径配置，不能当权重；.pkl 仅可见光极/处理数据命名文件，未加载，不能证明内容或假定为权重；不排除仓库外或非标准命名工件 |
| 固定标签空间 | 无经核验的心理情绪类别顺序、任务映射、训练来源、通道/特征版本注册信息 | classes_ 动态产生；n_classes=2 是模型参数，不能赋予抑郁/焦虑含义 |
| PACER | `core`、`modules`、`utils`、`config` 源码中无 PACER、频带原型共识、agreement/consensus 实现 | 技术方案有文字描述，不能证明此工程已实现；本文核验不覆盖仓库外算法 |
| 五频带 | 有 Welch 频带功率提取 | `eeg_features.py:51`、64；delta 0.5–4、theta 4–8、alpha 8–13、beta 13–30、gamma 30–45 Hz；这是描述性特征，不是模型证据或归因 |
| 信号质量 | ECG/EMG/fNIRS 专用质量计算、多模态启发式质量报告存在 | 质量量纲、计算依据、输出路径不同；均非 PACER 样本可靠性 |
| 统计信度 | ICC、Cronbach α、重测相关及元分析存在 | `reliability_meta.py:48`、105；需要会话/特征配对，非单样本预测置信度 |
| LLM 助手 | OpenAI 兼容客户端指向本地 Ollama qwen2.5:7b | `core/ai_core/llm_client.py:1`；未核验本地服务和模型是否安装，助手不能替代分类提供方 |
| 采集与部署 | 触发与 TCP 数据服务有实现；acquisition/modules/utils 和旧 deployment 多为占位 | 静态存在接口不等于设备连通、完整协议验证或可直接部署 |

“可证明”指直接由当前源码/文件元信息支持；技术方案里的性能、原创性、临床用途描述仅记为方案陈述。没有开展新的统计分析、文献真实性核验或临床验证。

## 现有可调用接口矩阵

表中形状 C×T 表示通道×采样点，N×F 表示样本×特征，N×C×T 表示试次×通道×采样点。所有数据输入须显式确认采样率、单位、轴、通道顺序、事件时间基准和去标识化样本标识；“源码有实现”不承诺当前环境依赖或全部参数组合可运行。

| 模块/接口与位置 | 输入 | 输出及副作用 | 迁移适配要求 |
|---|---|---|---|
| `GeneralPreprocessor.process`，preprocessing.py:137 | 四层字典；signal[M] 下 ndarray C×T、sampling_rate、channel_names；可选通道名 | 原地更新 signal[M].data/sampling_rate；processed.preprocessing[M].original_data/steps；返回同一字典 | 使用输入快照/派生工件；不可修改原工件；选择通道再重采样存在回填维度风险 |
| 通用 detrend/remove_baseline/bandpass_filter/notch_filter/harmonic_notch_filter/wavelet_denoising/adaptive_wavelet_denoising/remove_outliers/resample/normalize/median/Savitzky–Golay/Wiener/EEMD，preprocessing.py:419 起 | ndarray C×T、fs 和各方法参数 | ndarray；remove_outliers 另返回检测信息；缺选配依赖有降级路径 | 公开参数与步骤记录保留原含义，过滤频率须与 Nyquist 及窗口长度一致 |
| `EEGPreprocessor.process`，eeg_preprocessing.py:181 | EEG 四层字典；EEGPreprocessingConfig（参考、ICA、滤波、坏道、分段等） | 原地更新信号；processed.eeg_preprocessing 下 original_data/original_srate/history/config/bad_channels/ica_info/epochs | 与通用 preprocessing 路径不同；MNE 内部单位 V；适配层须拒绝未确认元信息 |
| `ECGPreprocessor.process_ECG`，ecg_preprocessing.py:106 | ECG C×T；通道参数为索引列表 | 原地信号；processed.ECG_preprocessing[M] 的 original_data、steps、results.signal_quality、summary | 显式调用 process_ECG，而非误用继承的 process；质量报告声明 ECG 算法来源 |
| `ECGPreprocessor.assess_ecg_quality`，ecg_preprocessing.py:388 | ECG C×T、fs、通道索引 | quality_score/quality_flag/per_channel_quality/bad_segments/recommendations | 最差导联分数用于 overall；不要跨模态混合计分 |
| `EMGPreprocessor.process`，emg_preprocessing.py:199 | EMG C×T；通道名列表；EMGPreprocessingConfig | 原地信号；processed.emg_preprocessing 的 history/config/signal_quality/activation_segments | 配置与 fs 兼容；整流/包络/标准化后信号不能继续标为原幅度单位 |
| `fNIRSPreprocessor.process_fNIRS`，fnirs_preprocessing.py:121 | fnirs，C×W×T 强度或 2D 数据，波长、距离、光学模型参数 | 保留原模态并新增 signal.HbO/HbR；processed.fNIRS_processing[M] 的 hb_data/channel_quality/motion_info/steps | fNIRS 大小写、原始光强/浓度类型、距离单位及 Hb 分支必须显式映射；源码会标 uM 后继续归一化，须保留此限制 |
| `MultiModalPreprocessor.process`，multimodal_preprocessing.py:180 | meta 必需 subject_id/task/modality/sampling_rate；每模态 data/fs/channel_names | ProcessingResult(success,processed_data,processing_stats,error_message,warnings,processing_time)；可能重采样/自动修复/原地修改 | success=False 为失败；时间同步 NONE/RESAMPLE/INTERPOLATE 实现，EVENT_ALIGNMENT 仅返回原字典 |
| `CommonFeatureExtractor` 四类 compute 与 extract_all_features，common_features.py:46/118/183/237/429 | 单通道 1D、fs | 时域、PSD、波形/小波、非线性特征字典；extract_all_features 可对 NaN/Inf 做替代 | 清洗或失败路径必须留痕，不能隐藏为科学有效结果 |
| `EEGFeatureExtractor.extract_band_powers`，eeg_features.py:64 | C×T 或 1D、fs、通道名、bands、relative、ratio_pairs | 平坦键 `通道_band_abs_power/rel_power` 及可选比值 | absolute 为 PSD 频率格点求和，不乘 Δf；需按实际代码说明，不能称验证过的物理积分功率 |
| EEG ERP/connectivity/graph/topographic/extract_all_eeg_features，eeg_features.py:129/229/407/487/557 | C×T；ERP 需事件采样点；网络需矩阵；地形需位置/名称 | ERP/连接矩阵及统计/图网络/空间特征字典 | 返回项混有标量、向量、矩阵；不应直接无规则 flatten 为训练特征 |
| `ECGFeatureExtractor.extract_ecg_features`，ecg_features.py:98 | 四层 ECG；默认通道 0、fs | common/morphological/hrv_time/hrv_frequency/hrv_nonlinear 字典；对象持有 r_peaks、毫秒 RR | add_features_to_data_dict 写 processed.ecg_features；多通道需上层明确逐通道调用；备用 HRV 算法不能伪装等价 |
| `EMGFeatureExtractor.extract_emg_features`，emg_features.py:101 | 四层 EMG；默认通道 0、fs；window_size 可选 | common/time_domain/frequency_domain/nonlinear；window_size 只截首窗口 | 窗口滑动接口为 extract_features_windowed:507；add_features_to_data_dict 写 processed.emg_features |
| `FNIRSFeatureExtractor`，fnirs_features.py:41/87/192 | HbO/HbR 两路、HRF 时窗、C×T 通道阵列 | 血氧统计/HRF/通道相关特征 | 不能把波长 0/1 默认为 HbO/HbR；类型确认在调用前完成 |
| `MultimodalFeaturePipeline.run_pipeline`，multimodal_pipeline.py:87 | 四层字典；selected_features 如 EEG:[time_domain,freq_domain,wavelet,nonlinear,band_power,erp,connectivity,spatial] | 从 signal[M].data 读取；结果更新 processed.feature[M]；捕获模态异常并继续 | 默认空选择并未使 EEG/fNIRS 提取所有；失败需基于请求类别与返回完整性识别；单数 feature 格式不同于统计 features |
| `SVMDecoder.fit/predict/predict_proba/evaluate/grid_search`，svm_decoder.py:89 起 | N×F、N 标签；预测需拟合；grid search 需合法分层折数 | 分类标签、N×K 概率、accuracy/kappa/f1/auc/itr 等；内部 StandardScaler | classes_ 是输出概率列顺序；fit 会剔除 NaN/Inf 行；不赋予心理标签；load 使用 joblib 不接受外来任意文件 |
| `EEGNetDecoder.fit/predict/predict_proba/extract_features`，eegnet.py:249 起 | N×C×T；2D 仅可按已知 C×T reshape；y 必须与 CrossEntropy 编码兼容 | 标签 argmax 索引、softmax 概率、隐特征；训练 history；save/load checkpoint | 需已训练权重、显式 0..K−1 标签映射及通道/窗口版本；未自动反映射 classes_；load 使用 weights_only=False，本审计未加载 |
| `MultimodalFusionDecoder`，multimodal_nn.py:155 起 | {模态:N×F}、N 标签，各模态样本一致；先 fit | 分类标签/概率/评估；attention 训练后 modality_weights_ 是训练集均值 | 注意力按模态，不按 EEG 五频带；predict 不输出逐样本权重；late 子 SVM 实际均接受拼接矩阵 |
| `ModelEvaluator.cross_validate` / `evaluate_and_store`，model_evaluation.py:59/265 | 解码器、X/y；stratified_kfold/kfold/loocv/holdout；is_multimodal | fold_metrics/mean_metrics/std_metrics、混淆矩阵、真实/预测；holdout 另含 trained_decoder；存 statistics.decoding.cross_validation | 按行划分，无 subject/group split；不满足方案跨被试 TVT；holdout Python 对象不可直接 JSON |
| `calculate_significance` / `multiple_comparison_correction`，significance_test.py:7/94 | {组名:1D 数值}、方法、paired；结果列表 | 两两比较 stat/p_value/method；校正后 corrected_p_value/significant_after_correction | ANOVA/Kruskal 仍逐组对比较，不能称全组 omnibus；不自动验证配对身份/正态/齐性；默认校正 α=0.05 |
| `statistical_test` / `calculate_effect_size` / `power_analysis`，advanced_stats.py:92/27/214 | 一/两组数值，检验/效应量/α 等 | 检验、效应量/SE/CI/解释，功效或样本量估计 | 功效和样本量是方法决策，不能自动替用户定设计；错误可返回 NaN+error 而非抛出 |
| `hypothesis_testing`，stat_inference.py:399 | processed.features[key].data/labels；两组标签；ttest/wilcoxon/permutation、校正 | 更新 processed.statistics.inference，stat/p/校正/效应量/样本量 | 必须先有矩阵与标签；不动态提取；wilcoxon 名称实际调用 Mann–Whitney U；cohens_d 返回绝对值 |
| `cluster_permutation`，stat_inference.py:539；底层 cluster_permutation_test:209 | 已有 epoch 数据/标签，N×C×T、fs/邻接、置换参数 | cluster mask/masses/p/significant clusters 等 | 标签、独立/配对设计、邻接与测试家族必须确认；不得把 cluster p 当逐点 p |
| `functional_connectivity`，connectivity_stats.py:359 | 已有 processed.epochs[M] 或 processed.epoch；PLI/PLV/wPLI/coh/MI，或 cross 两模态 | save_to_dict=True 写 statistics.connectivity；否则 (conn_mean,conn_epochs) | EEG 专用 epochs 的位置不同，需显式适配；跨模态时间/样本一致性不得猜测 |
| graph_theory_metrics/NBS/network_permutation_test，connectivity_stats.py:614/768/969 | 连接矩阵或已有分段与条件标签 | 图指标、组件显著性/置换分布或结果字典 | 图阈值/加权含义/随机种子等应记录；并非情绪疾病网络证据 |
| `reliability_analysis`，reliability_meta.py:48 | 顶层 processed_feature 矩阵及 event.session_id；icc/cronbach_alpha/test_retest | reliability_value/ci/p/feature_wise/interpretation；可 NaN/error | 需要严格受试者—会话配对；当前 ICC 用顺序造 subject IDs；与模型可靠性独立 |
| `meta_analysis`，reliability_meta.py:105 | effect_sizes、standard_errors、study_labels、fixed/random | 合并效应/CI/异质性/偏倚；默认生成/保存森林漏斗图 | 默认磁盘副作用应由工件服务约束；研究独立性与效应口径须确认 |
| 旧统计 GUI 与绘图类，statistical_analysis_dialog.py:771 起、statistical_plot.py | xlsx 特征/分组/通道；数值字典及显著性字典 | PyQt/Matplotlib 窗口、xlsx/json 导出、散点/分布/箱线/小提琴图 | 保留函数源码，不能把 QWidget 作为 FastAPI 返回；迁移使用原计算结果绘图，明确 n/单位/检验与校正 |

## 科学契约缺口与允许的边界处理

1. **不可推断标签。** 触发器默认标签是 NinaPro 手部动作，包含握拳、休息等；`meta.task=resting_state` 与 `n_classes=2` 也不能证明是心理健康任务。SVM 概率列对应训练 classes_；深度学习 argmax 返回数字索引而不是语义标签。必须有模型版本、权重来源、任务、类别顺序、窗口、通道、预处理版本才能启用筛查推理。
2. **分开报告三类量。** 多模态质量报告从全零、NaN/Inf、幅度范围和首通道 PSD 比值乘启发式系数；EMG quality_score 约 0–100；fNIRS 基于 SNR/CV 筛通道；ECG 使用导联质量及坏段。这些是信号处理结果。统计信度是会话/题项重复测量量。PACER 可靠性要求同一样本、同一类别顺序上的五频带后验、一致性、间隔、熵和定义明确的组合。当前缺该提供方，结果应为空并说明 unavailable，不得代算模型可靠性。
3. **五频带功率不等于模型贡献。** 现有 extract_band_powers 对 Welch PSD 求和，绝对值不乘频率间隔，邻带边界使用双闭区间、相对值分母是全 PSD。低 fs 下超 Nyquist 的频带可无输出。不能通过跨通道平均功率、归一化百分比或注意力模态均值推出 PACER 归因。前端可以显示“信号频带功率特征”，须标明算法与单位状态。
4. **避免悄然改动科学口径。** EEG 输入校验默认/重造 fs/通道，MNE raw 会猜单位；raw 在通用预处理前建立，最终从 raw 回写，通用步骤日志可能不代表最终输出实际经历该步骤。分段 reject 使用 `rejection_threshold * 1e-6`，默认本身已为 150e-6，需要方法确认，不能在迁移时静默修公式。EMG 原信号与标准化信号相减计算质量、fNIRS uM 标注后归一化也存在量纲限制。保持核心代码，API 严格输入及声明限制；需要改变算法时另行确认。
5. **统一结构只能做显式转换。** 特征调度写 `processed.feature[M]` 的平坦特征字典，推断模块要求 `processed.features[key]={data,labels}`，信度要求顶层 `processed_feature`；EEG 分段写 `processed.eeg_preprocessing.epochs`，连接模块读取 `processed.epochs[M]`/`processed.epoch`。转换必须带 feature_names、样本顺序、labels、subject/session IDs、选择通道及派生 lineage。矩阵、向量和图节点统计不可无规则拼成标量训练列。
6. **当前评估不是跨被试 TVT。** ModelEvaluator 无 GroupKFold/被试划分参数，随机分层行划分可能泄露同被试/重叠窗信息。训练源码不实现方案中无标签目标流自适应与检查点选择。不能将现有 CV 的均值/标准差或方案表格升级为工程已复现的跨被试性能。
7. **统计限制必须随结果。** significance_test 的“ANOVA”实际做每两组比较，缺假设诊断；advanced_stats 会独立剔除 NaN 并可截断配对数据，存在破坏配对身份风险；ICC 文档说 ICC(2,1) 而实现挑 ICC2k，且忽略实际 session 行排序来造配对 ID；Cronbach CI 用相关 Fisher 近似、限制 α 值，重测取每会话最短长度按行配对。应按明确、受限输入调用并标注方法，不据此宣称可靠或有效；本审计不修统计公式。
8. **未实现的选项不包装成已执行。** MultiModal EVENT_ALIGNMENT 返回原字典；特征调度空选择不完成所有类别；异常打印后可返回部分结果。新 API 要报告执行过的类别、跳过、错误和完整性；不可把任务 success 或非空 JSON 等同于科学有效性。

## 采集、触发与基础模块

- `core/acquisition/eeg_acquisition.py` 仅返回字符串“EEG数据”，不是数据采集驱动。`modules` 中运动想象仅打印字符串；LSL、数据增强、实时图形文件只有说明。`utils` 四个文件只有说明，没有数据格式、EDF、实验日志或交叉验证函数实现。`HybridFusion.fuse` 仅 np.concatenate([eeg,fmri])，没有多模态对齐或学习。
- `data_server.py` 有多模态环形缓冲区、事件管理、处理调度与 TCP 线程，按 Neuracle little-endian float32、Neuroscan big-endian int32（倍率 0.14827）、DSI 帧及默认 float32 解析。各解析器当前 events 返回空列表，只有手工事件接口；这不证明完整设备触发通道已解析。
- `UnifiedDataServer` 是 Thread，connect/start_recording/run/get_realtime_data/save_data/stop 是设备/写盘接口，须保留并按已确认设备配置绑定。环形读取可能包含初始化零区，unified_data 信号主要为实时窗口，不能直接当完整记录。默认创建 64 通道、1000 Hz、uV、subject S001 的字典是模板，不是真实元信息。
- EventManager 输出 `event.events.onset/duration/trial_type/value`，TriggerManager 输出 `event_rel_time/event_sample/event_value/event_label`，特征与 EEG 分段读取 `event.event_time/event_id`。触发第一时间归零不是自动证明与信号起点同步，统一时钟/offset 需明确。
- TriggerCore 构造时打开 serial 并检查设备；实际定义没有 open_serial 和 trigger_history，真实 output_event_data 不记录 trigger_history。TriggerEmulator 构造已开模拟状态并记录历史，也没有 open_serial。trigger_integration 调用 open_serial、trigger_history 且 load_data 后按 eeg_data/emg_data 取值，与真实类/四层字典契约不一致，不能直接宣称集成成功。本审计未调用硬件或模拟器。
- data_server 末尾 `bandpass_filter` 示例直接 return data，是占位，不应标记为真实滤波。旧部署 Dockerfile 与 requirements.txt 均只包含三引号说明文本，分别不是可构建 Docker 配置或可安装依赖清单。新的 React/FastAPI 部署须独立说明实际依赖，不能用这些旧文件证明部署完备。

## 技术方案出处与可引用边界

工作区唯一 `.doc`：`AIC-2026-72141251-AI+心理健康-心澜——基于脑电信号的心理健康检测系统-技术方案.doc`，2,057,216 字节，SHA-256：`cb44727e451a97b6a80536ee7fe407996a512b3b1c95bb3f2fb6518cd5002450`。

已完整读取 `review_artifacts/2026-11-14/extract_legacy_doc.py`，其读取 OLE FAT/miniFAT、WordDocument 的 FIB 与 0Table/1Table 中 piece table，按逻辑字符顺序取主文档文本。当前 1 个 piece，主文本声明和实际提取均 23,500 字符。脚本用正则去手机号/邮箱；保留 Word 的域代码和表格竖线标记，不包含图片像素、图内数值或页面布局。

本次在内存中移除脚本的 print/write_text 表达式后执行提取逻辑，**未改原 `.doc` 或既有摘录**。复算后的脱敏摘录与 `review_artifacts/2026-11-14/proposal_excerpt.txt` 全文完全相同：43,454 UTF-8 字节，SHA-256 `1bb61c282386a639aaee2eef849347bca899e9dc488890b11cd5583c3a835443`。该脚本用 ROOT.glob('*.doc') 的首个文件；当前只有一个文件，若将来出现多个，必须显式选择并记录来源。

| 摘录出处（按 proposal_excerpt.txt 行号） | 原文陈述 | 本次核验范围 |
|---|---|---|
| 28、35、42 | 情绪类别、可靠性评分、频带贡献；辅助筛查且不替代临床诊断 | 可确认是方案定位；不证明工程具备三类输出 |
| 51–60 | PACER、共享—私有、五频带原型、共识；置信度和一致性几何平均可靠性；轻量推理 | 工程缺这些实现/权重/契约；文中训练原型与推理辅助输出之间的导出机制尚需模型工件说明 |
| 70–77 | LibEER 的五频带 DE+LDS、被试/会话归一化、跨被试 TVT、AdamW 100 轮 | 当前 EEG 特征是时频/功率等，EEGNet 用 Adam，多模态 attention 固定 150 轮；不是此训练管线 |
| 82–83 | 五任务性能与提升表 | 仅方案陈述，未读取真实人的数据、未复现性能，不能当作本次验证结果 |
| 95–103 | 频带剖面、共识增益、r=0.700、图归因及应用价值 | 图像/原始统计与计算日志不在本次证据中；不验证数值或因果解释 |
| 103–106 | 尚未临床诊断级验证、低密度/在线/跨会话等限制 | 可引用为方案自述限制，不能据此免除实际应用验证 |

摘录参考文献条目仅作为原文题录来源，未访问数据库或验证 DOI/题录准确性；不得把它们写成“已核验文献”。本次未新造参考文献。

## LLM 助手工程修复建议（不改科学内容）

`core/ai_core/llm_client.py` 的 SimpleAIChat 初始化硬编码 URL、api_key、model_name，温度硬编码 0.7；`config/default.yaml` ai_assistant 的 backend/base_url/api_key/model_name/temperature/max_history=50 未被此类读取。OpenAI 客户端未显式 timeout/max_retries，故不能说超时/重试已按产品要求控制。

建议只做工程参数注入：用配置与环境覆盖地址/模型/温度/历史上限，设置明确连接与请求 timeout 及有限重试；对本地 Ollama 的健康/模型缺失给结构化错误，不把异常字符串当助手成功回复；配置端限制 loopback 并避免日志带密钥。

chat 在发送前永久 append user，成功后 append assistant，失败不回滚且历史无限增长。应按会话独立保存历史，保留 system，按完整 user/assistant 轮次或 token 上限裁剪；请求使用快照，成功后原子提交，失败保持一致或保存明确失败状态，防止重复失败堆积。需要并发串行化/锁或每会话实例，避免交叉回复；clear 与正在执行请求需版本/取消检查，防止清空后旧回复写回。以上均为工程建议，本审计不修改已有提示词、心理科研论断或算法。

## 验证记录与适用范围

已执行：范围文件与常见权重/数值工件路径清点；逐文件全部字节读取/编码识别及 Python AST 解析；公开接口与关键调用/写入/返回路径核对；PACER/原型/共识/可靠性关键词源码检索；方案摘录只读复算及哈希比较。未执行：pip 安装、算法 import、任何训练/推理、实际信号统计、pickle 解包、真实临床/个人数据分析、设备/LLM 连通、图像内数据提取或文献 DOI 验证。

与 `review_artifacts/2026-11-14/source_manifest.json` 对照，清单覆盖的 35 个 core/decoding、core/processing 源文件 SHA-256 全部一致；本文未改动任何核心文件。迁移中的其他目录存在主工程修改，本文不据此声称整个工程未改变。

补充读取迁移过程中新增的 `config/xinlan.json`：127.0.0.1:8765、本地 .xinlan-data、上传/阵列/队列上限、助手默认禁用、timeout=20 秒、history=10、retry_limit=0。它是新迁移配置，不证明旧 SimpleAIChat 已使用这些参数；本审计未审查新 backend 实现。

范围内 `Statistical_Analysis/__init__.py` 是 0 字节空文件；多个其他 __init__ 仅包注释。编译缓存 `__pycache__/*.pyc` 只清点存在性，不作为源码或模型工件。现有 migration-plan/progress 是迁移计划/状态文字，不是算法性能证据。

后续接入真实提供方所需最小契约：训练来源及模型版本、可信权重清单/校验、预处理与特征版本、输入形状/单位/采样率/通道顺序/窗口、任务标签顺序、预测概率归一化、五频带后验和贡献定义、可靠性算法及阈值适用范围、训练/验证/测试被试划分、无标签适配及推理边界、错误与低可靠复核策略。以上缺项不能由工程层臆补。

## 全部源文件读取清单与接口定义索引

以下清单由本次只读遍历生成：路径、字节数、行数、解码方式、SHA-256 前 12 位及实现状态。源文件哈希用于复现审计版本；数据工件不读取内容、不计算哈希。本文不把清点当成运行通过证明。


| 路径 | 字节 | 行 | 编码 | SHA-256 前12位 | 状态 |
|---|---:|---:|---|---|---|
| `config/default.yaml` | 905 | 55 | UTF-8 | `2e4020bb0342` | 默认参数配置 |
| `config/xinlan.json` | 394 | 15 | UTF-8 | `ea517497c6c4` | 迁移新增配置；已读取 |
| `core/acquisition/__init__.py` | 23 | 1 | UTF-8 | `53311f3c6833` | 仅包注释 |
| `core/acquisition/eeg_acquisition.py` | 94 | 4 | GBK | `bce210a6a562` | 最简占位接口 |
| `core/ai_core/llm_client.py` | 1538 | 37 | UTF-8 | `545e565a5c19` | 实现源码；静态审阅 |
| `core/decoding/__init__.py` | 20 | 1 | UTF-8 | `718eaf8932c0` | 仅包注释 |
| `core/decoding/classifiers/__init__.py` | 23 | 1 | UTF-8 | `09c86f83858a` | 仅包注释 |
| `core/decoding/classifiers/deep_learning/__init__.py` | 37 | 1 | UTF-8 | `363ee2e48f7d` | 仅包注释 |
| `core/decoding/classifiers/deep_learning/multimodal_nn.py` | 11940 | 330 | UTF-8 BOM | `1ebaffcc24eb` | 实现源码；静态审阅 |
| `core/decoding/classifiers/svm_decoder.py` | 8201 | 237 | UTF-8 BOM | `81a5f9b47251` | 实现源码；静态审阅 |
| `core/decoding/deep_learning/__init__.py` | 25 | 1 | UTF-8 | `5cf8de15858b` | 仅包注释 |
| `core/decoding/deep_learning/eegnet.py` | 15219 | 448 | UTF-8 BOM | `1256328bd35e` | 实现源码；静态审阅 |
| `core/decoding/model_evaluation.py` | 10470 | 314 | UTF-8 BOM | `a46cc77839d8` | 实现源码；静态审阅 |
| `core/io/trigger_system/__init__.py` | 26 | 1 | UTF-8 | `bb999c4d3eba` | 仅包注释 |
| `core/io/trigger_system/data_server.py` | 34954 | 988 | UTF-8 | `1481fc7bf0d5` | 实现源码；静态审阅 |
| `core/io/trigger_system/trigger_core.py` | 16226 | 375 | UTF-8 | `e86b03306608` | 实现源码；静态审阅 |
| `core/io/trigger_system/trigger_emulator.py` | 12128 | 241 | UTF-8 | `ddd750ae1f30` | 实现源码；静态审阅 |
| `core/io/trigger_system/trigger_integration.py` | 11536 | 236 | UTF-8 | `fbc254ff9bd5` | 实现源码；静态审阅 |
| `core/io/trigger_system/trigger_manager.py` | 9711 | 180 | UTF-8 | `be6955dd5567` | 实现源码；静态审阅 |
| `core/processing/__init__.py` | 22 | 1 | UTF-8 | `0d0a102703c6` | 仅包注释 |
| `core/processing/feature_extraction/__init__.py` | 30 | 1 | UTF-8 | `7c536e087f37` | 仅包注释 |
| `core/processing/feature_extraction/common_features.py` | 19224 | 502 | UTF-8 | `7167cf65d4cd` | 实现源码；静态审阅 |
| `core/processing/feature_extraction/ecg_features.py` | 29901 | 841 | UTF-8 | `9d51a1b40d3a` | 实现源码；静态审阅 |
| `core/processing/feature_extraction/eeg_features.py` | 32636 | 761 | UTF-8 | `ab8f1949c8da` | 实现源码；静态审阅 |
| `core/processing/feature_extraction/emg_features.py` | 22762 | 697 | UTF-8 | `dc7f7f76102f` | 实现源码；静态审阅 |
| `core/processing/feature_extraction/fnirs_features.py` | 12253 | 295 | UTF-8 | `b4d0495c17ac` | 实现源码；静态审阅 |
| `core/processing/feature_extraction/multimodal_pipeline.py` | 13793 | 266 | UTF-8 | `4d9acabc0213` | 实现源码；静态审阅 |
| `core/processing/fusion/__init__.py` | 18 | 1 | UTF-8 | `7f31e2bb6cc8` | 仅包注释 |
| `core/processing/fusion/hybrid_fusion.py` | 135 | 5 | GBK | `7dcd9dce0f3b` | 最简占位接口 |
| `core/processing/preprocessing/__init__.py` | 25 | 1 | UTF-8 | `b2d5bd2f9e11` | 仅包注释 |
| `core/processing/preprocessing/ecg_preprocessing.py` | 40024 | 1021 | UTF-8 | `ad853594b583` | 实现源码；静态审阅 |
| `core/processing/preprocessing/eeg_preprocessing.py` | 52117 | 1375 | UTF-8 | `3e9d98d72595` | 实现源码；静态审阅 |
| `core/processing/preprocessing/emg_preprocessing.py` | 57425 | 1539 | UTF-8 | `96dd441c8cd3` | 实现源码；静态审阅 |
| `core/processing/preprocessing/fnirs_preprocessing.py` | 55498 | 1279 | UTF-8 | `f9e889bfd744` | 实现源码；静态审阅 |
| `core/processing/preprocessing/fnirs_preprocessing_test.py` | 30346 | 816 | UTF-8 | `cecd2ac8c312` | 实现源码；静态审阅 |
| `core/processing/preprocessing/multimodal_preprocessing.py` | 48707 | 1257 | UTF-8 | `732a6a1dd1de` | 实现源码；静态审阅 |
| `core/processing/preprocessing/preprocessing.py` | 29444 | 821 | UTF-8 | `14c2486b8a1c` | 实现源码；静态审阅 |
| `core/processing/Statistical_Analysis/__init__.py` | 0 | 0 | UTF-8 | `e3b0c44298fc` | 空文件 |
| `core/processing/Statistical_Analysis/advanced_stats.py` | 23441 | 588 | UTF-8 | `3cfe4d1d757e` | 实现源码；静态审阅 |
| `core/processing/Statistical_Analysis/connectivity_stats.py` | 34857 | 1073 | UTF-8 | `106ed620f277` | 实现源码；静态审阅 |
| `core/processing/Statistical_Analysis/decoding_stats.py` | 17770 | 578 | UTF-8 | `f247da4f4e67` | 实现源码；静态审阅 |
| `core/processing/Statistical_Analysis/reliability_meta.py` | 22430 | 568 | UTF-8 | `977aad7edad5` | 实现源码；静态审阅 |
| `core/processing/Statistical_Analysis/significance_test.py` | 5779 | 146 | UTF-8 | `a6e945bf5aaa` | 实现源码；静态审阅 |
| `core/processing/Statistical_Analysis/stat_inference.py` | 22004 | 662 | UTF-8 | `0fb036e6c865` | 实现源码；静态审阅 |
| `core/processing/Statistical_Analysis/statistical_analysis_dialog.py` | 62766 | 1422 | UTF-8 | `d75d695f0600` | 实现源码；静态审阅 |
| `core/processing/Statistical_Analysis/statistical_plot.py` | 13713 | 355 | UTF-8 | `557ef475bff3` | 实现源码；静态审阅 |
| `deployment/docker/Dockerfile` | 18 | 1 | GBK | `ef8b0652ba47` | 说明或占位 |
| `deployment/requirements/requirements.txt` | 16 | 1 | GBK | `9398afa94e3e` | 说明或占位 |
| `docs/migration-plan.md` | 5920 | 77 | UTF-8 | `aece04ba732f` | 计划或进展文档 |
| `docs/migration-progress.md` | 617 | 7 | UTF-8 | `848b2fcd10a5` | 计划或进展文档 |
| `docs/protocols/eeg_setup.md` | 19 | 1 | GBK | `e6b9d54ff8a7` | 说明或占位 |
| `docs/tutorials/quickstart.md` | 20 | 1 | GBK | `3cdfee74d72e` | 说明或占位 |
| `modules/experiments/motor_imagery.py` | 92 | 4 | GBK | `505dcf9c8c99` | 最简占位接口 |
| `modules/interfaces/labstreaminglayer/lsl_interface.py` | 15 | 1 | GBK | `b32e72e54c22` | 说明或占位 |
| `modules/utilities/data_augmentation.py` | 20 | 1 | GBK | `58d69d97baf1` | 说明或占位 |
| `modules/visualization/realtime_plots.py` | 18 | 1 | GBK | `48ace4d869ab` | 说明或占位 |
| `utils/data_utils/bci_data_format.py` | 20 | 1 | GBK | `1861fde69d9a` | 说明或占位 |
| `utils/file_handlers/edf_handler.py` | 19 | 1 | GBK | `c91e7e1592f4` | 说明或占位 |
| `utils/logging/experiment_logger.py` | 16 | 1 | GBK | `95877ddb59fb` | 说明或占位 |
| `utils/validation/cross_validation.py` | 16 | 1 | GBK | `ec6a6e974eb0` | 说明或占位 |

清单共 60 个源文件、配置及既有文档（含最后补充的迁移配置）；所有 Python 文本均完成 AST 结构读取，未导入执行。GBK 占位源码未声明编码时，不能据此认为 Python 3 可直接导入。排除 .venv/.runtime、依赖、版本控制与缓存目录后，常见权重扩展名扫描无模型文件；扫描到 .venv 的 distutils-precedence.pth 路径配置，未加载，未认定为权重。

### 公开接口完整索引

- `core/acquisition/eeg_acquisition.py:3` — `EEGAcquisition.read_data(self)`
- `core/ai_core/llm_client.py:22` — `SimpleAIChat.chat(self, text)`
- `core/ai_core/llm_client.py:36` — `SimpleAIChat.clear(self)`
- `core/decoding/classifiers/deep_learning/multimodal_nn.py:96` — `_AttentionFusionModule.forward(self, modality_features: Dict[str, torch.Tensor])`
- `core/decoding/classifiers/deep_learning/multimodal_nn.py:155` — `MultimodalFusionDecoder.fit(self, X_dict: Dict[str, np.ndarray], y: np.ndarray) -> 'MultimodalFusionDecoder'`
- `core/decoding/classifiers/deep_learning/multimodal_nn.py:255` — `MultimodalFusionDecoder.predict(self, X_dict: Dict[str, np.ndarray]) -> np.ndarray`
- `core/decoding/classifiers/deep_learning/multimodal_nn.py:271` — `MultimodalFusionDecoder.predict_proba(self, X_dict: Dict[str, np.ndarray]) -> np.ndarray`
- `core/decoding/classifiers/deep_learning/multimodal_nn.py:287` — `MultimodalFusionDecoder.evaluate(self, X_dict: Dict[str, np.ndarray], y: np.ndarray, trial_time: float=4.0) -> dict`
- `core/decoding/classifiers/deep_learning/multimodal_nn.py:308` — `MultimodalFusionDecoder.get_modality_importance(self) -> Optional[Dict[str, float]]`
- `core/decoding/classifiers/svm_decoder.py:89` — `SVMDecoder.fit(self, X: np.ndarray, y: np.ndarray) -> 'SVMDecoder'`
- `core/decoding/classifiers/svm_decoder.py:114` — `SVMDecoder.predict(self, X: np.ndarray) -> np.ndarray`
- `core/decoding/classifiers/svm_decoder.py:119` — `SVMDecoder.predict_proba(self, X: np.ndarray) -> np.ndarray`
- `core/decoding/classifiers/svm_decoder.py:126` — `SVMDecoder.evaluate(self, X: np.ndarray, y: np.ndarray, trial_time: float=4.0) -> dict`
- `core/decoding/classifiers/svm_decoder.py:148` — `SVMDecoder.grid_search(self, X: np.ndarray, y: np.ndarray, param_grid: Optional[dict]=None, cv: int=5, scoring: str='accuracy') -> dict`
- `core/decoding/classifiers/svm_decoder.py:185` — `SVMDecoder.save(self, filepath: str)`
- `core/decoding/classifiers/svm_decoder.py:201` — `SVMDecoder.load(self, filepath: str) -> 'SVMDecoder'`
- `core/decoding/classifiers/svm_decoder.py:221` — `SVMDecoder.get_support_vectors_info(self) -> dict`
- `core/decoding/deep_learning/eegnet.py:120` — `_EEGNetModule.forward(self, x)`
- `core/decoding/deep_learning/eegnet.py:133` — `_EEGNetModule.get_features(self, x)`
- `core/decoding/deep_learning/eegnet.py:249` — `EEGNetDecoder.fit(self, X: np.ndarray, y: np.ndarray, X_val: np.ndarray=None, y_val: np.ndarray=None, verbose: bool=True) -> 'EEGNetDecoder'`
- `core/decoding/deep_learning/eegnet.py:356` — `EEGNetDecoder.predict(self, X: np.ndarray) -> np.ndarray`
- `core/decoding/deep_learning/eegnet.py:365` — `EEGNetDecoder.predict_proba(self, X: np.ndarray) -> np.ndarray`
- `core/decoding/deep_learning/eegnet.py:374` — `EEGNetDecoder.evaluate(self, X: np.ndarray, y: np.ndarray, trial_time: float=4.0) -> dict`
- `core/decoding/deep_learning/eegnet.py:395` — `EEGNetDecoder.extract_features(self, X: np.ndarray) -> np.ndarray`
- `core/decoding/deep_learning/eegnet.py:403` — `EEGNetDecoder.save(self, filepath: str)`
- `core/decoding/deep_learning/eegnet.py:419` — `EEGNetDecoder.load(self, filepath: str) -> 'EEGNetDecoder'`
- `core/decoding/model_evaluation.py:59` — `ModelEvaluator.cross_validate(self, decoder, X, y, is_multimodal: bool=False) -> dict`
- `core/decoding/model_evaluation.py:265` — `evaluate_and_store(data_dict: dict, decoder, X, y, cv_method: str='stratified_kfold', n_splits: int=5, trial_time: float=4.0, is_multimodal: bool=False) -> dict`
- `core/io/trigger_system/data_server.py:48` — `EnhancedRingBuffer.append_buffer(self, modality: str, data: np.ndarray)`
- `core/io/trigger_system/data_server.py:66` — `EnhancedRingBuffer.get_data(self, modality: str, n_samples: Optional[int]=None) -> np.ndarray`
- `core/io/trigger_system/data_server.py:81` — `EnhancedRingBuffer.get_all_data(self, modality: str) -> np.ndarray`
- `core/io/trigger_system/data_server.py:89` — `EnhancedRingBuffer.reset_modality(self, modality: str)`
- `core/io/trigger_system/data_server.py:96` — `EnhancedRingBuffer.reset_all(self)`
- `core/io/trigger_system/data_server.py:122` — `EventManager.add_event(self, event_type: str, sample_index: int, value: Any=None, description: str='', metadata: Dict=None) -> int`
- `core/io/trigger_system/data_server.py:163` — `EventManager.get_events_in_range(self, start_sample: int, end_sample: int, event_type: Optional[str]=None) -> List[Dict]`
- `core/io/trigger_system/data_server.py:179` — `EventManager.get_latest_events(self, n: int=10) -> List[Dict]`
- `core/io/trigger_system/data_server.py:184` — `EventManager.clear_events(self)`
- `core/io/trigger_system/data_server.py:190` — `EventManager.to_dataframe_format(self)`
- `core/io/trigger_system/data_server.py:213` — `ProcessingPipeline.add_processor(self, name: str, processor_func, config: Dict=None)`
- `core/io/trigger_system/data_server.py:222` — `ProcessingPipeline.process(self, data_dict: Dict, modality: str='EEG')`
- `core/io/trigger_system/data_server.py:248` — `ProcessingPipeline.enable_processor(self, name: str, enabled: bool=True)`
- `core/io/trigger_system/data_server.py:255` — `ProcessingPipeline.clear_processors(self)`
- `core/io/trigger_system/data_server.py:342` — `UnifiedDataServer.connect(self) -> bool`
- `core/io/trigger_system/data_server.py:370` — `UnifiedDataServer.disconnect(self)`
- `core/io/trigger_system/data_server.py:384` — `UnifiedDataServer.start_recording(self)`
- `core/io/trigger_system/data_server.py:403` — `UnifiedDataServer.stop_recording(self)`
- `core/io/trigger_system/data_server.py:416` — `UnifiedDataServer.run(self)`
- `core/io/trigger_system/data_server.py:703` — `UnifiedDataServer.add_event_manually(self, event_type: str, value: Any=None, description: str='')`
- `core/io/trigger_system/data_server.py:718` — `UnifiedDataServer.get_realtime_data(self, modality: str='EEG', n_seconds: float=1.0) -> np.ndarray`
- `core/io/trigger_system/data_server.py:728` — `UnifiedDataServer.get_data_summary(self) -> Dict`
- `core/io/trigger_system/data_server.py:740` — `UnifiedDataServer.save_data(self, filename: str, format: str='hdf5')`
- `core/io/trigger_system/data_server.py:831` — `UnifiedDataServer.stop(self)`
- `core/io/trigger_system/data_server.py:840` — `create_default_data_dict() -> Dict[str, Any]`
- `core/io/trigger_system/data_server.py:888` — `add_signal_modality(data_dict: Dict, modality: str, n_channels: int, sampling_rate: float, channel_names: List[str]=None, unit: str='uV', reference: str='average') -> Dict`
- `core/io/trigger_system/trigger_core.py:135` — `TriggerCore.refresh_serial_list(self) -> List`
- `core/io/trigger_system/trigger_core.py:139` — `TriggerCore.check_online(self) -> bool`
- `core/io/trigger_system/trigger_core.py:157` — `TriggerCore.get_device_name(self) -> str`
- `core/io/trigger_system/trigger_core.py:169` — `TriggerCore.get_device_info(self) -> Dict`
- `core/io/trigger_system/trigger_core.py:205` — `TriggerCore.get_sensor_info(self) -> List[Dict]`
- `core/io/trigger_system/trigger_core.py:232` — `TriggerCore.get_sensor_para(self, sensor_id: int) -> PackageSensorPara`
- `core/io/trigger_system/trigger_core.py:264` — `TriggerCore.set_sensor_para(self, sensor_id: int, sensor_para: PackageSensorPara)`
- `core/io/trigger_system/trigger_core.py:287` — `TriggerCore.output_event_data(self, event_data: int, trigger_to_be_out: int=1)`
- `core/io/trigger_system/trigger_core.py:302` — `TriggerCore.send(self, data)`
- `core/io/trigger_system/trigger_core.py:310` — `TriggerCore.read(self, function_id: int) -> bytes`
- `core/io/trigger_system/trigger_core.py:350` — `TriggerCore.close_serial(self)`
- `core/io/trigger_system/trigger_emulator.py:110` — `TriggerEmulator.refresh_serial_list(self) -> List[Dict]`
- `core/io/trigger_system/trigger_emulator.py:114` — `TriggerEmulator.check_online(self) -> bool`
- `core/io/trigger_system/trigger_emulator.py:119` — `TriggerEmulator.get_device_name(self) -> str`
- `core/io/trigger_system/trigger_emulator.py:123` — `TriggerEmulator.get_device_info(self) -> Dict`
- `core/io/trigger_system/trigger_emulator.py:137` — `TriggerEmulator.get_sensor_info(self) -> List[Dict]`
- `core/io/trigger_system/trigger_emulator.py:143` — `TriggerEmulator.get_sensor_para(self, sensor_id: int) -> MockSensorPara`
- `core/io/trigger_system/trigger_emulator.py:153` — `TriggerEmulator.set_sensor_para(self, sensor_id: int, sensor_para: MockSensorPara)`
- `core/io/trigger_system/trigger_emulator.py:160` — `TriggerEmulator.output_event_data(self, event_data: int, trigger_to_be_out: int=1)`
- `core/io/trigger_system/trigger_emulator.py:177` — `TriggerEmulator.send(self, data: Any)`
- `core/io/trigger_system/trigger_emulator.py:184` — `TriggerEmulator.read(self, function_id: int) -> bytes`
- `core/io/trigger_system/trigger_emulator.py:203` — `TriggerEmulator.close_serial(self)`
- `core/io/trigger_system/trigger_integration.py:39` — `integrate_trigger_with_bci_data(data_path: str, serial_name: str='COM3', use_emulator: bool=False, sampling_rate: float=2000.0, custom_trigger_map: Optional[Dict[int, str]]=None, trigger_event_list: List[int]=None, event_interval: float=2.0) -> Dict`
- `core/io/trigger_system/trigger_integration.py:131` — `batch_integrate_trigger(data_dir: str, serial_name: str='COM3', use_emulator: bool=False, sampling_rate: float=2000.0, custom_trigger_map: Optional[Dict[int, str]]=None, trigger_event_list: List[int]=None, event_interval: float=2.0) -> List[Dict]`
- `core/io/trigger_system/trigger_manager.py:57` — `TriggerManager.update_trigger_map(self, new_trigger_map: Dict[int, str])`
- `core/io/trigger_system/trigger_manager.py:78` — `TriggerManager.parse_trigger_history(self, trigger_history: List[Dict], reset: bool=True)`
- `core/io/trigger_system/trigger_manager.py:123` — `TriggerManager.get_standard_event(self) -> Dict`
- `core/io/trigger_system/trigger_manager.py:127` — `TriggerManager.save_event_to_txt(self, save_path: str, encoding: str='utf-8')`
- `core/processing/feature_extraction/common_features.py:46` — `CommonFeatureExtractor.compute_time_domain_features(self, data: np.ndarray) -> dict`
- `core/processing/feature_extraction/common_features.py:118` — `CommonFeatureExtractor.compute_freq_domain_features(self, data: np.ndarray, nperseg=None) -> dict`
- `core/processing/feature_extraction/common_features.py:183` — `CommonFeatureExtractor.compute_wavelet_features(self, data: np.ndarray, wavelet='db4', level=4) -> dict`
- `core/processing/feature_extraction/common_features.py:237` — `CommonFeatureExtractor.compute_nonlinear_features(self, data: np.ndarray) -> dict`
- `core/processing/feature_extraction/common_features.py:429` — `CommonFeatureExtractor.extract_all_features(self, data: np.ndarray) -> dict`
- `core/processing/feature_extraction/ecg_features.py:29` — `check_dependencies()`
- `core/processing/feature_extraction/ecg_features.py:98` — `ECGFeatureExtractor.extract_ecg_features(self, data_dict: Dict[str, Any], ecg_channel: Optional[int]=0) -> Dict[str, Any]`
- `core/processing/feature_extraction/ecg_features.py:167` — `ECGFeatureExtractor.detect_r_peaks(self, ecg: np.ndarray) -> np.ndarray`
- `core/processing/feature_extraction/ecg_features.py:206` — `ECGFeatureExtractor.extract_morphological_features(self, ecg: np.ndarray) -> Dict[str, float]`
- `core/processing/feature_extraction/ecg_features.py:309` — `ECGFeatureExtractor.extract_hrv_time_features(self) -> Dict[str, float]`
- `core/processing/feature_extraction/ecg_features.py:356` — `ECGFeatureExtractor.extract_hrv_frequency_features(self, resample_rate: float=4.0) -> Dict[str, float]`
- `core/processing/feature_extraction/ecg_features.py:567` — `ECGFeatureExtractor.extract_hrv_nonlinear_features(self) -> Dict[str, float]`
- `core/processing/feature_extraction/ecg_features.py:655` — `summarize_features(features: Dict[str, Any]) -> None`
- `core/processing/feature_extraction/ecg_features.py:719` — `add_features_to_data_dict(data_dict: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Any]`
- `core/processing/feature_extraction/eeg_features.py:64` — `EEGFeatureExtractor.extract_band_powers(self, data: np.ndarray, bands: List[str]=None, relative: bool=True, ratio_pairs: List[Tuple[str, str]]=None) -> Dict`
- `core/processing/feature_extraction/eeg_features.py:129` — `EEGFeatureExtractor.extract_erp_features(self, data: np.ndarray, event_times: List[int], window_pre: float=0.1, window_post: float=0.8, baseline_correction: bool=True, baseline_window: Tuple[float, float]=(-0.1, 0.0)) -> Dict`
- `core/processing/feature_extraction/eeg_features.py:229` — `EEGFeatureExtractor.compute_connectivity_features(self, data: np.ndarray, method: str='coherence', freq_band: Tuple[float, float]=None, symmetric: bool=True, verbose: bool=False) -> Dict`
- `core/processing/feature_extraction/eeg_features.py:407` — `EEGFeatureExtractor.compute_graph_features(self, connectivity_matrix: np.ndarray, threshold_type: str='density', threshold_value: float=0.2, weighted: bool=True) -> Dict`
- `core/processing/feature_extraction/eeg_features.py:487` — `EEGFeatureExtractor.compute_topographic_features(self, data: np.ndarray, freq_band: Tuple[float, float]=(8, 13), method: str='power') -> Dict`
- `core/processing/feature_extraction/eeg_features.py:557` — `EEGFeatureExtractor.extract_all_eeg_features(self, data: np.ndarray, extract_band_powers: bool=True, extract_erp: bool=False, event_times: List[int]=None, extract_connectivity: bool=True, extract_graph: bool=True, extract_spatial: bool=True, verbose: bool=False) -> Dict`
- `core/processing/feature_extraction/emg_features.py:29` — `check_dependencies()`
- `core/processing/feature_extraction/emg_features.py:101` — `EMGFeatureExtractor.extract_emg_features(self, data_dict: Dict[str, Any], emg_channel: Optional[int]=0, window_size: Optional[float]=None) -> Dict[str, Any]`
- `core/processing/feature_extraction/emg_features.py:168` — `EMGFeatureExtractor.extract_emg_time_features(self, emg: np.ndarray) -> Dict[str, float]`
- `core/processing/feature_extraction/emg_features.py:267` — `EMGFeatureExtractor.extract_emg_frequency_features(self, emg: np.ndarray) -> Dict[str, float]`
- `core/processing/feature_extraction/emg_features.py:369` — `EMGFeatureExtractor.extract_emg_nonlinear_features(self, emg: np.ndarray) -> Dict[str, float]`
- `core/processing/feature_extraction/emg_features.py:507` — `EMGFeatureExtractor.extract_features_windowed(self, emg: np.ndarray, window_size: float=0.25, overlap: float=0.5) -> List[Dict[str, Any]]`
- `core/processing/feature_extraction/emg_features.py:552` — `summarize_features(features: Dict[str, Any]) -> None`
- `core/processing/feature_extraction/emg_features.py:603` — `add_features_to_data_dict(data_dict: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Any]`
- `core/processing/feature_extraction/fnirs_features.py:41` — `FNIRSFeatureExtractor.extract_hbo_hbr_features(self, hbo: np.ndarray, hbr: np.ndarray) -> dict`
- `core/processing/feature_extraction/fnirs_features.py:87` — `FNIRSFeatureExtractor.extract_hrf_features(self, signal: np.ndarray, fs: float=None, baseline_window: tuple=None, task_window: tuple=None, t: np.ndarray=None) -> dict`
- `core/processing/feature_extraction/fnirs_features.py:192` — `FNIRSFeatureExtractor.compute_channel_correlation(self, data_2d: np.ndarray, ch_names: list=None, left_indices: list=None, right_indices: list=None, anterior_indices: list=None, posterior_indices: list=None) -> dict`
- `core/processing/feature_extraction/multimodal_pipeline.py:38` — `BCIDataProcessor.get_modalities(self) -> list`
- `core/processing/feature_extraction/multimodal_pipeline.py:41` — `BCIDataProcessor.get_modality_data(self, modality: str) -> dict`
- `core/processing/feature_extraction/multimodal_pipeline.py:68` — `BCIDataProcessor.save_features(self, modality: str, features: dict)`
- `core/processing/feature_extraction/multimodal_pipeline.py:87` — `MultimodalFeaturePipeline.run_pipeline(self) -> dict`
- `core/processing/fusion/hybrid_fusion.py:4` — `HybridFusion.fuse(self, eeg, fmri)`
- `core/processing/preprocessing/ecg_preprocessing.py:106` — `ECGPreprocessor.process_ECG(self, data_dict: Dict[str, Any], modality: str='ECG', channels: Optional[List[int]]=None) -> Dict[str, Any]`
- `core/processing/preprocessing/ecg_preprocessing.py:280` — `ECGPreprocessor.preprocess_ecg_signal(self, ecg_data: np.ndarray, sampling_rate: float, channels: List[int]=None) -> np.ndarray`
- `core/processing/preprocessing/ecg_preprocessing.py:356` — `ECGPreprocessor.enhance_qrs_wave(self, ecg_signal: np.ndarray, sampling_rate: float) -> np.ndarray`
- `core/processing/preprocessing/ecg_preprocessing.py:388` — `ECGPreprocessor.assess_ecg_quality(self, ecg_data: np.ndarray, sampling_rate: float, channels: List[int]=None) -> Dict[str, Any]`
- `core/processing/preprocessing/ecg_preprocessing.py:753` — `ECGPreprocessor.check_multi_lead_consistency(self, ecg_data: np.ndarray, sampling_rate: float, channels: List[int]) -> Dict[str, Any]`
- `core/processing/preprocessing/ecg_preprocessing.py:854` — `ECGPreprocessor.visualize_preprocessing_results(self, data_dict: Dict[str, Any], modality: str='ECG', channel_idx: int=0, time_range: Optional[Tuple[float, float]]=None, save_path: Optional[str]=None)`
- `core/processing/preprocessing/eeg_preprocessing.py:181` — `EEGPreprocessor.process(self, data_dict: Dict[str, Any], modality: str='EEG', channels: Optional[List[str]]=None) -> Dict[str, Any]`
- `core/processing/preprocessing/eeg_preprocessing.py:1223` — `EEGConfigFactory.create_motor_imagery_config() -> EEGPreprocessingConfig`
- `core/processing/preprocessing/eeg_preprocessing.py:1261` — `EEGConfigFactory.create_p300_config() -> EEGPreprocessingConfig`
- `core/processing/preprocessing/eeg_preprocessing.py:1300` — `EEGConfigFactory.create_ssvep_config() -> EEGPreprocessingConfig`
- `core/processing/preprocessing/eeg_preprocessing.py:1340` — `EEGConfigFactory.create_resting_state_config() -> EEGPreprocessingConfig`
- `core/processing/preprocessing/emg_preprocessing.py:199` — `EMGPreprocessor.process(self, data_dict: Dict[str, Any], modality: str='EMG', channels: Optional[List[str]]=None) -> Dict[str, Any]`
- `core/processing/preprocessing/emg_preprocessing.py:1184` — `EMGConfigFactory.create_surface_emg_config() -> EMGPreprocessingConfig`
- `core/processing/preprocessing/emg_preprocessing.py:1238` — `EMGConfigFactory.create_high_density_emg_config() -> EMGPreprocessingConfig`
- `core/processing/preprocessing/emg_preprocessing.py:1294` — `EMGConfigFactory.create_force_estimation_config() -> EMGPreprocessingConfig`
- `core/processing/preprocessing/emg_preprocessing.py:1345` — `EMGConfigFactory.create_fatigue_analysis_config() -> EMGPreprocessingConfig`
- `core/processing/preprocessing/emg_preprocessing.py:1396` — `EMGConfigFactory.create_realtime_config() -> EMGPreprocessingConfig`
- `core/processing/preprocessing/emg_preprocessing.py:1467` — `EMGBatchProcessor.process_batch(self, data_dicts: List[Dict[str, Any]], modalities: Union[str, List[str]]='EMG') -> List[Dict[str, Any]]`
- `core/processing/preprocessing/emg_preprocessing.py:1507` — `EMGBatchProcessor.save_results(self, save_path: str, format: str='numpy')`
- `core/processing/preprocessing/fnirs_preprocessing.py:121` — `fNIRSPreprocessor.process_fNIRS(self, data_dict: Dict[str, Any], modality: str='fnirs', return_hb_types: List[str]=['HbO', 'HbR']) -> Dict[str, Any]`
- `core/processing/preprocessing/fnirs_preprocessing.py:434` — `fNIRSPreprocessor.convert_to_optical_density(self, intensity_data: np.ndarray, baseline_period: Optional[Union[int, Tuple[int, int]]]=None) -> np.ndarray`
- `core/processing/preprocessing/fnirs_preprocessing.py:477` — `fNIRSPreprocessor.motion_artifact_correction(self, optical_density: np.ndarray, sampling_rate: float, method: MotionCorrectionMethod=MotionCorrectionMethod.SPLINE, threshold: float=3.0, **kwargs) -> Tuple[np.ndarray, Dict]`
- `core/processing/preprocessing/fnirs_preprocessing.py:721` — `fNIRSPreprocessor.convert_to_concentration(self, optical_density: np.ndarray, wavelengths: List[float], distances: Optional[np.ndarray]=None, dpf: Optional[Dict[float, float]]=None, extinction_coeffs: Optional[Dict[float, Dict[str, float]]]=None, optical_model: OpticalModel=OpticalModel.MODIFIED_BEER_LAMBERT) -> Dict[str, np.ndarray]`
- `core/processing/preprocessing/fnirs_preprocessing.py:881` — `fNIRSPreprocessor.channel_quality_assessment(self, intensity_data: np.ndarray, sampling_rate: float, distances: Optional[np.ndarray]=None) -> Tuple[np.ndarray, Dict]`
- `core/processing/preprocessing/fnirs_preprocessing.py:974` — `fNIRSPreprocessor.short_channel_regression(self, hb_data: Dict[str, np.ndarray], short_channel_indices: np.ndarray, long_channel_indices: np.ndarray) -> Dict[str, np.ndarray]`
- `core/processing/preprocessing/fnirs_preprocessing.py:1041` — `fNIRSPreprocessor.remove_physiological_noise(self, hb_data: Dict[str, np.ndarray], sampling_rate: float, cardiac_range: Tuple[float, float]=(0.8, 2.0), respiration_range: Tuple[float, float]=(0.1, 0.5)) -> Dict[str, np.ndarray]`
- `core/processing/preprocessing/fnirs_preprocessing.py:1106` — `fNIRSPreprocessor.baseline_correction(self, hb_data: Dict[str, np.ndarray], sampling_rate: float, event_times: List[float], baseline_window: Tuple[float, float]=(-5.0, 0.0), use_percentage: bool=False) -> Dict[str, np.ndarray]`
- `core/processing/preprocessing/fnirs_preprocessing.py:1174` — `fNIRSPreprocessor.visualize_preprocessing(self, data_dict: Dict[str, Any], modality: str='fnirs', channel_idx: int=0, wavelength_idx: int=0)`
- `core/processing/preprocessing/fnirs_preprocessing_test.py:33` — `load_bids_fNIRS_data(subject_dir, task_name='task-1')`
- `core/processing/preprocessing/fnirs_preprocessing_test.py:161` — `load_snirf_h5py(snirf_file)`
- `core/processing/preprocessing/fnirs_preprocessing_test.py:242` — `create_simulated_fNIRS_data()`
- `core/processing/preprocessing/fnirs_preprocessing_test.py:314` — `test_fNIRS_preprocessing(subject_dir, task_name='task-1')`
- `core/processing/preprocessing/fnirs_preprocessing_test.py:407` — `visualize_results(processed_data)`
- `core/processing/preprocessing/fnirs_preprocessing_test.py:433` — `create_custom_visualization(data_dict)`
- `core/processing/preprocessing/fnirs_preprocessing_test.py:489` — `create_simple_visualization(data_dict)`
- `core/processing/preprocessing/fnirs_preprocessing_test.py:514` — `save_processed_data(processed_data, output_dir='output')`
- `core/processing/preprocessing/fnirs_preprocessing_test.py:566` — `main()`
- `core/processing/preprocessing/fnirs_preprocessing_test.py:722` — `quick_test()`
- `core/processing/preprocessing/multimodal_preprocessing.py:180` — `MultiModalPreprocessor.process(self, data_dict: Dict[str, Any]) -> ProcessingResult`
- `core/processing/preprocessing/multimodal_preprocessing.py:914` — `MultiModalPreprocessor.get_processing_summary(self) -> Dict[str, Any]`
- `core/processing/preprocessing/multimodal_preprocessing.py:928` — `MultiModalPreprocessor.save_config(self, filepath: str)`
- `core/processing/preprocessing/multimodal_preprocessing.py:946` — `MultiModalPreprocessor.load_config(self, filepath: str)`
- `core/processing/preprocessing/multimodal_preprocessing.py:1010` — `MultiModalConfigFactory.create_motor_imagery_config() -> MultiModalConfig`
- `core/processing/preprocessing/multimodal_preprocessing.py:1045` — `MultiModalConfigFactory.create_affective_computing_config() -> MultiModalConfig`
- `core/processing/preprocessing/multimodal_preprocessing.py:1068` — `MultiModalConfigFactory.create_cognitive_load_config() -> MultiModalConfig`
- `core/processing/preprocessing/multimodal_preprocessing.py:1088` — `MultiModalConfigFactory.create_resting_state_config() -> MultiModalConfig`
- `core/processing/preprocessing/multimodal_preprocessing.py:1106` — `MultiModalConfigFactory.create_realtime_config() -> MultiModalConfig`
- `core/processing/preprocessing/multimodal_preprocessing.py:1129` — `example_usage()`
- `core/processing/preprocessing/preprocessing.py:137` — `GeneralPreprocessor.process(self, data_dict: Dict[str, Any], modality: str='EEG', channels: Optional[List[str]]=None) -> Dict[str, Any]`
- `core/processing/preprocessing/preprocessing.py:419` — `GeneralPreprocessor.detrend(data: np.ndarray, method: DetrendMethod=DetrendMethod.LINEAR, degree: int=2) -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:450` — `GeneralPreprocessor.remove_baseline(data: np.ndarray) -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:457` — `GeneralPreprocessor.bandpass_filter(data: np.ndarray, fs: float, lowcut: float, highcut: float, filter_type: FilterType=FilterType.BUTTERWORTH, order: int=4, ripple: float=1.0, attenuation: float=40.0) -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:503` — `GeneralPreprocessor.notch_filter(data: np.ndarray, fs: float, freq: float, Q: float=30.0) -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:517` — `GeneralPreprocessor.harmonic_notch_filter(data: np.ndarray, fs: float, base_freq: float, Q: float=30.0, n_harmonics: int=5) -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:531` — `GeneralPreprocessor.wavelet_denoising(data: np.ndarray, wavelet: WaveletType=WaveletType.DB4, level: int=4, threshold_method: str='soft', threshold_scale: float=1.0) -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:573` — `GeneralPreprocessor.adaptive_wavelet_denoising(data: np.ndarray, wavelet: WaveletType=WaveletType.DB4, level: int=4) -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:602` — `GeneralPreprocessor.remove_outliers(data: np.ndarray, threshold: float=3.0, method: str='mad') -> Tuple[np.ndarray, Dict]`
- `core/processing/preprocessing/preprocessing.py:651` — `GeneralPreprocessor.resample(data: np.ndarray, original_fs: float, target_fs: float, method: str='polyphase') -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:689` — `GeneralPreprocessor.normalize(data: np.ndarray, method: str='zscore', feature_range: Tuple[float, float]=(0, 1)) -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:740` — `GeneralPreprocessor.apply_median_filter(data: np.ndarray, window_size: int=3) -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:757` — `GeneralPreprocessor.apply_savitzky_golay(data: np.ndarray, window_size: int=5, polyorder: int=2) -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:777` — `GeneralPreprocessor.apply_wiener_filter(data: np.ndarray, noise_variance: Optional[float]=None) -> np.ndarray`
- `core/processing/preprocessing/preprocessing.py:795` — `GeneralPreprocessor.apply_ensemble_empirical_mode_decomposition(data: np.ndarray, n_imfs: int=5) -> np.ndarray`
- `core/processing/Statistical_Analysis/advanced_stats.py:27` — `calculate_effect_size(data1: Union[np.ndarray, List[float]], data2: Optional[Union[np.ndarray, List[float]]]=None, effect_type: str='cohens_d', test_type: str='independent', alpha: float=0.05) -> Dict`
- `core/processing/Statistical_Analysis/advanced_stats.py:92` — `statistical_test(data1: Union[np.ndarray, List[float]], data2: Optional[Union[np.ndarray, List[float]]]=None, test_type: str='t_test', paired: bool=False, alpha: float=0.05) -> Dict`
- `core/processing/Statistical_Analysis/advanced_stats.py:214` — `power_analysis(effect_size: float, alpha: float=0.05, power: float=0.8, test_type: str='t_test', groups: int=2) -> Dict`
- `core/processing/Statistical_Analysis/connectivity_stats.py:57` — `coherence(data, fs, freq_band=None, nperseg=None)`
- `core/processing/Statistical_Analysis/connectivity_stats.py:92` — `phase_locking_value(data, fs=None, freq_band=None)`
- `core/processing/Statistical_Analysis/connectivity_stats.py:135` — `phase_lag_index(data, fs=None, freq_band=None)`
- `core/processing/Statistical_Analysis/connectivity_stats.py:179` — `weighted_phase_lag_index(data, fs=None, freq_band=None)`
- `core/processing/Statistical_Analysis/connectivity_stats.py:224` — `mutual_information(data, bins=20)`
- `core/processing/Statistical_Analysis/connectivity_stats.py:266` — `cross_modal_plv(data1, data2, fs=None, freq_band=None)`
- `core/processing/Statistical_Analysis/connectivity_stats.py:313` — `cross_modal_coherence(data1, data2, fs, freq_band=None, nperseg=None)`
- `core/processing/Statistical_Analysis/connectivity_stats.py:359` — `functional_connectivity(data_dict, modality=DEFAULT_MODALITY, fusion_method=DEFAULT_FUSION, modalities=None, method='pli', freq_band=None, epoch_based=True, use_existing_epoch=True, save_to_dict=True)`
- `core/processing/Statistical_Analysis/connectivity_stats.py:614` — `graph_theory_metrics(connectivity_matrix, ch_names=None, threshold=None, weighted=True)`
- `core/processing/Statistical_Analysis/connectivity_stats.py:768` — `network_based_statistic(data_dict, condition1, condition2, modality=DEFAULT_MODALITY, method='pli', freq_band=None, n_permutations=1000, threshold_t=2.5, alpha=0.05, use_existing_epoch=True)`
- `core/processing/Statistical_Analysis/connectivity_stats.py:969` — `network_permutation_test(data_dict, condition1, condition2, modality=DEFAULT_MODALITY, metric='global_efficiency', n_permutations=5000, use_existing_epoch=True)`
- `core/processing/Statistical_Analysis/decoding_stats.py:156` — `classification_metrics(y_true, y_pred, y_score=None, average='macro')`
- `core/processing/Statistical_Analysis/decoding_stats.py:263` — `regression_metrics(y_true, y_pred, n_features=None)`
- `core/processing/Statistical_Analysis/decoding_stats.py:326` — `information_transfer_rate(accuracy, n_classes, trial_time)`
- `core/processing/Statistical_Analysis/decoding_stats.py:363` — `information_transfer_rate_nykopp(accuracy, n_classes, trial_time)`
- `core/processing/Statistical_Analysis/decoding_stats.py:415` — `evaluate_decoder(data_dict, feature_key=None, y_true=None, y_pred=None, y_score=None, task_type='classification', trial_time=4.0, n_classes=None, n_features=None)`
- `core/processing/Statistical_Analysis/decoding_stats.py:532` — `classification_report(y_true, y_pred, y_score=None, return_dict=False)`
- `core/processing/Statistical_Analysis/reliability_meta.py:48` — `reliability_analysis(data_dict: Dict, reliability_type: str='icc', session_key: str='session_id', feature_key: str='processed_feature', alpha: float=0.05) -> Dict`
- `core/processing/Statistical_Analysis/reliability_meta.py:105` — `meta_analysis(effect_sizes: Union[List[float], np.ndarray], standard_errors: Union[List[float], np.ndarray], study_labels: Optional[List[str]]=None, model_type: str='random', plot_forest: bool=True, plot_funnel: bool=True, save_plots: bool=True, plot_dir: str='./meta_plots/') -> Dict`
- `core/processing/Statistical_Analysis/significance_test.py:7` — `calculate_significance(data_dict, method='t-test', paired=False)`
- `core/processing/Statistical_Analysis/significance_test.py:94` — `multiple_comparison_correction(results, correction_method='bonferroni')`
- `core/processing/Statistical_Analysis/stat_inference.py:89` — `ttest_independent(X1, X2, equal_var=True, tail=0)`
- `core/processing/Statistical_Analysis/stat_inference.py:144` — `wilcoxon_test(X1, X2)`
- `core/processing/Statistical_Analysis/stat_inference.py:163` — `permutation_test(X1, X2, n_permutations=5000, tail=0, random_state=42)`
- `core/processing/Statistical_Analysis/stat_inference.py:209` — `cluster_permutation_test(X1, X2, srate=None, adjacency=None, n_permutations=5000, threshold_p=0.05, tail=0, min_cluster_duration=0.015, n_jobs=-1, random_state=42)`
- `core/processing/Statistical_Analysis/stat_inference.py:347` — `cohens_d(X1, X2, pooled=True)`
- `core/processing/Statistical_Analysis/stat_inference.py:361` — `eta_squared(ss_between, ss_total)`
- `core/processing/Statistical_Analysis/stat_inference.py:366` — `partial_eta_squared(ss_effect, ss_error)`
- `core/processing/Statistical_Analysis/stat_inference.py:371` — `auc_effect(y_true, y_score)`
- `core/processing/Statistical_Analysis/stat_inference.py:384` — `multiple_comparison_correction(p_values, method='fdr')`
- `core/processing/Statistical_Analysis/stat_inference.py:399` — `hypothesis_testing(data_dict, condition1, condition2, feature_key, test_type='ttest', correction='fdr', tail=0, n_permutations=5000, **kwargs)`
- `core/processing/Statistical_Analysis/stat_inference.py:539` — `cluster_permutation(data_dict, condition1, condition2, epoch_key, channels=None, n_permutations=5000, threshold_p=0.05, tail=0, min_cluster_duration=0.015, n_jobs=-1)`
- `core/processing/Statistical_Analysis/stat_inference.py:656` — `effect_size(data_dict, condition1, condition2, feature_key, **kwargs)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:780` — `ResultDialog.init_ui(self)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:830` — `ResultDialog.export_to_excel(self)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:844` — `read_xlsx(file_path)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:873` — `get_feature(feature_dict, channel_name=None, feature_name=None)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:912` — `convert_to_significance_dict(result)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:953` — `GroupDialog.get_group_data(self)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:983` — `ChannelSelectionDialog.get_selected_channels(self)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:1015` — `VisualisationSettingsDialog.get_settings(self)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:1039` — `MatplotlibWidget.plot_default(self)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:1044` — `MatplotlibWidget.plot(self, data, title='', y_label='', x_label='', legend=None, x_ticks=None, y_range=None, color='blue')`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:1059` — `MatplotlibWidget.plot_data(self)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:1231` — `StatisticalAnalysisDialog.add_group(self)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:1238` — `StatisticalAnalysisDialog.modify_group(self, item)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:1249` — `StatisticalAnalysisDialog.validate_groups(self)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:1298` — `StatisticalAnalysisDialog.run_analysis(self)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:1366` — `StatisticalAnalysisDialog.export_results(self)`
- `core/processing/Statistical_Analysis/statistical_analysis_dialog.py:1383` — `StatisticalAnalysisDialog.generate_visualization(self)`
- `core/processing/Statistical_Analysis/statistical_plot.py:29` — `ScatterPlotWindow.plot_scatter(self, data_dict)`
- `core/processing/Statistical_Analysis/statistical_plot.py:77` — `DensityHistogramWindow.plot_density_histogram(self, data_dict)`
- `core/processing/Statistical_Analysis/statistical_plot.py:126` — `SignificanceBoxPlotWindow.plot_boxplot_with_significance(self, data_dict, significance_dict)`
- `core/processing/Statistical_Analysis/statistical_plot.py:244` — `SignificanceViolinPlotWindow.plot_violin_with_significance(self, data_dict, significance_dict)`
- `modules/experiments/motor_imagery.py:3` — `MotorImagery.run(self)`

### 数据及候选权重元信息清单

仅记录元信息，不读取内容。路径名称不能证明数据是合成、脱敏、真实或已训练模型；pickle 未解包。排除新迁移前后端配置、虚拟/运行环境、IDE 目录与编译缓存。修改时间是本地文件系统时间，不是采集时间。

| 路径 | 扩展名 | 字节 | 本地修改时间 | 审阅状态 |
|---|---|---:|---|---|
| `core/io/S1_A1_E1.json` | .json | 31971401 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/io/S1_A1_E1.mat` | .mat | 2891171 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/io/sub-10_optodes.json` | .json | 2040 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/io/sub-10_optodes.tsv` | .tsv | 369 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/io/test_data_dict.json` | .json | 270031 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/processing/Statistical_Analysis/tested_eeg_features_output.json` | .json | 3253376 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/test_data/ecg_only.npy` | .npy | 1200128 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/test_data/eeg_only.npy` | .npy | 2880128 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/test_data/eeg_test.csv` | .csv | 7757259 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/test_data/emg_only.npy` | .npy | 1440128 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/test_data/multimodal_test.json` | .json | 48450423 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/test_data/multimodal_test.mat` | .mat | 6486032 | 2026-03-16T19:20:10 | 未加载内容 |
| `core/test_data/multimodal_test.npy` | .npy | 6482413 | 2026-03-16T19:20:10 | 未加载内容 |
| `extracted_features.csv` | .csv | 14926 | 2026-03-16T19:20:10 | 未加载内容 |
| `extracted_features.json` | .json | 16746 | 2026-03-16T19:20:10 | 未加载内容 |
| `features_for_visualizer.json` | .json | 1191 | 2026-03-16T19:20:10 | 未加载内容 |
| `output/processed_data/EEG_processed_20260415_154617.pkl` | .pkl | 210125754 | 2026-04-15T15:46:18 | 未加载内容 |
| `sub-10_optodes.pkl` | .pkl | 946 | 2026-03-16T19:20:10 | 未加载内容 |
| `test_data.npz` | .npz | 36309 | 2026-03-16T19:20:10 | 未加载内容 |
| `test_data_clean.npz` | .npz | 69135 | 2026-03-16T19:20:10 | 未加载内容 |
| `tests/data/ecg_only.npy` | .npy | 2880128 | 2026-03-16T19:20:10 | 未加载内容 |
| `tests/data/eeg_only.npy` | .npy | 5760128 | 2026-03-16T19:20:10 | 未加载内容 |
