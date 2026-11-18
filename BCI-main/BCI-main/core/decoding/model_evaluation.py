# -*- coding: utf-8 -*-
"""
交叉验证与模型评估管理器
===================================================
统一管理 SVM / EEGNet / 多模态融合的训练-评估-交叉验证流程。
将解码器与 decoding_stats 评估指标无缝衔接。

功能:
    1. K-Fold / Stratified K-Fold 交叉验证
    2. 留一法 (LOOCV)
    3. 训练/测试集划分评估
    4. 统一结果格式，写入 data_dict
"""

import numpy as np
import warnings
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

try:
    from sklearn.model_selection import (
        StratifiedKFold, KFold, LeaveOneOut, train_test_split
    )
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    warnings.warn("scikit-learn 未安装，交叉验证功能受限")


class ModelEvaluator:
    """
    统一模型评估管理器。

    Parameters
    ----------
    cv_method : str
        'stratified_kfold', 'kfold', 'loocv', 'holdout'
    n_splits : int
        折数 (kfold用)
    test_size : float
        测试集比例 (holdout用)
    random_state : int
        随机种子
    trial_time : float
        单次试验时长（秒），用于 ITR 计算
    """

    def __init__(self, cv_method: str = 'stratified_kfold',
                 n_splits: int = 5, test_size: float = 0.2,
                 random_state: int = 42, trial_time: float = 4.0):
        self.cv_method = cv_method
        self.n_splits = n_splits
        self.test_size = test_size
        self.random_state = random_state
        self.trial_time = trial_time

    def cross_validate(self, decoder, X, y,
                       is_multimodal: bool = False) -> dict:
        """
        执行交叉验证。

        Parameters
        ----------
        decoder : SVMDecoder | EEGNetDecoder | MultimodalFusionDecoder
            解码器实例（每折会重新初始化）
        X : ndarray 或 dict
            特征矩阵。多模态时为 {modality: ndarray}
        y : ndarray
            标签
        is_multimodal : bool
            是否多模态输入

        Returns
        -------
        results : dict
            fold_metrics, mean_metrics, std_metrics, all_y_true, all_y_pred
        """
        from core.processing.Statistical_Analysis.decoding_stats import (
            classification_metrics, information_transfer_rate
        )

        y = np.array(y)

        if self.cv_method == 'stratified_kfold':
            splitter = StratifiedKFold(n_splits=self.n_splits, shuffle=True,
                                       random_state=self.random_state)
        elif self.cv_method == 'kfold':
            splitter = KFold(n_splits=self.n_splits, shuffle=True,
                             random_state=self.random_state)
        elif self.cv_method == 'loocv':
            splitter = LeaveOneOut()
        elif self.cv_method == 'holdout':
            return self._holdout_evaluate(decoder, X, y, is_multimodal)
        else:
            raise ValueError(f"不支持的交叉验证方法: {self.cv_method}")

        # 获取用于分割的 X_ref
        if is_multimodal:
            X_ref = list(X.values())[0]
        else:
            X_ref = X if isinstance(X, np.ndarray) else np.array(X)

        fold_metrics = []
        all_y_true = []
        all_y_pred = []

        for fold_idx, (train_idx, test_idx) in enumerate(splitter.split(X_ref, y)):
            # 分割数据
            if is_multimodal:
                X_train = {k: v[train_idx] for k, v in X.items()}
                X_test = {k: v[test_idx] for k, v in X.items()}
            else:
                X_train, X_test = X_ref[train_idx], X_ref[test_idx]

            y_train, y_test = y[train_idx], y[test_idx]

            # 克隆解码器（重新初始化）
            dec = self._clone_decoder(decoder)

            # 训练
            if is_multimodal:
                dec.fit(X_train, y_train)
            else:
                dec.fit(X_train, y_train)

            # 评估
            if is_multimodal:
                y_pred = dec.predict(X_test)
            else:
                y_pred = dec.predict(X_test)

            metrics = classification_metrics(y_test, y_pred)
            n_classes = len(np.unique(y))
            metrics['itr'] = information_transfer_rate(
                metrics['accuracy'], n_classes, self.trial_time
            )

            fold_metrics.append(metrics)
            all_y_true.extend(y_test.tolist())
            all_y_pred.extend(y_pred.tolist())

            logger.info(f"Fold {fold_idx+1}: accuracy={metrics['accuracy']:.4f}")

        # 汇总
        metric_keys = ['accuracy', 'kappa', 'f1_macro', 'f1_weighted', 'itr']
        mean_metrics = {}
        std_metrics = {}
        for key in metric_keys:
            values = [m[key] for m in fold_metrics if key in m]
            if values:
                mean_metrics[key] = float(np.mean(values))
                std_metrics[key] = float(np.std(values))

        # 全局混淆矩阵
        overall = classification_metrics(all_y_true, all_y_pred)

        results = {
            'cv_method': self.cv_method,
            'n_splits': self.n_splits,
            'fold_metrics': fold_metrics,
            'mean_metrics': mean_metrics,
            'std_metrics': std_metrics,
            'overall_confusion_matrix': overall['confusion_matrix'],
            'overall_per_class': overall['per_class'],
            'all_y_true': all_y_true,
            'all_y_pred': all_y_pred,
        }

        logger.info(f"交叉验证完成: {self.cv_method}, "
                    f"accuracy={mean_metrics.get('accuracy', 0):.4f} "
                    f"+/- {std_metrics.get('accuracy', 0):.4f}")

        return results

    def _holdout_evaluate(self, decoder, X, y, is_multimodal):
        """留出法评估。"""
        from core.processing.Statistical_Analysis.decoding_stats import (
            classification_metrics, information_transfer_rate
        )

        y = np.array(y)
        n = len(y)
        indices = np.arange(n)

        # 分层分割
        if SKLEARN_AVAILABLE:
            train_idx, test_idx = train_test_split(
                indices, test_size=self.test_size,
                stratify=y, random_state=self.random_state
            )
        else:
            split = int(n * (1 - self.test_size))
            np.random.seed(self.random_state)
            np.random.shuffle(indices)
            train_idx, test_idx = indices[:split], indices[split:]

        if is_multimodal:
            X_train = {k: v[train_idx] for k, v in X.items()}
            X_test = {k: v[test_idx] for k, v in X.items()}
        else:
            X_train, X_test = X[train_idx], X[test_idx]

        y_train, y_test = y[train_idx], y[test_idx]

        dec = self._clone_decoder(decoder)
        dec.fit(X_train, y_train)
        y_pred = dec.predict(X_test)

        metrics = classification_metrics(y_test, y_pred)
        n_classes = len(np.unique(y))
        metrics['itr'] = information_transfer_rate(
            metrics['accuracy'], n_classes, self.trial_time
        )

        return {
            'cv_method': 'holdout',
            'test_size': self.test_size,
            'fold_metrics': [metrics],
            'mean_metrics': {k: metrics[k] for k in ['accuracy', 'kappa', 'f1_macro', 'itr'] if k in metrics},
            'std_metrics': {},
            'overall_confusion_matrix': metrics['confusion_matrix'],
            'overall_per_class': metrics['per_class'],
            'all_y_true': y_test.tolist(),
            'all_y_pred': y_pred.tolist(),
            'trained_decoder': dec,
        }

    def _clone_decoder(self, decoder):
        """克隆解码器（重新创建同参数实例）。"""
        cls = type(decoder)
        if cls.__name__ == 'SVMDecoder':
            return cls(
                kernel=decoder.kernel, C=decoder.C,
                gamma=decoder.gamma, probability=decoder.probability,
                random_state=self.random_state
            )
        elif cls.__name__ == 'EEGNetDecoder':
            return cls(
                n_channels=decoder.n_channels,
                n_samples=decoder.n_samples,
                n_classes=decoder.n_classes,
                F1=decoder.F1, F2=decoder.F2, D=decoder.D,
                dropout_rate=decoder.dropout_rate,
                learning_rate=decoder.learning_rate,
                batch_size=decoder.batch_size,
                epochs=decoder.epochs,
                patience=decoder.patience,
            )
        elif cls.__name__ == 'MultimodalFusionDecoder':
            return cls(
                fusion_method=decoder.fusion_method,
                n_classes=decoder.n_classes,
                hidden_dim=decoder.hidden_dim,
                dropout=decoder.dropout,
                random_state=self.random_state,
            )
        else:
            # 通用回退
            import copy
            return copy.deepcopy(decoder)


