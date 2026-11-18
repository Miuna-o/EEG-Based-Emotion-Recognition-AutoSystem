"""按已声明模态校验数组轴；不转置、展平或推断波长轴。"""
import numpy as np


def validate_signal_layout(modality, info, array):
    if array.dtype.hasobject or array.dtype.kind not in 'biufc' or not all(array.shape):
        raise ValueError('信号需为非空、非 object 数值数组')
    expected=('channels','samples')
    if array.ndim==3 and str(modality).lower() in ('fnirs','nirs'):
        expected=('channels','wavelengths','samples')
        channels=info.get('channel_names')
        wavelengths=info.get('wavelengths')
        if channels is None or len(channels)!=array.shape[0]:
            raise ValueError('fNIRS 三维输入须明确与 C 轴等长的通道名称')
        if wavelengths is None or len(wavelengths)!=array.shape[1]:
            raise ValueError('fNIRS 三维输入须明确与 W 轴等长的波长')
        values=np.asarray(wavelengths,dtype=float)
        if values.ndim!=1 or not np.isfinite(values).all() or (values<=0).any():
            raise ValueError('波长须为有限正数，单位 nm')
    elif array.ndim!=2:
        raise ValueError('仅接受 channels × samples，或元信息明确的 fNIRS C×W×T')
    order=info.get('axis_order')
    if order is not None:
        aliases={'channel':'channels','sample':'samples','time':'samples','wavelength':'wavelengths'}
        if isinstance(order,str):
            order={'CT':['channels','samples'],'CWT':['channels','wavelengths','samples']}.get(order,order.split(','))
        normalized=tuple(aliases.get(str(value).strip(),str(value).strip()) for value in order)
        if normalized!=expected:
            raise ValueError('axis_order 与冻结模态接口不一致；不能自动换轴')
    return expected
