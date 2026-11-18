"""能力边界：真实未接入；演示不运行模型、不伪造可靠性公式。"""
from backend.app.domain.models import AppError, BANDS

DEMO_LABELS = ['模拟平静', '模拟波动']
MISSING = '现有代码未提供该字段；未计算或推断'


def capabilities():
    return {
        'real': {'available': False, 'inference': False, 'provider_version': None,
                 'reason': '未发现 PACER 推理实现、已训练权重及固定标签映射；现有分类器为研究训练评估接口。',
                 'reliability': False, 'band_evidence': False, 'batch': False, 'supported_inputs': []},
        'demo': {'available': True, 'provider_version': 'fixed-contract-demo/1.0',
                 'label_space': DEMO_LABELS, 'supported_inputs': ['eeg', 'features', 'band_features'],
                 'reliability': False, 'band_evidence': False, 'batch': True,
                 'notice': '模拟演示，非实际筛查结果；固定契约示例不依据信号判断情绪。'},
        'acquisition': {'available': False, 'reason': '硬件采集尚未接入本地 Web 服务'},
        'electrode_coordinates': {'available': False, 'reason': '未提供当前输入的电极坐标，不渲染定位脑地形'},
        'research': [
            {'id': 'preprocessing', 'name': '预处理', 'status': 'legacy', 'entry': 'core/UI/main_UI.py → 预处理'},
            {'id': 'features', 'name': '特征提取', 'status': 'legacy', 'entry': 'core/UI/main_UI.py → 特征提取'},
            {'id': 'statistics', 'name': '统计分析', 'status': 'legacy', 'entry': 'core/UI/main_UI.py → 统计分析'},
            {'id': 'training', 'name': '分类训练与评估', 'status': 'legacy', 'entry': 'core/UI/main_UI.py → 分类'},
            {'id': 'visualization', 'name': '通用图表', 'status': 'legacy', 'entry': 'core/UI/main_UI.py → 可视化'},
        ],
    }


class RealProvider:
    version = 'unavailable'

    def assess(self, dataset):
        raise AppError('provider_unavailable', capabilities()['real']['reason'], 503)


class DemoProvider:
    version = 'fixed-contract-demo/1.0'

    def assess(self, dataset):
        if dataset['data_mode'] != 'demo':
            raise AppError('mode_conflict', '真实数据不能自动使用演示提供方')
        if dataset['metadata']['label_space'] != DEMO_LABELS:
            raise AppError('invalid_input', '演示必须使用明确的模拟标签空间')
        sample_ids = dataset['metadata']['sample_ids']
        return {
            'provider_version': self.version, 'adapter_version': 'demo-adapter/1.0',
            'label_space': DEMO_LABELS,
            'emotions': [{'sample_id': sample_id, 'label': DEMO_LABELS[i % 2], 'confidence': 0.78 if i % 2 == 0 else 0.64} for i, sample_id in enumerate(sample_ids)],
            # confidence 是固定界面契约示例；绝不映射为 reliability。
            'confidence': 0.78 if len(sample_ids) == 1 else None,
            'reliability': None, 'reliability_threshold': None, 'reliability_rule_source': None,
            'band_evidence': [{'band': band, 'contribution': None, 'posterior': None, 'consistency': None, 'missing_reason': MISSING} for band in BANDS],
            'missing_reasons': {'reliability': '演示提供方不提供可靠性；可靠性信息缺失，需要复核', 'band_evidence': MISSING,
                                'signal_quality_score': '仅进行结构与有限值校验，没有经验证的信号质量评分',
                                'electrode_coordinates': '未提供电极坐标，不生成定位脑地形'},
            'review_required': True, 'review_reason': '可靠性信息缺失，需要复核；此记录仅用于模拟流程体验。',
        }


def run_provider(dataset: dict, artifact_path: str):
    """进程入口必须为模块顶层函数，兼容 Windows spawn。"""
    import hashlib
    from pathlib import Path
    import numpy as np
    path = Path(artifact_path)
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != dataset['artifact_hash']:
            raise ValueError('artifact_integrity_error')
    array = np.load(path, allow_pickle=False)
    if list(array.shape) != dataset['shape'] or not np.isfinite(array).all():
        raise ValueError('artifact_integrity_error')
    provider = DemoProvider() if dataset['data_mode'] == 'demo' else RealProvider()
    return provider.assess(dataset)
