from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.infrastructure.config import Settings
from backend.app.adapters.providers import DemoProvider
from test_workspace_api import ready, submit


def test_history_display_codes_use_bound_input_version(tmp_path):
    app = create_app(Settings(storage_dir=tmp_path / 'store'), start_worker=False)
    with TestClient(app) as client:
        dataset = ready(client)
        job = submit(client, dataset).json()
        _, context = app.state.executor._claim()
        app.state.executor._commit(job['id'], output=DemoProvider().assess(context))
        result_id = client.get(f"/api/v1/jobs/{job['id']}").json()['assessment_id']
        report = client.post(f'/api/v1/assessments/{result_id}/reports', json={'format': 'json', 'expected_revision': 0}).json()
        response = client.patch(f"/api/v1/datasets/{dataset['id']}/metadata", json={'expected_version': dataset['version'], 'metadata': {'display_code': 'NEW-CODE'}})
        assert response.status_code == 200
        assert response.json()['metadata']['display_code'] == 'NEW-CODE'
        for uri in (f"/api/v1/jobs/{job['id']}", f'/api/v1/assessments/{result_id}', f"/api/v1/reports/{report['id']}"):
            assert client.get(uri).json()['display_code'] == 'SYN-001'
        assert client.get('/api/v1/jobs').json()[0]['display_code'] == 'SYN-001'
        assert client.get('/api/v1/assessments').json()[0]['display_code'] == 'SYN-001'
        assert client.get('/api/v1/reports').json()[0]['display_code'] == 'SYN-001'
