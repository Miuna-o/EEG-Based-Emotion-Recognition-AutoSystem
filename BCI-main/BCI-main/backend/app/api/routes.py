import importlib.util
import io
import json
import hmac
import hashlib
import os
from pathlib import Path
from typing import Literal
import zipfile

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.app.adapters.input_adapter import FORMATS
from backend.app.adapters.providers import capabilities
from backend.app.adapters.assistant import ChatRequest, chat as assistant_chat, status as assistant_status
from backend.app.domain.models import (
    AppError, Assessment, Dataset, Job, JobRequest, MetadataPatch, Report, ReportRequest, Review, ReviewRequest,
)

router = APIRouter(prefix='/api/v1')


@router.get('/assistant/status')
def get_assistant_status(request: Request):
    return assistant_status(workspace(request).settings)


@router.post('/assistant/chat')
def post_assistant_chat(body: ChatRequest, request: Request):
    return assistant_chat(workspace(request).settings, body)


def workspace(request):
    return request.app.state.workspace


@router.get('/health')
def health(request: Request):
    return {'status': 'ok', 'name': '心澜', 'version': '1.0.0', 'schema_version': '1.0', 'config_version': workspace(request).settings.config_version,
            'real_provider_available': False, 'instance_id': os.environ.get('XINLAN_LAUNCH_ID'), 'process_id': os.getpid()}


@router.post('/system/stop', include_in_schema=False)
def system_stop(request: Request):
    expected = os.environ.get('XINLAN_STOP_TOKEN', '')
    supplied = request.headers.get('X-Xinlan-Token', '')
    if not expected or not hmac.compare_digest(expected, supplied) or not hasattr(request.app.state, 'request_shutdown'):
        raise AppError('not_authorized', '只能由持有本次启动凭据的启动器停止服务', 403)
    request.app.state.request_shutdown()
    return {'status': 'stopping'}


@router.get('/capabilities')
def get_capabilities():
    return {**capabilities(), 'import_formats': FORMATS, 'ordinary_upload_pickle': False}


@router.get('/datasets', response_model=list[Dataset])
def datasets(request: Request):
    return workspace(request).datasets()


@router.post('/datasets/import', response_model=Dataset, status_code=201)
def import_dataset(request: Request, file: UploadFile = File(...), data_mode: Literal['real', 'demo'] = Form('real')):
    app = workspace(request)
    limit = app.settings.max_upload_mb * 1024 * 1024
    payload = file.file.read(limit + 1)
    return app.import_dataset(payload, Path(file.filename or '').suffix.lower(), data_mode)


@router.get('/datasets/{identity}', response_model=Dataset)
def dataset(identity: str, request: Request, version: int | None = Query(default=None, ge=1)):
    return workspace(request).dataset(identity, version)


@router.patch('/datasets/{identity}/metadata', response_model=Dataset)
def metadata(identity: str, body: MetadataPatch, request: Request):
    return workspace(request).patch_metadata(identity, body)


@router.get('/datasets/{identity}/preview')
def preview(identity: str, request: Request, version: int | None = Query(default=None, ge=1)):
    return workspace(request).preview(identity, version)


@router.post('/jobs', response_model=Job, status_code=201)
def submit(body: JobRequest, request: Request):
    return workspace(request).submit(body)


@router.get('/jobs', response_model=list[Job])
def jobs(request: Request):
    return workspace(request).jobs()


@router.get('/jobs/{identity}', response_model=Job)
def job(identity: str, request: Request):
    return workspace(request).job(identity)


@router.post('/jobs/{identity}/cancel', response_model=Job)
def cancel(identity: str, request: Request):
    return workspace(request).cancel(identity)


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    idempotency_key: str = Field(min_length=1, max_length=128)


@router.post('/jobs/{identity}/retry', response_model=Job, status_code=201)
def retry(identity: str, body: RetryRequest, request: Request):
    return workspace(request).retry(identity, body.idempotency_key)


@router.get('/assessments', response_model=list[Assessment])
def assessments(request: Request):
    return workspace(request).assessments()


@router.get('/assessments/{identity}', response_model=Assessment)
def assessment(identity: str, request: Request):
    return workspace(request).assessment(identity)


@router.get('/assessments/{identity}/reviews', response_model=list[Review])
def reviews(identity: str, request: Request):
    return workspace(request).reviews(identity)


