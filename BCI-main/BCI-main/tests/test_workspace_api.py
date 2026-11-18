"""心澜应用边界回归：只使用固定合成输入，不训练任何模型。"""
import importlib.util
import io
import time

import numpy as np
import pytest


@pytest.fixture
def client(tmp_path):
    assert importlib.util.find_spec('backend') is not None, '本地应用服务尚未实现'
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from backend.app.infrastructure.config import Settings
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'store'))) as instance:
        yield instance


def upload(client, mode='demo', values=None):
    data = np.arange(64, dtype=np.float64).reshape(2, 32) if values is None else values
    buffer = io.BytesIO()
    np.save(buffer, data, allow_pickle=False)
    response = client.post('/api/v1/datasets/import', files={'file': ('input.npy', buffer.getvalue())}, data={'data_mode': mode})
    assert response.status_code == 201, response.text
    return response.json()


def ready(client, mode='demo'):
    dataset = upload(client, mode)
    response = client.patch(f"/api/v1/datasets/{dataset['id']}/metadata", json={
        'expected_version': 1, 'metadata': {
            'kind': 'eeg', 'axes': ['channel', 'time'], 'sampling_rate': 128,
            'channels': ['F3', 'F4'], 'unit': 'uV', 'sample_ids': ['window-001'],
            'label_space': ['模拟平静', '模拟波动'] if mode == 'demo' else ['positive', 'negative'],
            'modality': 'EEG', 'display_code': 'SYN-001',
        }})
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, dataset, key='run-1'):
    return client.post('/api/v1/jobs', json={
        'dataset_id': dataset['id'], 'dataset_version': dataset['version'],
        'provider': 'demo' if dataset['data_mode'] == 'demo' else 'real', 'idempotency_key': key,
    })


def finished(client, job):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job['id']}").json()
        if job['status'] in ('succeeded', 'failed', 'cancelled', 'interrupted'):
            return job
        time.sleep(0.05)
    pytest.fail('任务未在测试时限内结束')


def assessment(client):
    dataset = ready(client)
    response = submit(client, dataset)
    assert response.status_code == 201, response.text
    job = finished(client, response.json())
    assert job['status'] == 'succeeded', job
    result = client.get(f"/api/v1/assessments/{job['assessment_id']}")
    assert result.status_code == 200
    return dataset, result.json()


def test_missing_real_provider_never_falls_back(client):
    caps = client.get('/api/v1/capabilities').json()
    assert caps['real']['available'] is False
    dataset = ready(client, 'real')
    response = submit(client, dataset)
    assert response.status_code == 503
    assert response.json()['code'] == 'provider_unavailable'
    assert client.get('/api/v1/jobs').json() == []


def test_draft_cannot_submit_and_metadata_conflict(client):
    dataset = upload(client)
    assert submit(client, dataset).status_code == 422
    payload = {'expected_version': 8, 'metadata': {'unit': 'uV'}}
    assert client.patch(f"/api/v1/datasets/{dataset['id']}/metadata", json=payload).status_code == 409


@pytest.mark.parametrize('field,value', [('sampling_rate', 0), ('unit', 'banana'), ('axes', ['time', 'time']), ('channels', ['F3'])])
def test_invalid_semantics_cannot_submit(client, field, value):
    dataset = ready(client)
    response = client.patch(f"/api/v1/datasets/{dataset['id']}/metadata", json={
        'expected_version': dataset['version'], 'metadata': {field: value}})
    if response.status_code == 200:
        assert submit(client, response.json()).status_code == 422
    else:
        assert response.status_code == 422


def test_objects_and_nan_rejected_without_deserialization(client):
    buf = io.BytesIO()
    np.save(buf, np.array([{'never': 'deserialize'}], dtype=object))
    response = client.post('/api/v1/datasets/import', files={'file': ('object.npy', buf.getvalue())})
    assert response.status_code == 422
    buf = io.BytesIO()
    np.save(buf, np.array([[np.nan, 1.0]]))
    assert client.post('/api/v1/datasets/import', files={'file': ('nan.npy', buf.getvalue())}).status_code == 422


def test_labels_must_match_sample_identity(client):
    dataset = ready(client)
    response = client.patch(f"/api/v1/datasets/{dataset['id']}/metadata", json={
        'expected_version': dataset['version'], 'metadata': {
            'labels': ['模拟平静'], 'label_sample_ids': ['another-window']}})
    assert response.status_code == 422


def test_idempotency_and_missing_evidence(client):
    dataset = ready(client)
    first = submit(client, dataset)
    second = submit(client, dataset)
    assert first.json()['id'] == second.json()['id']
    job = finished(client, first.json())
    assert job['status'] == 'succeeded', job
    result = client.get(f"/api/v1/assessments/{job['assessment_id']}").json()
    assert result['data_mode'] == 'demo'
    assert result['reliability'] is None
    assert result['review_required'] is True
    assert result['missing_reasons']['reliability']
    assert [x['band'] for x in result['band_evidence']] == ['delta', 'theta', 'alpha', 'beta', 'gamma']
    assert all(x['contribution'] is None for x in result['band_evidence'])


def test_review_append_only_conflict_and_report_provenance(client):
    dataset, result = assessment(client)
    uri = f"/api/v1/assessments/{result['id']}"
    before = client.post(uri + '/reports', json={'format': 'json', 'expected_revision': 0})
    assert before.status_code == 201, before.text
    snapshot = client.get(f"/api/v1/reports/{before.json()['id']}/download").json()
    assert snapshot['status'] == 'draft'
    assert snapshot['data_mode'] == 'demo'
    payload = {'expected_revision': 0, 'reviewer': 'reviewer-01', 'status': 'reviewed', 'opinion': '模拟流程验证，需另行采集真实资料。', 'idempotency_key': 'review-1'}
    review = client.post(uri + '/reviews', json=payload)
    assert review.status_code == 201, review.text
    assert client.post(uri + '/reviews', json=payload).json()['id'] == review.json()['id']
    assert client.post(uri + '/reviews', json={**payload, 'idempotency_key': 'review-2'}).status_code == 409
    updated = client.get(uri).json()
    assert updated['reliability'] is None and updated['review_revision'] == 1
    report = client.post(uri + '/reports', json={'format': 'json', 'expected_revision': 1}).json()
    snapshot = client.get(f"/api/v1/reports/{report['id']}/download").json()
    assert snapshot['status'] == 'reviewed'
    assert snapshot['assessment']['dataset_version'] == dataset['version']
    assert len(snapshot['reviews']) == 1
    # 原快照保持草稿，但复核修订后不允许冒充当前报告再次常规下载。
    assert client.get(f"/api/v1/reports/{before.json()['id']}/download").status_code == 409


def test_old_result_marked_stale_after_metadata_version(client):
    dataset, result = assessment(client)
    response = client.patch(f"/api/v1/datasets/{dataset['id']}/metadata", json={
        'expected_version': dataset['version'], 'metadata': {'display_code': 'SYN-002'}})
    assert response.status_code == 200
    uri = f"/api/v1/assessments/{result['id']}"
    assert client.get(uri).json()['stale'] is True
    assert client.post(uri + '/reports', json={'format': 'json', 'expected_revision': 0}).status_code == 409


def test_request_error_has_trace_id_and_no_arbitrary_path(client):
    response = client.get('/api/v1/datasets/not-a-real-id')
    assert response.status_code == 404
    assert set(response.json()) == {'code', 'message', 'details', 'request_id'}
    assert response.json()['request_id']
    assert client.get('/api/v1/reports/..%2F..%2Fconfig/download').status_code in (404, 422)

