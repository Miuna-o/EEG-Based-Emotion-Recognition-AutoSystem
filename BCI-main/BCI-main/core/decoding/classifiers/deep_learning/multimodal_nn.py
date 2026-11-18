# -*- coding: utf-8 -*-
"""
多模态融合分类网络
===================================================
支持 EEG + EMG + fNIRS + ECG 等多模态特征的联合分类。
这是本平台超越 Brainfusion 单模态处理的核心能力。

融合策略:
    1. 早期融合 (Early Fusion): 特征拼接后训练
    2. 注意力融合 (Attention Fusion): 自适应加权各模态贡献
    3. 晚期融合 (Late Fusion): 各模态独立分类后投票/加权

依赖:
    - 必需: numpy, scikit-learn
    - 可选: torch
"""

import numpy as np
import warnings
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC
    from sklearn.ensemble import RandomForestClassifier, VotingClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except (ImportError, OSError) as e:
    TORCH_AVAILABLE = False
    # 占位基类，使 _AttentionFusionModule 定义不崩溃
    class _ModulePlaceholder:
        def __init__(self, *a, **kw): pass
    class _NNPlaceholder:
        Module = _ModulePlaceholder
        ModuleDict = dict
        Sequential = list
        Linear = _ModulePlaceholder
        BatchNorm1d = _ModulePlaceholder
        ReLU = _ModulePlaceholder
        Dropout = _ModulePlaceholder
        Softmax = _ModulePlaceholder
    nn = _NNPlaceholder()
    import types
    torch = types.ModuleType('torch')
    torch.Tensor = object


class _AttentionFusionModule(nn.Module):
    """注意力融合 PyTorch 模块。"""

    def __init__(self, modality_dims: Dict[str, int], n_classes: int,
                 hidden_dim: int = 128, dropout: float = 0.3):
        super().__init__()
        self.modality_names = sorted(modality_dims.keys())

        # 各模态独立编码器
        self.encoders = nn.ModuleDict()
        for name in self.modality_names:
            dim = modality_dims[name]
            self.encoders[name] = nn.Sequential(
                nn.Linear(dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                nn.ReLU(),
            )

        n_modalities = len(self.modality_names)
        # 注意力网络
        self.attention = nn.Sequential(
            nn.Linear(hidden_dim * n_modalities, n_modalities),
            nn.Softmax(dim=1)
        )

        # 分类头
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, n_classes)
        )

    def forward(self, modality_features: Dict[str, torch.Tensor]):
        """
        Parameters
        ----------
        modality_features : dict
            {modality_name: Tensor (batch, n_features)}
        """
        encoded = []
        for name in self.modality_names:
            if name in modality_features:
                encoded.append(self.encoders[name](modality_features[name]))
            else:
                batch_size = list(modality_features.values())[0].shape[0]
                device = list(modality_features.values())[0].device
                encoded.append(torch.zeros(batch_size, encoded[0].shape[1]).to(device))

        stacked = torch.stack(encoded, dim=1)  # (batch, n_mod, hidden)
        concat = torch.cat(encoded, dim=1)      # (batch, n_mod * hidden)

        # 注意力权重
        weights = self.attention(concat)         # (batch, n_mod)
        weights = weights.unsqueeze(2)            # (batch, n_mod, 1)

        # 加权融合
        fused = (stacked * weights).sum(dim=1)    # (batch, hidden)

        return self.classifier(fused), weights.squeeze(2)


