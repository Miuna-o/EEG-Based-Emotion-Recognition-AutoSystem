import hashlib
import io
import json

from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
from pypdf import PdfReader

from backend.app.main import create_app
from backend.app.infrastructure.config import Settings
from core.io.data_io import DataDictBuilder, DataSaver
from test_workspace_api import assessment


def test_pdf_is_real_chinese_document_and_demo_watermark(tmp_path):
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'pdf'))) as client:
        _, result = assessment(client)
        response = client.post(f"/api/v1/assessments/{result['id']}/reports", json={'format': 'pdf', 'expected_revision': 0})
        assert response.status_code == 201, response.text
        downloaded = client.get(f"/api/v1/reports/{response.json()['id']}/download")
        assert downloaded.content.startswith(b'%PDF-')
        document = PdfReader(io.BytesIO(downloaded.content))
        texts = [page.extract_text() for page in document.pages]
        assert all('模拟演示，非实际筛查结果' in text for text in texts)
        assert '可靠性信息缺失' in ''.join(texts)
        assert '草稿' in ''.join(texts)
        assert result['input_hash'] in ''.join(texts).replace('\n', '')


def test_safe_legacy_npz_import_preserves_original_and_metadata(tmp_path):
    data = DataDictBuilder.create_empty_data_dict()
    DataDictBuilder.add_signal(data, np.arange(64).reshape(2, 32), 128, ['F3', 'F4'], 'EEG', unit='uV')
    DataDictBuilder.add_event(data, 'synthetic-event', 0.05)
    path = tmp_path / 'legacy-safe.npz'
    DataSaver.save(data, str(path), 'npz')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'data'), start_worker=False)) as client:
        response = client.post('/api/v1/datasets/import', files={'file': ('safe.npz', path.read_bytes())})
        assert response.status_code == 201, response.text
        dataset = response.json()
        assert dataset['metadata']['sampling_rate'] == 128
        assert dataset['metadata']['channels'] == ['F3', 'F4']
        assert dataset['provenance']['event'] == data['event']
        assert dataset['validation_status'] == 'draft'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_excel_import_does_not_write_source_folder(tmp_path):
    excel = tmp_path / 'same.xlsx'
    sentinel = tmp_path / 'same.csv'
    pd.DataFrame({'F3': [1.0, 2.0], 'F4': [3.0, 4.0]}).to_excel(excel, index=False)
    sentinel.write_bytes(b'UNCHANGED')
    original = excel.read_bytes()
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'storage'), start_worker=False)) as client:
        response = client.post('/api/v1/datasets/import', files={'file': ('same.xlsx', original)})
        assert response.status_code == 201
        assert response.json()['metadata']['sampling_rate'] is None
    assert sentinel.read_bytes() == b'UNCHANGED'
    assert excel.read_bytes() == original


def test_preview_preserves_peak_and_original_artifact(tmp_path):
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'storage', preview_points=100), start_worker=False)) as client:
        data = np.zeros((1, 2000))
        data[0, 457] = 987
        data[0, 458] = -765
        buf = io.BytesIO()
        np.save(buf, data, allow_pickle=False)
        dataset = client.post('/api/v1/datasets/import', files={'file': ('peak.npy', buf.getvalue())}).json()
        updated = client.patch(f"/api/v1/datasets/{dataset['id']}/metadata", json={'expected_version': 1, 'metadata': {
            'kind': 'eeg', 'modality': 'EEG', 'axes': ['channel', 'time'], 'sampling_rate': 128, 'unit': 'uV', 'channels': ['F3']}}).json()
        preview = client.get(f"/api/v1/datasets/{dataset['id']}/preview").json()
        points = preview['series'][0]['points']
        assert [457 / 128, 987] in points
        assert [458 / 128, -765] in points
        assert len(points) <= 100
        assert preview['sample_count'] == 2000
        assert preview['channel_count'] == 1
        assert np.isclose(preview['series'][0]['rms'], ((987**2 + 765**2) / 2000)**0.5)
        assert updated['source_hash'] == dataset['source_hash']

