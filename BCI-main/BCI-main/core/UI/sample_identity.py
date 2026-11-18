"""分类文件的样本身份协议；不把等长、文件名或导入动作当成匹配证据。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

IDENTITY_COLUMNS={'dataset_id','dataset_version','version','sample_id','sample_ids'}


def _scalar(value):
    if isinstance(value,np.ndarray):
        if value.ndim!=0: raise ValueError('数据集身份/版本必须为标量')
        value=value.item()
    if isinstance(value,np.generic):value=value.item()
    return value


def sample_contract(mapping, required=False):
    fields=('dataset_id','dataset_version','version','sample_ids')
    if not any(name in mapping for name in fields):
        if required:raise ValueError('缺少 dataset_id、dataset_version、sample_ids；旧无 ID 标签不能用于训练')
        return None
    if 'dataset_id' not in mapping or 'sample_ids' not in mapping or not any(k in mapping for k in ('dataset_version','version')):
        raise ValueError('样本身份契约不完整：须提供数据集、版本与有序 sample_ids')
    dataset=_scalar(mapping['dataset_id'])
    version=_scalar(mapping.get('dataset_version',mapping.get('version')))
    if 'dataset_version' in mapping and 'version' in mapping and _scalar(mapping['version'])!=version:
        raise ValueError('两个版本字段冲突')
    if not isinstance(dataset,str) or not dataset.strip():raise ValueError('dataset_id 必须为非空字符串')
    if isinstance(version,bool) or not isinstance(version,int) or version<1:raise ValueError('dataset_version 必须为正整数')
    values=np.asarray(mapping['sample_ids'])
    if values.ndim!=1 or not len(values):raise ValueError('sample_ids 必须是非空一维有序标识')
    ids=values.tolist()
    if any(not isinstance(value,str) or not value.strip() for value in ids) or len(set(ids))!=len(ids):
        raise ValueError('sample_ids 必须为唯一、非空字符串')
    return {'dataset_id':dataset,'dataset_version':version,'sample_ids':tuple(ids)}


def identity_key(contract):
    if contract is None:return None
    return (contract['dataset_id'],contract['dataset_version'],tuple(contract['sample_ids']))


def validate_label_binding(features, labels, feature_contract, label_contract):
    if feature_contract is None or label_contract is None:
        raise ValueError('缺少经核对的样本身份；不能自动绑定无 ID 旧标签')
    if identity_key(feature_contract)!=identity_key(label_contract):
        raise ValueError('标签的数据集、版本或 sample_id 顺序不匹配；请显式核对并重新导出，未自动重排')
    y=np.asarray(labels)
    arrays=list(features.values()) if isinstance(features,dict) else [features]
    size=len(feature_contract['sample_ids'])
    if y.ndim!=1 or len(y)!=size or not arrays or any(np.asarray(array).ndim<2 or len(array)!=size for array in arrays):
        raise ValueError('特征、标签与 sample_ids 的观察数不一致')
    if y.dtype.kind in 'biufc' and not np.isfinite(y).all():raise ValueError('标签含非有限值')
    if y.dtype.kind not in 'biufcUS':raise ValueError('标签须为数值或字符串类别，不能包含对象/缺失值')


def _csv_mapping(path):
    frame=pd.read_csv(path,dtype={'dataset_id':'string','sample_id':'string'})
    mapping={}
    for key in ('dataset_id','dataset_version','version'):
        if key in frame:
            values=frame[key].drop_duplicates().tolist()
            if len(values)!=1:raise ValueError(f'CSV {key} 必须在整个文件中一致')
            mapping[key]=values[0]
    if 'sample_id' in frame:mapping['sample_ids']=frame['sample_id'].tolist()
    if 'label' in frame:mapping['labels']=frame['label'].to_numpy()
    if 'labels' in mapping and mapping['labels'].dtype.hasobject:
        if all(isinstance(value,str) for value in mapping['labels']):
            mapping['labels']=np.asarray(mapping['labels'].tolist(),dtype=str)
    columns=[key for key in frame if key not in IDENTITY_COLUMNS and key!='label']
    if columns:mapping['features']=frame[columns].apply(pd.to_numeric,errors='raise').to_numpy()
    return mapping


def _load_mapping(path):
    suffix=Path(path).suffix.lower()
    if suffix=='.npz':
        with np.load(path,allow_pickle=False) as archive:return {key:archive[key] for key in archive.files}
    if suffix=='.json':
        with open(path,encoding='utf-8') as handle:return json.load(handle)
    if suffix=='.csv':return _csv_mapping(path)
    return None


def load_feature_samples(path):
    suffix=Path(path).suffix.lower()
    if suffix=='.npy':return np.load(path,allow_pickle=False),None,None
    data=_load_mapping(path)
    if isinstance(data,list):return np.asarray(data),None,None
    if not isinstance(data,dict):raise ValueError('请选择 NPY/NPZ/JSON/CSV 特征文件')
    contract=sample_contract(data)
    features=data.get('features',data.get('X'))
    if features is None:
        if any(key in data for key in ('meta','signal','event','processed')):
            raise ValueError('信号归档不是分类样本；请先显式导出样本特征与身份')
        reserved=IDENTITY_COLUMNS|{'labels','y'}
        features={key:np.asarray(value,dtype=float) for key,value in data.items() if key not in reserved}
        if not features:raise ValueError('文件缺少 features/X')
    elif isinstance(features,dict):features={key:np.asarray(value,dtype=float) for key,value in features.items()}
    else:features=np.asarray(features)
    labels=data.get('labels',data.get('y'))
    if labels is not None:labels=np.asarray(labels)
    return features,labels,contract


def load_label_samples(path):
    data=_load_mapping(path)
    if not isinstance(data,dict):raise ValueError('标签须为带 dataset_id/version/sample_ids 的 NPZ/JSON/CSV；无身份旧标签已禁用')
    contract=sample_contract(data,required=True)
    labels=data.get('labels',data.get('y'))
    if labels is None:raise ValueError('标签文件须有 labels/y；CSV 使用明确 label 列')
    return np.asarray(labels),contract
