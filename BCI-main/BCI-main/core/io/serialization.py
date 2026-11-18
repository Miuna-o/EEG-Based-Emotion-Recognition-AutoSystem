"""安全四层数据字典序列化；不使用 pickle，保留 ndarray 的 dtype 和形状。"""
import json
import copy
import numpy as np
import datetime
from enum import Enum
from core.io.enum_schema import enum_descriptor
from core.io.signal_layout import validate_signal_layout

FORMAT = 'bci-data-dict'
VERSION = 2


def normalize_data_dict(data):
    """兼容旧 JSON：仅归一化信号数组，不猜测轴或单位，不篡改已有元信息。"""
    if not isinstance(data, dict):
        raise ValueError('数据必须是四层字典')
    result = copy.deepcopy(data)
    for key in ('meta', 'signal', 'event', 'processed'):
        result.setdefault(key, {})
        if not isinstance(result[key], dict):
            raise ValueError(f'{key} 必须是字典')
    for modality, info in result['signal'].items():
        if not isinstance(info, dict) or 'data' not in info:
            raise ValueError(f'{modality} 缺少信号数据')
        array = np.asarray(info['data'])
        if array.dtype.hasobject or array.dtype.kind not in 'biufc':
            raise ValueError('信号必须为非 object 数值数组')
        if array.ndim == 1:
            array = array.reshape(1, -1)
        validate_signal_layout(modality,info,array)
        info['data'] = array
        rate = info.get('sampling_rate')
        if rate is not None and (not np.isfinite(rate) or rate <= 0):
            raise ValueError('采样率必须是正的有限数值')
    return result


def _encode(value, arrays=None):
    if isinstance(value,Enum):
        type_name=type(value).__module__+'.'+type(value).__qualname__
        enum_descriptor(type_name,value.name,value.value)
        return {'__enum__':{'type':type_name,'name':value.name,'value':value.value}}
    if isinstance(value,np.datetime64):
        return {'__datetime64__':{'dtype':value.dtype.str,'value':str(value)}}
    if isinstance(value,(datetime.datetime,datetime.date,datetime.time)):
        return {'__datetime__':{'type':type(value).__name__,'value':value.isoformat()}}
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise ValueError('不能序列化 object 数组')
        marker = {'dtype':value.dtype.str, 'shape':list(value.shape)}
        if arrays is None:
            marker['__ndarray__'] = True
            marker['values'] = _encode(value.tolist())
        else:
            key = f'array_{len(arrays)}'
            arrays[key] = value
            marker['__ndarray__'] = key
        return marker
    if isinstance(value, np.generic):
        return _encode(value.item(), arrays)
    if isinstance(value, complex):
        return {'__complex__':[value.real,value.imag]}
    if isinstance(value, float) and not np.isfinite(value):
        return {'__float__':'nan' if np.isnan(value) else 'inf' if value>0 else '-inf'}
    if isinstance(value, tuple):
        return {'__tuple__':[_encode(v, arrays) for v in value]}
    if isinstance(value, dict):
        if any(str(key) in ('__ndarray__','__complex__','__tuple__','__float__','__mapping__','__enum__','__datetime__','__datetime64__') for key in value):
            return {'__mapping__':[[str(k),_encode(v,arrays)] for k,v in value.items()]}
        return {str(k):_encode(v,arrays) for k,v in value.items()}
    if isinstance(value, list):
        return [_encode(v,arrays) for v in value]
    if value is None or isinstance(value,(str,int,float,bool)):
        return value
    raise ValueError(f'不支持的元信息类型：{type(value).__name__}')


def _decode(value, arrays=None):
    if isinstance(value,list):
        return [_decode(v,arrays) for v in value]
    if not isinstance(value,dict):
        return value
    if set(value)=={'__enum__'}:
        descriptor=value['__enum__']
        if not isinstance(descriptor,dict) or set(descriptor)!={'type','name','value'}:
            raise ValueError('Enum 数据描述无效')
        return enum_descriptor(descriptor['type'],descriptor['name'],descriptor['value'])
    if set(value)=={'__datetime64__'}:
        descriptor=value['__datetime64__'];dtype=np.dtype(descriptor['dtype'])
        if dtype.kind!='M': raise ValueError('时间标记 dtype 必须为 datetime64')
        return np.asarray(descriptor['value'],dtype=dtype)[()]
    if set(value)=={'__datetime__'}:
        descriptor=value['__datetime__']
        cls={'datetime':datetime.datetime,'date':datetime.date,'time':datetime.time}.get(descriptor['type'])
        if cls is None: raise ValueError('不支持的标准时间类型')
        return cls.fromisoformat(descriptor['value'])
    if set(value)=={'__mapping__'}:
        return {k:_decode(v,arrays) for k,v in value['__mapping__']}
    if '__ndarray__' in value:
        dtype = np.dtype(value['dtype'])
        if dtype.hasobject: raise ValueError('拒绝 object 数组')
        if arrays is None:
            result=np.asarray(_decode(value['values']),dtype=dtype).reshape(value['shape'])
        else:
            result=np.asarray(arrays[value['__ndarray__']])
            if result.dtype != dtype or list(result.shape) != value['shape']:
                raise ValueError('数组与 schema 的 dtype/shape 不一致')
            result=result.copy()
        return result
    if set(value)=={'__tuple__'}: return tuple(_decode(v,arrays) for v in value['__tuple__'])
    if set(value)=={'__complex__'}: return complex(*value['__complex__'])
    if set(value)=={'__float__'}: return float(value['__float__'])
    return {k:_decode(v,arrays) for k,v in value.items()}


def encode_json(data):
    """返回可 JSON 编码的 dict；调用方负责 UTF-8 写文件。"""
    return {'format':FORMAT,'version':VERSION,'payload':_encode(data)}


def decode_json(data):
    """接收已解析的 JSON dict（或 JSON 字符串），返回归一化四层字典。"""
    if isinstance(data,str): data=json.loads(data)
    if isinstance(data,dict) and data.get('format')==FORMAT:
        if data.get('version')!=VERSION: raise ValueError('不支持的 schema 版本')
        data=_decode(data['payload'])
    return normalize_data_dict(data)


def encode_npz(data):
    """返回可以传入 np.savez_compressed 的纯数值/Unicode 数组映射。"""
    arrays={}
    schema={'format':FORMAT,'version':VERSION,'payload':_encode(data,arrays)}
    arrays['__schema__']=np.asarray(json.dumps(schema,ensure_ascii=False,allow_nan=False))
    return arrays


def decode_npz(archive):
    """接收 allow_pickle=False 打开的 NpzFile 或 array dict；不负责关闭文件。"""
    if '__schema__' not in archive: raise ValueError('缺少安全 NPZ schema')
    schema=json.loads(str(np.asarray(archive['__schema__']).item()))
    if schema.get('format')!=FORMAT or schema.get('version')!=VERSION:
        raise ValueError('不支持的 NPZ schema')
    for key in archive.keys():
        if np.asarray(archive[key]).dtype.hasobject: raise ValueError('拒绝 object 数组')
    return normalize_data_dict(_decode(schema['payload'],archive))
