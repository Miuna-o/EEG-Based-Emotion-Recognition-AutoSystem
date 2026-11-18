"""本地生命周期管理。凭 PID+创建时间+实例令牌识别服务，绝不强杀外部进程。"""
import argparse
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.infrastructure.config import load_settings


def request_json(base, path, *, token=None, timeout=2):
    request = urllib.request.Request(base + path, data=b'' if token else None,
                                     headers={'X-Xinlan-Token': token} if token else {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


@contextmanager
def lifecycle_lock(root):
    path = root / 'launcher.lock'
    root.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('另一启动器正在处理，请稍后重试') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def owned_process(state):
    import psutil
    try:
        process = psutil.Process(state['pid'])
        command = process.cmdline()
        if abs(process.create_time() - state['created']) < 0.1 and '-m' in command and 'backend.app' in command and Path(process.exe()).resolve() == Path(state['python']).resolve():
            return process
    except (psutil.Error, KeyError, ValueError):
        pass
    return None


def start(settings, *, open_browser=True, instance_id=None):
    import psutil
    host = '[::1]' if settings.host == '::1' else settings.host
    base = f'http://{host}:{settings.port}'
    state_path = settings.storage_dir / 'launcher.json'
    with lifecycle_lock(settings.storage_dir):
        try:
            health = request_json(base, '/api/v1/health')
        except (OSError, ValueError):
            health = None
        if state_path.exists():
            previous = json.loads(state_path.read_text(encoding='utf-8'))
            if owned_process(previous) is not None and (previous.get('base_url') != base or not health):
                raise RuntimeError('已有本启动器服务仍在启动、运行或安全结束；修改端口前请先停止，再启动。')
        if health:
            if health.get('name') != '心澜':
                raise RuntimeError('端口已被其他服务使用；请修改配置端口')
            print(f'心澜服务已运行：{base}。启动器不会接管外部进程。')
            if open_browser:
                webbrowser.open(base)
            return
        with socket.socket(socket.AF_INET6 if settings.host == '::1' else socket.AF_INET) as check:
            try:
                check.bind((settings.host, settings.port))
            except OSError as exc:
                raise RuntimeError('端口被占用；请关闭占用服务或修改心澜配置，不会强制结束其他进程') from exc
        token, instance = secrets.token_urlsafe(32), instance_id or secrets.token_hex(16)
        env = {**os.environ, 'XINLAN_STOP_TOKEN': token, 'XINLAN_LAUNCH_ID': instance, 'PYTHONUTF8': '1'}
        log_path = settings.storage_dir / 'service.log'
        with log_path.open('ab') as output:
            process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'backend.app'], cwd=ROOT, env=env,
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        owned = psutil.Process(process.pid)
        state = {'pid': process.pid, 'created': owned.create_time(), 'python': str(Path(sys.executable).resolve()),
                 'instance_id': instance, 'token': token, 'base_url': base}
        temp = state_path.with_suffix('.pending')
        temp.write_text(json.dumps(state), encoding='utf-8')
        os.replace(temp, state_path)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('服务启动失败，请查看存储目录中的 service.log')
            try:
                health = request_json(base, '/api/v1/health')
                if health.get('instance_id') == instance:
                    print(f'心澜已启动：{base}')
                    print('真实筛查提供方未接入；数据核对、演示流程与报告可用。')
                    if open_browser:
                        webbrowser.open(base)
                    return state
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        raise RuntimeError('服务启动超时，未强杀进程；请运行 diagnose 并检查日志')


def stop(settings, *, expected_instance=None):
    import psutil
    state_path = settings.storage_dir / 'launcher.json'
    with lifecycle_lock(settings.storage_dir):
        if not state_path.exists():
            print('没有本启动器管理的服务；未结束任何外部进程。')
            return
        state = json.loads(state_path.read_text(encoding='utf-8'))
        if expected_instance is not None and state.get('instance_id') != expected_instance:
            # 桌面退出只能回收自己创建的实例，不能接管已有网页或开发服务。
            return
        process = owned_process(state)
        if process is None:
            print('原启动进程已不存在或身份不符；未结束任何进程。')
            return
        health = request_json(state['base_url'], '/api/v1/health')
        # Windows venv redirector 的 PID 与实际解释器子进程不同；仅认可已核验父进程树。
        owned_pids = {process.pid, *(child.pid for child in process.children(recursive=True))}
        if health.get('instance_id') != state['instance_id'] or health.get('process_id') not in owned_pids:
            raise RuntimeError('服务实例身份不符，拒绝停止')
        request_json(state['base_url'], '/api/v1/system/stop', token=state['token'])
        try:
            process.wait(timeout=15)
        except psutil.TimeoutExpired as exc:
            raise RuntimeError('服务正在安全结束任务，尚未停止；不会强杀计算进程，请稍后重试') from exc
        state_path.unlink(missing_ok=True)
        print('心澜服务已安全停止。')


def diagnose(settings):
    print('心澜环境诊断')
    print(f'Python {sys.version.split()[0]}；服务端口 {settings.port}；配置版本 {settings.config_version}')
    for name in ('fastapi', 'uvicorn', 'pydantic', 'numpy', 'pandas', 'openpyxl', 'reportlab', 'psutil'):
        print(f'{name}: ' + ('可用' if importlib.util.find_spec(name) else '缺失'))
    print('前端构建：' + ('可用' if (ROOT / 'frontend/dist/index.html').exists() else '未构建，请执行 npm run build'))
    try:
        host = '[::1]' if settings.host == '::1' else settings.host
        health = request_json(f'http://{host}:{settings.port}', '/api/v1/health')
        print('服务状态：' + health.get('status', '未知'))
    except (OSError, ValueError):
        print('服务状态：未启动')
    print('真实推理：未接入。研究算法和旧桌面入口保留。')


def main():
    parser = argparse.ArgumentParser(description='心澜本地启动器')
    parser.add_argument('action', choices=['start', 'stop', 'diagnose'])
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    settings = load_settings()
    try:
        if args.action == 'start':
            start(settings, open_browser=not args.no_browser)
        elif args.action == 'stop':
            stop(settings)
        else:
            diagnose(settings)
    except (RuntimeError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
