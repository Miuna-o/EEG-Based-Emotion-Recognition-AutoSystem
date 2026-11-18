# -*- coding: utf-8 -*-
"""
SVM 解码器
===================================================
支持多种核函数的 SVM 分类器，集成特征选择、超参数搜索、模型持久化。
完全兼容四层数据字典，输出结果自动写入 data_dict['processed']。

功能:
    1. 训练/预测（支持概率输出）
    2. 网格搜索超参数优化
    3. 特征标准化（自动 fit/transform）
    4. 模型保存/加载（joblib）
    5. 与 decoding_stats.py 无缝集成

依赖:
    - 必需: numpy, scikit-learn
    - 可选: joblib（模型持久化）
"""

import numpy as np
import warnings
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from sklearn.svm import SVC
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import GridSearchCV, StratifiedKFold
    from sklearn.pipeline import Pipeline
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    warnings.warn("scikit-learn 未安装，SVM 解码器不可用")

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False


class SVMDecoder:
    """
    SVM 脑机接口解码器。

    Parameters
    ----------
    kernel : str
        核函数: 'rbf', 'linear', 'poly', 'sigmoid'
    C : float
        正则化参数
    gamma : str or float
        核系数: 'scale', 'auto', 或浮点数
    probability : bool
        是否启用概率估计
    random_state : int
        随机种子
    """

    def __init__(self, kernel='rbf', C=1.0, gamma='scale',
                 probability=True, random_state=42):
        if not SKLEARN_AVAILABLE:
            raise ImportError("scikit-learn 未安装")

        self.kernel = kernel
        self.C = C
        self.gamma = gamma
        self.probability = probability
        self.random_state = random_state

        self.pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('svm', SVC(
                kernel=kernel, C=C, gamma=gamma,
                probability=probability,
                random_state=random_state,
                class_weight='balanced'
            ))
        ])

        self.is_fitted = False
        self.classes_ = None
        self.n_features_ = None
        self.best_params_ = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> 'SVMDecoder':
        """训练 SVM 模型。"""
        X = np.array(X, dtype=np.float64)
        y = np.array(y)

        if X.ndim != 2:
            raise ValueError(f"X 必须是 2D 数组，得到 {X.ndim}D")
        if len(X) != len(y):
            raise ValueError(f"样本数不匹配: X={len(X)}, y={len(y)}")

        mask = np.isfinite(X).all(axis=1)
        if not mask.all():
            n_bad = (~mask).sum()
            warnings.warn(f"移除 {n_bad} 个含 NaN/Inf 的样本")
            X, y = X[mask], y[mask]

        self.pipeline.fit(X, y)
        self.is_fitted = True
        self.classes_ = self.pipeline.named_steps['svm'].classes_
        self.n_features_ = X.shape[1]

        logger.info(f"SVM 训练完成: {len(X)} 样本, {self.n_features_} 特征, "
                    f"{len(self.classes_)} 类别, kernel={self.kernel}")
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测标签。"""
        self._check_fitted()
        return self.pipeline.predict(np.array(X, dtype=np.float64))

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测概率分布。"""
        self._check_fitted()
        if not self.probability:
            raise ValueError("probability=False，无法输出概率")
        return self.pipeline.predict_proba(np.array(X, dtype=np.float64))

    def evaluate(self, X: np.ndarray, y: np.ndarray,
                 trial_time: float = 4.0) -> dict:
        """评估模型，返回 accuracy/kappa/f1/auc/itr/confusion_matrix。"""
        from core.processing.Statistical_Analysis.decoding_stats import (
            classification_metrics, information_transfer_rate
        )
        y_pred = self.predict(X)
        y_score = None
        if self.probability and len(self.classes_) == 2:
            y_score = self.predict_proba(X)[:, 1]

        metrics = classification_metrics(y, y_pred, y_score)
        n_classes = len(self.classes_)
        metrics['itr'] = information_transfer_rate(
            metrics['accuracy'], n_classes, trial_time
        )
        metrics['n_classes'] = n_classes
        metrics['n_test_samples'] = len(y)
        metrics['model_type'] = 'SVM'
        metrics['kernel'] = self.kernel
        return metrics

    def grid_search(self, X: np.ndarray, y: np.ndarray,
                    param_grid: Optional[dict] = None,
                    cv: int = 5, scoring: str = 'accuracy') -> dict:
        """网格搜索超参数优化。"""
        if param_grid is None:
            param_grid = {
                'svm__C': [0.1, 1.0, 10.0, 100.0],
                'svm__gamma': ['scale', 'auto', 0.01, 0.1, 1.0],
                'svm__kernel': ['rbf', 'linear']
            }

        X = np.array(X, dtype=np.float64)
        y = np.array(y)
        cv_splitter = StratifiedKFold(n_splits=cv, shuffle=True,
                                       random_state=self.random_state)
        gs = GridSearchCV(
            self.pipeline, param_grid, cv=cv_splitter,
            scoring=scoring, n_jobs=-1, refit=True, return_train_score=True
        )
        gs.fit(X, y)

        self.pipeline = gs.best_estimator_
        self.is_fitted = True
        self.classes_ = self.pipeline.named_steps['svm'].classes_
        self.n_features_ = X.shape[1]
        self.best_params_ = gs.best_params_

        return {
            'best_params': gs.best_params_,
            'best_score': gs.best_score_,
            'cv_results': {
                'mean_test_score': gs.cv_results_['mean_test_score'].tolist(),
                'std_test_score': gs.cv_results_['std_test_score'].tolist(),
                'params': [str(p) for p in gs.cv_results_['params']],
            }
        }

    def save(self, filepath: str):
        """保存模型到文件。"""
        if not JOBLIB_AVAILABLE:
            raise ImportError("需要 joblib")
        self._check_fitted()
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        joblib.dump({
            'pipeline': self.pipeline,
            'classes_': self.classes_,
            'n_features_': self.n_features_,
            'best_params_': self.best_params_,
            'config': {'kernel': self.kernel, 'C': self.C,
                       'gamma': self.gamma, 'probability': self.probability}
        }, filepath)
        logger.info(f"模型已保存: {filepath}")

    def load(self, filepath: str) -> 'SVMDecoder':
        """从文件加载模型。"""
        if not JOBLIB_AVAILABLE:
            raise ImportError("需要 joblib")
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"模型文件不存在: {filepath}")

        data = joblib.load(filepath)
        self.pipeline = data['pipeline']
        self.classes_ = data['classes_']
        self.n_features_ = data['n_features_']
        self.best_params_ = data.get('best_params_')
        self.is_fitted = True
        config = data.get('config', {})
        self.kernel = config.get('kernel', self.kernel)
        self.C = config.get('C', self.C)
        self.gamma = config.get('gamma', self.gamma)
        logger.info(f"模型已加载: {filepath}")
        return self

    def get_support_vectors_info(self) -> dict:
        """获取支持向量信息。"""
        self._check_fitted()
        svm = self.pipeline.named_steps['svm']
        return {
            'n_support': svm.n_support_.tolist(),
            'n_total_sv': sum(svm.n_support_),
            'classes': self.classes_.tolist(),
        }

    def _check_fitted(self):
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练，请先调用 fit()")

    def __repr__(self):
        status = "已训练" if self.is_fitted else "未训练"
        return f"SVMDecoder(kernel='{self.kernel}', C={self.C}, status={status})"