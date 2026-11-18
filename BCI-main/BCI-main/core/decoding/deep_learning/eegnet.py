# -*- coding: utf-8 -*-
"""
EEGNet - 端到端 EEG 深度学习分类模型
===================================================
基于 Lawhern et al. (2018) 的 EEGNet 架构实现。

架构:
    时间卷积 -> 深度卷积(逐通道) -> 可分离卷积 -> 全连接分类

功能:
    1. 模型构建（可配置 F1/F2/D/dropout）
    2. 训练（含早停、学习率调度）
    3. 预测（标签 + 概率）
    4. 模型保存/加载
    5. 与 decoding_stats 集成评估

依赖:
    - 必需: numpy
    - 可选: torch (PyTorch), scikit-learn

参考:
    Lawhern et al. "EEGNet: A Compact Convolutional Neural Network for
    EEG-based Brain-Computer Interfaces" (2018) J. Neural Eng.
"""

import numpy as np
import warnings
import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except (ImportError, OSError) as e:
    TORCH_AVAILABLE = False
    warnings.warn(f"PyTorch 不可用，EEGNet 已禁用: {e}")
    # 占位，使类定义不崩溃
    class _ModulePlaceholder:
        def __init__(self, *a, **kw): pass
    class _NNPlaceholder:
        Module = _ModulePlaceholder
        Sequential = list
        Conv2d = _ModulePlaceholder
        BatchNorm2d = _ModulePlaceholder
        ELU = _ModulePlaceholder
        AvgPool2d = _ModulePlaceholder
        Dropout = _ModulePlaceholder
        Linear = _ModulePlaceholder
        Flatten = _ModulePlaceholder
    nn = _NNPlaceholder()
    import types
    torch = types.ModuleType('torch')
    optim = None
    DataLoader = None
    TensorDataset = None

try:
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class _EEGNetModule(nn.Module):
    """EEGNet PyTorch 模块。"""

    def __init__(self, n_channels: int, n_samples: int, n_classes: int,
                 F1: int = 8, F2: int = 16, D: int = 2,
                 dropout_rate: float = 0.5):
        super().__init__()

        self.n_channels = n_channels
        self.n_samples = n_samples
        self.n_classes = n_classes

        # Block 1: 时间卷积 + 深度卷积
        self.block1 = nn.Sequential(
            # 时间卷积: (1, n_channels, n_samples) -> (F1, n_channels, n_samples)
            nn.Conv2d(1, F1, (1, 64), padding=(0, 32), bias=False),
            nn.BatchNorm2d(F1),
            # 深度卷积 (逐通道): (F1, n_channels, n_samples) -> (F1*D, 1, n_samples)
            nn.Conv2d(F1, F1 * D, (n_channels, 1), groups=F1, bias=False),
            nn.BatchNorm2d(F1 * D),
            nn.ELU(),
            nn.AvgPool2d((1, 4)),
            nn.Dropout(dropout_rate)
        )

        # Block 2: 可分离卷积
        self.block2 = nn.Sequential(
            # 深度可分离卷积
            nn.Conv2d(F1 * D, F1 * D, (1, 16), padding=(0, 8),
                      groups=F1 * D, bias=False),
            nn.Conv2d(F1 * D, F2, (1, 1), bias=False),
            nn.BatchNorm2d(F2),
            nn.ELU(),
            nn.AvgPool2d((1, 8)),
            nn.Dropout(dropout_rate)
        )

        # 计算展平后的特征维度
        self._flat_features = self._get_flat_features(n_channels, n_samples)

        # 分类器
        self.classifier = nn.Linear(self._flat_features, n_classes)

    def _get_flat_features(self, n_channels, n_samples):
        """计算卷积输出的展平维度。"""
        x = torch.zeros(1, 1, n_channels, n_samples)
        x = self.block1(x)
        x = self.block2(x)
        return x.view(1, -1).size(1)

    def forward(self, x):
        """
        前向传播。

        Parameters
        ----------
        x : Tensor, shape (batch, 1, n_channels, n_samples)
        """
        x = self.block1(x)
        x = self.block2(x)
        x = x.view(x.size(0), -1)
        return self.classifier(x)

    def get_features(self, x):
        """提取深度特征（分类层之前）。"""
        x = self.block1(x)
        x = self.block2(x)
        return x.view(x.size(0), -1)


