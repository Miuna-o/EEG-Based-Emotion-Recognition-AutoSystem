"""旧研究入口契约回归；只读写临时合成文件，不启动可见窗口。"""
import hashlib
import json
import os
os.environ.setdefault('MPLBACKEND', 'Agg')
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pandas as pd
from core.data_bus import DataBus
from core.io.data_io import DataDictBuilder, DataLoader, DataSaver


class LegacyContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture(self):
        d = DataDictBuilder.create_empty_data_dict()
        DataDictBuilder.add_signal(d, np.arange(40).reshape(2,20), 250,
                                   ['F3','F4'], 'EEG', unit='uV')
        DataDictBuilder.add_signal(d, np.arange(20).reshape(1,20), 100,
                                   ['ECG1'], 'ECG', unit='mV')
        DataDictBuilder.add_event(d, '合成事件', .02, .01)
        d['processed']['features'] = {'alpha': np.array([1.2, 1.4])}
        d['meta']['extra'] = {'说明':'保留', 'nested':[1, {'x':2}]}
        return d

    def assert_roundtrip(self, before, after):
        self.assertEqual(before['meta'], after['meta'])
        self.assertEqual(before['event'], after['event'])
        self.assertEqual(list(before['signal']), list(after['signal']))
        for key, entry in before['signal'].items():
            target = after['signal'][key]
            self.assertIsInstance(target['data'], np.ndarray)
            np.testing.assert_array_equal(entry['data'], target['data'])
            self.assertEqual(entry['data'].dtype, target['data'].dtype)
            self.assertEqual({k:v for k,v in entry.items() if k!='data'},
                             {k:v for k,v in target.items() if k!='data'})
        np.testing.assert_array_equal(before['processed']['features']['alpha'],
                                      after['processed']['features']['alpha'])

    def test_excel_does_not_touch_sibling_csv_or_source(self):
        excel, sibling = self.root/'same.xlsx', self.root/'same.csv'
        pd.DataFrame({'F3':[1.,2.,3.]}).to_excel(excel,index=False)
        sibling.write_bytes(b'sentinel\n')
        digest=hashlib.sha256(excel.read_bytes()).digest()
        result=DataLoader().load(str(excel),fs=250,modality='EEG')
        self.assertTrue(sibling.exists(), '同名 CSV 被删除')
        self.assertEqual(sibling.read_bytes(),b'sentinel\n')
        self.assertEqual(hashlib.sha256(excel.read_bytes()).digest(),digest)
        self.assertEqual(result['meta']['file_path'], str(excel))

    def test_npz_lossless_safe_roundtrip(self):
        original=self.fixture(); path=self.root/'sample.npz'
        DataSaver.save(original,str(path),'npz')
        self.assert_roundtrip(original,DataLoader().load(str(path)))
        with np.load(path,allow_pickle=False) as archive:
            for key in archive.files:
                self.assertFalse(archive[key].dtype.hasobject)

    def test_json_lossless_normalizes_arrays(self):
        original=self.fixture(); path=self.root/'sample.json'
        DataSaver.save(original,str(path),'json')
        self.assert_roundtrip(original,DataLoader().load(str(path)))

    def test_plain_json_normalizes_signal_list(self):
        d=self.fixture()
        path=self.root/'plain.json'
        path.write_text(json.dumps(d,default=lambda a:a.tolist(),ensure_ascii=False),encoding='utf-8')
        loaded=DataLoader().load(str(path))
        self.assertIsInstance(loaded['signal']['EEG']['data'],np.ndarray)

    def test_numpy_metadata_is_local_and_explicit_rate_wins(self):
        archive,plain=self.root/'a.npz',self.root/'b.npy'
        np.savez(archive,data=np.zeros((2,20)),fs=128.)
        np.save(plain,np.zeros((2,20)))
        loader=DataLoader(); loader.load(str(archive))
        self.assertEqual(loader.load(str(plain),fs=250)['signal']['UNKNOWN']['sampling_rate'],250)
        self.assertEqual(loader.load(str(archive),fs=300)['signal']['UNKNOWN']['sampling_rate'],300)

    def test_object_numpy_refused_even_if_allow_pickle_requested(self):
        path=self.root/'objects.npy'; np.save(path,np.array({'signal':{}},dtype=object))
        for opts in ({},{'allow_pickle':True}):
            with self.assertRaises(ValueError):
                DataLoader().load(str(path),**opts)

    def test_pickle_import_refused(self):
        import pickle
        path=self.root/'sample.pkl'; path.write_bytes(pickle.dumps(self.fixture()))
        with self.assertRaises(ValueError): DataLoader().load(str(path))

    def test_reset_keeps_subscription(self):
        bus=DataBus(); seen=[]; bus.on_change('features',seen.append)
        bus.set_data('features','before'); bus.reset(); bus.set_data('features','after')
        self.assertIn('after',seen)
        self.assertIn(None,seen)

    def test_new_raw_invalidates_all_downstream(self):
        bus=DataBus(); bus.set_data('raw_data_dict',{'file':'A'})
        for stage in ('processed_data_dict','features','labels','decode_result','statistics'):
            bus.set_data(stage, {'file':'old'})
        bus.set_data('raw_data_dict',{'file':'B'})
        self.assertEqual(bus.get_best_data_dict(),{'file':'B'})
        for stage in ('processed_data_dict','features','labels','decode_result','statistics'):
            self.assertIsNone(bus.get_data(stage))

    def test_stale_revision_cannot_commit(self):
        bus=DataBus(); bus.set_data('raw_data_dict',{'file':'A'})
        self.assertTrue(hasattr(bus,'get_revision'),'缺少版本身份')
        old=bus.get_revision(); bus.set_data('raw_data_dict',{'file':'B'})
        self.assertFalse(bus.set_data('features',{'x':1},expected_revision=old))
        self.assertIsNone(bus.get_data('features'))

    def test_new_feature_file_clears_labels_model_and_result(self):
        from core.UI.panel.decoding_panel import DecodingPanel
        path=self.root/'features.csv';pd.DataFrame({'a':[1.,2.]}).to_csv(path,index=False)
        cleared=[]
        dummy=SimpleNamespace(features=None,labels=np.array([0,1]),data_bus=None,
                              trained_model='old',eval_results={'old':1},
                              _clear_displayed_results=lambda:cleared.append(True),
                              _update_data_status=lambda:None)
        with patch('core.UI.panel.decoding_panel.filedialog.askopenfilename',return_value=str(path)), \
             patch('core.UI.panel.decoding_panel.messagebox.showinfo'), \
             patch('core.UI.panel.decoding_panel.messagebox.showerror'):
            DecodingPanel._load_features_file(dummy)
        self.assertIsNone(dummy.labels)
        self.assertIsNone(dummy.trained_model)
        self.assertIsNone(dummy.eval_results)
        self.assertEqual(cleared,[True],'旧结果虽然失效，界面仍展示旧图/旧文本')

    def test_long_summary_explicitly_adapts_channel_and_feature(self):
        from core.UI.panel.analysis_panel_tk import read_xlsx
        path=self.root/'summary.xlsx'
        pd.DataFrame([{'Modality':'EEG','Category':'frequency','Channel':ch,
                       'Feature':'alpha','Value':val,'Data_Type':'float'}
                      for ch,val in [('F3',1.2),('F4',1.4)]]).to_excel(path,index=False)
        parsed=read_xlsx(str(path))
        self.assertEqual(parsed['ch_names'],['F3','F4'])
        self.assertEqual(list(parsed['feature']),['frequency/alpha'])
        self.assertEqual(parsed['feature']['frequency/alpha'],[[1.2],[1.4]])

    def test_missing_rate_stays_draft(self):
        path=self.root/'draft.npy';np.save(path,np.zeros((2,20)))
        loaded=DataLoader().load(str(path))
        self.assertIsNone(loaded['signal']['UNKNOWN']['sampling_rate'])
        self.assertIsNone(loaded['signal']['UNKNOWN']['duration'])

    def test_real_signal_parse_failure_never_creates_demo(self):
        from core.visualizer.signal_view import SignalView
        with patch('core.visualizer.signal_view.tk.Frame.__init__'), \
             patch.object(SignalView,'_parse_data',side_effect=ValueError('broken')), \
             patch.object(SignalView,'_create_fallback_data') as fallback, \
             patch('core.visualizer.signal_view.messagebox.showerror'), \
             patch.object(SignalView,'setup_ui'), patch.object(SignalView,'update_plot'):
            try: SignalView(None,{'signal':{}})
            except (ValueError,RuntimeError): pass
        fallback.assert_not_called()

    def test_empty_statistics_contains_no_generated_data(self):
        from core.visualizer.stats_view import StatisticalAnalysisView
        from matplotlib.figure import Figure
        dummy=SimpleNamespace(stats_results={},effect_size_figure=Figure(),
            effect_canvas=SimpleNamespace(draw=lambda:None),
            sort_effects_var=SimpleNamespace(get=lambda:False),
            show_ci_var=SimpleNamespace(get=lambda:False))
        StatisticalAnalysisView.update_effect_plot(dummy)
        ax=dummy.effect_size_figure.axes[0]
        self.assertEqual(len(ax.collections),0,'空真实统计生成了效应量点')
        self.assertTrue(any('缺少' in text.get_text() or '无' in text.get_text() for text in ax.texts))

    def test_metadata_reserved_keys_and_tuples_roundtrip(self):
        d=self.fixture();d['meta']['reserved']={'__ndarray__':'literal'}
        d['meta']['tuple']=(1,'二');d['processed']['complex']=np.array([1+2j])
        for extension in ('json','npz'):
            path=self.root/f'extended.{extension}'
            DataSaver.save(d,str(path),extension)
            try: loaded=DataLoader().load(str(path))
            except Exception as exc:self.fail(f'元信息键不能无损往返：{exc}')
            self.assertEqual(loaded['meta'],d['meta'])
            np.testing.assert_array_equal(loaded['processed']['complex'],d['processed']['complex'])

    def test_real_bar_missing_features_never_generates_demo(self):
        from core.visualizer.bar_view import BarView
        dummy=SimpleNamespace(current_modality=None,data_dict={'signal':{},'processed':{}},
                              _create_demo_data=lambda:self.fail('真实缺失特征调用了随机演示'))
        try:BarView._load_from_data_dict(dummy)
        except ValueError:pass

    def test_bad_text_column_is_rejected_instead_of_nan(self):
        path=self.root/'bad.csv';path.write_text('F3,F4\n1,broken\n',encoding='utf-8')
        with self.assertRaises(ValueError):DataLoader().load(str(path),fs=250,modality='EEG')

    def test_empty_pvalue_and_reliability_plots_show_no_observations(self):
        from core.visualizer.stats_view import StatisticalAnalysisView
        from matplotlib.figure import Figure
        dummy=SimpleNamespace(stats_results={},p_value_figure=Figure(),reliability_figure=Figure(),
            pvalue_canvas=SimpleNamespace(draw=lambda:None),reliability_canvas=SimpleNamespace(draw=lambda:None))
        StatisticalAnalysisView.update_pvalue_plot(dummy)
        StatisticalAnalysisView.update_reliability_plot(dummy)
        self.assertFalse(dummy.p_value_figure.axes[0].patches)
        self.assertFalse(dummy.reliability_figure.axes[0].collections)

    def test_feature_summary_keeps_actual_channel_prefix_and_global_observation(self):
        from core.UI.feature_summary import feature_summary_rows
        rows=feature_summary_rows({'F3_mean':1.,'F4_mean':2.,'global':3.},'EEG',['F3','F4'])
        self.assertEqual([(r['Channel'],r['Feature'],r['Value']) for r in rows],
                         [('F3','mean',1.),('F4','mean',2.),('Global','global',3.)])

    def test_failed_json_save_preserves_existing_output(self):
        path=self.root/'output.json';path.write_bytes(b'existing-output')
        d=self.fixture();d['meta']['unsupported']=object()
        with self.assertRaises(ValueError):DataSaver.save(d,str(path),'json')
        self.assertEqual(path.read_bytes(),b'existing-output')

    def test_mixed_global_and_channel_summary_keeps_observation_scope(self):
        from core.UI.panel.analysis_panel_tk import read_xlsx,get_feature
        path=self.root/'mixed.xlsx'
        pd.DataFrame([{'Modality':'EEG','Category':'feature','Channel':ch,'Feature':name,'Value':val}
            for ch,name,val in [('F3','mean',1),('F4','mean',2),('Global','global',3)]]).to_excel(path,index=False)
        try: parsed=read_xlsx(str(path))
        except Exception as exc:self.fail(f'合法的全局/通道观察混合长表被拒绝：{exc}')
        self.assertEqual(get_feature(parsed,'F3','feature/mean'),[1.])
        self.assertEqual(get_feature(parsed,'Global','feature/global'),[3.])
        with self.assertRaises(ValueError):get_feature(parsed,'F3','feature/global')

    def test_unlabelled_vector_is_not_inferred_as_channel_observations(self):
        from core.UI.feature_summary import feature_summary_rows
        rows=feature_summary_rows({'unknown_axis':np.array([1.,2.])},'EEG',['F3','F4'])
        self.assertEqual(rows,[],'仅长度相等不能证明向量轴就是通道轴')


if __name__=='__main__': unittest.main()
