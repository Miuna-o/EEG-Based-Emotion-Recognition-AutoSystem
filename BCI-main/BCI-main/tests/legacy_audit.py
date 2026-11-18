"""生成旧入口差异与冻结源码核对记录；不导入计算模块。"""
import difflib
import hashlib
import json
import platform
import sys
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
ARTIFACTS=PROJECT.parents[2]/'review_artifacts'/'migration-2026-11-14'
BASE=json.loads((ARTIFACTS/'baseline.json').read_text(encoding='utf-8'))
BACKUP=ARTIFACTS/'original-source'
legacy=[]
for item in BASE:
    path=item['path']
    if path in ('core/io/data_io.py','core/data_bus.py') or path.startswith(('core/UI/','core/visualizer/')):
        if not path.endswith('.py'): continue
        current=PROJECT/path;original=BACKUP/path
        if current.exists() and hashlib.sha256(current.read_bytes()).hexdigest()!=item['sha256']:
            legacy.append(path)
new=['core/io/serialization.py','core/UI/dispatch.py','core/UI/feature_summary.py',
     'tests/test_legacy_regressions.py','tests/test_legacy_threads.py','tests/legacy_hidden_smoke.py','tests/legacy_audit.py',
     'docs/legacy-correctness-report.md','core/io/enum_schema.py','core/io/signal_layout.py',
     'core/UI/sample_identity.py','tests/test_legacy_review_regressions.py']
diff=[]
for name in legacy+new:
    old=(BACKUP/name).read_text(encoding='utf-8').splitlines(keepends=True) if (BACKUP/name).exists() else []
    current=(PROJECT/name).read_text(encoding='utf-8').splitlines(keepends=True)
    diff.extend(difflib.unified_diff(old,current,fromfile='original/'+name,tofile='current/'+name))
(ARTIFACTS/'legacy-correctness.diff').write_text(''.join(diff),encoding='utf-8')
frozen=[item for item in BASE if item['path'].startswith(('core/decoding/','core/processing/'))]
mismatches=[item['path'] for item in frozen if not (PROJECT/item['path']).exists() or
            hashlib.sha256((PROJECT/item['path']).read_bytes()).hexdigest()!=item['sha256']]
import numpy,pandas,scipy
record={'python':sys.executable,'python_version':platform.python_version(),
        'numpy':numpy.__version__,'pandas':pandas.__version__,'scipy':scipy.__version__,
        'modified_legacy_files':legacy,'new_files':new,
        'frozen_files_checked':len(frozen),'frozen_mismatches':mismatches,
        'test_command':"python -B -X utf8 -m unittest discover -s tests -p 'test_legacy*.py' -v",
        'test_log':'legacy-tests.log','hidden_smoke_log':'legacy-hidden-smoke.log'}
(ARTIFACTS/'legacy-validation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False,indent=2))
assert not mismatches,'冻结计算源码发生变化'
