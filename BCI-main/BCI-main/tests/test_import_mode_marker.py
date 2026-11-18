import io
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.infrastructure.config import Settings


@pytest.mark.parametrize('format', ['json', 'npz'])
def test_explicit_file_demo_marker_cannot_be_imported_real(tmp_path, format):
    document = {'metadata': {}, 'data_mode': 'demo'}
    if format == 'json':
        payload = json.dumps({**document, 'data': [[1, 2]]}).encode()
    else:
        buffer = io.BytesIO()
        np.savez(buffer, data=np.array([[1, 2]]), metadata=np.array(json.dumps(document)))
        payload = buffer.getvalue()
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'data'), start_worker=False)) as client:
        response = client.post('/api/v1/datasets/import', files={'file': ('sample.' + format, payload)}, data={'data_mode': 'real'})
        assert response.status_code == 422
        assert response.json()['code'] == 'mode_conflict'
