# -*- coding: utf-8 -*-
"""
DataBus - 面板间数据共享总线
===================================================
解决各面板独立加载数据、互不通信的核心架构缺陷。
所有面板共享同一个 DataBus 实例，通过事件机制自动通知下游。

数据流:
    加载原始数据 → 预处理 → 特征提取 → 解码分类 → 统计分析
                                                    ↓
                                                 可视化
"""

import threading
import copy
from typing import Any, Callable, Dict, List, Optional


class DataBus:
    """
    面板间数据共享中枢。

    Attributes
    ----------
    raw_data_dict : dict or None
        原始加载的四层数据字典
    processed_data_dict : dict or None
        预处理后的数据字典
    features : dict or None
        提取的特征 {modality: {feature_name: value}}
    labels : np.ndarray or None
        事件标签（用于分类）
    decode_result : dict or None
        解码/分类结果 {y_pred, y_score, metrics, model_info}
    statistics : dict or None
        统计分析结果
    current_file_path : str or None
        当前加载的文件路径
    """

    # 数据阶段常量
    STAGE_RAW = "raw_data_dict"
    STAGE_PROCESSED = "processed_data_dict"
    STAGE_FEATURES = "features"
    STAGE_LABELS = "labels"
    STAGE_DECODE = "decode_result"
    STAGE_STATISTICS = "statistics"

    def __init__(self):
        self._lock = threading.RLock()
        self._revision = 0
        self.dataset_id = None
        self._dispatcher = None
        self._listeners: Dict[str, List[Callable]] = {}
        self._metadata = {}

        # 数据存储
        self.raw_data_dict: Optional[dict] = None
        self.processed_data_dict: Optional[dict] = None
        self.features: Optional[dict] = None
        self.labels: Optional[Any] = None
        self.decode_result: Optional[dict] = None
        self.statistics: Optional[dict] = None
        self.current_file_path: Optional[str] = None

    def get_revision(self):
        """计算请求绑定此版本；任何输入变化均使旧请求失效。"""
        with self._lock:
            return self._revision

    def set_dispatcher(self, dispatcher):
        """可选主线程队列派发器；工作线程不接触 Tk。"""
        self._dispatcher = dispatcher

    def set_data(self, stage: str, data: Any, expected_revision=None, metadata=None):
        """
        设置某个阶段的数据，并通知所有监听者。

        Parameters
        ----------
        stage : str
            数据阶段，使用 STAGE_* 常量
        data : Any
            数据内容
        """
        with self._lock:
            stages = (self.STAGE_RAW,self.STAGE_PROCESSED,self.STAGE_FEATURES,
                      self.STAGE_LABELS,self.STAGE_DECODE,self.STAGE_STATISTICS)
            if stage not in stages:
                raise ValueError(f"未知数据阶段: {stage}")
            if expected_revision is not None and expected_revision != self._revision:
                return False
            downstream = {
                self.STAGE_RAW: stages[1:],
                self.STAGE_PROCESSED: (self.STAGE_FEATURES,self.STAGE_LABELS,self.STAGE_DECODE,self.STAGE_STATISTICS),
                self.STAGE_FEATURES: (self.STAGE_LABELS,self.STAGE_DECODE,self.STAGE_STATISTICS),
                self.STAGE_LABELS: (self.STAGE_DECODE,self.STAGE_STATISTICS),
                self.STAGE_DECODE: (self.STAGE_STATISTICS,),
            }.get(stage, ())
            if stage in stages[:4]:
                self._revision += 1
            if stage == self.STAGE_RAW:
                import uuid
                self.dataset_id = str(uuid.uuid4()) if data is not None else None
            for target in downstream:
                setattr(self,target,None)
                self._metadata[target]=None
            setattr(self, stage, data)
            self._metadata[stage]=copy.deepcopy(metadata) if data is not None else None
        for target in downstream:
            self._notify(target,None)
        self._notify(stage, data)
        return True

    def get_data(self, stage: str) -> Any:
        """获取某个阶段的数据。"""
        with self._lock:
            return getattr(self, stage, None)

    def get_metadata(self, stage):
        with self._lock:
            return copy.deepcopy(self._metadata.get(stage))

    def get_best_data_dict(self) -> Optional[dict]:
        """
        获取当前最佳的数据字典（优先返回预处理后的）。
        用于特征提取/可视化等面板自动选择最新数据。
        """
        with self._lock:
            if self.processed_data_dict is not None:
                return self.processed_data_dict
            return self.raw_data_dict

    def on_change(self, stage: str, callback: Callable):
        """
        注册数据变更监听器。

        Parameters
        ----------
        stage : str
            要监听的数据阶段
        callback : callable
            回调函数，签名: callback(data)
        """
        with self._lock:
            self._listeners.setdefault(stage, []).append(callback)

    def off_change(self, stage: str, callback: Callable):
        """移除监听器。"""
        if stage in self._listeners:
            self._listeners[stage] = [
                cb for cb in self._listeners[stage] if cb != callback
            ]

    def _notify(self, stage: str, data: Any):
        """通知所有监听该阶段的回调。"""
        with self._lock:
            callbacks = list(self._listeners.get(stage, []))
            revision = self._revision
        for callback in callbacks:
            try:
                if self._dispatcher:
                    self._dispatcher.post(lambda cb=callback, value=data, target=stage:
                        cb(value) if self.get_data(target) is value else None)
                else:
                    callback(data)
            except Exception as e:
                print(f"[DataBus] 通知回调异常 ({stage}): {e}")

    def reset(self):
        """重置所有数据（加载新文件时调用）。"""
        with self._lock:
            self.raw_data_dict = None
            self.processed_data_dict = None
            self.features = None
            self.labels = None
            self.decode_result = None
            self.statistics = None
            self.current_file_path = None
            self.dataset_id = None
            self._revision += 1
            self._metadata.clear()
        for stage in (self.STAGE_RAW,self.STAGE_PROCESSED,self.STAGE_FEATURES,
                      self.STAGE_LABELS,self.STAGE_DECODE,self.STAGE_STATISTICS):
            self._notify(stage,None)

    def get_pipeline_status(self) -> dict:
        """获取当前管线各阶段的完成状态。"""
        return {
            "raw_loaded": self.raw_data_dict is not None,
            "preprocessed": self.processed_data_dict is not None,
            "features_extracted": self.features is not None,
            "labels_available": self.labels is not None,
            "decoded": self.decode_result is not None,
            "statistics_done": self.statistics is not None,
            "file_path": self.current_file_path,
        }

    def __repr__(self):
        status = self.get_pipeline_status()
        stages = [k for k, v in status.items() if v is True]
        return f"<DataBus completed=[{', '.join(stages)}]>"
