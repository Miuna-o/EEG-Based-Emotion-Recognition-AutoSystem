"""防止后端契约变更后继续发布旧的前端实体 schema。"""
import json
from pathlib import Path

from backend.app.main import create_app


def test_generated_frontend_openapi_matches_live_contract():
    root = Path(__file__).resolve().parents[1]
    saved = json.loads((root / 'frontend/src/generated/openapi.json').read_text(encoding='utf-8'))
    actual = create_app(start_worker=False).openapi()
    assert saved == actual
