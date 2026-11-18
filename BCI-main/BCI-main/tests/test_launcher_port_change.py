"""同一存储更换端口前，必须先停止已归属的服务，避免遗留实例。"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import psutil

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def test_port_change_does_not_replace_live_owned_instance(tmp_path):
    port_a, port_b = free_port(), free_port()
    while port_a == port_b:
        port_b = free_port()
    store = tmp_path / 'store'
    state_path = store / 'launcher.json'
    def run(action, port):
        env = {**os.environ, 'XINLAN_STORAGE_DIR': str(store), 'XINLAN_PORT': str(port)}
        return subprocess.run([sys.executable, '-X', 'utf8', 'scripts/launcher.py', action, '--no-browser'],
                              cwd=ROOT, env=env, text=True, encoding='utf-8', capture_output=True, timeout=45)
    original = None
    try:
        response = run('start', port_a)
        assert response.returncode == 0, response.stderr
        original = json.loads(state_path.read_text())
        changed = run('start', port_b)
        assert changed.returncode == 1
        assert '先停止' in changed.stderr
        assert json.loads(state_path.read_text())['pid'] == original['pid']
    finally:
        if state_path.exists():
            run('stop', port_b)
        # RED 阶段原实现可能覆盖实例记录；仅恢复本测试自己的凭据以安全清理。
        if original and psutil.pid_exists(original['pid']):
            state_path.write_text(json.dumps(original), encoding='utf-8')
            run('stop', port_a)
