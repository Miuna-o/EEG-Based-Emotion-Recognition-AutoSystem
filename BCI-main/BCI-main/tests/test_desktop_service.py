"""桌面宿主断开后回收自己的服务，绝不停止已存在的服务。"""
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def environment(tmp_path, port):
    return {**os.environ, 'XINLAN_PORT': str(port),
            'XINLAN_STORAGE_DIR': str(tmp_path / 'data'), 'PYTHONUTF8': '1'}


def supervisor(env):
    return subprocess.Popen([sys.executable, '-B', '-X', 'utf8', 'scripts/desktop_service.py'],
                            cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding='utf-8')


def handshake(process):
    lines = queue.Queue()
    threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
    line = lines.get(timeout=40)
    assert line, '桌面监督进程尚未提供就绪协议'
    return json.loads(line)


def health(port):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{port}/api/v1/health', timeout=2) as response:
        return json.load(response)


def cleanup(process):
    if process.poll() is None:
        process.stdin.close()
        process.wait(timeout=30)


def test_parent_eof_stops_owned_service(tmp_path):
    port = free_port()
    process = supervisor(environment(tmp_path, port))
    try:
        ready = handshake(process)
        assert ready['status'] == 'ready'
        assert ready['owns_service'] is True
        assert ready['url'] == f'http://127.0.0.1:{port}'
        assert health(port)['status'] == 'ok'
        cleanup(process)
        assert process.returncode == 0, process.stderr.read()
        assert not (tmp_path / 'data/launcher.json').exists()
        with socket.socket() as probe:
            assert probe.connect_ex(('127.0.0.1', port)) != 0
    finally:
        cleanup(process)


def test_desktop_exit_keeps_preexisting_service(tmp_path):
    port = free_port()
    env = environment(tmp_path, port)
    def launcher(action):
        return subprocess.run([sys.executable, '-X', 'utf8', 'scripts/launcher.py', action, '--no-browser'],
                              cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=40)
    assert launcher('start').returncode == 0
    before = health(port)
    process = supervisor(env)
    try:
        assert handshake(process)['owns_service'] is False
        process.stdin.write('stop\n')
        process.stdin.flush()
        process.wait(timeout=20)
        assert process.returncode == 0, process.stderr.read()
        assert health(port)['instance_id'] == before['instance_id']
    finally:
        cleanup(process)
        assert launcher('stop').returncode == 0


def test_busy_port_returns_error_without_creating_instance(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        process = supervisor(environment(tmp_path, listener.getsockname()[1]))
        try:
            result = handshake(process)
            assert result['status'] == 'error'
            assert '端口' in result['message']
            process.wait(timeout=10)
            assert process.returncode != 0
            assert not (tmp_path / 'data/launcher.json').exists()
            assert listener.getsockname()[1] > 0
        finally:
            cleanup(process)
