"""冻结预处理接口的有限 Enum 数据白名单；读取文件不会导入 Enum 类。"""
ENUM_TYPES = {
    'preprocessing.FilterType': {'BUTTERWORTH':'butterworth','CHEBYSHEV1':'chebyshev1',
        'CHEBYSHEV2':'chebyshev2','BESSEL':'bessel','ELLIPTIC':'elliptic','FIR':'fir'},
    'preprocessing.WaveletType': {'DB1':'db1','DB2':'db2','DB4':'db4','DB6':'db6','DB8':'db8',
        'SYM4':'sym4','SYM8':'sym8','COIF1':'coif1','COIF3':'coif3','HAAR':'haar'},
    'preprocessing.DetrendMethod': {'LINEAR':'linear','CONSTANT':'constant','POLY':'polynomial','SPLINE':'spline'},
    'eeg_preprocessing.ReferenceType': {'AVERAGE':'average','LINKED_MASTOIDS':'linked_mastoids',
        'CZ':'cz','REST':'rest','NONE':'none'},
    'eeg_preprocessing.ICAMethod': {'INFOMAX':'infomax','FASTICA':'fastica','PICARD':'picard',
        'EXTENDED_INFOMAX':'extended_infomax'},
    'eeg_preprocessing.ArtifactRemovalMethod': {'ICA_AUTO':'ica_auto','ICA_MANUAL':'ica_manual',
        'REGRESSION':'regression','SSP':'ssp','ASR':'asr','ADAPTIVE':'adaptive'},
    'emg_preprocessing.RectificationMethod': {'NONE':'none','FULL_WAVE':'full_wave','HALF_WAVE':'half_wave',
        'SQUARE':'square','ROOT_MEAN_SQUARE':'rms'},
    'emg_preprocessing.EnvelopeExtractionMethod': {'NONE':'none','MOVING_AVERAGE':'moving_average',
        'LOWPASS':'lowpass','HILBERT':'hilbert','TEAGER_KAISER':'teager_kaiser','ABSOLUTE':'absolute'},
    'emg_preprocessing.MuscleActivationDetectionMethod': {'NONE':'none','THRESHOLD':'threshold',
        'STATISTICAL':'statistical','DOUBLE_THRESHOLD':'double_threshold','TEAGER_KAISER':'teager_kaiser','WAVELET':'wavelet'},
    'ecg_preprocessing.ECGQualityFlag': {'EXCELLENT':'excellent','GOOD':'good','FAIR':'fair','POOR':'poor','UNUSABLE':'unusable'},
    'fnirs_preprocessing.MotionCorrectionMethod': {'SPLINE':'spline','PCA':'pca','WAVELET':'wavelet','HMP':'hmp'},
    'fnirs_preprocessing.OpticalModel': {'MODIFIED_BEER_LAMBERT':'modified_beer_lambert','SPATIALLY_RESOLVED':'spatially_resolved'},
    'multimodal_preprocessing.ProcessingMode': {'SEQUENTIAL':'sequential','PARALLEL':'parallel','SELECTIVE':'selective'},
    'multimodal_preprocessing.TimeSyncMethod': {'RESAMPLE':'resample','INTERPOLATE':'interpolate','EVENT_ALIGN':'event_align','NONE':'none'},
}
ENUM_TYPES = {'core.processing.preprocessing.'+key:value for key,value in ENUM_TYPES.items()}


def enum_descriptor(type_name, member_name, value):
    if not all(isinstance(item,str) for item in (type_name,member_name,value)):
        raise ValueError('Enum 类型、成员和值必须为白名单字符串')
    members = ENUM_TYPES.get(type_name)
    if members is None or member_name not in members or members[member_name] != value:
        raise ValueError('Enum 类型、成员或值不属于冻结接口白名单')
    return {'enum_type':type_name,'enum_name':member_name,'enum_value':value}
