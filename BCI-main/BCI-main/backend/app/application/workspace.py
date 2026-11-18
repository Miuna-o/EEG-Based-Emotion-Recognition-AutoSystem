"""数据版本、复核记录与工件的事务边界。"""
import hashlib
import json
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from backend.app.adapters.input_adapter import parse_input, preview_array, validation_errors
from backend.app.adapters.providers import DEMO_LABELS, capabilities
from backend.app.domain.models import (
    AppError, Artifact, Assessment, Dataset, Job, JobRequest, Metadata, MetadataPatch,
    Report, ReportRequest, Review, ReviewRequest, Session, new_id, now,
)
from backend.app.infrastructure.store import Store, encode


class Workspace:
    def __init__(self, settings):
        self.settings = settings
        self.store = Store(settings.storage_dir)

    def import_dataset(self, payload: bytes, suffix: str, mode: str):
        if mode not in ('real', 'demo'):
            raise AppError('invalid_input', '必须明确选择真实或模拟模式')
        if len(payload) > self.settings.max_upload_mb * 1024 * 1024:
            raise AppError('upload_limit', '上传文件超过配置上限', 413)
        array, meta, provenance = parse_input(payload, suffix, self.settings)
        if provenance.get('data_mode') == 'demo' and mode != 'demo':
            raise AppError('mode_conflict', '文件明确标记为模拟来源，不能导入为真实筛查数据')
        identity, session_id, artifact_id = new_id('ds'), new_id('session'), new_id('artifact')
        if not meta.display_code:
            meta.display_code = ('DEMO-' if mode == 'demo' else 'DATA-') + identity[-8:].upper()
        errors = validation_errors(meta, list(array.shape))
        path, digest = self.store.atomic_write('artifacts', artifact_id, 'npy', lambda stream: np.save(stream, array, allow_pickle=False))
        artifact = Artifact(id=artifact_id, sha256=digest, shape=list(array.shape), dtype=str(array.dtype), size_bytes=path.stat().st_size, created_at=now())
        dataset = Dataset(id=identity, version=1, data_mode=mode, session_id=session_id,
                          source_hash=hashlib.sha256(payload).hexdigest(), source_format=suffix,
                          artifact_id=artifact_id, shape=list(array.shape), dtype=str(array.dtype), metadata=meta,
                          provenance=provenance, validation_status='draft' if errors else 'ready', validation_errors=errors,
                          quality={'finite': True, 'missing_count': 0, 'element_count': int(array.size),
                                   'minimum': float(array.min()), 'maximum': float(array.max()), 'signal_quality_score': None,
                                   'note': '仅做结构与数值校验；不代表信号质量合格或具有临床意义'}, created_at=now())
        try:
            with self.store.transaction() as db:
                db.execute('INSERT INTO artifacts VALUES (?,?)', (artifact_id, encode(artifact)))
                db.execute('INSERT INTO datasets VALUES (?,?,?)', (identity, 1, encode(dataset)))
                db.execute('INSERT INTO heads VALUES (?,?)', (identity, 1))
                session = Session(id=session_id, dataset_id=identity, data_mode=mode, created_at=now())
                db.execute('INSERT INTO sessions VALUES (?,?)', (session_id, encode(session)))
        except BaseException:
            # 仅清理本次内部生成且尚未发布的工件，不碰用户文件。
            path.unlink(missing_ok=True)
            raise
        return dataset

    def dataset(self, identity, version=None):
        with self.store.transaction() as db:
            return Dataset.model_validate(self.store.dataset(db, identity, version))

    def datasets(self):
        with self.store.transaction() as db:
            rows = db.execute('SELECT d.payload FROM datasets d JOIN heads h ON d.id=h.id AND d.version=h.version ORDER BY d.rowid DESC LIMIT 500').fetchall()
            return [Dataset.model_validate_json(row['payload']) for row in rows]

    def patch_metadata(self, identity: str, patch: MetadataPatch):
        with self.store.transaction() as db:
            old = self.store.dataset(db, identity)
            if old['version'] != patch.expected_version:
                raise AppError('version_conflict', '数据已更新，请重新载入后核对', 409)
            merged = {**old['metadata'], **patch.metadata}
            # 样本映射改变会使旧标签失效，只有同一次显式提交的标签可以保留。
            if any(name in patch.metadata and patch.metadata[name] != old['metadata'].get(name) for name in ('sample_ids', 'axes', 'kind', 'feature_names')) and 'labels' not in patch.metadata:
                merged.update(labels=None, label_sample_ids=None)
            try:
                metadata = Metadata.model_validate(merged)
            except ValidationError as exc:
                raise AppError('invalid_input', '元信息无效', details=[{'field': '.'.join(str(x) for x in error['loc']), 'message': error['msg']} for error in exc.errors()]) from exc
            errors = validation_errors(metadata, old['shape'])
            if any('标签' in error for error in errors) and metadata.labels is not None:
                raise AppError('invalid_input', '标签与数据样本身份不一致', details=errors)
            updated = Dataset.model_validate({**old, 'version': old['version'] + 1, 'metadata': metadata,
                                              'validation_status': 'draft' if errors else 'ready', 'validation_errors': errors})
            db.execute('INSERT INTO datasets VALUES (?,?,?)', (identity, updated.version, encode(updated)))
            db.execute('UPDATE heads SET version=? WHERE id=?', (updated.version, identity))
            return updated

    def preview(self, identity, version=None):
        dataset = self.dataset(identity, version)
        path = self.store.path('artifacts', dataset.artifact_id, 'npy')
        array = np.load(path, allow_pickle=False, mmap_mode='r')
        return {**preview_array(array, dataset.metadata, self.settings.preview_points),
                'dataset_id': dataset.id, 'dataset_version': dataset.version, 'data_mode': dataset.data_mode, 'source_hash': dataset.source_hash}

    def submit(self, request: JobRequest, retry_of=None):
        fingerprint = hashlib.sha256(encode({**request.model_dump(exclude={'idempotency_key'}), 'retry_of': retry_of}).encode()).hexdigest()
        with self.store.transaction() as db:
            existing = db.execute('SELECT payload,fingerprint FROM jobs WHERE idem=?', (request.idempotency_key,)).fetchone()
            if existing:
                if existing['fingerprint'] != fingerprint:
                    raise AppError('version_conflict', '同一幂等标识已用于不同输入', 409)
                return Job.model_validate_json(existing['payload'])
            dataset = self.store.dataset(db, request.dataset_id)
            if dataset['version'] != request.dataset_version:
                raise AppError('version_conflict', '提交版本已过期，请重新核对数据', 409)
            if dataset['validation_status'] != 'ready':
                raise AppError('invalid_input', '元信息尚未核对完整，草稿不能分析', details=dataset['validation_errors'])
            if request.provider != dataset['data_mode']:
                raise AppError('mode_conflict', '提供方与数据来源模式不一致')
            if request.provider == 'real':
                raise AppError('provider_unavailable', capabilities()['real']['reason'], 503)
            if dataset['metadata']['label_space'] != DEMO_LABELS:
                raise AppError('invalid_input', '演示提供方只支持明确的模拟标签空间', details={'label_space': DEMO_LABELS})
            jobs = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM jobs')]
            if sum(job['status'] in ('queued', 'running', 'cancelling') for job in jobs) >= self.settings.queue_capacity:
                raise AppError('queue_full', '本地任务队列已满，请等待已有任务结束', 429)
            attempt = 1
            if retry_of:
                previous = self.store.get(db, 'jobs', retry_of)
                if previous['status'] not in ('failed', 'interrupted', 'cancelled'):
                    raise AppError('invalid_transition', '仅失败、中断或已取消任务可以重试', 409)
                attempt = previous['attempt'] + 1
            job = Job(id=new_id('job'), display_code=dataset['metadata']['display_code'], dataset_id=dataset['id'], dataset_version=dataset['version'], input_hash=dataset['source_hash'],
                      provider=request.provider, data_mode=dataset['data_mode'], status='queued', stage='等待执行', attempt=attempt,
                      retry_of=retry_of, total_count=len(dataset['metadata']['sample_ids']), created_at=now(),
                      logs=[{'time': now(), 'stage': 'queued', 'message': '输入版本已固定，任务已入队'}])
            db.execute('INSERT INTO jobs VALUES (?,?,?,?)', (job.id, request.idempotency_key, fingerprint, encode(job)))
            return job

    def jobs(self):
        with self.store.transaction() as db:
            return [self._job(db, row['id']) for row in db.execute('SELECT id FROM jobs ORDER BY rowid DESC LIMIT 500').fetchall()]

    def _job(self, db, identity):
        payload = self.store.get(db, 'jobs', identity)
        bound = self.store.dataset(db, payload['dataset_id'], payload['dataset_version'])
        return Job.model_validate({**payload, 'display_code': bound['metadata']['display_code']})

    def job(self, identity):
        with self.store.transaction() as db:
            return self._job(db, identity)

    def cancel(self, identity):
        from backend.app.jobs.executor import transition
        with self.store.transaction() as db:
            job = self.store.get(db, 'jobs', identity)
            if job['status'] == 'queued':
                transition(job, 'cancelled', '尚未执行，已取消')
            elif job['status'] == 'running':
                transition(job, 'cancelling', '取消请求中；等待安全边界，迟到结果将丢弃')
            db.execute('UPDATE jobs SET payload=? WHERE id=?', (encode(job), identity))
            return Job.model_validate(job)

    def retry(self, identity, key):
        old = self.job(identity)
        return self.submit(JobRequest(dataset_id=old.dataset_id, dataset_version=old.dataset_version, provider=old.provider,
                                      idempotency_key=key), retry_of=identity)

    def _assessment(self, db, identity):
        result = self.store.get(db, 'assessments', identity)
        bound = self.store.dataset(db, result['dataset_id'], result['dataset_version'])
        result['display_code'] = bound['metadata']['display_code']
        result['stale'] = self.store.dataset(db, result['dataset_id'])['version'] != result['dataset_version']
        reviews = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM reviews WHERE assessment_id=? ORDER BY revision', (identity,))]
        result['review_revision'] = len(reviews)
        result['review_status'] = reviews[-1]['status'] if reviews else 'pending'
        return Assessment.model_validate(result), reviews

    def assessment(self, identity):
        with self.store.transaction() as db:
            result, _ = self._assessment(db, identity)
            return result

    def assessments(self):
        with self.store.transaction() as db:
            return [self._assessment(db, row['id'])[0] for row in db.execute('SELECT id FROM assessments ORDER BY rowid DESC LIMIT 500').fetchall()]

    def reviews(self, identity):
        with self.store.transaction() as db:
            _, reviews = self._assessment(db, identity)
            return [Review.model_validate(review) for review in reviews]

    def review(self, identity, request: ReviewRequest):
        fingerprint = hashlib.sha256(encode(request.model_dump(exclude={'idempotency_key'})).encode()).hexdigest()
        with self.store.transaction() as db:
            previous = db.execute('SELECT payload,fingerprint FROM reviews WHERE assessment_id=? AND idem=?', (identity, request.idempotency_key)).fetchone()
            if previous:
                if previous['fingerprint'] != fingerprint:
                    raise AppError('version_conflict', '复核幂等标识已用于不同内容', 409)
                return Review.model_validate_json(previous['payload'])
            result, reviews = self._assessment(db, identity)
            if result.stale:
                raise AppError('version_conflict', '结果已过期，请使用当前数据版本重新分析', 409)
            if result.review_revision != request.expected_revision:
                raise AppError('version_conflict', '复核已被更新，请先阅读最新记录', 409)
            review = Review(id=new_id('review'), assessment_id=identity, dataset_id=result.dataset_id, dataset_version=result.dataset_version,
                            revision=len(reviews) + 1, reviewer=request.reviewer, status=request.status, opinion=request.opinion, created_at=now())
            db.execute('INSERT INTO reviews VALUES (?,?,?,?,?,?)', (review.id, identity, review.revision, request.idempotency_key, fingerprint, encode(review)))
            return review

    def create_report(self, identity, request: ReportRequest):
        from backend.app.application.reporting import render_pdf
        with self.store.transaction() as db:
            result, reviews = self._assessment(db, identity)
            if result.stale or result.review_revision != request.expected_revision:
                raise AppError('version_conflict', '结果或复核版本已变更，请重新载入', 409)
            dataset = self.store.dataset(db, result.dataset_id, result.dataset_version)
            report_id, generated_at = new_id('report'), now()
            status = 'reviewed' if result.review_status == 'reviewed' else 'draft'
            snapshot = {'schema_version': '1.0', 'report_id': report_id, 'status': status, 'data_mode': result.data_mode,
                        'generated_at': generated_at, 'dataset': dataset, 'assessment': result.model_dump(mode='json'), 'reviews': reviews,
                        'boundary': '辅助评估，不替代临床诊断。情绪状态不等于心理疾病。',
                        'watermark': '模拟演示，非实际筛查结果' if result.data_mode == 'demo' else None}
            data = encode(snapshot).encode('utf-8') if request.format == 'json' else render_pdf(snapshot)
            path, digest = self.store.atomic_write('reports', report_id, request.format, lambda stream: stream.write(data))
            report = Report(id=report_id, display_code=dataset['metadata']['display_code'], assessment_id=identity, dataset_id=result.dataset_id, dataset_version=result.dataset_version,
                            review_revision=result.review_revision, format=request.format, data_mode=result.data_mode,
                            status=status, sha256=digest, created_at=generated_at)
            try:
                db.execute('INSERT INTO reports VALUES (?,?)', (report_id, encode(report)))
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            return report

    def report(self, identity):
        with self.store.transaction() as db:
            return self._report(db, identity)

    def _report(self, db, identity):
        report = self.store.get(db, 'reports', identity)
        bound = self.store.dataset(db, report['dataset_id'], report['dataset_version'])
        current = self.store.dataset(db, report['dataset_id'])
        assessment, _ = self._assessment(db, report['assessment_id'])
        reasons = []
        if current['version'] != report['dataset_version']:
            reasons.append('数据集已更新')
        if assessment.review_revision != report['review_revision']:
            reasons.append('人工复核记录已更新')
        return Report.model_validate({**report, 'display_code': bound['metadata']['display_code'], 'stale': bool(reasons), 'stale_reason': '；'.join(reasons) or None,
                                      'current_dataset_version': current['version'], 'current_review_revision': assessment.review_revision})

    def reports(self):
        with self.store.transaction() as db:
            return [self._report(db, row['id']) for row in db.execute('SELECT id FROM reports ORDER BY rowid DESC LIMIT 500').fetchall()]

