"""真实子进程启停验证，使用隔离存储和空闲端口。"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request

import psutil

ROOT = Path(__file__).resolve().parents[1]


def test_owned_start_duplicate_start_and_stop(tmp_path):
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        port = server.getsockname()[1]
    env = {**os.environ, 'XINLAN_STORAGE_DIR': str(tmp_path / 'storage'), 'XINLAN_PORT': str(port), 'PYTHONUTF8': '1'}
    def run(action):
        return subprocess.run([sys.executable, '-X', 'utf8', 'scripts/launcher.py', action, '--no-browser'], cwd=ROOT, env=env,
                              text=True, encoding='utf-8', capture_output=True, timeout=45)
    state_file = tmp_path / 'storage/launcher.json'
    try:
        first = run('start')
        assert first.returncode == 0, first.stdout + first.stderr
        first_state = json.loads(state_file.read_text())
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/health') as response:
            health = json.load(response)
        assert health['instance_id'] == first_state['instance_id']
        assert run('start').returncode == 0
        assert json.loads(state_file.read_text())['pid'] == first_state['pid']
        stopped = run('stop')
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
        assert not psutil.pid_exists(first_state['pid'])
        assert not state_file.exists()
    finally:
        if state_file.exists():
            run('stop')


def test_busy_port_does_not_kill_listener(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        env = {**os.environ, 'XINLAN_STORAGE_DIR': str(tmp_path / 'storage'), 'XINLAN_PORT': str(port)}
        result = subprocess.run([sys.executable, '-X', 'utf8', 'scripts/launcher.py', 'start', '--no-browser'], cwd=ROOT, env=env,
                                text=True, encoding='utf-8', capture_output=True, timeout=15)
        assert result.returncode == 1
        assert '端口被占用' in result.stderr
        assert listener.getsockname()[1] == port
        assert not (tmp_path / 'storage/launcher.json').exists()
