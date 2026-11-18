from concurrent.futures.process import BrokenProcessPool
import io
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from backend.app.main import create_app
from backend.app.infrastructure.config import Settings
from test_workspace_api import ready, submit, assessment


def test_broken_pool_submission_ends_claimed_job(tmp_path):
    app = create_app(Settings(storage_dir=tmp_path / 'data'), start_worker=False)
    with TestClient(app) as client:
        dataset = ready(client)
        job = submit(client, dataset).json()
        executor = app.state.executor
        class BrokenPool:
            def submit(self, *args):
                executor.stop_event.set()
                raise BrokenProcessPool('synthetic failure')
            def shutdown(self, **kwargs):
                pass
        executor.pool = BrokenPool()
        executor._dispatch()
        result = client.get(f"/api/v1/jobs/{job['id']}").json()
        assert result['status'] == 'failed'
        assert result['error_code'] == 'worker_interrupted'
        assert client.post(f"/api/v1/jobs/{job['id']}/cancel").json()['status'] == 'failed'


def test_stale_report_requires_explicit_historical_archive(tmp_path):
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'data'))) as client:
        _, result = assessment(client)
        uri = f"/api/v1/assessments/{result['id']}"
        report = client.post(uri + '/reports', json={'format': 'json', 'expected_revision': 0}).json()
        original = client.get(f"/api/v1/reports/{report['id']}/download").content
        client.post(uri + '/reviews', json={'expected_revision': 0, 'reviewer': 'R01', 'status': 'reviewed', 'opinion': '固定测试', 'idempotency_key': 'new'})
        listed = client.get('/api/v1/reports').json()[0]
        assert listed['stale'] is True and listed['current_review_revision'] == 1
        assert client.get(f"/api/v1/reports/{report['id']}/download").status_code == 409
        archive = client.get(f"/api/v1/reports/{report['id']}/download?historical=true")
        assert archive.status_code == 200 and archive.headers['content-type'] == 'application/zip'
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            assert bundle.read(f"HISTORICAL-STALE-{report['id']}.json") == original
            assert '已过期' in bundle.read('readme.txt').decode('utf-8')


def test_chunked_upload_limited_before_multipart_spool(tmp_path):
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'data', max_upload_mb=1), start_worker=False)) as client:
        spooled = []
        original = UploadFile.write
        async def record_write(self, data):
            spooled.append(len(data))
            return await original(self, data)
        boundary = 'synthetic-upload-boundary'
        payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="x.npy"\r\n\r\n'.encode() + b'A' * (3 * 1024 * 1024) + f'\r\n--{boundary}--\r\n'.encode())
        with patch.object(UploadFile, 'write', record_write):
            response = client.post('/api/v1/datasets/import', content=iter([payload]), headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        assert response.status_code == 413
        assert sum(spooled) == 0


def test_csv_header_must_be_explicit_and_unique(tmp_path):
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'data'), start_worker=False)) as client:
        for payload in (b'1,2\n3,4\n', b'F3,F3\n1,2\n3,4\n'):
            response = client.post('/api/v1/datasets/import', files={'file': ('x.csv', payload)})
            assert response.status_code == 422


def test_metadata_container_type_is_validated(tmp_path):
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'data'), start_worker=False)) as client:
        response = client.post('/api/v1/datasets/import', files={'file': ('x.json', b'{"data":[[1,2]],"metadata":{},"provenance":[]}')})
        assert response.status_code == 422


def test_untrusted_host_cannot_read_local_records(tmp_path):
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'data'), start_worker=False)) as client:
        assert client.get('/api/v1/datasets', headers={'Host': 'untrusted.example'}).status_code == 400
