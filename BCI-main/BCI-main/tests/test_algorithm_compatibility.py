"""冻结源码与固定信号兼容验证；不训练模型，不验证真实筛查效度。"""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT.parents[2] / 'review_artifacts/migration-2026-11-14'


def test_frozen_algorithm_sources_have_identical_hashes():
    baseline = json.loads((EVIDENCE / 'baseline.json').read_text(encoding='utf-8'))
    frozen = [item for item in baseline if item['path'].startswith(('core/decoding/', 'core/processing/'))]
    assert len(frozen) >= 35
    changed = [item['path'] for item in frozen if hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest() != item['sha256']]
    assert changed == []


def test_fixed_eeg_features_equal_original_source_output():
    from core.processing.feature_extraction.eeg_features import EEGFeatureExtractor
    times = np.arange(512, dtype=np.float64) / 128
    values = np.stack([12 * np.sin(2 * np.pi * 10 * times), 8 * np.sin(2 * np.pi * 6 * times + 0.3)])
    baseline = json.loads((EVIDENCE / 'algorithm-baseline.json').read_text(encoding='utf-8'))
    actual = EEGFeatureExtractor(128, ['F3', 'F4']).extract_band_powers(values)
    assert set(actual) == set(baseline)
    np.testing.assert_array_equal([actual[key] for key in sorted(actual)], [baseline[key] for key in sorted(baseline)])
