# -*- coding: utf-8 -*-
"""
智融脑机 - 解码分类面板
===================================================
提供 SVM / EEGNet / 多模态融合 三种解码器的训练、评估、模型管理。
集成交叉验证、ITR 计算、混淆矩阵可视化。
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import copy
from core.UI.dispatch import MainThreadDispatcher
from core.UI.sample_identity import (load_feature_samples, load_label_samples,
    sample_contract, identity_key, validate_label_binding)
import traceback
import numpy as np
from pathlib import Path

# 动态添加项目根目录到 sys.path
start_path = Path(__file__).resolve().parent
for parent in [start_path] + list(start_path.parents):
    if parent.name == 'core':
        project_root = parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        break
else:
    raise RuntimeError("未找到名为 'core' 的目录")

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# 导入解码器模块
try:
    from core.decoding.classifiers.svm_decoder import SVMDecoder
    SVM_AVAILABLE = True
except ImportError:
    SVM_AVAILABLE = False

try:
    from core.decoding.deep_learning.eegnet import EEGNetDecoder
    EEGNET_AVAILABLE = True
except ImportError:
    EEGNET_AVAILABLE = False

try:
    from core.decoding.classifiers.deep_learning.multimodal_nn import MultimodalFusionDecoder
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False

try:
    from core.decoding.model_evaluation import ModelEvaluator
    EVALUATOR_AVAILABLE = True
except ImportError:
    EVALUATOR_AVAILABLE = False

try:
    from core.processing.Statistical_Analysis.decoding_stats import (
        classification_metrics, information_transfer_rate, classification_report
    )
    STATS_AVAILABLE = True
except ImportError:
    STATS_AVAILABLE = False

try:
    import matplotlib
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MPL_AVAILABLE = True
except ImportError:
    MPL_AVAILABLE = False


class DecodingPanel(tk.Frame):
    """
    解码分类面板 - 支持 SVM / EEGNet / 多模态融合。

    Parameters
    ----------
    parent : tk.Widget
        父容器
    data_bus : DataBus, optional
        数据总线实例
    show_navigation : bool
        是否显示内部导航
    """

    # 解码器类型
    DECODERS = {
        'SVM': {'available': SVM_AVAILABLE, 'desc': 'SVM 支持向量机 — 经典BCI分类器，适合小样本'},
        'EEGNet': {'available': EEGNET_AVAILABLE, 'desc': 'EEGNet 深度学习 — 端到端EEG分类，需要GPU加速'},
        'MultimodalFusion': {'available': FUSION_AVAILABLE, 'desc': '多模态融合 — EEG+EMG+fNIRS联合分类'},
    }

    def __init__(self, parent, data_bus=None, show_navigation=False):
        super().__init__(parent, bg="#F5F7FA")
        self._ui = MainThreadDispatcher(self)
        self._data_generation = 0
        self._feature_identity = None
        self._label_identity = None
        self._feature_contract = None
        self._label_contract = None
        self.data_bus = data_bus
        self.show_navigation = show_navigation

        # 状态
        self.features = None
        self.labels = None
        self.current_decoder = None
        self.trained_model = None
        self.eval_results = None

        # 构建 UI
        self._build_ui()

        # 监听 DataBus
        if self.data_bus:
            self.data_bus.on_change('features', self._on_features_ready)
            self.data_bus.on_change('labels', self._on_labels_ready)
            self.bind('<Destroy>',self._unsubscribe,add='+')

    def _unsubscribe(self, event):
        if event.widget is self and self.data_bus:
            self.data_bus.off_change('features',self._on_features_ready)
            self.data_bus.off_change('labels',self._on_labels_ready)

    def _build_ui(self):
        """构建面板界面。"""
        # 主滚动区域
        main_frame = tk.Frame(self, bg="#F5F7FA")
        main_frame.pack(fill='both', expand=True, padx=20, pady=15)

        # ===== 标题 =====
        title_frame = tk.Frame(main_frame, bg="#F5F7FA")
        title_frame.pack(fill='x', pady=(0, 15))

        tk.Label(title_frame, text="解码与分类",
                 font=("微软雅黑", 20, "bold"), bg="#F5F7FA", fg="#1A1A2E"
                 ).pack(side='left')

        tk.Label(title_frame, text="训练模型 · 交叉验证 · 性能评估 · ITR计算",
                 font=("微软雅黑", 10), bg="#F5F7FA", fg="#888"
                 ).pack(side='left', padx=(15, 0), pady=(8, 0))

        # ===== 数据状态栏 =====
        status_frame = tk.LabelFrame(main_frame, text="数据状态",
                                      font=("微软雅黑", 10, "bold"),
                                      bg="#FFFFFF", fg="#333", padx=15, pady=10)
        status_frame.pack(fill='x', pady=(0, 12))

        self.status_label = tk.Label(
            status_frame,
            text="等待特征数据... (请先在特征提取面板提取特征)",
            font=("微软雅黑", 9), bg="#FFFFFF", fg="#999"
        )
        self.status_label.pack(anchor='w')

        self.data_info_label = tk.Label(
            status_frame, text="",
            font=("微软雅黑", 9), bg="#FFFFFF", fg="#555"
        )
        self.data_info_label.pack(anchor='w', pady=(5, 0))

        # ===== 手动加载按钮 =====
        load_frame = tk.Frame(status_frame, bg="#FFFFFF")
        load_frame.pack(fill='x', pady=(8, 0))

        tk.Button(load_frame, text="加载特征文件",
                  command=self._load_features_file,
                  font=("微软雅黑", 9), bg="#4A90D9", fg="white",
                  relief='flat', padx=12, pady=4, cursor='hand2'
                  ).pack(side='left')

        tk.Button(load_frame, text="加载标签文件",
                  command=self._load_labels_file,
                  font=("微软雅黑", 9), bg="#5BA65B", fg="white",
                  relief='flat', padx=12, pady=4, cursor='hand2'
                  ).pack(side='left', padx=(10, 0))

        # ===== 解码器选择 =====
        decoder_frame = tk.LabelFrame(main_frame, text="选择解码器",
                                       font=("微软雅黑", 10, "bold"),
                                       bg="#FFFFFF", fg="#333", padx=15, pady=10)
        decoder_frame.pack(fill='x', pady=(0, 12))

        self.decoder_var = tk.StringVar(value='SVM')
        for name, info in self.DECODERS.items():
            state = 'normal' if info['available'] else 'disabled'
            rb = tk.Radiobutton(
                decoder_frame, text=f"{name}  —  {info['desc']}",
                variable=self.decoder_var, value=name, state=state,
                font=("微软雅黑", 9), bg="#FFFFFF", fg="#333",
                selectcolor="#FFFFFF", activebackground="#FFFFFF",
                anchor='w'
            )
            rb.pack(fill='x', pady=2)

        # ===== 参数配置 =====
        params_frame = tk.LabelFrame(main_frame, text="参数配置",
                                      font=("微软雅黑", 10, "bold"),
                                      bg="#FFFFFF", fg="#333", padx=15, pady=10)
        params_frame.pack(fill='x', pady=(0, 12))

        # SVM 参数行
        svm_row = tk.Frame(params_frame, bg="#FFFFFF")
        svm_row.pack(fill='x', pady=3)
        tk.Label(svm_row, text="SVM核函数:", font=("微软雅黑", 9),
                 bg="#FFFFFF").pack(side='left')
        self.kernel_var = tk.StringVar(value='rbf')
        ttk.Combobox(svm_row, textvariable=self.kernel_var,
                     values=['rbf', 'linear', 'poly', 'sigmoid'],
                     width=10, state='readonly').pack(side='left', padx=5)

        tk.Label(svm_row, text="C:", font=("微软雅黑", 9),
                 bg="#FFFFFF").pack(side='left', padx=(15, 0))
        self.c_var = tk.StringVar(value='1.0')
        tk.Entry(svm_row, textvariable=self.c_var, width=8,
                 font=("微软雅黑", 9)).pack(side='left', padx=5)

        # 交叉验证参数行
        cv_row = tk.Frame(params_frame, bg="#FFFFFF")
        cv_row.pack(fill='x', pady=3)
        tk.Label(cv_row, text="验证方法:", font=("微软雅黑", 9),
                 bg="#FFFFFF").pack(side='left')
        self.cv_var = tk.StringVar(value='stratified_kfold')
        ttk.Combobox(cv_row, textvariable=self.cv_var,
                     values=['stratified_kfold', 'kfold', 'holdout', 'loocv'],
                     width=16, state='readonly').pack(side='left', padx=5)

        tk.Label(cv_row, text="折数:", font=("微软雅黑", 9),
                 bg="#FFFFFF").pack(side='left', padx=(15, 0))
        self.n_splits_var = tk.StringVar(value='5')
        tk.Entry(cv_row, textvariable=self.n_splits_var, width=5,
                 font=("微软雅黑", 9)).pack(side='left', padx=5)

        tk.Label(cv_row, text="Trial时长(秒):", font=("微软雅黑", 9),
                 bg="#FFFFFF").pack(side='left', padx=(15, 0))
        self.trial_time_var = tk.StringVar(value='4.0')
        tk.Entry(cv_row, textvariable=self.trial_time_var, width=6,
                 font=("微软雅黑", 9)).pack(side='left', padx=5)

        # 超参数搜索开关
        search_row = tk.Frame(params_frame, bg="#FFFFFF")
        search_row.pack(fill='x', pady=3)
        self.grid_search_var = tk.BooleanVar(value=False)
        tk.Checkbutton(search_row, text="启用网格搜索（自动优化超参数，耗时较长）",
                       variable=self.grid_search_var,
                       font=("微软雅黑", 9), bg="#FFFFFF"
                       ).pack(anchor='w')

        # ===== 操作按钮 =====
        btn_frame = tk.Frame(main_frame, bg="#F5F7FA")
        btn_frame.pack(fill='x', pady=(0, 12))

        self.train_btn = tk.Button(
            btn_frame, text="开始训练与评估",
            command=self._start_training,
            font=("微软雅黑", 11, "bold"), bg="#2D7DDB", fg="white",
            relief='flat', padx=25, pady=8, cursor='hand2',
            activebackground="#1E6BC6", activeforeground="white"
        )
        self.train_btn.pack(side='left')

        tk.Button(btn_frame, text="保存模型",
                  command=self._save_model,
                  font=("微软雅黑", 10), bg="#5BA65B", fg="white",
                  relief='flat', padx=15, pady=6, cursor='hand2'
                  ).pack(side='left', padx=(15, 0))

        tk.Button(btn_frame, text="加载模型",
                  command=self._load_model,
                  font=("微软雅黑", 10), bg="#E8912D", fg="white",
                  relief='flat', padx=15, pady=6, cursor='hand2'
                  ).pack(side='left', padx=(10, 0))

        # ===== 进度条 =====
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            main_frame, variable=self.progress_var,
            maximum=100, mode='indeterminate'
        )
        self.progress_bar.pack(fill='x', pady=(0, 5))

        self.progress_label = tk.Label(
            main_frame, text="", font=("微软雅黑", 9),
            bg="#F5F7FA", fg="#666"
        )
        self.progress_label.pack(anchor='w')

        # ===== 结果区域（分两列） =====
        result_container = tk.Frame(main_frame, bg="#F5F7FA")
        result_container.pack(fill='both', expand=True, pady=(10, 0))

        # 左：文本结果
        left_frame = tk.LabelFrame(result_container, text="评估结果",
                                    font=("微软雅黑", 10, "bold"),
                                    bg="#FFFFFF", fg="#333", padx=10, pady=8)
        left_frame.pack(side='left', fill='both', expand=True, padx=(0, 8))

        self.result_text = tk.Text(
            left_frame, wrap='word', font=("Consolas", 10),
            bg="#FAFAFA", fg="#333", height=18, relief='flat',
            state='disabled'
        )
        scrollbar = ttk.Scrollbar(left_frame, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.result_text.pack(fill='both', expand=True)

        # 右：图表区
        right_frame = tk.LabelFrame(result_container, text="混淆矩阵 / 训练曲线",
                                     font=("微软雅黑", 10, "bold"),
                                     bg="#FFFFFF", fg="#333", padx=10, pady=8)
        right_frame.pack(side='right', fill='both', expand=True, padx=(8, 0))

        self.chart_frame = tk.Frame(right_frame, bg="#FFFFFF")
        self.chart_frame.pack(fill='both', expand=True)

    # ===== 数据加载 =====

    def _clear_displayed_results(self):
        self.result_text.config(state='normal')
        self.result_text.delete('1.0','end')
        self.result_text.config(state='disabled')
        for widget in self.chart_frame.winfo_children():
            widget.destroy()

    def _on_features_ready(self, features):
        metadata=self.data_bus.get_metadata('features') if self.data_bus else None
        contract=sample_contract(metadata or {})
        identity=identity_key(contract)
        if features is not self.features or identity!=self._feature_identity:
            self._data_generation+=1
            self.labels=None;self._label_contract=None;self._label_identity=None
            self.trained_model=None;self.eval_results=None
            self._clear_displayed_results()
        self.features=features
        self._feature_contract=contract
        self._feature_identity=identity
        self._update_data_status()

    def _on_labels_ready(self, labels):
        contract=None;identity=None
        if labels is not None:
            try:
                metadata=self.data_bus.get_metadata('labels') if self.data_bus else None
                candidate=sample_contract(metadata or {})
                if candidate is not None and self._feature_contract is not None:
                    validate_label_binding(self.features,labels,self._feature_contract,candidate)
                    contract=candidate;identity=identity_key(candidate)
            except ValueError:
                labels=None
        if labels is not self.labels or identity!=self._label_identity:
            self._data_generation+=1
            self.trained_model=None;self.eval_results=None
            self._clear_displayed_results()
        self.labels=labels;self._label_contract=contract;self._label_identity=identity
        self._update_data_status()

    def _load_features_file(self):
        path=filedialog.askopenfilename(title='选择特征与样本身份文件',
            filetypes=[('安全特征文件','*.npz *.json *.csv *.npy'),('所有文件','*.*')])
        if not path:return
        self._data_generation=getattr(self,'_data_generation',0)+1
        self.features=None;self.labels=None;self.trained_model=None;self.eval_results=None
        self._feature_contract=None;self._label_contract=None
        self._feature_identity=None;self._label_identity=None
        self._clear_displayed_results()
        if self.data_bus:self.data_bus.set_data('features',None)
        try:
            features,labels,contract=load_feature_samples(path)
            if labels is not None and contract is not None:
                validate_label_binding(features,labels,contract,contract)
            self.features=features;self.labels=labels
            self._feature_contract=contract;self._feature_identity=identity_key(contract)
            if labels is not None and contract is not None:
                self._label_contract=contract;self._label_identity=identity_key(contract)
            if self.data_bus:
                self.data_bus.set_data('features',features,metadata=contract)
                self.data_bus.set_data('labels',labels,metadata=contract if labels is not None else None)
            self._update_data_status()
            detail='样本身份已声明' if contract else '身份缺失，仅为特征草稿，不能训练'
            messagebox.showinfo('已加载',f'{os.path.basename(path)}；{detail}')
        except Exception as exc:
            self.features=None;self.labels=None;self._feature_contract=None;self._label_contract=None
            self._feature_identity=None;self._label_identity=None
            self._update_data_status()
            messagebox.showerror('加载失败',str(exc))

    def _load_labels_file(self):
        path=filedialog.askopenfilename(title='选择带数据集/版本/sample_id 的标签文件',
            filetypes=[('身份标签文件','*.npz *.json *.csv'),('所有文件','*.*')])
        if not path:return
        self._data_generation+=1
        self.labels=None;self._label_contract=None;self._label_identity=None
        self.trained_model=None;self.eval_results=None
        self._clear_displayed_results()
        if self.data_bus:self.data_bus.set_data('labels',None)
        try:
            labels,contract=load_label_samples(path)
            validate_label_binding(self.features,labels,self._feature_contract,contract)
            self.labels=labels;self._label_contract=contract;self._label_identity=identity_key(contract)
            if self.data_bus:self.data_bus.set_data('labels',labels,metadata=contract)
            self._update_data_status()
            messagebox.showinfo('已核对','数据集、版本与 sample_id 顺序一致；没有自动重排')
        except Exception as exc:
            self._update_data_status()
            messagebox.showerror('标签绑定失败',str(exc))

    def _update_data_status(self):
        """更新数据状态显示。"""
        parts = []
        if self.features is not None:
            if isinstance(self.features, dict):
                mods = list(self.features.keys())
                total_feat = sum(
                    v.shape[1] if isinstance(v, np.ndarray) and v.ndim == 2 else 0
                    for v in self.features.values()
                )
                parts.append(f"多模态特征: {mods}, 共 {total_feat} 维")
            elif isinstance(self.features, np.ndarray):
                parts.append(f"特征矩阵: {self.features.shape}")
            else:
                parts.append("特征已加载")

        if self.labels is not None:
            labels = np.array(self.labels)
            classes = np.unique(labels)
            parts.append(f"标签: {len(labels)} 样本, {len(classes)} 类别 {classes.tolist()}")

        if parts:
            if self.features is not None and self._feature_contract is None:
                parts.append('样本身份缺失：只能保留草稿，不能提交训练')
            if self.labels is not None and self._label_contract is None:
                parts.append('标签尚未通过数据集/版本/sample_id 核对')
            self.status_label.config(text="数据就绪", fg="#2D7DDB")
            self.data_info_label.config(text=" | ".join(parts))
        else:
            self.status_label.config(text="等待特征数据...", fg="#999")
            self.data_info_label.config(text="")

    # ===== 训练与评估 =====

    def _start_training(self):
        """开始训练（后台线程）。"""
        if self.features is None:
            messagebox.showwarning("提示", "请先加载特征数据")
            return
        if self.labels is None:
            messagebox.showwarning("提示", "请先加载标签数据")
            return

        try:
            validate_label_binding(self.features,self.labels,self._feature_contract,self._label_contract)
            options = {name: getattr(self, name).get() for name in
                ('decoder_var','cv_var','n_splits_var','trial_time_var','kernel_var','c_var','grid_search_var')}
            snapshot = {'features':copy.deepcopy(self.features), 'labels':np.asarray(self.labels).copy(),
                        'options':options, 'generation':self._data_generation,
                        'sample_identity':copy.deepcopy(self._feature_contract),
                        'revision':self.data_bus.get_revision() if self.data_bus else None}
            arrays = list(snapshot['features'].values()) if isinstance(snapshot['features'],dict) else [snapshot['features']]
            if not arrays or any(np.asarray(a).ndim < 2 or len(a) != len(snapshot['labels']) or
                                 not np.isfinite(np.asarray(a,dtype=float)).all() for a in arrays):
                raise ValueError('特征必须为有限值矩阵，并按样本顺序与标签等长')
            int(options['n_splits_var']); float(options['trial_time_var']); float(options['c_var'])
        except Exception as exc:
            messagebox.showerror('输入无效',str(exc))
            return
        self.train_btn.config(state='disabled', text="训练中...")
        self.progress_bar.start(10)
        self.progress_label.config(text="正在训练模型，请稍候...")

        thread = threading.Thread(target=self._train_worker, args=(snapshot,), daemon=True)
        thread.start()

    def _train_worker(self, snapshot):
        """训练工作线程。"""
        try:
            decoder_type = snapshot['options']['decoder_var']
            cv_method = snapshot['options']['cv_var']
            n_splits = int(snapshot['options']['n_splits_var'])
            trial_time = float(snapshot['options']['trial_time_var'])
            is_multimodal = isinstance(snapshot['features'], dict)

            # 准备数据
            if is_multimodal:
                X = {k: np.array(v, dtype=np.float64) for k, v in snapshot['features'].items()}
            else:
                X = np.array(snapshot['features'], dtype=np.float64)
            y = np.array(snapshot['labels'])

            # 创建解码器
            n_classes = len(np.unique(y))

            if decoder_type == 'SVM':
                kernel = snapshot['options']['kernel_var']
                C = float(snapshot['options']['c_var'])
                decoder = SVMDecoder(kernel=kernel, C=C)

                if snapshot['options']['grid_search_var']:
                    self._ui.post(self._training_progress,snapshot,"正在执行网格搜索...")
                    gs_result = decoder.grid_search(X, y, cv=n_splits)

            elif decoder_type == 'EEGNet':
                if X.ndim == 2:
                    n_ch = 1
                    n_samples = X.shape[1]
                elif X.ndim == 3:
                    n_ch = X.shape[1]
                    n_samples = X.shape[2]
                else:
                    raise ValueError(f"EEGNet 需要 2D/3D 输入, 得到 {X.ndim}D")

                decoder = EEGNetDecoder(
                    n_channels=n_ch, n_samples=n_samples,
                    n_classes=n_classes
                )

            elif decoder_type == 'MultimodalFusion':
                if not is_multimodal:
                    raise ValueError("多模态融合需要字典格式的多模态特征输入")
                decoder = MultimodalFusionDecoder(
                    fusion_method='attention', n_classes=n_classes
                )

            # 交叉验证
            self._ui.post(self._training_progress,snapshot,f"正在进行 {cv_method} 交叉验证 ({n_splits} 折)...")

            evaluator = ModelEvaluator(
                cv_method=cv_method, n_splits=n_splits,
                trial_time=trial_time
            )
            results = evaluator.cross_validate(
                decoder, X, y, is_multimodal=is_multimodal
            )

            # 训练最终模型（全数据）
            self._ui.post(self._training_progress,snapshot,"正在训练最终模型（全量数据）...")

            final_decoder = evaluator._clone_decoder(decoder)
            if is_multimodal:
                final_decoder.fit(X, y)
            else:
                final_decoder.fit(X, y)

            self._ui.post(self._commit_training, snapshot, final_decoder, results, decoder_type, trial_time)

        except Exception as e:
            traceback.print_exc()
            self._ui.post(self._finish_training_error, snapshot, str(e))

    def _training_current(self, snapshot):
        return snapshot['generation'] == self._data_generation and (not self.data_bus or
               snapshot['revision'] == self.data_bus.get_revision())

    def _training_progress(self, snapshot, text):
        if self._training_current(snapshot):
            self.progress_label.config(text=text)

    def _finish_training_error(self, snapshot, error):
        if self._training_current(snapshot):
            self._on_train_error(error)
        else:
            self.progress_bar.stop()
            self.train_btn.config(state='normal',text='开始训练与评估')
            self.progress_label.config(text='输入已变更，旧任务结果已丢弃')

    def _commit_training(self, snapshot, model, results, decoder_type, trial_time):
        if not self._training_current(snapshot):
            self._finish_training_error(snapshot,'旧版本')
            return
        self.trained_model = model
        self.eval_results = results
        if self.data_bus:
            self.data_bus.set_data('decode_result',{'model':model,'eval_results':results,
                'decoder_type':decoder_type,'input_revision':snapshot['revision'],
                'sample_identity':snapshot['sample_identity']},
                expected_revision=snapshot['revision'])
        self._show_results(results,decoder_type,trial_time)

    def _on_train_error(self, err_msg):
        """训练失败回调。"""
        self.progress_bar.stop()
        self.train_btn.config(state='normal', text="开始训练与评估")
        self.progress_label.config(text=f"训练失败: {err_msg}", fg="red")
        messagebox.showerror("训练失败", err_msg)

    def _show_results(self, results, decoder_type, trial_time):
        """显示评估结果。"""
        self.progress_bar.stop()
        self.train_btn.config(state='normal', text="开始训练与评估")
        self.progress_label.config(text="训练完成!", fg="#2D7DDB")

        # ===== 文本结果 =====
        self.result_text.config(state='normal')
        self.result_text.delete('1.0', 'end')

        mean = results.get('mean_metrics', {})
        std = results.get('std_metrics', {})

        text = f"{'=' * 50}\n"
        text += f"  解码器: {decoder_type}\n"
        text += f"  验证方法: {results.get('cv_method', '?')} ({results.get('n_splits', '?')} 折)\n"
        text += f"{'=' * 50}\n\n"

        text += "【交叉验证结果（均值 ± 标准差）】\n"
        text += f"  准确率 (Accuracy):  {mean.get('accuracy', 0):.4f} ± {std.get('accuracy', 0):.4f}\n"
        text += f"  Kappa 系数:         {mean.get('kappa', 0):.4f} ± {std.get('kappa', 0):.4f}\n"
        text += f"  F1 (macro):         {mean.get('f1_macro', 0):.4f} ± {std.get('f1_macro', 0):.4f}\n"
        text += f"  F1 (weighted):      {mean.get('f1_weighted', 0):.4f} ± {std.get('f1_weighted', 0):.4f}\n"

        if 'itr' in mean:
            text += f"\n【信息传输率 (ITR)】\n"
            text += f"  ITR:  {mean['itr']:.2f} ± {std.get('itr', 0):.2f} bits/min\n"
            text += f"  (trial_time = {trial_time}s)\n"

        # 每折结果
        fold_metrics = results.get('fold_metrics', [])
        if fold_metrics:
            text += f"\n【各折结果】\n"
            for i, fm in enumerate(fold_metrics):
                text += f"  Fold {i+1}: acc={fm.get('accuracy', 0):.4f}  "
                text += f"kappa={fm.get('kappa', 0):.4f}  "
                text += f"f1={fm.get('f1_macro', 0):.4f}\n"

        # 每类结果
        per_class = results.get('overall_per_class', {})
        if per_class:
            text += f"\n【每类指标】\n"
            text += f"  {'类别':8s} {'精确率':8s} {'召回率':8s} {'F1':8s}\n"
            text += f"  {'-' * 35}\n"
            for label, m in per_class.items():
                text += (f"  {str(label):8s} {m['precision']:8.4f} "
                         f"{m['recall']:8.4f} {m['f1']:8.4f}\n")

        self.result_text.insert('1.0', text)
        self.result_text.config(state='disabled')

        # ===== 可视化: 混淆矩阵 =====
        if MPL_AVAILABLE:
            self._plot_confusion_matrix(results)

    def _plot_confusion_matrix(self, results):
        """绘制混淆矩阵到图表区域。"""
        # 清除旧图
        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        cm = results.get('overall_confusion_matrix')
        if cm is None:
            return

        cm = np.array(cm)

        fig, ax = plt.subplots(figsize=(4.5, 3.8), dpi=100)
        fig.patch.set_facecolor('white')

        im = ax.imshow(cm, interpolation='nearest', cmap='Blues')
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

        n_classes = cm.shape[0]
        ax.set_xticks(range(n_classes))
        ax.set_yticks(range(n_classes))

        labels = list(results.get('overall_per_class', {}).keys())
        if len(labels) == n_classes:
            ax.set_xticklabels(labels, fontsize=8)
            ax.set_yticklabels(labels, fontsize=8)

        # 数值标注
        thresh = cm.max() / 2
        for i in range(n_classes):
            for j in range(n_classes):
                color = 'white' if cm[i, j] > thresh else 'black'
                ax.text(j, i, str(int(cm[i, j])),
                        ha='center', va='center', color=color, fontsize=10)

        ax.set_xlabel('预测标签', fontsize=9)
        ax.set_ylabel('真实标签', fontsize=9)
        ax.set_title('混淆矩阵', fontsize=11, fontweight='bold')
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)
        plt.close(fig)

    # ===== 模型保存/加载 =====

    def _save_model(self):
        """保存训练好的模型。"""
        if self.trained_model is None:
            messagebox.showwarning("提示", "没有可保存的模型，请先训练")
            return

        path = filedialog.asksaveasfilename(
            title="保存模型",
            defaultextension=".pkl",
            filetypes=[("模型文件", "*.pkl *.pth"), ("所有文件", "*.*")]
        )
        if not path:
            return

        try:
            self.trained_model.save(path)
            messagebox.showinfo("成功", f"模型已保存: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _load_model(self):
        messagebox.showwarning('能力限制','旧模型加载涉及对象反序列化，普通入口已禁用；请使用可信离线迁移流程')
