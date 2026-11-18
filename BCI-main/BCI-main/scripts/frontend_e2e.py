"""测试监督器：复用外部 Vite，或启动并只清理自己持有句柄的 Node 进程。"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import time
import urllib.request

FRONTEND = Path(__file__).resolve().parents[1] / 'frontend'
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def available(url):
    try:
        with OPENER.open(url, timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def main():
    node = shutil.which('node')
    if not node:
        raise RuntimeError('缺少 Node.js，请先安装 Node 22.12 或更新版本')
    if not available('http://127.0.0.1:8765/api/v1/health'):
        raise RuntimeError('请先启动心澜本地服务，再运行端到端验证')
    owned = None
    (FRONTEND / '.npm-cache').mkdir(exist_ok=True)
    with (FRONTEND / '.npm-cache/verify-vite.log').open('ab') as log:
        try:
            if not available('http://127.0.0.1:5173'):
                owned = subprocess.Popen([node, str(FRONTEND / 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5173', '--strictPort'],
                                         cwd=FRONTEND, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                deadline = time.monotonic() + 20
                while not available('http://127.0.0.1:5173'):
                    if owned.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError('验证开发服务未启动，请查看 frontend/.npm-cache/verify-vite.log')
                    time.sleep(0.2)
            print('使用本地开发服务验证；仅清理本监督器启动的进程。', flush=True)
            result = subprocess.run([node, str(FRONTEND / 'node_modules/@playwright/test/cli.js'), 'test'], cwd=FRONTEND)
            return result.returncode
        finally:
            if owned is not None and owned.poll() is None:
                owned.terminate()
                owned.wait(timeout=10)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
