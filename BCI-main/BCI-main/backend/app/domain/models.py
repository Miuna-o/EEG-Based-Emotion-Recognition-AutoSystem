"""传输与持久化契约。缺失证据保持 None，绝不补零或估算。"""
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = '1.0'
BANDS = ['delta', 'theta', 'alpha', 'beta', 'gamma']
TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted'}
TRANSITIONS = {
    'queued': {'running', 'cancelled', 'interrupted'},
    'running': {'cancelling', 'succeeded', 'failed', 'interrupted'},
    'cancelling': {'cancelled', 'interrupted'},
    'succeeded': set(), 'failed': set(), 'cancelled': set(), 'interrupted': set(),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f'{prefix}_{uuid4().hex}'


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Metadata(Contract):
    display_code: str = Field(default='', max_length=80)
    modality: Literal['EEG', 'FEATURES'] | None = None
    kind: Literal['eeg', 'features', 'band_features'] | None = None
    axes: list[str] = Field(default_factory=list, max_length=3)
    sampling_rate: float | None = Field(default=None, gt=0, le=100000)
    channels: list[str] = Field(default_factory=list, max_length=1024)
    bands: list[Literal['delta', 'theta', 'alpha', 'beta', 'gamma']] = Field(default_factory=list)
    unit: Literal['uV', 'mV', 'V', 'dimensionless', 'uV^2', 'uV^2/Hz', 'bit', 'nat'] | None = None
    feature_names: list[str] = Field(default_factory=list, max_length=10000)
    sample_ids: list[str] = Field(default_factory=list, max_length=100000)
    label_space: list[str] = Field(default_factory=list, max_length=100)
    labels: list[str] | None = Field(default=None, max_length=100000)
    label_sample_ids: list[str] | None = Field(default=None, max_length=100000)
    source_description: str = Field(default='', max_length=300)

    @field_validator('axes', 'channels', 'bands', 'feature_names', 'sample_ids', 'label_space')
    @classmethod
    def unique_names(cls, value):
        if len(set(value)) != len(value) or any(not str(x).strip() or len(str(x)) > 128 for x in value):
            raise ValueError('名称必须非空、唯一且不超过 128 字符')
        return value


class Artifact(Contract):
    id: str
    sha256: str
    shape: list[int]
    dtype: str
    size_bytes: int
    created_at: str


class Dataset(Contract):
    id: str
    version: int
    schema_version: str = SCHEMA_VERSION
    data_mode: Literal['real', 'demo']
    session_id: str
    source_hash: str
    source_format: str
    artifact_id: str
    shape: list[int]
    dtype: str
    metadata: Metadata
    provenance: dict[str, Any] = Field(default_factory=dict)
    validation_status: Literal['draft', 'ready']
    validation_errors: list[str]
    quality: dict[str, Any]
    created_at: str


class Session(Contract):
    id: str
    dataset_id: str
    data_mode: Literal['real', 'demo']
    created_at: str


class MetadataPatch(Contract):
    expected_version: int = Field(ge=1)
    metadata: dict[str, Any]


class JobRequest(Contract):
    dataset_id: str
    dataset_version: int = Field(ge=1)
    provider: Literal['real', 'demo']
    idempotency_key: str = Field(min_length=1, max_length=128)


class Job(Contract):
    id: str
    display_code: str | None = None
    dataset_id: str
    dataset_version: int
    input_hash: str
    provider: Literal['real', 'demo']
    data_mode: Literal['real', 'demo']
    status: Literal['queued', 'running', 'cancelling', 'succeeded', 'failed', 'cancelled', 'interrupted']
    stage: str
    attempt: int = 1
    retry_of: str | None = None
    processed_count: int = 0
    total_count: int
    elapsed_seconds: float | None = None
    remaining_seconds: float | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    assessment_id: str | None = None
    error_code: str | None = None
    logs: list[dict[str, str]] = Field(default_factory=list)


class BandEvidence(Contract):
    band: Literal['delta', 'theta', 'alpha', 'beta', 'gamma']
    contribution: float | None = None
    posterior: list[float] | None = None
    consistency: float | None = Field(default=None, ge=0, le=1)
    missing_reason: str | None = None


class EmotionOutput(Contract):
    sample_id: str
    label: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class Assessment(Contract):
    id: str
    display_code: str | None = None
    schema_version: str = SCHEMA_VERSION
    dataset_id: str
    dataset_version: int
    session_id: str
    job_id: str
    input_hash: str
    config_version: str
    provider_version: str
    adapter_version: str
    label_space: list[str]
    emotions: list[EmotionOutput]
    confidence: float | None = Field(default=None, ge=0, le=1)
    reliability: float | None = Field(default=None, ge=0, le=1)
    reliability_threshold: float | None = Field(default=None, ge=0, le=1)
    reliability_rule_source: str | None = None
    band_evidence: list[BandEvidence]
    quality: dict[str, Any]
    missing_reasons: dict[str, str]
    review_required: bool
    review_reason: str
    data_mode: Literal['real', 'demo']
    generated_at: str
    review_revision: int = 0
    review_status: Literal['pending', 'reviewed', 'needs_followup'] = 'pending'
    stale: bool = False

    @model_validator(mode='after')
    def evidence_contract(self):
        if [item.band for item in self.band_evidence] != BANDS:
            raise ValueError('频带证据必须按 delta/theta/alpha/beta/gamma 完整列出，缺失值显式为 null')
        for item in self.band_evidence:
            if item.posterior is not None and (len(item.posterior) != len(self.label_space) or any(x < 0 or x > 1 for x in item.posterior)):
                raise ValueError('频带后验长度与标签空间不符或概率越界')
            if any(value is None for value in (item.contribution, item.posterior, item.consistency)) and not item.missing_reason:
                raise ValueError('缺失频带证据必须说明原因')
        if self.reliability is None:
            if not self.review_required or not self.missing_reasons.get('reliability'):
                raise ValueError('缺失可靠性必须说明原因并要求复核')
        elif self.reliability_threshold is None or not self.reliability_rule_source:
            if not self.review_required:
                raise ValueError('没有提供方复核规则时不能自动免除复核')
        elif self.reliability < self.reliability_threshold and not self.review_required:
            raise ValueError('低于提供方明确阈值的结果必须复核')
        return self


class ReviewRequest(Contract):
    expected_revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=80)
    status: Literal['reviewed', 'needs_followup']
    opinion: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator('reviewer', 'opinion')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('不能只包含空格')
        return value.strip()


class Review(Contract):
    id: str
    assessment_id: str
    dataset_id: str
    dataset_version: int
    revision: int
    reviewer: str
    status: Literal['reviewed', 'needs_followup']
    opinion: str
    created_at: str


class ReportRequest(Contract):
    format: Literal['json', 'pdf']
    expected_revision: int = Field(ge=0)


class Report(Contract):
    id: str
    display_code: str | None = None
    assessment_id: str
    dataset_id: str
    dataset_version: int
    review_revision: int
    format: Literal['json', 'pdf']
    data_mode: Literal['real', 'demo']
    status: Literal['draft', 'reviewed']
    sha256: str
    created_at: str
    stale: bool = False
    stale_reason: str | None = None
    current_dataset_version: int | None = None
    current_review_revision: int | None = None


class ErrorResponse(Contract):
    code: str
    message: str
    details: Any = None
    request_id: str


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 422, details=None):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details

