"""独立审查 I1–I7 的接口组合回归；合成文件、无可见 UI、无训练。"""
import importlib
import ast
import json
import tempfile
import subprocess
import sys
import hashlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pandas as pd


class LegacyReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def decoder(self):
        from core.UI.panel.decoding_panel import DecodingPanel
        panel=DecodingPanel.__new__(DecodingPanel)
        for key,value in {'features':None,'labels':None,'data_bus':None,'trained_model':None,
            'eval_results':None,'_data_generation':0,'_feature_identity':None,'_label_identity':None,
            '_feature_contract':None,'_label_contract':None}.items():setattr(panel,key,value)
        panel._update_data_status=lambda:None;panel._clear_displayed_results=lambda:None
        for name,value in {'decoder_var':'SVM','cv_var':'holdout','n_splits_var':'2',
            'trial_time_var':'4','kernel_var':'rbf','c_var':'1','grid_search_var':False}.items():
            setattr(panel,name,SimpleNamespace(get=lambda value=value:value))
        panel.train_btn=SimpleNamespace(config=lambda **kw:None)
        panel.progress_bar=SimpleNamespace(start=lambda *args:None)
        panel.progress_label=SimpleNamespace(config=lambda **kw:None)
        return panel

    def feature_file(self):
        path=self.root/'features.npz'
        np.savez(path,features=np.ones((4,2)),sample_ids=np.array(['a','b','c','d']),
                 dataset_id=np.array('A'),dataset_version=np.array(3))
        return path

    def load_features(self,panel,path):
        with patch('core.UI.panel.decoding_panel.filedialog.askopenfilename',return_value=str(path)), \
             patch('core.UI.panel.decoding_panel.messagebox.showinfo'), \
             patch('core.UI.panel.decoding_panel.messagebox.showerror'):
            panel._load_features_file()

    def load_labels(self,panel,path):
        errors=[]
        with patch('core.UI.panel.decoding_panel.filedialog.askopenfilename',return_value=str(path)), \
             patch('core.UI.panel.decoding_panel.messagebox.showinfo'), \
             patch('core.UI.panel.decoding_panel.messagebox.showwarning'), \
             patch('core.UI.panel.decoding_panel.messagebox.showerror',side_effect=lambda *args:errors.append(args)):
            panel._load_labels_file()
        return errors

    def assert_training_blocked(self,panel):
        started=[]
        def thread(**kwargs):started.append(kwargs);return SimpleNamespace(start=lambda:None)
        with patch('core.UI.panel.decoding_panel.threading.Thread',side_effect=thread), \
             patch('core.UI.panel.decoding_panel.messagebox.showwarning'), \
             patch('core.UI.panel.decoding_panel.messagebox.showerror'):
            panel._start_training()
        self.assertEqual(started,[],'无匹配样本身份的标签进入了训练提交')

    def test_i1_feature_invalidation_removes_both_aliases_and_closes_views(self):
        from core.UI.main_UI import MainUI
        import tkinter as tk
        closed=[];window=tk.Toplevel.__new__(tk.Toplevel)
        window.destroy=lambda:closed.append('closed')
        visual=SimpleNamespace(data_dict={'processed':{'feature':{'EEG':{'F3_mean':1}},
            'features':{'F3_mean':1}}},winfo_children=lambda:[window])
        MainUI._shared_features(SimpleNamespace(panels={'可视化':visual}),None)
        self.assertNotIn('feature',visual.data_dict['processed'])
        self.assertNotIn('features',visual.data_dict['processed'])
        self.assertEqual(closed,['closed'])

    def test_i2_feature_contract_retains_ids_and_dataset_version(self):
        panel=self.decoder();self.load_features(panel,self.feature_file())
        self.assertIsNotNone(panel._feature_contract,'特征文件的样本契约被丢弃')
        self.assertEqual(tuple(panel._feature_contract['sample_ids']),('a','b','c','d'))
        self.assertEqual(panel._feature_contract['dataset_id'],'A')
        self.assertEqual(panel._feature_contract['dataset_version'],3)

    def test_i2_wrong_dataset_version_or_sample_order_cannot_bind(self):
        for dataset,version,ids in [('B',3,['a','b','c','d']),('A',2,['a','b','c','d']),
                                    ('A',3,['d','c','b','a'])]:
            with self.subTest(dataset=dataset,version=version,ids=ids):
                panel=self.decoder();self.load_features(panel,self.feature_file())
                path=self.root/'labels.npz'
                np.savez(path,labels=np.array([0,1,0,1]),sample_ids=np.array(ids),
                         dataset_id=np.array(dataset),dataset_version=np.array(version))
                self.load_labels(panel,path)
                self.assertIsNone(panel._label_identity,'错误标签被赋成当前特征身份')
                self.assert_training_blocked(panel)

    def test_i2_unknown_id_numpy_labels_do_not_allow_training(self):
        panel=self.decoder();self.load_features(panel,self.feature_file())
        path=self.root/'unknown.npy';np.save(path,[0,1,0,1]);self.load_labels(panel,path)
        self.assertIsNone(panel._label_identity)
        self.assert_training_blocked(panel)

    def test_i2_csv_sample_id_column_is_metadata_not_label(self):
        panel=self.decoder();self.load_features(panel,self.feature_file())
        path=self.root/'labels.csv'
        pd.DataFrame({'dataset_id':['A']*4,'dataset_version':[3]*4,'label':[0,1,0,1],
                      'sample_id':['a','b','c','d']}).to_csv(path,index=False)
        errors=self.load_labels(panel,path)
        self.assertEqual(errors,[])
        np.testing.assert_array_equal(panel.labels,[0,1,0,1])
        self.assertIsNotNone(panel._label_contract)
        self.assertEqual(panel._label_identity,panel._feature_identity)

    def test_i3_fnirs_three_dimensional_roundtrip_and_ingress(self):
        from core.io.data_io import DataSaver,DataLoader
        from core.UI.dispatch import require_signal_metadata
        data={'meta':{},'signal':{'fNIRS':{'data':np.ones((2,2,20)), 'sampling_rate':10.,
            'unit':'raw-intensity','channel_names':['C1','C2'],'wavelengths':[730,850]}},
            'event':{},'processed':{}}
        for fmt in ('npz','json'):
            with self.subTest(fmt=fmt):
                path=self.root/f'fnirs.{fmt}'
                DataSaver.save(data,str(path),fmt)
                try:loaded=DataLoader().load(str(path));require_signal_metadata(loaded)
                except ValueError as exc:self.fail(f'合法 C×W×T 被拒绝：{exc}')
                np.testing.assert_array_equal(loaded['signal']['fNIRS']['data'],data['signal']['fNIRS']['data'])

    def test_i4_default_ecg_config_has_safe_typed_enum_encoding(self):
        from core.processing.preprocessing.ecg_preprocessing import ECGConfig
        from core.io.data_io import DataSaver,DataLoader
        data={'meta':{},'signal':{'ECG':{'data':np.ones((1,20)),'sampling_rate':250.,'unit':'V'}},
            'event':{},'processed':{'ECG_preprocessing':{'ECG':{'results':{
                'processing_config':ECGConfig().__dict__}}}}}
        for fmt in ('npz','json'):
            with self.subTest(fmt=fmt):
                path=self.root/f'ecg.{fmt}'
                try:DataSaver.save(data,str(path),fmt);loaded=DataLoader().load(str(path))
                except ValueError as exc:self.fail(f'默认 ECG 配置无法安全归档：{exc}')
                value=loaded['processed']['ECG_preprocessing']['ECG']['results']['processing_config']['filter_type']
                self.assertEqual(value['enum_type'],'core.processing.preprocessing.preprocessing.FilterType')
                self.assertEqual(value['enum_name'],'BUTTERWORTH')
                self.assertEqual(value['enum_value'],'butterworth')

    def test_i5_cross_file_modalities_never_reach_statistical_core(self):
        from core.UI.panel.analysis_panel_tk import StatisticalAnalysisPanel,adapt_feature_summary
        def dataset(mod,value):
            return adapt_feature_summary(pd.DataFrame([{'Modality':mod,'Category':'feature',
                'Channel':'Global','Feature':'mean','Value':value,'Unit':'V','Scope':'global'}]))
        captured=[];errors=[]
        panel=SimpleNamespace(is_valid=True,result=[],_current_fig=None,data_bus=None,
            group_files={'A':[dataset('EEG',1),dataset('ECG',2)],
                         'B':[dataset('EEG',3),dataset('ECG',4)]},group_select_features={},
            status_label_var=SimpleNamespace(set=lambda _:None),update_idletasks=lambda:None,
            channel_var=SimpleNamespace(get=lambda:'Global'),channel_combo={'state':'readonly'},
            feature_var=SimpleNamespace(get=lambda:'feature/mean'),method_var=SimpleNamespace(get=lambda:'t-test'),
            enable_correction_var=SimpleNamespace(get=lambda:False))
        with patch('core.UI.panel.analysis_panel_tk.calculate_significance',side_effect=lambda data,**kw:captured.append(data) or []), \
             patch('core.UI.panel.analysis_panel_tk.messagebox.showwarning'), \
             patch('core.UI.panel.analysis_panel_tk.messagebox.showerror',side_effect=lambda *args:errors.append(args)):
            StatisticalAnalysisPanel.run_analysis(panel)
        self.assertEqual(captured,[],'EEG/ECG 同名观察混入同一次统计调用')
        self.assertTrue(errors)

    def test_i6_public_plot_module_imports_without_backend_mutation(self):
        with patch('matplotlib.use',side_effect=AssertionError('导入不应切换后端')):
            try:module=importlib.import_module('core.visualizer.plot_core')
            except NameError as exc:self.fail(f'公开帮助模块无法导入：{exc}')
        self.assertTrue(callable(module.plot_raw))

    def test_i7_bar_reads_actual_pipeline_feature_alias(self):
        from core.visualizer.bar_view import BarView
        panel=SimpleNamespace(current_modality='EEG',data_dict={'signal':{'EEG':{
            'channel_names':['F3','F4']}},'processed':{'feature':{'EEG':{'F3_mean':1.,'F4_mean':2.}}}})
        with patch('core.visualizer.bar_view.messagebox.showinfo'):
            try:BarView._load_from_data_dict(panel)
            except ValueError as exc:self.fail(f'实际流水线特征不能进入柱状图：{exc}')
        self.assertEqual(panel.df['mean'].tolist(),[1.,2.])

    def test_audit_does_not_rewrite_source_line_endings(self):
        project=self.root/'AIC'/'BCI-main'/'BCI-main'/'BCI-main';project.mkdir(parents=True)
        artifacts=project.parents[2]/'review_artifacts'/'migration-2026-11-14';artifacts.mkdir(parents=True)
        source=project/'core/UI/probe.py';source.parent.mkdir(parents=True);source.write_bytes(b'x=1\n')
        original=artifacts/'original-source/core/UI/probe.py';original.parent.mkdir(parents=True)
        original.write_bytes(b'x=1\r\n')
        (artifacts/'baseline.json').write_text(json.dumps([{'path':'core/UI/probe.py',
            'sha256':hashlib.sha256(original.read_bytes()).hexdigest()}]),encoding='utf-8')
        script=Path(__file__).with_name('legacy_audit.py').read_text(encoding='utf-8')
        names=next(ast.literal_eval(node.value) for node in ast.parse(script).body
                   if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='new' for target in node.targets))
        for name in names:
            path=project/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# synthetic\n',encoding='utf-8')
        (project/'tests/legacy_audit.py').write_text(script,encoding='utf-8')
        result=subprocess.run([sys.executable,'-B','-X','utf8',str(project/'tests/legacy_audit.py')],
            capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(source.read_bytes(),b'x=1\n','审计修改了被审查源码')

    def test_wide_table_bad_or_missing_numeric_observations_are_rejected(self):
        from core.UI.panel.analysis_panel_tk import read_xlsx
        for value in ('broken',float('nan')):
            with self.subTest(value=value):
                path=self.root/'wide.xlsx'
                pd.DataFrame({'Channel':['F3','F4'],'mean':[1.,value]}).to_excel(path,index=False)
                with self.assertRaises(ValueError):read_xlsx(str(path))

    def test_i4_numpy_timestamp_and_all_modality_configs_remain_portable(self):
        from core.processing.preprocessing.eeg_preprocessing import EEGPreprocessingConfig
        from core.processing.preprocessing.emg_preprocessing import EMGPreprocessingConfig
        from core.processing.preprocessing.ecg_preprocessing import ECGConfig
        from core.processing.preprocessing.fnirs_preprocessing import fNIRSConfig
        from core.io.serialization import encode_json,decode_json
        data={'meta':{},'signal':{},'event':{},'processed':{'timestamp':np.datetime64('2026-11-15T01:02:03','us'),
            'configs':{cls.__name__:cls().__dict__ for cls in
                       (EEGPreprocessingConfig,EMGPreprocessingConfig,ECGConfig,fNIRSConfig)}}}
        try:loaded=decode_json(encode_json(data))
        except ValueError as exc:self.fail(f'实际配置/时间记录不能安全编码：{exc}')
        self.assertEqual(loaded['processed']['timestamp'],data['processed']['timestamp'])
        self.assertEqual(loaded['processed']['configs']['ECGConfig']['filter_type']['enum_value'],'butterworth')

    def test_i4_unknown_enum_type_cannot_request_import(self):
        from core.io.serialization import decode_json
        value={'format':'bci-data-dict','version':2,'payload':{'meta':{'x':{'__enum__':{
            'type':'builtins.eval','name':'execute','value':'anything'}}},'signal':{},'event':{},'processed':{}}}
        with patch('importlib.import_module',side_effect=AssertionError('文件不应触发模块导入')):
            with self.assertRaises(ValueError):decode_json(value)

    def test_explicit_demo_is_fixed_and_does_not_change_global_numpy_rng(self):
        from core.UI.panel.visualization_panel import NeuroPioneerPanel
        from core.visualizer.bar_view import BarView
        before=np.random.get_state();self.addCleanup(np.random.set_state,before)
        panel=SimpleNamespace(data_bus=None,file_path_var=SimpleNamespace(set=lambda _:None),update_file_info=lambda:None)
        with patch('core.UI.panel.visualization_panel.messagebox.showinfo'):
            NeuroPioneerPanel.load_demo_data(panel);first=panel.data_dict['signal']['EEG']['data'].copy()
            NeuroPioneerPanel.load_demo_data(panel)
        after=np.random.get_state()
        self.assertEqual(before[2:],after[2:]);np.testing.assert_array_equal(before[1],after[1])
        np.testing.assert_array_equal(first,panel.data_dict['signal']['EEG']['data'])
        self.assertEqual(panel.data_dict['meta']['data_source'],'simulation')
        bar=SimpleNamespace()
        with patch('core.visualizer.bar_view.messagebox.showinfo'):
            BarView._create_demo_data(bar);frame=bar.df.copy();BarView._create_demo_data(bar)
        np.testing.assert_array_equal(before[1],np.random.get_state()[1])
        pd.testing.assert_frame_equal(frame,bar.df)

    def test_mne_electrical_readers_preserve_si_values_and_label_volts(self):
        import mne
        from core.io.data_io import DataLoader
        values=np.array([[-2**-20,0.,2**-20,2**-19]])
        raw=mne.io.RawArray(values,mne.create_info(['F3'],250,'eeg'),verbose=False)
        for suffix,reader in [('edf','read_raw_edf'),('set','read_raw_eeglab')]:
            with self.subTest(suffix=suffix), patch.object(mne.io,reader,return_value=raw):
                result=DataLoader().load(str(self.root/f'synthetic.{suffix}'))['signal']['EEG']
                np.testing.assert_array_equal(result['data'],raw.get_data())
                self.assertEqual(result['unit'],'V','MNE SI 电压被误标为微伏')

    def test_non_voltage_mne_channels_are_not_claimed_as_volts(self):
        import mne
        from core.io.data_io import DataLoader
        raw=mne.io.RawArray(np.ones((1,4)),mne.create_info(['STI'],250,'stim'),verbose=False)
        with patch.object(mne.io,'read_raw_edf',return_value=raw):
            with self.assertRaises(ValueError):DataLoader().load(str(self.root/'mixed.edf'))


if __name__=='__main__':unittest.main()
