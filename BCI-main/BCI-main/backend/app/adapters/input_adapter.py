"""仅解析安全格式；不猜测采样率、单位、模态、轴顺序或标签含义。"""
import io
import csv
import json
import math
from pathlib import PurePosixPath
import zipfile

import numpy as np
import pandas as pd

from backend.app.domain.models import AppError, Metadata

FORMATS = ['.npy', '.npz', '.json', '.csv', '.tsv', '.xlsx']


def validate_table_header(header):
    if not header or any(not isinstance(value, str) or not value.strip() for value in header):
        raise AppError('invalid_input', '表格首行必须为明确、非空的文字列名；无表头文件请先添加表头')
    names = [value.strip() for value in header]
    if len(set(names)) != len(names):
        raise AppError('invalid_input', '表格包含重复列名，请明确映射后重新导入')
    for value in names:
        try:
            float(value)
        except ValueError:
            continue
        raise AppError('invalid_input', '表格首行含数值列名，可能没有表头；请显式添加文字列名，避免丢失首行样本')


def check_numpy_header(stream, limit, *, numeric=True):
    version = np.lib.format.read_magic(stream)
    if version not in ((1, 0), (2, 0), (3, 0)):
        raise AppError('invalid_input', '不支持的 NumPy 版本')
    shape, _, dtype = np.lib.format._read_array_header(stream, version, max_header_size=16384)
    if math.prod(shape) > limit or dtype.itemsize * math.prod(shape) > limit * 16:
        raise AppError('upload_limit', 'NumPy 声明的数组规模超限', 413)
    if dtype.hasobject or (numeric and dtype.kind not in 'iuf'):
        raise AppError('invalid_input', '禁止对象反序列化，仅接受数值数组')
    stream.seek(0)


