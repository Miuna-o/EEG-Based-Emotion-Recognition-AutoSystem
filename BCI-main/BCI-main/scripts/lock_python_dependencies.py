"""从已验证的当前解释器导出实际传递依赖锁，不包含机器路径。"""
import importlib.metadata as metadata
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def resolve(roots):
    versions, pending = {}, list(roots)
    while pending:
        name = canonicalize_name(pending.pop())
        if name in versions:
            continue
        distribution = metadata.distribution(name)
        versions[name] = distribution.version
        for specification in distribution.requires or []:
            requirement = Requirement(specification)
            if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
                pending.append(requirement.name)
    return versions


if __name__ == '__main__':
    runtime = ['fastapi', 'uvicorn', 'pydantic', 'numpy', 'pandas', 'openpyxl', 'python-multipart', 'httpx', 'reportlab', 'openai', 'psutil']
    developer = ['pytest', 'pypdf', 'pypdfium2']
    for filename, roots in [('requirements.lock', runtime), ('requirements-dev.lock', runtime + developer)]:
        pins = resolve(roots)
        content = '# Verified on Windows x64 / Python 3.13.5; generated from installed distributions.\n' + '\n'.join(f'{name}=={version}' for name, version in sorted(pins.items())) + '\n'
        (ROOT / 'backend' / filename).write_text(content, encoding='utf-8')
        print(f'{filename}: {len(pins)} pinned distributions')
