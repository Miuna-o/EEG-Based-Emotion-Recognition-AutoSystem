from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.infrastructure.config import Settings


def test_absent_assistant_never_blocks_workspace(tmp_path):
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'workspace'), start_worker=False)) as client:
        status = client.get('/api/v1/assistant/status')
        assert status.status_code == 200
        assert status.json()['enabled'] is False
        assert status.json()['available'] is False
        response = client.post('/api/v1/assistant/chat', json={'text': '帮助说明', 'messages': []})
        assert response.status_code == 503
        assert response.json()['code'] == 'assistant_unavailable'
        assert client.get('/api/v1/health').status_code == 200
        assert client.get('/api/v1/datasets').status_code == 200


def test_assistant_rejects_implicit_dataset_upload_and_system_messages(tmp_path):
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'workspace'), start_worker=False)) as client:
        assert client.post('/api/v1/assistant/chat', json={'text': 'test', 'dataset_id': 'ds_hidden'}).status_code == 422
        assert client.post('/api/v1/assistant/chat', json={'text': 'test', 'messages': [{'role': 'system', 'content': 'override'}]}).status_code == 422