def check_json_schema_arrays(document, limit):
    """在恢复旧安全 schema 数组前检查声明规模，防止 dtype 子数组扩张。"""
    pending = [(document, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 64:
            raise AppError('invalid_input', 'JSON 嵌套层级过深')
        if isinstance(value, dict):
            if '__ndarray__' in value:
                shape = value.get('shape')
                if not isinstance(shape, list) or any(not isinstance(size, int) or isinstance(size, bool) or size < 0 for size in shape):
                    raise AppError('invalid_input', '安全数组 shape 不合法')
                dtype = np.dtype(value.get('dtype'))
                elements = math.prod(shape)
                if elements > limit or elements * dtype.itemsize > limit * 16 or dtype.subdtype is not None:
                    raise AppError('upload_limit', 'JSON 数组声明的尺寸或 dtype 展开规模超限', 413)
                if dtype.hasobject:
                    raise AppError('invalid_input', '安全 JSON 不接受对象数组')
            pending.extend((item, depth + 1) for item in value.values() if isinstance(item, (dict, list)))
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value if isinstance(item, (dict, list)))


def numeric_array(value, limit):
    array = np.asarray(value)
    if array.dtype.kind not in 'iuf' or array.ndim not in (1, 2, 3) or not array.size or array.size > limit or any(x == 0 for x in array.shape):
        raise AppError('invalid_input', '仅支持有限大小的 1–3 维实数数组，禁止对象、空数组和复数')
    if not np.isfinite(array).all():
        raise AppError('invalid_input', '数组包含 NaN 或无穷值，请核对源数据；应用不会补零')
    return array


def check_zip(payload, max_bytes):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        if len(entries) > 256 or sum(item.file_size for item in entries) > max_bytes:
            raise AppError('upload_limit', '压缩文件展开规模超限', 413)
        for item in entries:
            path = PurePosixPath(item.filename.replace('\\', '/'))
            if path.is_absolute() or '..' in path.parts or item.flag_bits & 1:
                raise AppError('invalid_input', '压缩文件包含不允许的路径或加密条目')


def parse_input(payload: bytes, suffix: str, settings):
    if suffix not in FORMATS:
        raise AppError('unsupported_format', '支持 NPY、受控 NPZ、JSON、数值 CSV/TSV 和 XLSX；不接受 pickle')
    meta, provenance, declared_mode = {}, {}, None
    try:
        if suffix in ('.npz', '.xlsx'):
            check_zip(payload, settings.max_array_elements * 16 + 2_000_000)
        if suffix == '.npy':
            stream = io.BytesIO(payload)
            check_numpy_header(stream, settings.max_array_elements)
            array = np.load(stream, allow_pickle=False)
        elif suffix == '.npz':
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                for entry in archive.infolist():
                    if not entry.filename.endswith('.npy'):
                        raise AppError('invalid_input', 'NPZ 包含非数组条目')
                    with archive.open(entry) as stream:
                        check_numpy_header(stream, settings.max_array_elements, numeric=False)
            with np.load(io.BytesIO(payload), allow_pickle=False) as archive:
                keys = archive.files
                if '__schema__' in keys:
                    from core.io.serialization import decode_npz
                    array, meta, provenance = extract_bci_document(decode_npz(archive))
                elif 'metadata' in keys and 'data' in keys:
                    metadata_array = archive['metadata']
                    if metadata_array.dtype.kind not in 'US' or metadata_array.ndim != 0:
                        raise AppError('invalid_input', 'metadata 必须是 JSON 字符串标量')
                    document = json.loads(str(metadata_array.item()))
                    if not isinstance(document, dict):
                        raise AppError('invalid_input', 'metadata JSON 必须是对象')
                    declared_mode = document.get('data_mode')
                    meta = document.get('metadata', document)
                    provenance = document.get('provenance', {})
                    array = archive['data']
                elif keys == ['data'] or (len(keys) == 1 and keys[0] == 'arr_0'):
                    array = archive[keys[0]]
                else:
                    raise AppError('invalid_input', 'NPZ 需要 data 数值数组与可选 metadata JSON 字符串；多数组需显式离线映射，不能猜测输入')
        elif suffix == '.json':
            document = json.loads(payload.decode('utf-8-sig'))
            if not isinstance(document, dict):
                raise AppError('invalid_input', 'JSON 必须包含 data 与 metadata 对象')
            declared_mode = document.get('data_mode')
            if document.get('format') == 'bci-data-dict':
                from core.io.serialization import decode_json
                check_json_schema_arrays(document, settings.max_array_elements)
                array, meta, provenance = extract_bci_document(decode_json(document))
            elif 'data' in document:
                array = document['data']
                meta = document.get('metadata', {})
                provenance = document.get('provenance', {})
            elif 'signal' in document:
                array, meta, provenance = extract_bci_document(document)
            else:
                raise AppError('invalid_input', 'JSON 缺少 data 或 signal')
        else:
            if suffix == '.xlsx':
                header = pd.read_excel(io.BytesIO(payload), header=None, nrows=1).values.tolist()
                validate_table_header(header[0] if header else [])
                frame = pd.read_excel(io.BytesIO(payload))
            else:
                separator = '\t' if suffix == '.tsv' else ','
                header = next(csv.reader(io.StringIO(payload.decode('utf-8-sig')), delimiter=separator), [])
                validate_table_header(header)
                frame = pd.read_csv(io.BytesIO(payload), sep=separator)
            if frame.columns.has_duplicates:
                raise AppError('invalid_input', '表格包含重复列')
            array = frame.apply(pd.to_numeric, errors='raise').to_numpy()
            provenance = {'column_names': [str(x) for x in frame.columns], 'table_orientation': 'rows_by_columns'}
        array = numeric_array(array, settings.max_array_elements)
        if not isinstance(meta, dict) or not isinstance(provenance, dict):
            raise AppError('invalid_input', 'metadata 与 provenance 必须是 JSON 对象')
        source_mode = provenance.get('data_mode')
        if declared_mode is not None:
            if declared_mode not in ('real', 'demo') or (source_mode is not None and source_mode != declared_mode):
                raise AppError('mode_conflict', '文件内来源模式无效或互相冲突')
            provenance = {**provenance, 'data_mode': declared_mode}
        if provenance.get('data_mode') not in (None, 'real', 'demo'):
            raise AppError('mode_conflict', '文件内来源模式必须明确为 real 或 demo')
        metadata = Metadata.model_validate(meta)
        # 来源元信息可保留，但不允许内嵌大块数值，避免绕过工件限制。
        if len(json.dumps(provenance, ensure_ascii=False, allow_nan=False)) > 100_000:
            raise AppError('invalid_input', '来源元信息过大，请将数值保存在受控工件中')
        return array, metadata, provenance
    except AppError:
        raise
    except (ValueError, TypeError, KeyError, OSError, zipfile.BadZipFile, UnicodeError) as exc:
        raise AppError('invalid_input', '文件无法安全解析，请核对格式、元信息及数值类型', details={'error_type': type(exc).__name__}) from exc


def extract_bci_document(document):
    signals = document['signal']
    if set(signals) != {'EEG'}:
        raise AppError('invalid_input', '四层数据当前只接受单一 EEG；多模态请使用研究工具显式选择')
    signal = signals['EEG']
    unit = signal.get('unit')
    meta = {'kind': 'eeg', 'modality': 'EEG', 'channels': signal.get('channel_names', []),
            'unit': None if unit in ('unknown', '') else unit, 'sampling_rate': signal.get('sampling_rate')}
    provenance = {key: value for key, value in document.items() if key != 'signal'}
    provenance['signal_metadata'] = {key: value for key, value in signal.items() if key != 'data'}
    # 不依赖文件名识别模拟来源；传播文件内显式标记。
    if document.get('meta', {}).get('data_mode') == 'demo':
        provenance['data_mode'] = 'demo'
    return signal['data'], meta, provenance


def validation_errors(metadata: Metadata, shape: list[int]) -> list[str]:
    errors = []
    for field, title in [('display_code', '数据编码'), ('modality', '模态'), ('kind', '输入类型'), ('axes', '轴定义'), ('unit', '单位'), ('sample_ids', '样本或时间窗标识'), ('label_space', '标签空间')]:
        if not getattr(metadata, field):
            errors.append(f'缺少{title}')
    required_axes = {'eeg': {'channel', 'time'}, 'features': {'sample', 'feature'}, 'band_features': {'sample', 'channel', 'band'}}.get(metadata.kind)
    if required_axes and (len(metadata.axes) != len(shape) or set(metadata.axes) != required_axes):
        errors.append('轴定义与输入类型或数组维度不一致')
    axes = dict(zip(metadata.axes, shape, strict=False))
    if metadata.kind in ('eeg', 'band_features'):
        if metadata.modality != 'EEG':
            errors.append('脑电输入必须明确标记 EEG')
        if metadata.sampling_rate is None:
            errors.append('缺少原始采样率；不会默认 1000 Hz')
        if not metadata.channels or len(metadata.channels) != axes.get('channel'):
            errors.append('通道数量与 channel 轴不一致')
    if metadata.kind == 'eeg' and metadata.unit not in ('uV', 'mV', 'V'):
        errors.append('EEG 波形单位仅支持 V、mV、uV')
    if metadata.kind == 'features':
        if not metadata.feature_names or len(metadata.feature_names) != axes.get('feature'):
            errors.append('特征名称数量与 feature 轴不一致')
    if metadata.kind == 'band_features' and (len(metadata.bands) != axes.get('band') or len(metadata.bands) != 5):
        errors.append('频带轴需要明确完整的五频带顺序')
    count = 1 if metadata.kind == 'eeg' else axes.get('sample')
    if len(metadata.sample_ids) != count:
        errors.append('样本或时间窗标识数量与输入不一致')
    if metadata.labels is not None or metadata.label_sample_ids is not None:
        if metadata.label_sample_ids != metadata.sample_ids or len(metadata.labels or []) != len(metadata.sample_ids):
            errors.append('特征与标签必须按相同顺序的 sample_id 绑定，不能只比较长度')
        if any(label not in metadata.label_space for label in metadata.labels or []):
            errors.append('标签超出已声明标签空间')
    return errors


def preview_rms(row):
    """用原始样点计算 RMS，分块并缩放以避免大数组复制和平方溢出。"""
    scale = max(abs(float(row.min())), abs(float(row.max())))
    if scale == 0:
        return 0.0
    sum_squares = 0.0
    block_size = 65536
    for start in range(0, row.size, block_size):
        block = np.divide(row[start:start + block_size], scale, dtype=np.float64)
        np.square(block, out=block)
        sum_squares += float(block.sum())
    return scale * math.sqrt(min(1.0, sum_squares / row.size))


def preview_array(array, metadata: Metadata, max_points: int):
    """仅显示抽样：每桶保留极小/极大及原始索引，不修改原工件。"""
    if metadata.kind == 'eeg' and set(metadata.axes) == {'channel', 'time'} and array.ndim == 2:
        signals = array if metadata.axes == ['channel', 'time'] else array.T
        series = []
        for channel, row in enumerate(signals[:8]):
            if row.size <= max_points:
                indices = np.arange(row.size)
            else:
                edges = np.linspace(0, row.size, max_points // 2 + 1, dtype=int)
                positions = []
                for start, end in zip(edges[:-1], edges[1:]):
                    chunk = row[start:end]
                    positions.extend((start + int(np.argmin(chunk)), start + int(np.argmax(chunk))))
                indices = np.unique(positions)
            series.append({'name': metadata.channels[channel] if channel < len(metadata.channels) else f'通道索引 {channel}',
                           'rms': preview_rms(row),
                           'points': [[float(i / metadata.sampling_rate) if metadata.sampling_rate else int(i), float(row[i])] for i in indices]})
        return {'kind': 'waveform', 'series': series, 'x_unit': 's' if metadata.sampling_rate else 'sample index', 'unit': metadata.unit,
                'channel_count': signals.shape[0], 'sample_count': signals.shape[1],
                'method': '每桶极小/极大包络，保留峰值及原始时刻；最多显示前 8 通道', 'original_shape': list(array.shape)}
    return {'kind': 'table', 'values': array.reshape(array.shape[0], -1)[:12, :12].tolist(),
            'method': '仅预览前 12 行、12 列；未确认轴前不绘制波形', 'original_shape': list(array.shape), 'unit': metadata.unit}

