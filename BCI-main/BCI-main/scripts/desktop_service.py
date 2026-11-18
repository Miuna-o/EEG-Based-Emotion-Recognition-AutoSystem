"""原生宿主的隐藏监督进程：标准输入 EOF（含宿主崩溃）触发自有实例清理。"""
from contextlib import redirect_stdout
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.launcher import start, stop
from backend.app.infrastructure.config import load_settings


def main():
    settings = load_settings()
    instance = secrets.token_hex(16)
    try:
        with redirect_stdout(sys.stderr):
            owned = start(settings, open_browser=False, instance_id=instance)
        host = '[::1]' if settings.host == '::1' else settings.host
        print(json.dumps({'status': 'ready', 'url': f'http://{host}:{settings.port}',
                          'owns_service': owned is not None,
                          'profile_dir': str(settings.storage_dir / 'desktop-profile')}, ensure_ascii=False), flush=True)
        # 管道由桌面宿主持有；不用轮询 PID，也不会误判 PID 重用。
        for line in sys.stdin:
            if line.strip() == 'stop':
                break
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False), flush=True)
        return 1
    finally:
        with redirect_stdout(sys.stderr):
            stop(settings, expected_instance=instance)


if __name__ == '__main__':
    raise SystemExit(main())