class EEGNetDecoder:
    """
    EEGNet 解码器 - 端到端 EEG 分类。

    Parameters
    ----------
    n_channels : int
        EEG 通道数
    n_samples : int
        每个 trial 的采样点数
    n_classes : int
        分类类别数
    F1, F2, D : int
        EEGNet 超参数
    dropout_rate : float
        Dropout 比率
    learning_rate : float
        学习率
    batch_size : int
        批大小
    epochs : int
        最大训练轮数
    patience : int
        早停耐心值
    device : str
        'cuda' 或 'cpu'
    """

    def __init__(self, n_channels: int = 32, n_samples: int = 128,
                 n_classes: int = 2, F1: int = 8, F2: int = 16,
                 D: int = 2, dropout_rate: float = 0.5,
                 learning_rate: float = 0.001, batch_size: int = 32,
                 epochs: int = 200, patience: int = 20,
                 device: str = 'auto'):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch 未安装")

        self.n_channels = n_channels
        self.n_samples = n_samples
        self.n_classes = n_classes
        self.F1 = F1
        self.F2 = F2
        self.D = D
        self.dropout_rate = dropout_rate
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.epochs = epochs
        self.patience = patience

        if device == 'auto':
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = torch.device(device)

        self.model = None
        self.is_fitted = False
        self.classes_ = None
        self.train_history = {'loss': [], 'val_loss': [], 'accuracy': []}
        self._scaler = StandardScaler() if SKLEARN_AVAILABLE else None

    def _build_model(self):
        """构建 EEGNet 模型。"""
        self.model = _EEGNetModule(
            n_channels=self.n_channels,
            n_samples=self.n_samples,
            n_classes=self.n_classes,
            F1=self.F1, F2=self.F2, D=self.D,
            dropout_rate=self.dropout_rate
        ).to(self.device)
        return self.model

    def _prepare_data(self, X: np.ndarray, y: np.ndarray = None,
                      fit_scaler: bool = False):
        """
        准备 PyTorch 数据。

        Parameters
        ----------
        X : ndarray, shape (n_trials, n_channels, n_samples)
            或 (n_trials, n_features) 的 2D 特征矩阵
        y : ndarray, optional
        fit_scaler : bool
            是否 fit 标准化器
        """
        X = np.array(X, dtype=np.float32)

        # 如果是 2D (n_trials, n_features)，尝试重塑
        if X.ndim == 2:
            n_trials = X.shape[0]
            if X.shape[1] == self.n_channels * self.n_samples:
                X = X.reshape(n_trials, self.n_channels, self.n_samples)
            else:
                raise ValueError(
                    f"2D 输入 shape {X.shape}，无法重塑为 "
                    f"({n_trials}, {self.n_channels}, {self.n_samples})"
                )

        if X.ndim == 3:
            X = X[:, np.newaxis, :, :]  # (batch, 1, channels, samples)

        X_tensor = torch.FloatTensor(X).to(self.device)

        if y is not None:
            y = np.array(y)
            y_tensor = torch.LongTensor(y).to(self.device)
            return X_tensor, y_tensor

        return X_tensor

    def fit(self, X: np.ndarray, y: np.ndarray,
            X_val: np.ndarray = None, y_val: np.ndarray = None,
            verbose: bool = True) -> 'EEGNetDecoder':
        """
        训练 EEGNet 模型。

        Parameters
        ----------
        X : ndarray, shape (n_trials, n_channels, n_samples)
        y : ndarray, shape (n_trials,)
        X_val, y_val : ndarray, optional
            验证集（用于早停）
        verbose : bool
            是否打印训练进度
        """
        X_t, y_t = self._prepare_data(X, y, fit_scaler=True)
        self.classes_ = np.unique(y)

        # 自动推断维度
        if X_t.dim() == 4:
            self.n_channels = X_t.shape[2]
            self.n_samples = X_t.shape[3]

        self._build_model()

        # 类别权重（处理不平衡）
        class_counts = np.bincount(y)
        weights = 1.0 / (class_counts + 1e-6)
        weights = weights / weights.sum() * len(weights)
        class_weights = torch.FloatTensor(weights).to(self.device)

        criterion = nn.CrossEntropyLoss(weight=class_weights)
        optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=self.patience // 3
        )

        dataset = TensorDataset(X_t, y_t)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        # 验证集
        has_val = X_val is not None and y_val is not None
        if has_val:
            X_v, y_v = self._prepare_data(X_val, y_val)

        best_val_loss = float('inf')
        best_state = None
        patience_counter = 0

        self.train_history = {'loss': [], 'val_loss': [], 'accuracy': []}

        for epoch in range(self.epochs):
            # 训练
            self.model.train()
            epoch_loss = 0
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                outputs = self.model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()

            avg_loss = epoch_loss / len(loader)
            self.train_history['loss'].append(avg_loss)

            # 验证
            if has_val:
                self.model.eval()
                with torch.no_grad():
                    val_out = self.model(X_v)
                    val_loss = criterion(val_out, y_v).item()
                    val_pred = val_out.argmax(dim=1).cpu().numpy()
                    val_acc = np.mean(val_pred == y_val)

                self.train_history['val_loss'].append(val_loss)
                self.train_history['accuracy'].append(val_acc)
                scheduler.step(val_loss)

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    best_state = {k: v.clone() for k, v in self.model.state_dict().items()}
                    patience_counter = 0
                else:
                    patience_counter += 1

                if patience_counter >= self.patience:
                    if verbose:
                        logger.info(f"早停于 epoch {epoch+1}")
                    break

                if verbose and (epoch + 1) % 10 == 0:
                    logger.info(f"Epoch {epoch+1}/{self.epochs} - "
                                f"loss: {avg_loss:.4f} - val_loss: {val_loss:.4f} - "
                                f"val_acc: {val_acc:.4f}")
            else:
                if verbose and (epoch + 1) % 10 == 0:
                    logger.info(f"Epoch {epoch+1}/{self.epochs} - loss: {avg_loss:.4f}")

        # 恢复最佳模型
        if best_state is not None:
            self.model.load_state_dict(best_state)

        self.is_fitted = True
        logger.info(f"EEGNet 训练完成: {len(y)} 样本, {len(self.classes_)} 类别")
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测标签。"""
        self._check_fitted()
        X_t = self._prepare_data(X)
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(X_t)
            return outputs.argmax(dim=1).cpu().numpy()

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测概率分布。"""
        self._check_fitted()
        X_t = self._prepare_data(X)
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(X_t)
            return torch.softmax(outputs, dim=1).cpu().numpy()

    def evaluate(self, X: np.ndarray, y: np.ndarray,
                 trial_time: float = 4.0) -> dict:
        """评估模型，返回分类指标 + ITR。"""
        from core.processing.Statistical_Analysis.decoding_stats import (
            classification_metrics, information_transfer_rate
        )
        y_pred = self.predict(X)
        y_score = None
        if len(self.classes_) == 2:
            y_score = self.predict_proba(X)[:, 1]

        metrics = classification_metrics(y, y_pred, y_score)
        n_classes = len(self.classes_)
        metrics['itr'] = information_transfer_rate(
            metrics['accuracy'], n_classes, trial_time
        )
        metrics['n_classes'] = n_classes
        metrics['model_type'] = 'EEGNet'
        metrics['train_history'] = self.train_history
        return metrics

    def extract_features(self, X: np.ndarray) -> np.ndarray:
        """提取 EEGNet 深度特征（分类层之前的激活）。"""
        self._check_fitted()
        X_t = self._prepare_data(X)
        self.model.eval()
        with torch.no_grad():
            return self.model.get_features(X_t).cpu().numpy()

    def save(self, filepath: str):
        """保存模型。"""
        self._check_fitted()
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        torch.save({
            'model_state': self.model.state_dict(),
            'classes_': self.classes_,
            'config': {
                'n_channels': self.n_channels, 'n_samples': self.n_samples,
                'n_classes': self.n_classes, 'F1': self.F1, 'F2': self.F2,
                'D': self.D, 'dropout_rate': self.dropout_rate,
            },
            'train_history': self.train_history,
        }, filepath)
        logger.info(f"EEGNet 已保存: {filepath}")

    def load(self, filepath: str) -> 'EEGNetDecoder':
        """加载模型。"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"模型文件不存在: {filepath}")
        checkpoint = torch.load(filepath, map_location=self.device, weights_only=False)
        config = checkpoint['config']
        self.n_channels = config['n_channels']
        self.n_samples = config['n_samples']
        self.n_classes = config['n_classes']
        self.F1 = config['F1']
        self.F2 = config['F2']
        self.D = config['D']
        self.dropout_rate = config['dropout_rate']
        self.classes_ = checkpoint['classes_']
        self.train_history = checkpoint.get('train_history', {})

        self._build_model()
        self.model.load_state_dict(checkpoint['model_state'])
        self.is_fitted = True
        logger.info(f"EEGNet 已加载: {filepath}")
        return self

    def _check_fitted(self):
        if not self.is_fitted or self.model is None:
            raise RuntimeError("模型尚未训练，请先调用 fit()")

    def __repr__(self):
        status = "已训练" if self.is_fitted else "未训练"
        return (f"EEGNetDecoder(ch={self.n_channels}, samples={self.n_samples}, "
                f"classes={self.n_classes}, status={status})")