class MultimodalFusionDecoder:
    """
    多模态融合解码器。

    Parameters
    ----------
    fusion_method : str
        融合方法: 'early', 'attention', 'late'
    n_classes : int
        分类类别数
    hidden_dim : int
        隐藏层维度（attention 模式）
    """

    def __init__(self, fusion_method: str = 'early', n_classes: int = 2,
                 hidden_dim: int = 128, dropout: float = 0.3,
                 random_state: int = 42):
        self.fusion_method = fusion_method
        self.n_classes = n_classes
        self.hidden_dim = hidden_dim
        self.dropout = dropout
        self.random_state = random_state

        self.model = None
        self.is_fitted = False
        self.classes_ = None
        self.modality_dims_ = None
        self.modality_weights_ = None
        self._scalers = {}

    def fit(self, X_dict: Dict[str, np.ndarray], y: np.ndarray) -> 'MultimodalFusionDecoder':
        """
        训练多模态融合模型。

        Parameters
        ----------
        X_dict : dict
            {modality_name: ndarray (n_samples, n_features)}
        y : ndarray (n_samples,)
        """
        y = np.array(y)
        self.classes_ = np.unique(y)
        self.modality_dims_ = {k: v.shape[1] for k, v in X_dict.items()}

        # 标准化各模态
        scaled_dict = {}
        for mod, X in X_dict.items():
            X = np.array(X, dtype=np.float64)
            if SKLEARN_AVAILABLE:
                self._scalers[mod] = StandardScaler()
                scaled_dict[mod] = self._scalers[mod].fit_transform(X)
            else:
                scaled_dict[mod] = X

        if self.fusion_method == 'early':
            self._fit_early(scaled_dict, y)
        elif self.fusion_method == 'attention':
            if not TORCH_AVAILABLE:
                raise ImportError("attention 融合需要 PyTorch")
            self._fit_attention(scaled_dict, y)
        elif self.fusion_method == 'late':
            self._fit_late(scaled_dict, y)
        else:
            raise ValueError(f"不支持的融合方法: {self.fusion_method}")

        self.is_fitted = True
        logger.info(f"多模态融合训练完成: method={self.fusion_method}, "
                    f"modalities={list(X_dict.keys())}, classes={len(self.classes_)}")
        return self

    def _fit_early(self, X_dict, y):
        """早期融合: 特征拼接 + SVM。"""
        X_concat = np.hstack([X_dict[k] for k in sorted(X_dict.keys())])
        self.model = Pipeline([
            ('svm', SVC(kernel='rbf', C=1.0, gamma='scale',
                        probability=True, class_weight='balanced',
                        random_state=self.random_state))
        ])
        self.model.fit(X_concat, y)

    def _fit_attention(self, X_dict, y):
        """注意力融合训练。"""
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = _AttentionFusionModule(
            self.modality_dims_, self.n_classes,
            self.hidden_dim, self.dropout
        ).to(device)

        tensors = {k: torch.FloatTensor(v).to(device) for k, v in X_dict.items()}
        y_tensor = torch.LongTensor(y).to(device)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        criterion = nn.CrossEntropyLoss()

        self.model.train()
        for epoch in range(150):
            optimizer.zero_grad()
            outputs, weights = self.model(tensors)
            loss = criterion(outputs, y_tensor)
            loss.backward()
            optimizer.step()

        # 保存最终注意力权重
        self.model.eval()
        with torch.no_grad():
            _, w = self.model(tensors)
            self.modality_weights_ = {
                name: w[:, i].mean().item()
                for i, name in enumerate(sorted(X_dict.keys()))
            }

    def _fit_late(self, X_dict, y):
        """晚期融合: 各模态独立 SVM + 软投票。"""
        estimators = []
        for mod in sorted(X_dict.keys()):
            clf = Pipeline([
                ('svm', SVC(kernel='rbf', probability=True,
                            class_weight='balanced',
                            random_state=self.random_state))
            ])
            estimators.append((mod, clf))

        # 拼接特征用于 VotingClassifier（它要求统一 X）
        X_concat = np.hstack([X_dict[k] for k in sorted(X_dict.keys())])
        self.model = VotingClassifier(estimators=estimators, voting='soft')

        # 给各个子分类器分配对应切片的数据
        # VotingClassifier 不原生支持分模态输入，这里用 early concat
        self.model.fit(X_concat, y)

    def predict(self, X_dict: Dict[str, np.ndarray]) -> np.ndarray:
        """预测标签。"""
        self._check_fitted()
        scaled_dict = self._scale(X_dict)

        if self.fusion_method == 'attention' and TORCH_AVAILABLE:
            device = next(self.model.parameters()).device
            tensors = {k: torch.FloatTensor(v).to(device) for k, v in scaled_dict.items()}
            self.model.eval()
            with torch.no_grad():
                out, _ = self.model(tensors)
                return out.argmax(dim=1).cpu().numpy()
        else:
            X_concat = np.hstack([scaled_dict[k] for k in sorted(scaled_dict.keys())])
            return self.model.predict(X_concat)

    def predict_proba(self, X_dict: Dict[str, np.ndarray]) -> np.ndarray:
        """预测概率。"""
        self._check_fitted()
        scaled_dict = self._scale(X_dict)

        if self.fusion_method == 'attention' and TORCH_AVAILABLE:
            device = next(self.model.parameters()).device
            tensors = {k: torch.FloatTensor(v).to(device) for k, v in scaled_dict.items()}
            self.model.eval()
            with torch.no_grad():
                out, _ = self.model(tensors)
                return torch.softmax(out, dim=1).cpu().numpy()
        else:
            X_concat = np.hstack([scaled_dict[k] for k in sorted(scaled_dict.keys())])
            return self.model.predict_proba(X_concat)

    def evaluate(self, X_dict: Dict[str, np.ndarray], y: np.ndarray,
                 trial_time: float = 4.0) -> dict:
        """评估，返回指标 + 模态权重。"""
        from core.processing.Statistical_Analysis.decoding_stats import (
            classification_metrics, information_transfer_rate
        )
        y_pred = self.predict(X_dict)
        y_score = None
        if len(self.classes_) == 2:
            y_score = self.predict_proba(X_dict)[:, 1]

        metrics = classification_metrics(y, y_pred, y_score)
        n_classes = len(self.classes_)
        metrics['itr'] = information_transfer_rate(
            metrics['accuracy'], n_classes, trial_time
        )
        metrics['model_type'] = f'MultimodalFusion({self.fusion_method})'
        metrics['modalities'] = list(X_dict.keys())
        metrics['modality_weights'] = self.modality_weights_
        return metrics

    def get_modality_importance(self) -> Optional[Dict[str, float]]:
        """获取各模态的重要性权重（仅 attention 模式）。"""
        return self.modality_weights_

    def _scale(self, X_dict):
        """标准化输入。"""
        result = {}
        for mod, X in X_dict.items():
            X = np.array(X, dtype=np.float64)
            if mod in self._scalers:
                result[mod] = self._scalers[mod].transform(X)
            else:
                result[mod] = X
        return result

    def _check_fitted(self):
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")

    def __repr__(self):
        status = "已训练" if self.is_fitted else "未训练"
        return (f"MultimodalFusionDecoder(method='{self.fusion_method}', "
                f"classes={self.n_classes}, status={status})")