"""SQLite 原子元信息提交；所有文件名称由内部生成的 ID 决定。"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from backend.app.domain.models import AppError


def encode(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ('artifacts', 'reports', 'tmp'):
            (self.root / name).mkdir(exist_ok=True)
        self.db_path = self.root / 'workspace.sqlite3'
        with self.transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS datasets (id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(id,version));
                CREATE TABLE IF NOT EXISTS heads (id TEXT PRIMARY KEY, version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS assessments (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL, revision INTEGER NOT NULL, idem TEXT NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(assessment_id,revision), UNIQUE(assessment_id,idem));
                CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            ''')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get(db, table, object_id):
        if table not in {'artifacts', 'sessions', 'jobs', 'assessments', 'reviews', 'reports'}:
            raise ValueError('invalid internal table')
        row = db.execute(f'SELECT payload FROM {table} WHERE id=?', (object_id,)).fetchone()
        if row is None:
            raise AppError('not_found', '记录不存在', 404)
        return json.loads(row['payload'])

    @staticmethod
    def dataset(db, dataset_id, version=None):
        if version is None:
            head = db.execute('SELECT version FROM heads WHERE id=?', (dataset_id,)).fetchone()
            if head is None:
                raise AppError('not_found', '数据集不存在', 404)
            version = head['version']
        row = db.execute('SELECT payload FROM datasets WHERE id=? AND version=?', (dataset_id, version)).fetchone()
        if row is None:
            raise AppError('not_found', '数据版本不存在', 404)
        return json.loads(row['payload'])

    def path(self, category: str, object_id: str, extension: str) -> Path:
        if category not in {'artifacts', 'reports'} or extension not in {'npy', 'pdf', 'json'} or not re.fullmatch(r'[a-z]+_[0-9a-f]{32}', object_id):
            raise AppError('invalid_input', '工件标识无效')
        target = self.root / category / f'{object_id}.{extension}'
        if target.parent.resolve() != (self.root / category).resolve():
            raise AppError('invalid_input', '工件位置无效')
        return target

    def atomic_write(self, category, object_id, extension, writer):
        target = self.path(category, object_id, extension)
        if target.exists():
            raise AppError('version_conflict', '不可覆盖已发布工件', 409)
        descriptor, name = tempfile.mkstemp(prefix='commit-', dir=self.root / 'tmp')
        temp = Path(name)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                writer(stream)
                stream.flush()
                os.fsync(stream.fileno())
            with temp.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            os.replace(temp, target)
            return target, digest
        finally:
            temp.unlink(missing_ok=True)

