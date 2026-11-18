import json
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.infrastructure.config import Settings


def test_legacy_json_declared_dtype_size_cannot_bypass_array_limit(tmp_path):
    document = {'format': 'bci-data-dict', 'version': 2, 'payload': {
        'meta': {}, 'signal': {'EEG': {'data': {'__ndarray__': True, 'dtype': '(1000000,)f8', 'shape': [1, 1], 'values': [[1]]},
                                      'sampling_rate': 128, 'channel_names': ['F3'], 'unit': 'uV'}}, 'event': {}, 'processed': {}}}
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'storage', max_array_elements=64), start_worker=False)) as client:
        response = client.post('/api/v1/datasets/import', files={'file': ('bad.json', json.dumps(document).encode())})
        assert response.status_code == 413
        assert response.json()['code'] == 'upload_limit'
