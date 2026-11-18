"""测试辅助：只操作指定心澜测试进程的原生窗口，不操作其他应用。"""
import ctypes
from ctypes import wintypes
import sys
import time
from pathlib import Path

user32 = ctypes.windll.user32
target = int(sys.argv[1])
action = sys.argv[2]
windows = []
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


@callback_type
def collect(handle, _):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    if pid.value == target:
        text = ctypes.create_unicode_buffer(256)
        kind = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(handle, text, 256)
        user32.GetClassNameW(handle, kind, 256)
        windows.append((handle, text.value, kind.value))
    return True


user32.EnumWindows(collect, 0)
if action in ('save-default', 'cancel-download'):
    end = time.monotonic() + 15
    dialogs = []
    while time.monotonic() < end:
        windows.clear()
        user32.EnumWindows(collect, 0)
        dialogs = [h for h,t,k in windows if k == '#32770' and t == '保存心澜文件']
        if dialogs: break
        time.sleep(.1)
    if not dialogs: raise RuntimeError('没有出现本测试进程的系统保存对话框')
    time.sleep(.6)
    user32.PostMessageW(dialogs[0],0x0111,1 if action == 'save-default' else 2,0)
    profile = ctypes.create_unicode_buffer(1024)
    ctypes.windll.shell32.SHGetFolderPathW(None,0x28,None,0,profile)
    print(Path(profile.value)/'Downloads')
elif action == 'close-preview':
    for handle,title,kind in windows:
        if title == '心澜 · 报告预览': user32.PostMessageW(handle,0x0010,0,0)
elif action == 'close':
    for handle,title,kind in windows:
        if kind == '#32770': user32.PostMessageW(handle,0x0111,2 if title == '保存心澜文件' else 1,0)
        if title == '心澜' and kind.startswith('WindowsForms'): user32.PostMessageW(handle,0x0010,0,0)
else:
    print(windows)
