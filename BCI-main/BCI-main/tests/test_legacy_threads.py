"""在无 Tk 窗口环境下验证实际队列、过期结果与控件恢复。"""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from core.UI.dispatch import MainThreadDispatcher


class FakeWidget:
    def __init__(self): self.owner=threading.get_ident();self.calls=[]
    def after(self,*args):
        if threading.get_ident()!=self.owner: raise AssertionError('后台调用 Tk after')
        self.calls.append(args);return len(self.calls)
    def after_cancel(self,*args): pass
    def bind(self,*args,**kwargs): pass


class LegacyThreadTests(unittest.TestCase):
    def test_worker_only_enqueues_and_stale_generation_is_dropped(self):
        widget=FakeWidget(); dispatcher=MainThreadDispatcher(widget);seen=[]
        version=dispatcher.invalidate()
        worker=threading.Thread(target=lambda:dispatcher.post(seen.append,'old',generation=version))
        worker.start();worker.join()
        self.assertEqual(seen,[])
        dispatcher.invalidate();dispatcher._drain();self.assertEqual(seen,[])
        worker=threading.Thread(target=lambda:dispatcher.after(0,seen.append,'current'))
        worker.start();worker.join();dispatcher._drain()
        self.assertEqual(seen,['current'])
        dispatcher.close();dispatcher.post(seen.append,'after-close');dispatcher._drain()
        self.assertEqual(seen,['current'])

    def test_stale_training_never_commits_and_restores_button(self):
        from core.UI.panel.decoding_panel import DecodingPanel
        states=[]
        dummy=SimpleNamespace(_data_generation=2,data_bus=None,trained_model=None,eval_results=None,
            progress_bar=SimpleNamespace(stop=lambda:states.append('stopped')),
            train_btn=SimpleNamespace(config=lambda **kw:states.append(kw)),
            progress_label=SimpleNamespace(config=lambda **kw:states.append(kw)),
            _show_results=lambda *args:states.append('displayed'))
        dummy._training_current=lambda snap:DecodingPanel._training_current(dummy,snap)
        dummy._finish_training_error=lambda *args:DecodingPanel._finish_training_error(dummy,*args)
        DecodingPanel._commit_training(dummy,{'generation':1,'revision':None},'old',{},'SVM',4.)
        self.assertIsNone(dummy.trained_model)
        self.assertNotIn('displayed',states)
        self.assertTrue(any(isinstance(v,dict) and v.get('state')=='normal' for v in states))

    def test_ai_exception_is_dispatched_and_restores_send(self):
        from core.UI.panel.ai_chat_panel import AIChatWindow
        queued=[];states=[]
        dummy=SimpleNamespace(ai_logic=SimpleNamespace(chat=lambda _:(_ for _ in ()).throw(ValueError('offline'))),
            _ui=SimpleNamespace(post=lambda cb,*args:queued.append((cb,args))),_request_generation=1,
            is_thinking=True,send_btn=SimpleNamespace(config=lambda **kw:states.append(kw)),
            append_text=lambda *args:states.append(args),_thinking_frame=None)
        dummy._display_reply=lambda *args:AIChatWindow._display_reply(dummy,*args)
        try:
            try: AIChatWindow._run_ai(dummy,'hello',1)
            except TypeError: AIChatWindow._run_ai(dummy,'hello')
        except Exception as exc:
            self.fail(f'助手异常未转为 UI 恢复消息：{exc}')
        self.assertEqual(len(queued),1)
        callback,args=queued[0];callback(*args)
        self.assertFalse(dummy.is_thinking)
        self.assertTrue(any(isinstance(v,dict) and v.get('state')=='normal' for v in states))

    def test_preprocessing_uses_main_thread_config_and_private_input_snapshot(self):
        from core.UI.panel.preprocessing_panel import PreprocessingApp
        import numpy as np
        owner=threading.get_ident(); workers=[];queued=[];seen=[]
        class Variable:
            def get(self):
                self_owner=threading.get_ident()
                if self_owner != owner: raise AssertionError('后台读取 Tk 变量')
                return True
        raw={'signal':{'EEG':{'data':np.ones((2,20)), 'sampling_rate':250,'unit':'uV'}}}
        dummy=SimpleNamespace(is_processing=False,modality_vars={'EEG':Variable()},
            raw_data_dict=raw,processed_data_dict=None,data_bus=None,result_vars={},mod_quality_vars={},
            _ui=SimpleNamespace(generation=1,post=lambda callback,*args:queued.append((callback,args))),
            lbl_status=SimpleNamespace(config=lambda **kwargs:None),
            _ui_update_on_error=lambda msg:seen.append(msg),
            _commit_processed=lambda *args:seen.append(args),
            _finish_processing_error=lambda *args:seen.append(args))
        dummy._build_multimodal_config=lambda mods: Variable().get()
        class Processor:
            def __init__(self,config):seen.append(config)
            def process(self,data):
                seen.append(data['signal']['EEG']['data'].copy())
                return SimpleNamespace(success=True,processed_data=data)
        def capture_thread(*args,**kwargs):
            workers.append(kwargs['target']);return SimpleNamespace(start=lambda:None)
        with patch('core.UI.panel.preprocessing_panel.threading.Thread',side_effect=capture_thread), \
             patch('core.UI.panel.preprocessing_panel.MultiModalPreprocessor',Processor):
            PreprocessingApp.action_run_preprocessing(dummy)
            self.assertEqual(len(workers),1)
            raw['signal']['EEG']['data'][:]=99
            # mock Thread 只捕获提交；使用原生 Thread 消费快照以检查线程所有权。
        worker=threading.Thread(target=workers[0])
        with patch('core.UI.panel.preprocessing_panel.MultiModalPreprocessor',Processor):
            worker.start();worker.join()
        self.assertEqual(len(queued),1)
        self.assertTrue(seen[0])
        np.testing.assert_array_equal(seen[1],np.ones((2,20)))


if __name__=='__main__':unittest.main()
