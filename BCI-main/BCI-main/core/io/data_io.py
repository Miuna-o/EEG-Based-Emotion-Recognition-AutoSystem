#!/usr/bin/env python3
"""
universal_bio_signal_converter.py
万能生物信号数据转换器 - 纯IO/转换版本

直接运行！不需要任何其他文件！
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import pickle
from datetime import datetime
from enum import Enum
import warnings
import tempfile
from core.io.serialization import encode_json, decode_json, encode_npz, decode_npz


# ==================== 信号类型枚举 ====================
class SignalType(Enum):
    """信号类型枚举"""
    EEG = "eeg"
    EMG = "emg"
    ECG = "ecg"
    GSR = "gsr"
    FNIRS = "fnirs"
    ET = "eyetracker"
    RESP = "resp"
    OTHER = "other"


# ==================== 数据字典构建器 ====================
class DataDictBuilder:
    """标准数据字典构建器 - 四层结构: meta, signal, event, processed"""

    @staticmethod
    def create_empty_data_dict() -> Dict[str, Any]:
        """创建空的四层数据字典"""
        return {
            "meta": {
                "subject_id": "",
                "session_id": "",
                "task": "",
                "recording_time": "",
                "file_path": "",
                "format_version": "1.0",
                "modality": [],
                "device": "",
                "notes": ""
            },
            "signal": {},
            "event": {
                "event_id": [],
                "event_label": [],
                "event_time": [],
                "duration": []
            },
            "processed": {
                "features": {},
                "artifacts": {},
                "filtered_data": {}
            }
        }

    @staticmethod
    def build_meta(
            subject_id: str = "",
            session_id: str = "",
            task: str = "",
            recording_time: str = "",
            file_path: str = "",
            modality: List[str] = None,
            device: str = "",
            sampling_rate: float = None,
            n_channels: int = None,
            channel_names: List[str] = None,
            **kwargs
    ) -> Dict[str, Any]:
        """构建meta层"""
        if modality is None:
            modality = []
        if channel_names is None:
            channel_names = []

        meta = {
            "subject_id": subject_id,
            "session_id": session_id,
            "task": task,
            "recording_time": recording_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file_path": file_path,
            "format_version": "1.0",
            "modality": modality,
            "device": device,
            "notes": kwargs.get("notes", "")
        }

        if sampling_rate is not None:
            meta["sampling_rate"] = float(sampling_rate)
        if n_channels is not None:
            meta["n_channels"] = int(n_channels)
        if channel_names:
            meta["channel_names"] = channel_names

        for key, value in kwargs.items():
            if key not in meta and key != "notes":
                meta[key] = value

        return meta

    @staticmethod
    def add_signal(
            data_dict: Dict,
            data: np.ndarray,
            sampling_rate: float,
            channel_names: List[str],
            modality: str,
            signal_type: str = None,
            unit: str = None,
            **signal_info
    ) -> Dict:
        """添加信号到signal层"""
        if sampling_rate is not None and (not np.isfinite(sampling_rate) or sampling_rate <= 0):
            raise ValueError('采样率必须是有限正数')
        if "signal" not in data_dict:
            data_dict["signal"] = {}

        # 验证数据维度
        if data.ndim == 1:
            data = data.reshape(1, -1)
        elif data.ndim == 2 and data.shape[0] > data.shape[1]:
            if len(channel_names) == data.shape[1]:
                data = data.T

        # 验证通道名
        if len(channel_names) != data.shape[0]:
            channel_names = [f"Ch{i + 1}" for i in range(data.shape[0])]

        signal_entry = {
            "data": np.asarray(data, dtype=np.float32),
            "sampling_rate": float(sampling_rate) if sampling_rate is not None else None,
            "channel_names": list(channel_names),
            "signal_type": signal_type or modality.lower(),
            "unit": unit or "unknown",
            "n_channels": data.shape[0],
            "n_samples": data.shape[1],
            "duration": data.shape[1] / sampling_rate if sampling_rate is not None else None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **signal_info
        }

        data_dict["signal"][modality.upper()] = signal_entry

        # 更新meta中的modality列表
        if modality.upper() not in data_dict["meta"].get("modality", []):
            data_dict["meta"].setdefault("modality", []).append(modality.upper())

        return data_dict

    @staticmethod
    def add_event(
            data_dict: Dict,
            event_label: str,
            event_time: float,
            duration: float = 0.0,
            event_id: int = None
    ) -> Dict:
        """添加事件到event层"""
        if "event" not in data_dict:
            data_dict["event"] = {
                "event_id": [],
                "event_label": [],
                "event_time": [],
                "duration": []
            }

        if event_id is None:
            event_id = len(data_dict["event"]["event_id"]) + 1

        data_dict["event"]["event_id"].append(event_id)
        data_dict["event"]["event_label"].append(event_label)
        data_dict["event"]["event_time"].append(event_time)
        data_dict["event"]["duration"].append(duration)

        return data_dict


# ==================== 支持的输入格式 ====================
SUPPORTED_INPUT_FORMATS = {
    'csv': 'CSV文件',
    'tsv': 'TSV文件',
    'txt': '文本文件',
    'xlsx': 'Excel文件',
    'xls': 'Excel文件(旧版)',
    'edf': 'EDF/EDF+格式',
    'bdf': 'BDF格式',
    'gdf': 'GDF格式',
    'set': 'EEGLAB SET格式',
    'vhdr': 'BrainVision头文件',
    'vmrk': 'BrainVision标记文件',
    'eeg': 'BrainVision EEG文件',
    'snirf': 'SNIRF格式',
    'nirs': 'NIRS数据格式',
    'mat': 'MATLAB MAT文件',
    'npy': 'NumPy二进制格式',
    'npz': 'NumPy压缩格式',
    'json': 'JSON格式',
    'pkl': '旧 Pickle（普通导入已禁用）',
}

SUPPORTED_OUTPUT_FORMATS = ['json', 'npz', 'pkl', 'csv', 'tsv', 'mat']


# ==================== 格式检测 ====================
def detect_format(file_path: str) -> str:
    """根据扩展名检测文件格式"""
    path = Path(file_path)
    suffix = path.suffix.lower().lstrip('.')
    return suffix if suffix in SUPPORTED_INPUT_FORMATS else 'unknown'


# ==================== 加载器 ====================
class DataLoader:
    """读取文件 → 标准数据字典"""

    def __init__(self):
        self.builder = DataDictBuilder()

    def load(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """加载文件，返回标准数据字典"""
        format = detect_format(file_path)

        if format == 'unknown':
            raise ValueError(f"不支持的文件格式: {file_path}")

        print(f"读取: {Path(file_path).name} ({format})")

        # 根据格式加载
        if format in ['csv', 'tsv', 'txt']:
            return self._load_text(file_path, format, **kwargs)
        elif format in ['xlsx', 'xls']:
            return self._load_excel(file_path, **kwargs)
        elif format in ['edf', 'bdf', 'gdf']:
            return self._load_edf(file_path, format, **kwargs)
        elif format == 'mat':
            return self._load_mat(file_path, **kwargs)
        elif format in ['npy', 'npz']:
            return self._load_numpy(file_path, **kwargs)
        elif format in ['snirf', 'nirs']:
            return self._load_fnirs(file_path, **kwargs)
        elif format in ['set', 'vhdr', 'eeg']:
            return self._load_eeg(file_path, format, **kwargs)
        elif format == 'json':
            return self._load_json(file_path, **kwargs)
        elif format == 'pkl':
            return self._load_pickle(file_path, **kwargs)
        else:
            raise ValueError(f"未实现加载器: {format}")

    def _load_text(self, file_path: str, format: str, **kwargs) -> Dict:
        """加载文本文件"""
        delimiter = ',' if format == 'csv' else '\t' if format == 'tsv' else kwargs.get('delimiter', ',')

        df = pd.read_csv(file_path, delimiter=delimiter)
        return self._from_dataframe(df, file_path, **kwargs)

    def _from_dataframe(self, df, file_path, **kwargs):
        """仅在内存中解析，不创建源目录临时文件。缺少采样率保持草稿。"""
        data_dict = self.builder.create_empty_data_dict()

        fs = kwargs.get('fs', kwargs.get('sampling_rate'))
        modality = kwargs.get('modality', 'UNKNOWN').upper()
        subject_id = kwargs.get('subject_id', Path(file_path).stem)
        session_id = kwargs.get('session_id', 'session1')
        task = kwargs.get('task', 'unknown')
        unit = kwargs.get('unit', 'unknown')

        signal_cols = kwargs.get('signal_columns', df.columns.tolist())

        if signal_cols:
            data = df[signal_cols].apply(pd.to_numeric, errors='raise').values.T
            self.builder.add_signal(
                data_dict, data, fs, signal_cols, modality,
                signal_type=modality.lower(), unit=unit
            )

        meta = self.builder.build_meta(
            subject_id=subject_id, session_id=session_id, task=task,
            file_path=str(file_path), modality=[modality] if modality != 'UNKNOWN' else [],
            device=kwargs.get('device', ''), sampling_rate=fs,
            n_channels=len(signal_cols), channel_names=signal_cols
        )
        data_dict['meta'] = meta
        return data_dict

    def _load_excel(self, file_path: str, **kwargs) -> Dict:
        """加载Excel文件"""
        sheet_name = kwargs.get('sheet_name', 0)
        df = pd.read_excel(file_path, sheet_name=sheet_name)

        return self._from_dataframe(df, file_path, **kwargs)

    def _load_edf(self, file_path: str, format: str, **kwargs) -> Dict:
        """加载EDF/BDF/GDF文件"""
        try:
            import mne
        except ImportError:
            raise ImportError("请安装mne: pip install mne")

        readers = {
            'edf': mne.io.read_raw_edf,
            'bdf': mne.io.read_raw_bdf,
            'gdf': mne.io.read_raw_gdf
        }

        # 读取文件
        raw = readers[format](file_path, preload=True)
        unit = self._mne_voltage_unit(raw, kwargs.get('unit'))

        # 修复：使用更基础的方法获取数据
        # 方法1：通过索引获取所有通道
        n_channels = len(raw.ch_names)
        n_times = len(raw.times)

        # 创建数据数组
        data = np.zeros((n_channels, n_times))

        # 逐个通道读取数据
        for idx, ch_name in enumerate(raw.ch_names):
            data[idx, :] = raw.get_data(picks=[idx])[0]

        fs = raw.info['sfreq']
        ch_names = raw.ch_names

        data_dict = self.builder.create_empty_data_dict()
        modality = kwargs.get('modality', 'EEG').upper()

        self.builder.add_signal(
            data_dict, data, fs, ch_names, modality,
            signal_type='eeg', unit=unit
        )

        # 获取设备信息（如果可用）
        device_info = raw.info.get('device_info', {})
        device_name = device_info.get('model', 'unknown') if device_info else 'unknown'

        meta = self.builder.build_meta(
            subject_id=kwargs.get('subject_id', Path(file_path).stem),
            session_id=kwargs.get('session_id', 'session1'),
            task=kwargs.get('task', 'unknown'),
            file_path=str(file_path),
            modality=[modality],
            device=device_name,
            sampling_rate=fs,
            n_channels=len(ch_names),
            channel_names=ch_names,
            meas_date=str(raw.info.get('meas_date', '')) if raw.info.get('meas_date') else ''
        )
        data_dict['meta'] = meta

        # 如果有事件/刺激信息，也加载
        try:
            # 尝试查找事件通道
            stim_channels = mne.pick_types(raw.info, stim=True, misc=False)
            if len(stim_channels) > 0:
                events = mne.find_events(raw, stim_channel=stim_channels, verbose=False, shortest_event=1)
                if len(events) > 0:
                    for event in events:
                        self.builder.add_event(
                            data_dict,
                            event_label=f"event_{event[2]}",
                            event_time=event[0] / fs,
                            event_id=event[2]
                        )
        except Exception as e:
            # 如果没有事件信息，忽略
            print(f"没有找到事件信息: {e}")

        return data_dict

    @staticmethod
    def _mne_voltage_unit(raw, declared_unit=None):
        """MNE get_data(units=None) 返回 SI；仅在每通道明示电压时标 V。"""
        from mne._fiff.constants import FIFF
        channels=raw.info.get('chs',[])
        types=raw.get_channel_types()
        electrical={'eeg','eog','ecg','emg','seeg','ecog','dbs'}
        if not channels or any(info.get('unit')!=FIFF.FIFF_UNIT_V for info in channels) or any(kind not in electrical for kind in types):
            raise ValueError('MNE 文件含非电压/未知单位通道；需显式分离通道与单位，未统一标为 V')
        if declared_unit not in (None,'V'):
            raise ValueError('读取器返回 SI 电压 V；不能只改标签冒充其他单位，未缩放数值')
        return 'V'

    def _load_mat(self, file_path: str, **kwargs) -> Dict:
        """加载MAT文件"""
        try:
            import scipy.io
        except ImportError:
            raise ImportError("请安装scipy: pip install scipy")

        mat_data = scipy.io.loadmat(file_path)
        data_dict = self.builder.create_empty_data_dict()

        data_key = kwargs.get('data_key')
        if not data_key:
            for key in mat_data:
                if not key.startswith('__') and isinstance(mat_data[key], np.ndarray):
                    data_key = key
                    break

        if data_key:
            data = mat_data[data_key]
            fs = kwargs.get('fs', kwargs.get('sampling_rate'))

            if data.ndim == 1:
                data = data.reshape(1, -1)
            elif data.ndim == 2 and data.shape[0] > data.shape[1]:
                data = data.T

            ch_names = kwargs.get('channel_names', [f'Ch{i + 1}' for i in range(data.shape[0])])
            modality = kwargs.get('modality', 'UNKNOWN').upper()

            self.builder.add_signal(
                data_dict, data, fs, ch_names, modality,
                signal_type=modality.lower(), unit=kwargs.get('unit', 'unknown')
            )

            meta = self.builder.build_meta(
                subject_id=kwargs.get('subject_id', Path(file_path).stem),
                session_id=kwargs.get('session_id', 'session1'),
                task=kwargs.get('task', 'unknown'),
                file_path=str(file_path),
                modality=[modality] if modality != 'UNKNOWN' else [],
                device='',
                sampling_rate=fs,
                n_channels=data.shape[0],
                channel_names=ch_names
            )
            data_dict['meta'] = meta

        return data_dict

    def _load_numpy(self, file_path: str, **kwargs) -> Dict:
        """普通导入只读取非 object 数组；归档元信息局限于当前文件。"""
        metadata = {}
        if Path(file_path).suffix.lower() == '.npz':
            with np.load(file_path, allow_pickle=False) as archive:
                if '__schema__' in archive.files:
                    return decode_npz(archive)
                arrays = {key: archive[key] for key in archive.files}
            keys = [key for key in ('data','signal','eeg','emg','ecg','fnirs','values','raw') if key in arrays]
            if not keys:
                keys = [key for key,array in arrays.items() if array.ndim >= 1 and array.dtype.kind in 'biufc']
            if len(keys) != 1:
                raise ValueError('旧 NPZ 的数据键不明确；请离线迁移为安全 schema')
            data = arrays.pop(keys[0])
            metadata = {key:array.tolist() for key,array in arrays.items()}
        else:
            data = np.load(file_path, allow_pickle=False)
        if data.dtype.hasobject or data.dtype.kind not in 'biufc':
            raise ValueError('只支持非 object 数值数组')
        if data.ndim == 1:
            data = data.reshape(1,-1)
        if data.ndim != 2 or not all(data.shape):
            raise ValueError('请输入明确的 channels × samples 二维数组')
        fs = kwargs.get('fs', kwargs.get('sampling_rate', metadata.get('fs', metadata.get('sampling_rate'))))
        if fs is not None and (not np.isfinite(fs) or fs <= 0):
            raise ValueError('采样率必须是有限正数')
        channels = kwargs.get('channel_names', metadata.get('channel_names', [f'Ch{i+1}' for i in range(data.shape[0])]))
        if len(channels) != data.shape[0]:
            raise ValueError('通道名称与 channels × samples 轴不一致')
        modality = kwargs.get('modality','UNKNOWN').upper()
        result = self.builder.create_empty_data_dict()
        self.builder.add_signal(result,data,fs,channels,modality,unit=kwargs.get('unit','unknown'))
        # add_signal 保留历史 float32 约定；二维 NumPy 入口不猜测转置。
        result['signal'][modality]['data'] = data.copy()
        result['signal'][modality]['n_channels'], result['signal'][modality]['n_samples'] = data.shape
        result['signal'][modality]['channel_names'] = list(channels)
        result['signal'][modality]['duration'] = data.shape[1]/fs if fs is not None else None
        result['meta'] = self.builder.build_meta(subject_id=kwargs.get('subject_id',Path(file_path).stem),
            session_id=kwargs.get('session_id','session1'),task=kwargs.get('task','unknown'),
            file_path=str(file_path),modality=[modality],sampling_rate=fs,
            n_channels=data.shape[0],channel_names=channels)
        for key,value in metadata.items():
            result['meta'].setdefault(key,value)
        return result

    def _load_fnirs(self, file_path: str, **kwargs) -> Dict:
        raise ValueError('旧 fNIRS 读取器未实现真实信号解析；请使用已有明确元信息的 JSON/NPZ，不能以随机数据替代')

    def _load_eeg(self, file_path: str, format: str, **kwargs) -> Dict:
        """加载EEGLAB/BrainVision文件"""
        try:
            import mne
        except ImportError:
            raise ImportError("请安装mne: pip install mne")

        if format == 'set':
            raw = mne.io.read_raw_eeglab(file_path, preload=True)
        elif format in ['vhdr', 'eeg']:
            raw = mne.io.read_raw_brainvision(file_path, preload=True)
        else:
            raise ValueError(f"不支持的EEG格式: {format}")

        unit = self._mne_voltage_unit(raw, kwargs.get('unit'))
        data = raw.get_data()
        fs = raw.info['sfreq']
        ch_names = raw.ch_names

        data_dict = self.builder.create_empty_data_dict()

        self.builder.add_signal(
            data_dict, data, fs, ch_names, 'EEG',
            signal_type='eeg', unit=unit
        )

        meta = self.builder.build_meta(
            subject_id=kwargs.get('subject_id', Path(file_path).stem),
            session_id=kwargs.get('session_id', 'session1'),
            task=kwargs.get('task', 'unknown'),
            file_path=str(file_path),
            modality=['EEG'],
            device='',
            sampling_rate=fs,
            n_channels=len(ch_names),
            channel_names=ch_names
        )
        data_dict['meta'] = meta
        return data_dict

    def _load_json(self, file_path: str, **kwargs) -> Dict:
        with open(file_path, 'r', encoding='utf-8') as handle:
            return decode_json(json.load(handle))

    def _load_pickle(self, file_path: str, **kwargs) -> Dict:
        raise ValueError('普通导入禁用 pickle；旧对象文件须在独立可信离线流程迁移')


# ==================== 保存器 ====================
class DataSaver:
    """标准数据字典 → 保存为各种格式"""

    @staticmethod
    def save(data_dict: Dict, output_path: str, format: str = 'json', **kwargs):
        """保存数据字典"""
        print(f"💾 保存: {Path(output_path).name} ({format})")

        savers = {
            'json': DataSaver._save_json,
            'npz': DataSaver._save_npz,
            'pkl': DataSaver._save_pickle,
            'csv': DataSaver._save_text,
            'tsv': DataSaver._save_text,
            'mat': DataSaver._save_mat,
        }

        if format not in savers:
            raise ValueError(f"不支持的输出格式: {format}")

        target = Path(output_path)
        descriptor, temporary = tempfile.mkstemp(prefix='.bci-save-', suffix=f'.{format}', dir=str(target.parent))
        os.close(descriptor)
        try:
            savers[format](data_dict, temporary, format, **kwargs)
            if Path(temporary).stat().st_size == 0:
                raise ValueError('没有可保存的数据；未发布空文件')
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)

    @staticmethod
    def _save_json(data_dict: Dict, output_path: str, format: str = None, **kwargs):
        with open(output_path, 'w', encoding='utf-8') as handle:
            json.dump(encode_json(data_dict), handle, indent=2, ensure_ascii=False, allow_nan=False)

    @staticmethod
    def _save_npz(data_dict: Dict, output_path: str, format: str = None, **kwargs):
        np.savez_compressed(output_path, **encode_npz(data_dict))


    @staticmethod
    def _save_pickle(data_dict: Dict, output_path: str, format: str = None, **kwargs):
        """保存为Pickle"""
        with open(output_path, 'wb') as f:
            pickle.dump(data_dict, f)

    @staticmethod
    def _save_text(data_dict: Dict, output_path: str, format: str, **kwargs):
        """保存为文本文件"""
        delimiter = ',' if format == 'csv' else '\t'

        if 'signal' in data_dict and data_dict['signal']:
            modality = list(data_dict['signal'].keys())[0]
            info = data_dict['signal'][modality]

            if 'data' in info:
                data = info['data']
                fs = info.get('sampling_rate', 1)
                ch_names = info.get('channel_names', [])

                df_dict = {'time': np.arange(data.shape[1]) / fs}
                for i, ch in enumerate(ch_names):
                    if i < data.shape[0]:
                        df_dict[ch] = data[i]

                pd.DataFrame(df_dict).to_csv(output_path, sep=delimiter, index=False)

    @staticmethod
    def _save_mat(data_dict: Dict, output_path: str, format: str = None, **kwargs):
        """保存为MAT文件"""
        try:
            import scipy.io
        except ImportError:
            raise ImportError("请安装scipy: pip install scipy")

        mat_dict = {}

        if 'signal' in data_dict and data_dict['signal']:
            modality = list(data_dict['signal'].keys())[0]
            info = data_dict['signal'][modality]

            if 'data' in info:
                mat_dict['data'] = info['data']
                mat_dict['fs'] = info.get('sampling_rate', 1)
                mat_dict['channel_names'] = info.get('channel_names', [])

        mat_dict['meta'] = data_dict.get('meta', {})
        mat_dict['event'] = data_dict.get('event', {})

        scipy.io.savemat(output_path, mat_dict, **kwargs)


# ==================== 转换器 ====================
class Converter:
    """文件格式转换器"""

    def __init__(self):
        self.loader = DataLoader()
        self.saver = DataSaver()

    def convert(self, input_file: str, output_file: str = None,
                output_format: str = 'json', **kwargs) -> Dict:
        """转换文件格式"""
        print(f"\n🚀 开始转换: {input_file}")

        data_dict = self.loader.load(input_file, **kwargs)

        if output_file is None:
            output_file = str(Path(input_file).with_suffix(f'.{output_format}'))

        self.saver.save(data_dict, output_file, output_format, **kwargs)
        print(f"✅ 完成: {input_file} -> {output_file}")

        return data_dict


# ==================== 批量转换器 ====================
class BatchConverter:
    """批量文件转换器"""

    def __init__(self):
        self.converter = Converter()

    def convert_batch(self, input_dir: str, output_dir: str = None,
                      pattern: str = "*", output_format: str = 'json',
                      recursive: bool = False, **kwargs):
        """批量转换目录中的文件"""
        input_path = Path(input_dir)
        if not input_path.exists():
            print(f"❌ 目录不存在: {input_dir}")
            return

        output_path = Path(output_dir) if output_dir else input_path / 'converted'
        output_path.mkdir(parents=True, exist_ok=True)

        files = []
        for ext in SUPPORTED_INPUT_FORMATS.keys():
            if recursive:
                files.extend(input_path.rglob(f"{pattern}.{ext}"))
                files.extend(input_path.rglob(f"{pattern}"))
            else:
                files.extend(input_path.glob(f"{pattern}.{ext}"))
                files.extend(input_path.glob(f"{pattern}"))

        files = list(set(files))

        if not files:
            print(f"⚠️ 未找到文件")
            return

        print(f"📁 找到 {len(files)} 个文件")

        success = 0
        failed = 0

        for i, f in enumerate(files, 1):
            try:
                rel_path = f.relative_to(input_path) if recursive else f.name
                out_file = output_path / f"{f.stem}.{output_format}"

                print(f"\n[{i}/{len(files)}] 🔄 {rel_path}")

                self.converter.convert(str(f), str(out_file), output_format, **kwargs)
                success += 1
            except Exception as e:
                print(f"    ❌ 失败: {str(e)}")
                failed += 1

        print(f"\n{'=' * 50}")
        print(f"📊 批量转换完成")
        print(f"   ✅ 成功: {success}")
        print(f"   ❌ 失败: {failed}")
        print(f"   📁 输出目录: {output_path}")


# ==================== 命令行 ====================
def main():
    parser = argparse.ArgumentParser(
        description='万能生物信号数据转换器 - 纯IO/转换版本',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('input', nargs='?', help='输入文件')
    group.add_argument('-i', '--input-dir', help='输入目录（批量模式）')

    parser.add_argument('-o', '--output', help='输出文件或目录')
    parser.add_argument('-f', '--output-format', default='json',
                        choices=SUPPORTED_OUTPUT_FORMATS,
                        help='输出格式 (默认: json)')

    parser.add_argument('--subject-id', help='被试ID')
    parser.add_argument('--session-id', default='session1', help='会话ID')
    parser.add_argument('--task', help='任务名称')
    parser.add_argument('--modality', help='信号模态 (EEG, EMG, ECG, GSR, FNIRS, ET, RESP)')
    parser.add_argument('--fs', type=float, help='采样率(Hz)')
    parser.add_argument('--unit', help='信号单位')

    parser.add_argument('-p', '--pattern', default='*', help='文件匹配模式 (默认: *)')
    parser.add_argument('-r', '--recursive', action='store_true', help='递归子目录')
    parser.add_argument('--list-formats', action='store_true', help='显示支持的格式')

    args = parser.parse_args()

    if args.list_formats:
        print("📁 支持的输入格式:")
        for fmt, desc in SUPPORTED_INPUT_FORMATS.items():
            print(f"   .{fmt:6} - {desc}")
        print("\n💾 支持的输出格式:")
        for fmt in SUPPORTED_OUTPUT_FORMATS:
            print(f"   {fmt}")
        return 0

    kwargs = {
        'subject_id': args.subject_id,
        'session_id': args.session_id,
        'task': args.task,
        'modality': args.modality,
        'fs': args.fs,
        'unit': args.unit,
    }
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    try:
        if args.input_dir:
            converter = BatchConverter()
            converter.convert_batch(
                args.input_dir, args.output, args.pattern,
                args.output_format, args.recursive, **kwargs
            )
        elif args.input:
            converter = Converter()
            converter.convert(args.input, args.output, args.output_format, **kwargs)
        return 0
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
