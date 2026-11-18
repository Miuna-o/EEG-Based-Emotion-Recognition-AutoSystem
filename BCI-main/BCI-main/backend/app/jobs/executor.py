"""一个调度线程 + 一个 Windows spawn 进程；状态只在事务中迁移。"""
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime
import json
import logging
import multiprocessing
import threading

from backend.app.adapters.providers import run_provider
from backend.app.domain.models import AppError, Assessment, TERMINAL, TRANSITIONS, new_id, now
from backend.app.infrastructure.store import encode

LOGGER = logging.getLogger('xinlan.jobs')


def transition(job, status, message):
    if status not in TRANSITIONS[job['status']]:
        raise AppError('invalid_transition', '任务状态不允许此操作', 409)
    job['status'], job['stage'] = status, message
    job['logs'].append({'time': now(), 'stage': status, 'message': message})
    if status == 'running':
        job['started_at'] = now()
    if status in TERMINAL:
        job['finished_at'] = now()
        if job['started_at']:
            job['elapsed_seconds'] = max(0, (datetime.fromisoformat(job['finished_at']) - datetime.fromisoformat(job['started_at'])).total_seconds())


class Executor:
    def __init__(self, workspace):
        self.workspace, self.store = workspace, workspace.store
        self.stop_event = threading.Event()
        self.thread = None
        self.pool = None

    def recover(self):
        with self.store.transaction() as db:
            for row in db.execute('SELECT id,payload FROM jobs').fetchall():
                job = json.loads(row['payload'])
                if job['status'] not in TERMINAL:
                    transition(job, 'interrupted', '服务重启，先前执行状态已失联；可显式重试')
                    db.execute('UPDATE jobs SET payload=? WHERE id=?', (encode(job), job['id']))

    def start(self):
        self.recover()
        self.pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn'))
        self.thread = threading.Thread(target=self._dispatch, name='xinlan-dispatch', daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.pool:
            self.pool.shutdown(wait=False, cancel_futures=True)

    def _claim(self):
        with self.store.transaction() as db:
            for row in db.execute('SELECT payload FROM jobs ORDER BY rowid').fetchall():
                job = json.loads(row['payload'])
                if job['status'] != 'queued':
                    continue
                current = self.store.dataset(db, job['dataset_id'])
                if current['version'] != job['dataset_version']:
                    transition(job, 'cancelled', '数据版本已更新，任务未执行')
                    db.execute('UPDATE jobs SET payload=? WHERE id=?', (encode(job), job['id']))
                    continue
                transition(job, 'running', '正在执行固定演示契约')
                db.execute('UPDATE jobs SET payload=? WHERE id=?', (encode(job), job['id']))
                artifact = self.store.get(db, 'artifacts', current['artifact_id'])
                return job, {**current, 'artifact_hash': artifact['sha256']}
        return None

    def _commit(self, job_id, output=None, failure=None):
        with self.store.transaction() as db:
            job = self.store.get(db, 'jobs', job_id)
            if job['status'] in TERMINAL:
                return
            dataset = self.store.dataset(db, job['dataset_id'])
            if job['status'] == 'cancelling':
                transition(job, 'cancelled', '计算已到安全边界，结果已丢弃')
            elif dataset['version'] != job['dataset_version']:
                transition(job, 'failed', '数据版本已变化，迟到结果已丢弃')
                job['error_code'] = 'version_conflict'
            elif failure:
                transition(job, 'failed', '任务执行失败；查看错误码后可重试')
                job['error_code'] = failure
            else:
                try:
                    result = Assessment(id=new_id('assessment'), display_code=dataset['metadata']['display_code'], dataset_id=dataset['id'], dataset_version=dataset['version'],
                                        session_id=dataset['session_id'], job_id=job_id, input_hash=dataset['source_hash'],
                                        config_version=self.workspace.settings.config_version, quality=dataset['quality'],
                                        data_mode=dataset['data_mode'], generated_at=now(), **output)
                    if [item.sample_id for item in result.emotions] != dataset['metadata']['sample_ids'] or any(item.label not in result.label_space for item in result.emotions):
                        raise ValueError('provider_contract_error')
                    if result.label_space != dataset['metadata']['label_space']:
                        raise ValueError('provider_contract_error')
                except (ValueError, TypeError):
                    transition(job, 'failed', '提供方输出未通过契约验证，未发布结果')
                    job['error_code'] = 'provider_contract_error'
                else:
                    db.execute('INSERT INTO assessments VALUES (?,?)', (result.id, encode(result)))
                    job['assessment_id'] = result.id
                    job['processed_count'] = job['total_count']
                    transition(job, 'succeeded', '演示完成；需要人工复核')
            db.execute('UPDATE jobs SET payload=? WHERE id=?', (encode(job), job_id))
            LOGGER.info('job_id=%s stage=%s code=%s elapsed=%s', job_id, job['status'], job['error_code'], job['elapsed_seconds'])

    def _dispatch(self):
        while not self.stop_event.is_set():
            job = None
            try:
                claim = self._claim()
                if claim is None:
                    self.stop_event.wait(0.15)
                    continue
                job, dataset = claim
                future = self.pool.submit(run_provider, dataset, str(self.store.path('artifacts', dataset['artifact_id'], 'npy')))
                while not future.done() and not self.stop_event.wait(0.1):
                    pass
                if self.stop_event.is_set():
                    # 关闭时不发布结果；下次启动恢复 interrupted。
                    return
                try:
                    output = future.result()
                except BrokenProcessPool:
                    raise
                except Exception:
                    self._commit(job['id'], failure='provider_failed')
                else:
                    self._commit(job['id'], output=output)
            except BrokenProcessPool:
                if job is not None:
                    self._commit(job['id'], failure='worker_interrupted')
                self.pool.shutdown(wait=False, cancel_futures=True)
                if not self.stop_event.is_set():
                    self.pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn'))
            except Exception:
                LOGGER.error('code=executor_error stage=dispatch')
                if job is not None:
                    try:
                        self._commit(job['id'], failure='executor_error')
                    except Exception:
                        LOGGER.error('code=persistence_error stage=commit')
                self.stop_event.wait(0.5)

