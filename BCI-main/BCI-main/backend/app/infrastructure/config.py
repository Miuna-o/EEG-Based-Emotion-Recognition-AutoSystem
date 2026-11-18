"""单一配置入口：代码默认 < config/xinlan.json < XINLAN_ 环境变量。"""
import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    storage_dir: Path = PROJECT_ROOT / '.xinlan-data'
    host: str = '127.0.0.1'
    port: int = Field(default=8765, ge=1024, le=65535)
    max_upload_mb: int = Field(default=32, ge=1, le=256)
    max_array_elements: int = Field(default=4_000_000, ge=1, le=32_000_000)
    queue_capacity: int = Field(default=8, ge=1, le=32)
    preview_points: int = Field(default=1000, ge=100, le=4000)
    allowed_origins: list[str] = ['http://127.0.0.1:5173', 'http://localhost:5173']
    assistant_enabled: bool = False
    assistant_base_url: str = 'http://127.0.0.1:11434/v1'
    assistant_model: str = 'qwen2.5:7b'
    assistant_timeout_seconds: float = Field(default=20, ge=1, le=120)
    assistant_max_history: int = Field(default=10, ge=0, le=30)
    assistant_retry_limit: int = Field(default=0, ge=0, le=2)

    @field_validator('host')
    @classmethod
    def local_only(cls, value):
        if value not in ('127.0.0.1', '::1'):
            raise ValueError('首版本地单操作者仅允许回环监听')
        return value

    @field_validator('assistant_base_url')
    @classmethod
    def local_assistant(cls, value):
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('localhost', '127.0.0.1', '::1') or parsed.username or parsed.password:
            raise ValueError('助手仅允许本机服务，不接受凭据 URL')
        return value.rstrip('/')

    @property
    def config_version(self):
        payload = self.model_dump(mode='json')
        payload.pop('storage_dir')
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def load_settings() -> Settings:
    config_path = Path(os.environ.get('XINLAN_CONFIG', str(PROJECT_ROOT / 'config/xinlan.json')))
    data = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    for name in Settings.model_fields:
        raw = os.environ.get('XINLAN_' + name.upper())
        if raw is not None:
            try:
                data[name] = json.loads(raw)
            except json.JSONDecodeError:
                data[name] = raw
    result = Settings(**data)
    if not result.storage_dir.is_absolute():
        result.storage_dir = (PROJECT_ROOT / result.storage_dir).resolve()
    return result
