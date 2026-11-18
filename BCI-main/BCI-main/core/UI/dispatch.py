"""Tk 主线程队列：后台只入队；销毁与版本切换后丢弃旧回调。"""
import queue
import threading
import traceback


class MainThreadDispatcher:
    def __init__(self, widget, interval=25):
        self.widget=widget
        self.interval=interval
        self.owner=threading.get_ident()
        self.queue=queue.Queue()
        self.closed=False
        self.generation=0
        self.timer=widget.after(interval,self._drain)
        widget.bind('<Destroy>',self._on_destroy,add='+')

    def _on_destroy(self,event):
        if event.widget is self.widget:
            self.close()

    def invalidate(self):
        self.generation+=1
        return self.generation

    def post(self,callback,*args,generation=None):
        if not self.closed:
            self.queue.put((generation,callback,args))

    def after(self,delay,callback,*args):
        """兼容旧 after(0,...) 调用；只入队，绝不从工作线程调用 Tk。"""
        self.post(callback,*args)

    def _drain(self):
        if threading.get_ident()!=self.owner:
            raise RuntimeError('UI 队列必须由创建线程消费')
        if self.closed: return
        for _ in range(100):
            try: generation,callback,args=self.queue.get_nowait()
            except queue.Empty: break
            if generation is None or generation==self.generation:
                try: callback(*args)
                except Exception: traceback.print_exc()
        self.timer=self.widget.after(self.interval,self._drain)

    def close(self):
        self.closed=True
        try: self.widget.after_cancel(self.timer)
        except Exception: pass


def require_signal_metadata(data):
    """仅校验计算前提，不填采样率、单位或改动预处理公式。"""
    import numpy as np
    from core.io.signal_layout import validate_signal_layout
    signal=data.get('signal',{}) if data else {}
    if not signal: raise ValueError('缺少信号数据')
    for modality,info in signal.items():
        rate=info.get('sampling_rate')
        if rate is None or not np.isfinite(rate) or rate<=0:
            raise ValueError(f'{modality} 缺少明确采样率；请先补齐元信息')
        if info.get('unit') in (None,'','unknown'):
            raise ValueError(f'{modality} 缺少明确单位；请先补齐元信息')
        array=np.asarray(info.get('data'))
        validate_signal_layout(modality,info,array)
        if not np.isfinite(array).all():
            raise ValueError('信号包含非有限观察值；须明确处理，不能静默丢弃')
