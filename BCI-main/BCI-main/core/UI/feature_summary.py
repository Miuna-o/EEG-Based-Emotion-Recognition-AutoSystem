"""特征到查看长表的导出边界；不将全局值复制成通道独立观测。"""
import numpy as np


def get_modality_features(data, modality):
    """统一既有 feature[modality] 与旧 features 平坦字典的读取边界。"""
    processed=data.get('processed',{})
    mapping=processed.get('feature')
    if mapping is None: mapping=processed.get('features')
    if not isinstance(mapping,dict) or not mapping:
        raise ValueError('缺少真实特征数据；请先提取特征')
    matched=next((key for key in mapping if str(key).lower()==str(modality).lower()),None)
    if matched is not None:
        mapping=mapping[matched]
    elif any(str(key).lower() in ('eeg','ecg','emg','fnirs','nirs') for key in mapping):
        raise ValueError(f'当前模态 {modality} 没有已提取特征')
    if not isinstance(mapping,dict) or not mapping:
        raise ValueError('当前数据不是通道特征字典；分类样本矩阵需使用分类结果视图')
    return mapping


def feature_summary_rows(features, modality, channels):
    rows=[]
    def visit(mapping,path=()):
        for key,value in mapping.items():
            if isinstance(value,dict):
                visit(value,path+(str(key),));continue
            name=str(key);channel='Global'
            # 使用实际通道名称前缀，不依赖 Ch1/F3 启发式编号。
            for ch in sorted(channels,key=len,reverse=True):
                if name.startswith(str(ch)+'_'):
                    channel=str(ch);name=name[len(str(ch))+1:];break
            array=np.asarray(value)
            if array.ndim==0 and array.dtype.kind in 'biuf':
                values=[(channel,float(array))]
            else:
                continue  # 矩阵/连接性等留在 NPZ；不猜测统计观察单位。
            for ch,val in values:
                rows.append({'Modality':modality,'Category':'/'.join(path) or 'feature',
                    'Channel':ch,'Feature':name,'Value':val,'Data_Type':'float',
                    'Scope':'global' if ch=='Global' else 'channel','Unit':None})
    visit(features)
    return rows
