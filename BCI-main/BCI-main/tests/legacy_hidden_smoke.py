"""显式隐藏桌面烟测；不训练，不打开 Qt 子窗口，不进入长时间 mainloop。"""
import time
import numpy as np
import tkinter as tk
from unittest.mock import patch
from types import SimpleNamespace
from core.UI.main_UI import MainUI
from core.io.data_io import DataDictBuilder

original_setup=MainUI.setup_ui
def hidden_setup(self):
    self.withdraw()
    original_setup(self)
MainUI.setup_ui=hidden_setup
app=MainUI()
try:
    missing=[name for name,panel in app.panels.items() if panel is None]
    assert not missing, f'面板未成功初始化：{missing}'
    d=DataDictBuilder.create_empty_data_dict()
    DataDictBuilder.add_signal(d,np.ones((2,64)),250,['F3','F4'],'EEG',unit='uV')
    app.data_bus.set_data('raw_data_dict',d)
    def drain():
        until=time.monotonic()+.12
        while time.monotonic()<until:
            app.update()
            time.sleep(.01)
    drain()
    assert app.panels['预处理'].raw_data_dict['signal']['EEG']['data'].shape==(2,64)
    assert app.panels['特征提取'].selected_modality=='EEG'
    assert app.panels['可视化'].data_dict['signal']['EEG']['sampling_rate']==250
    app.data_bus.set_data('features',{'EEG':{'F3_mean':1.,'F4_mean':2.}})
    drain()
    from core.visualizer.bar_view import BarView
    visual=app.panels['可视化']
    bar=SimpleNamespace(current_modality='EEG',data_dict=visual.data_dict)
    with patch('core.visualizer.bar_view.messagebox.showinfo'):
        BarView._load_from_data_dict(bar)
    assert bar.df['mean'].tolist()==[1.,2.]
    child=tk.Toplevel(visual);child.withdraw()
    app.data_bus.set_data('features',None);drain()
    assert not child.winfo_exists()
    assert 'feature' not in visual.data_dict['processed']
    contract={'dataset_id':app.data_bus.dataset_id,'dataset_version':1,'sample_ids':['s1','s2','s3']}
    app.data_bus.set_data('features',np.ones((3,2)),metadata=contract)
    app.data_bus.set_data('labels',np.array([0,1,0]),metadata=contract)
    drain()
    decoder=app.panels['解码分类']
    assert decoder.features.shape==(3,2)
    assert np.array_equal(decoder.labels,[0,1,0])
    assert decoder._feature_identity==decoder._label_identity
    assert decoder._feature_contract is not None and decoder._label_contract is not None
    decoder.result_text.config(state='normal')
    decoder.result_text.insert('1.0','STALE_RESULT')
    decoder.result_text.config(state='disabled')
    app.data_bus.reset();drain()
    assert decoder.labels is None and decoder.features is None
    assert app.panels['预处理'].raw_data_dict is None
    assert app.panels['可视化'].data_dict is None
    assert 'STALE_RESULT' not in decoder.result_text.get('1.0','end')
    assert all(app.data_bus._listeners.values())
    print('HIDDEN_SMOKE_OK: 5 panels, shared raw/features/labels, reset subscriptions')
finally:
    app.destroy()
