"""任务竞态的确定性事务验证，不依赖 sleep 命中竞态窗口。"""
import io
import json

from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend.app.main import create_app
from backend.app.infrastructure.config import Settings
from backend.app.adapters.providers import DemoProvider
from backend.app.domain.models import Assessment
from test_workspace_api import ready, submit


@pytest.fixture
def controlled(tmp_path):
    app = create_app(Settings(storage_dir=tmp_path / 'data'), start_worker=False)
    with TestClient(app) as client:
        yield client, app.state.workspace, app.state.executor


def test_cancel_at_result_boundary_discards_late_output(controlled):
    client, app, executor = controlled
    dataset = ready(client)
    job = submit(client, dataset).json()
    claimed, context = executor._claim()
    assert claimed['id'] == job['id']
    response = client.post(f"/api/v1/jobs/{job['id']}/cancel")
    assert response.json()['status'] == 'cancelling'
    executor._commit(job['id'], output=DemoProvider().assess(context))
    assert client.get(f"/api/v1/jobs/{job['id']}").json()['status'] == 'cancelled'
    assert client.get('/api/v1/assessments').json() == []


def test_version_change_at_commit_prevents_cross_version_result(controlled):
    client, app, executor = controlled
    dataset = ready(client)
    job = submit(client, dataset).json()
    _, context = executor._claim()
    response = client.patch(f"/api/v1/datasets/{dataset['id']}/metadata", json={'expected_version': dataset['version'], 'metadata': {'display_code': 'NEW'}})
    assert response.status_code == 200
    executor._commit(job['id'], output=DemoProvider().assess(context))
    job = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert job['status'] == 'failed' and job['error_code'] == 'version_conflict'
    assert client.get('/api/v1/assessments').json() == []


def test_retry_keeps_attempt_history_and_is_idempotent(controlled):
    client, app, executor = controlled
    dataset = ready(client)
    job = submit(client, dataset).json()
    executor._claim()
    executor._commit(job['id'], failure='provider_failed')
    uri = f"/api/v1/jobs/{job['id']}/retry"
    retry = client.post(uri, json={'idempotency_key': 'retry-1'})
    assert retry.status_code == 201
    second = client.post(uri, json={'idempotency_key': 'retry-1'})
    assert retry.json()['id'] == second.json()['id']
    assert retry.json()['attempt'] == 2 and retry.json()['retry_of'] == job['id']
    assert client.get(f"/api/v1/jobs/{job['id']}").json()['status'] == 'failed'
    assert len(client.get('/api/v1/jobs').json()) == 2


def test_restart_marks_inflight_interrupted_and_preserves_data(tmp_path):
    settings = Settings(storage_dir=tmp_path / 'persistent')
    first = create_app(settings, start_worker=False)
    with TestClient(first) as client:
        dataset = ready(client)
        job = submit(client, dataset).json()
        first.state.executor._claim()
        assert client.get(f"/api/v1/jobs/{job['id']}").json()['status'] == 'running'
    with TestClient(create_app(settings, start_worker=False)) as client:
        recovered = client.get(f"/api/v1/jobs/{job['id']}").json()
        assert recovered['status'] == 'interrupted'
        assert recovered['finished_at']
        assert client.get(f"/api/v1/datasets/{dataset['id']}").json()['source_hash'] == dataset['source_hash']
        assert client.post(f"/api/v1/jobs/{job['id']}/retry", json={'idempotency_key': 'restart-retry'}).status_code == 201


def test_queue_capacity_and_idempotency_payload_conflict(tmp_path):
    with TestClient(create_app(Settings(storage_dir=tmp_path / 'bounded', queue_capacity=1), start_worker=False)) as client:
        dataset = ready(client)
        assert submit(client, dataset).status_code == 201
        assert submit(client, dataset, 'new-key').status_code == 429
        request = {'dataset_id': dataset['id'], 'dataset_version': 100, 'provider': 'demo', 'idempotency_key': 'run-1'}
        assert client.post('/api/v1/jobs', json=request).status_code == 409


def test_simulation_source_cannot_be_relabelled_real(controlled):
    client, _, _ = controlled
    sample = client.get('/api/v1/demo/sample').content
    response = client.post('/api/v1/datasets/import', files={'file': ('sample.json', sample)}, data={'data_mode': 'real'})
    assert response.status_code == 422
    assert response.json()['code'] == 'mode_conflict'


def test_declared_huge_numpy_header_is_rejected_before_allocating(controlled):
    client, _, _ = controlled
    buffer = io.BytesIO()
    np.lib.format.write_array_header_1_0(buffer, {'descr': '<f8', 'fortran_order': False, 'shape': (10**10, 4)})
    response = client.post('/api/v1/datasets/import', files={'file': ('oversized.npy', buffer.getvalue())})
    assert response.status_code == 413


def test_low_reliability_requires_provider_rule_and_review(controlled):
    client, _, executor = controlled
    dataset = ready(client)
    job = submit(client, dataset).json()
    _, context = executor._claim()
    # 仅注入固定的提供方契约示例，验证应用不抬高可靠性。
    output = DemoProvider().assess(context)
    output.update(reliability=0.2, reliability_threshold=0.7, reliability_rule_source='test-fixture-only/1', review_required=True, review_reason='固定契约示例：低于提供方阈值')
    executor._commit(job['id'], output=output)
    result = client.get('/api/v1/assessments').json()[0]
    assert result['reliability'] == 0.2 and result['review_required']
    invalid = {**result, 'review_required': False}
    with pytest.raises(ValueError):
        Assessment.model_validate(invalid)


def test_cross_origin_mutation_is_rejected(controlled):
    client, _, _ = controlled
    response = client.post('/api/v1/jobs', json={}, headers={'Origin': 'https://foreign.invalid'})
    assert response.status_code == 403
    assert response.json()['code'] == 'origin_rejected'