@router.post('/assessments/{identity}/reviews', response_model=Review, status_code=201)
def review(identity: str, body: ReviewRequest, request: Request):
    return workspace(request).review(identity, body)


@router.post('/assessments/{identity}/reports', response_model=Report, status_code=201)
def create_report(identity: str, body: ReportRequest, request: Request):
    return workspace(request).create_report(identity, body)


@router.get('/reports', response_model=list[Report])
def reports(request: Request):
    return workspace(request).reports()


@router.get('/reports/{identity}/download')
def download(identity: str, request: Request, historical: bool = False, preview: bool = False):
    app = workspace(request)
    report = app.report(identity)
    path = app.store.path('reports', report.id, report.format)
    if not path.is_file():
        raise AppError('artifact_missing', '报告工件缺失，请检查存储备份', 404)
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != report.sha256:
            raise AppError('artifact_corrupted', '报告文件完整性检查失败，请检查备份', 409)
    if report.stale:
        if not historical:
            raise AppError('version_conflict', '报告已过期，不能作为当前报告下载；可明确选择历史存档', 409, details={'reason': report.stale_reason})
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(f'HISTORICAL-STALE-{report.id}.{report.format}', path.read_bytes())
            bundle.writestr('readme.txt', '历史存档：已过期，不能作为当前筛查报告。\n原因：' + report.stale_reason + '\n原始报告是生成时刻的不可变快照，请同时阅读 current-context.json。\n')
            bundle.writestr('current-context.json', report.model_dump_json(indent=2))
        return Response(archive.getvalue(), media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="HISTORICAL-STALE-{report.id}.zip"'})
    media = 'application/pdf' if report.format == 'pdf' else 'application/json'
    return FileResponse(path, media_type=media, filename=f'xinlan-{report.data_mode}-{report.status}-{report.id}.{report.format}',
                        content_disposition_type='inline' if preview and report.format == 'pdf' else 'attachment')


@router.get('/reports/{identity}', response_model=Report)
def report_metadata(identity: str, request: Request):
    return workspace(request).report(identity)


@router.get('/settings')
def settings(request: Request):
    app = workspace(request)
    return {'effective': app.settings.model_dump(mode='json'), 'config_version': app.settings.config_version,
            'priority': '默认值 < config/xinlan.json < XINLAN_ 环境变量；修改文件后重启生效',
            'version': '1.0.0', 'privacy': '本地单操作者。使用数据编码；助手只接收您明确输入的文字。',
            'pdf_available': importlib.util.find_spec('reportlab') is not None and Path('C:/Windows/Fonts/simsun.ttc').exists(),
            'legacy_entry': 'scripts/start-legacy.ps1'}


@router.get('/diagnostics/download')
def diagnostics(request: Request):
    app = workspace(request)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        diagnostic = {'application': '心澜', 'version': '1.0.0', 'config_version': app.settings.config_version,
                      'capabilities': capabilities(), 'jobs': [{'id': job.id, 'status': job.status, 'stage': job.stage,
                                                             'error_code': job.error_code, 'elapsed_seconds': job.elapsed_seconds} for job in app.jobs()]}
        archive.writestr('diagnostics.json', json.dumps(diagnostic, ensure_ascii=False, indent=2))
        archive.writestr('README.txt', '不包含原始信号、意见、数据编码、完整用户路径或助手会话。\n')
    return Response(buffer.getvalue(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="xinlan-diagnostics.zip"'})


@router.get('/demo/sample')
def demo_sample():
    import numpy as np
    times = np.arange(512, dtype=np.float64) / 128
    data = np.stack([12 * np.sin(2 * np.pi * 10 * times), 8 * np.sin(2 * np.pi * 6 * times + 0.3)])
    payload = {'data': data.tolist(), 'metadata': {'display_code': 'DEMO-001', 'kind': 'eeg', 'modality': 'EEG',
               'axes': ['channel', 'time'], 'sampling_rate': 128, 'channels': ['F3', 'F4'], 'unit': 'uV',
               'sample_ids': ['demo-window-001'], 'label_space': ['模拟平静', '模拟波动'],
               'source_description': '固定正弦合成样本；非受试者数据，无情绪推理意义'},
               'provenance': {'data_mode': 'demo', 'generator': 'fixed-sine/1.0'}}
    return Response(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(), media_type='application/json',
                    headers={'Content-Disposition': 'attachment; filename="xinlan-demo-sample.json"'})