def evaluate_and_store(data_dict: dict, decoder, X, y,
                       cv_method: str = 'stratified_kfold',
                       n_splits: int = 5,
                       trial_time: float = 4.0,
                       is_multimodal: bool = False) -> dict:
    """
    一站式评估接口: 交叉验证 + 结果写入 data_dict。

    Parameters
    ----------
    data_dict : dict
        四层数据字典
    decoder : any decoder
        解码器实例
    X : ndarray or dict
        特征
    y : ndarray
        标签
    cv_method : str
        交叉验证方法
    n_splits : int
        折数
    trial_time : float
        试验时长（秒）
    is_multimodal : bool
        多模态标志

    Returns
    -------
    data_dict : dict
        结果写入 data_dict['processed']['statistics']['decoding']
    """
    evaluator = ModelEvaluator(
        cv_method=cv_method,
        n_splits=n_splits,
        trial_time=trial_time,
    )
    results = evaluator.cross_validate(decoder, X, y, is_multimodal)

    # 写入四层字典
    if 'processed' not in data_dict:
        data_dict['processed'] = {}
    if 'statistics' not in data_dict['processed']:
        data_dict['processed']['statistics'] = {}
    if 'decoding' not in data_dict['processed']['statistics']:
        data_dict['processed']['statistics']['decoding'] = {}

    data_dict['processed']['statistics']['decoding']['cross_validation'] = results

    return data_dict