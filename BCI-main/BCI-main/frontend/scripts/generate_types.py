"""从真实 FastAPI OpenAPI schema 生成 TypeScript 契约，禁止手写替代领域类型。"""
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from backend.app.main import create_app

schema = create_app(start_worker=False).openapi()
target = PROJECT / 'frontend/src/generated'
target.mkdir(parents=True, exist_ok=True)
(target / 'openapi.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding='utf-8')

def ts(spec):
    if '$ref' in spec:
        return spec['$ref'].rsplit('/', 1)[1]
    if 'anyOf' in spec:
        return ' | '.join(ts(item) for item in spec['anyOf'])
    if 'enum' in spec:
        return ' | '.join(json.dumps(item, ensure_ascii=False) for item in spec['enum'])
    if 'const' in spec:
        return json.dumps(spec['const'], ensure_ascii=False)
    kind = spec.get('type')
    if kind == 'array':
        return f'Array<{ts(spec["items"])}>'
    if kind == 'object':
        if 'properties' in spec:
            required = spec.get('required', [])
            return '{ ' + '; '.join(f'{json.dumps(key)}{"" if key in required else "?"}: {ts(value)}' for key, value in spec['properties'].items()) + ' }'
        return 'Record<string, ' + (ts(spec['additionalProperties']) if isinstance(spec.get('additionalProperties'), dict) else 'unknown') + '>'
    return {'string': 'string', 'integer': 'number', 'number': 'number', 'boolean': 'boolean', 'null': 'null'}.get(kind, 'unknown')

lines = ['// Generated from backend.app.main.create_app().openapi(); run npm run types:generate.']
for name, spec in schema['components']['schemas'].items():
    lines.append(f'export type {name} = {ts(spec)};')
(target / 'api.ts').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'Generated {len(lines)-1} schema types')
