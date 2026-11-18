import { lazy, Suspense, useRef, useState } from "react";
import type { Dataset, Job, Metadata } from "../generated/api";
import {
  go,
  idempotencyKey,
  post,
  request,
  useAction,
  useResource,
} from "../api";
import type { Capabilities, Preview } from "../api";
import {
  Badge,
  Button,
  Card,
  DemoNotice,
  Empty,
  ErrorBox,
  Icon,
  ModeBadge,
  Notice,
  PageHeading,
  StatusBadge,
} from "../ui";
import "../import-workspace.css";

const SignalPreview = lazy(() => import("../SignalPreview"));
const steps = ["选择数据", "核对元信息", "预览与质量", "确认提交"];

const parseNames = (value: string) =>
  value
    .split(/[,，\n]/)
    .map((name) => name.trim())
    .filter(Boolean);
const listFields = [
  "axes",
  "channels",
  "bands",
  "feature_names",
  "sample_ids",
  "label_space",
] as const;
type ListField = (typeof listFields)[number];
const isListField = (key: keyof Metadata): key is ListField =>
  listFields.some((field) => field === key);
const fieldLabels: Record<string, string> = {
  display_code: "数据编码",
  axes: "轴定义（按数组顺序）",
  sampling_rate: "采样率（Hz）",
  channels: "通道名称",
  bands: "频带名称",
  feature_names: "特征名称",
  sample_ids: "样本编码",
  label_space: "标签空间（不自动推断）",
  source_description: "来源说明",
};
function MetadataEditor({
  dataset,
  onSaved,
}: {
  dataset: Dataset;
  onSaved: () => void;
}) {
  const [metadata, setMetadata] = useState<Metadata>(dataset.metadata);
  const [listDrafts, setListDrafts] = useState<Record<ListField, string>>(
    () =>
      Object.fromEntries(
        listFields.map((key) => [
          key,
          (dataset.metadata[key] ?? []).join(", "),
        ]),
      ) as Record<ListField, string>,
  );
  const action = useAction();
  const update = (key: keyof Metadata, value: unknown) =>
    setMetadata((previous) => ({ ...previous, [key]: value }));
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void action.run(async (signal) => {
          const normalized: Metadata = { ...metadata };
          for (const key of listFields) {
            if (key === "bands")
              normalized.bands = parseNames(
                listDrafts[key],
              ) as Metadata["bands"];
            else normalized[key] = parseNames(listDrafts[key]);
          }
          // 只提交相对绑定版本发生变化的字段，旧标签由后端按映射变更规则撤销。
          const changed: Record<string, unknown> = {};
          for (const [key, value] of Object.entries(normalized)) {
            if (
              JSON.stringify(value) !==
              JSON.stringify(dataset.metadata[key as keyof Metadata])
            )
              changed[key] = value;
          }
          await request<Dataset>(`/datasets/${dataset.id}/metadata`, {
            method: "PATCH",
            body: JSON.stringify({
              expected_version: dataset.version,
              metadata: changed,
            }),
            signal,
          });
          onSaved();
        });
      }}
    >
      <div className="form-grid">
        <label>
          输入类型
          <select
            value={metadata.kind ?? ""}
            onChange={(event) => {
              update("kind", event.target.value || null);
              update(
                "modality",
                event.target.value === "eeg" ||
                  event.target.value === "band_features"
                  ? "EEG"
                  : event.target.value
                    ? "FEATURES"
                    : null,
              );
            }}
          >
            <option value="">请明确选择</option>
            <option value="eeg">脑电信号（eeg）</option>
            <option value="features">特征矩阵（features）</option>
            <option value="band_features">频带特征（band_features）</option>
          </select>
        </label>
        <label>
          单位
          <select
            value={metadata.unit ?? ""}
            onChange={(event) => update("unit", event.target.value || null)}
          >
            <option value="">尚未确认</option>
            {[
              "uV",
              "mV",
              "V",
              "dimensionless",
              "uV^2",
              "uV^2/Hz",
              "bit",
              "nat",
            ].map((unit) => (
              <option key={unit}>{unit}</option>
            ))}
          </select>
        </label>
        {(
          [
            "display_code",
            "axes",
            "sampling_rate",
            "channels",
            "bands",
            "feature_names",
            "sample_ids",
            "label_space",
            "source_description",
          ] as const
        ).map((key) => (
          <label
            key={key}
            className={
              ["sample_ids", "source_description"].includes(key) ? "span-2" : ""
            }
          >
            {fieldLabels[key]}
            {isListField(key) ? (
              <textarea
                rows={2}
                value={listDrafts[key]}
                onChange={(event) =>
                  setListDrafts((previous) => ({
                    ...previous,
                    [key]: event.target.value,
                  }))
                }
                placeholder={
                  key === "axes"
                    ? "例如：channel, time；按真实数组轴顺序填写"
                    : key === "bands"
                      ? "delta, theta, alpha, beta, gamma（按实际顺序）"
                      : key === "label_space"
                        ? "由数据说明或模型契约明确指定"
                        : undefined
                }
              />
            ) : (
              <input
                value={metadata[key] ?? ""}
                type={key === "sampling_rate" ? "number" : "text"}
                min={key === "sampling_rate" ? "0.001" : undefined}
                step={key === "sampling_rate" ? "any" : undefined}
                onChange={(event) =>
                  update(
                    key,
                    key === "sampling_rate"
                      ? event.target.value
                        ? Number(event.target.value)
                        : null
                      : event.target.value,
                  )
                }
              />
            )}
          </label>
        ))}
      </div>
      <p className="hint">
        列表可使用逗号或换行分隔，保存时解析。二维 EEG 明确
        channel/time；批次数据明确 sample 轴。不会猜测通道、标签或物理单位。
      </p>
      <ErrorBox error={action.error} />
      <div className="form-actions">
        <Button
          type="submit"
          variant="secondary"
          icon="check"
          disabled={action.pending}
        >
          {action.pending ? "正在保存…" : "保存元信息并重新校验"}
        </Button>
        <Button
          type="button"
          variant="quiet"
          disabled={action.pending}
          onClick={onSaved}
        >
          读取最新版本
        </Button>
        <span className="hint">
          使用版本 v{dataset.version} 校验并创建新版本
        </span>
      </div>
    </form>
  );
}
export function ImportPage({
  params,
  capabilities,
}: {
  params: URLSearchParams;
  capabilities?: Capabilities;
}) {
  const mode = params.get("mode") === "demo" ? "demo" : "real";
  const identity = params.get("dataset");
  const step = Math.max(1, Math.min(4, Number(params.get("step") ?? 1)));
  const datasetQuery = useResource<Dataset>(
    identity ? `/datasets/${identity}` : null,
  );
  const dataset = datasetQuery.data;
  const preview = useResource<Preview>(
    dataset && step === 3
      ? `/datasets/${dataset.id}/preview?version=${dataset.version}`
      : null,
  );
  const action = useAction();
  const submitKey = useRef<{ binding: string; value: string } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const navigate = (next: number, id = identity) => {
    setConfirmed(false);
    go(`/import?mode=${mode}${id ? "&dataset=" + id : ""}&step=${next}`);
  };
  const importFile = (file: File) =>
    void action.run(async (signal) => {
      const body = new FormData();
      body.append("file", file);
      body.append("data_mode", mode);
      const imported = await request<Dataset>("/datasets/import", {
        method: "POST",
        body,
        signal,
      });
      navigate(2, imported.id);
    });
  const importDemo = () =>
    void action.run(async (signal) => {
      const response = await fetch("/api/v1/demo/sample", { signal });
      if (!response.ok) throw new Error("无法读取演示样本，请检查本地服务。");
      const blob = await response.blob();
      const body = new FormData();
      body.append(
        "file",
        new File([blob], "xinlan-demo-sample.json", {
          type: "application/json",
        }),
      );
      body.append("data_mode", "demo");
      const imported = await request<Dataset>("/datasets/import", {
        method: "POST",
        body,
        signal,
      });
      navigate(2, imported.id);
    });
  return (
    <div className="import-workspace">
      <PageHeading
        title="新建筛查"
        description="导入数据，核对元信息，再预览与提交。每次更新元信息都会创建新版本。"
        photo={step === 1 ? "import" : undefined}
      />
      <ol className="import-steps" aria-label="导入进度">
        {steps.map((label, index) => (
          <li
            key={label}
            aria-current={step === index + 1 ? "step" : undefined}
            className={step > index + 1 ? "complete" : undefined}
          >
            <span className="import-step-number" aria-hidden="true">
              {step > index + 1 ? <Icon name="check" size={15} /> : index + 1}
            </span>
            <span>{label}</span>
          </li>
        ))}
      </ol>
      {mode === "demo" && <DemoNotice />}
      <ErrorBox error={action.error ?? datasetQuery.error} />
      {step === 1 && (
        <div className="import-columns">
          <Card title="选择数据来源">
            <div
              className="import-mode-picker"
              role="group"
              aria-label="数据来源"
            >
              <button
                type="button"
                aria-pressed={mode === "real"}
                className="import-mode-real"
                disabled={action.pending}
                onClick={() => go("/import?mode=real")}
              >
                <span className="import-mode-icon">
                  <Icon name="shield" size={19} />
                </span>
                <span className="import-mode-copy">
                  <strong>真实数据</strong>
                  <small>导入并核对研究数据</small>
                </span>
                <span className="import-mode-selection" aria-hidden="true" />
              </button>
              <button
                type="button"
                aria-pressed={mode === "demo"}
                className="import-mode-demo"
                disabled={action.pending}
                onClick={() => go("/import?mode=demo")}
              >
                <span className="import-mode-icon">
                  <Icon name="signal" size={19} />
                </span>
                <span className="import-mode-copy">
                  <strong>模拟演示</strong>
                  <small>固定合成数据，体验全流程</small>
                </span>
                <span className="import-mode-selection" aria-hidden="true" />
              </button>
            </div>
            {mode === "demo" && (
              <div className="import-demo-sample">
                <div>
                  <strong>固定合成样本</strong>
                  <p>两通道、128 Hz 的合成正弦信号。</p>
                </div>
                <Button
                  disabled={action.pending}
                  onClick={importDemo}
                  icon="signal"
                >
                  {action.pending ? "正在导入…" : "导入固定合成样本"}
                </Button>
              </div>
            )}
            <div
              className={`import-dropzone ${dragging ? "dragging" : ""}`}
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                if (!action.pending && event.dataTransfer.files[0])
                  importFile(event.dataTransfer.files[0]);
              }}
            >
              <span className="import-upload-icon">
                <Icon name="upload" size={24} />
              </span>
              <h3>将数据文件拖到这里</h3>
              <p>支持纯数值数据，导入数据保存在本机。</p>
              <label className="button secondary import-file-picker">
                选择数据文件
                <input
                  aria-label="选择数据文件"
                  type="file"
                  accept=".npy,.npz,.json,.csv,.tsv,.xlsx"
                  disabled={action.pending}
                  onChange={(event) => {
                    if (event.target.files?.[0])
                      importFile(event.target.files[0]);
                  }}
                />
              </label>
              <small>.npy · .npz · .json · .csv · .tsv · .xlsx</small>
            </div>
          </Card>
          <div className="import-guide">
            <Card title="导入前准备">
              <ul className="import-checklist">
                <li>使用匿名数据编码，避免填写姓名等身份信息。</li>
                <li>明确数组 shape、轴顺序、采样率与通道顺序。</li>
                <li>特征数据需说明特征名称、单位和标签空间。</li>
                <li>不接收 pickle 或对象数组；不修改原始数据。</li>
                <li>
                  CSV、TSV、XLSX
                  首行需包含非数值且唯一的列名，后续行只包含数值。
                </li>
              </ul>
            </Card>
            {mode === "real" && (
              <Notice>
                <strong>真实推理暂不可用</strong>
                <p>
                  {capabilities?.real.reason ??
                    "正在读取服务端模型能力；未确认前不提交真实分析。"}
                </p>
                <p>仍可导入并核对数据，保存草稿供后续接入。</p>
              </Notice>
            )}
            <Card title="关于辅助评估">
              <p className="muted">
                脑电支持的状态评估需要结合数据质量、适用人群与专业复核。结果不能替代临床诊断或专业心理评估。
              </p>
            </Card>
          </div>
        </div>
      )}
      {step > 1 && !dataset && !datasetQuery.error && (
        <Empty title="正在读取数据版本…" />
      )}
      {dataset && step > 1 && (
        <>
          <Card className="import-dataset-summary">
            <div>
              <ModeBadge mode={dataset.data_mode} />
              <strong>
                {dataset.metadata.display_code || "未设置数据编码"}
              </strong>
              <StatusBadge status={dataset.validation_status} />
            </div>
            <div className="import-summary-facts">
              <span>
                shape <code>[{dataset.shape.join(", ")}]</code>
              </span>
              <span>
                dtype <code>{dataset.dtype}</code>
              </span>
              <span>
                版本 <b>v{dataset.version}</b>
              </span>
              <span>
                来源 <b>{dataset.source_format}</b>
              </span>
            </div>
          </Card>
          {step === 2 && (
            <Card
              title="核对数据元信息"
              extra={<Badge tone="blue">数据版本 v{dataset.version}</Badge>}
            >
              <MetadataEditor
                key={`${dataset.id}/${dataset.version}`}
                dataset={dataset}
                onSaved={datasetQuery.refresh}
              />
              {dataset.validation_errors.length > 0 && (
                <Notice>
                  <strong>以下信息仍待确认，当前保持草稿</strong>
                  <ul>
                    {dataset.validation_errors.map((error) => (
                      <li key={error}>{error}</li>
                    ))}
                  </ul>
                </Notice>
              )}
              <div className="wizard-actions">
                <Button variant="quiet" onClick={() => navigate(1)}>
                  重新选择文件
                </Button>
                <Button onClick={() => navigate(3)} icon="arrow">
                  继续预览
                </Button>
              </div>
            </Card>
          )}
          {step === 3 && (
            <Card
              title="数据预览"
              className="import-preview"
              extra={<ModeBadge mode={dataset.data_mode} />}
            >
              <ErrorBox error={preview.error} retry={preview.refresh} />
              {preview.data ? (
                <>
                  {preview.data.kind === "waveform" ? (
                    <Suspense fallback={<Empty title="正在加载数值图表…" />}>
                      <SignalPreview
                        key={`${preview.data.dataset_id}/${preview.data.dataset_version}`}
                        preview={preview.data}
                        metadata={dataset.metadata}
                      />
                    </Suspense>
                  ) : (
                    <div className="table-scroll import-preview-table">
                      <table>
                        <caption>
                          数值预览 · 前 {preview.data.values.length} 行 × {preview.data.values[0]?.length ?? 0} 列 · 单位 {preview.data.unit ?? "尚未确认"}
                        </caption>
                        <tbody>
                          {preview.data.values?.map((row, index) => (
                            <tr key={index}>
                              {row.map((value, column) => (
                                <td key={column}>
                                  {Number(value).toPrecision(5)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {preview.data.kind === "table" && (
                    <p className="hint">
                      {dataset.metadata.kind === "features" || dataset.metadata.kind === "band_features"
                        ? "这里按原数组顺序显示部分特征值。多维数据会沿第一轴逐行展开。"
                        : "暂以数值表显示。核对输入类型和轴定义后，脑电信号可按通道绘图。"}
                    </p>
                  )}
                  <div className="facts-grid">
                    <div>
                      <span>结构校验</span>
                      <strong>
                        {dataset.validation_status === "ready"
                          ? "通过"
                          : "信息不足"}
                      </strong>
                    </div>
                    <div>
                      <span>信号质量评分</span>
                      <strong>未提供</strong>
                    </div>
                    <div>
                      <span>源文件哈希</span>
                      <code title={dataset.source_hash}>
                        {dataset.source_hash.slice(0, 20)}…
                      </code>
                    </div>
                  </div>
                  <p className="hint">
                    有限数值与结构校验不等于经过验证的信号质量评分。此预览不进行统计推断。
                  </p>
                </>
              ) : (
                !preview.error && <Empty title="正在读取数值预览…" />
              )}
              <div className="wizard-actions">
                <Button variant="secondary" onClick={() => navigate(2)}>
                  返回核对
                </Button>
                <Button
                  disabled={!preview.data || !!preview.error}
                  onClick={() => navigate(4)}
                  icon="arrow"
                >
                  继续确认
                </Button>
              </div>
            </Card>
          )}
          {step === 4 && (
            <Card title="确认并提交">
              <div className="facts-grid">
                <div>
                  <span>数据编码</span>
                  <strong>{dataset.metadata.display_code || "未设置"}</strong>
                </div>
                <div>
                  <span>输入类型 / 轴</span>
                  <strong>
                    {dataset.metadata.kind ?? "未确认"} /{" "}
                    {dataset.metadata.axes?.join(" → ") || "未确认"}
                  </strong>
                </div>
                <div>
                  <span>标签空间</span>
                  <strong>
                    {dataset.metadata.label_space?.join("、") || "未确认"}
                  </strong>
                </div>
              </div>
              <Notice tone="blue">
                <strong>任务绑定数据版本 v{dataset.version}</strong>
                <p>
                  评估记录保留来源哈希、配置版本与提供方版本。后续元信息变更会将旧结果标为过期。
                </p>
              </Notice>
              {dataset.validation_status !== "ready" && (
                <Notice>
                  <strong>元信息尚不完整，草稿不能提交分析</strong>
                  <ul>
                    {dataset.validation_errors.map((error) => (
                      <li key={error}>{error}</li>
                    ))}
                  </ul>
                </Notice>
              )}
              {mode === "real" && !capabilities?.real.available && (
                <Notice>
                  <strong>真实推理暂不可用</strong>
                  <p>{capabilities?.real.reason ?? "服务端能力尚未确认"}</p>
                </Notice>
              )}
              <label className="checkbox-line">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                我已核对数据来源、轴定义与标签空间
              </label>
              <div className="wizard-actions">
                <Button variant="secondary" onClick={() => navigate(2)}>
                  返回核对
                </Button>
                <Button
                  disabled={
                    !confirmed ||
                    dataset.validation_status !== "ready" ||
                    (mode === "real" && !capabilities?.real.available) ||
                    dataset.data_mode !== mode ||
                    action.pending
                  }
                  onClick={() =>
                    void action.run(async (signal) => {
                      const binding = JSON.stringify([
                        dataset.id,
                        dataset.version,
                        dataset.data_mode,
                      ]);
                      if (submitKey.current?.binding !== binding)
                        submitKey.current = {
                          binding,
                          value: idempotencyKey(),
                        };
                      const job = await post<Job>(
                        "/jobs",
                        {
                          dataset_id: dataset.id,
                          dataset_version: dataset.version,
                          provider: mode,
                          idempotency_key: submitKey.current.value,
                        },
                        signal,
                      );
                      go("/jobs/" + job.id);
                    })
                  }
                  icon="arrow"
                >
                  {action.pending
                    ? "正在提交…"
                    : mode === "demo"
                      ? "提交演示任务"
                      : "提交筛查任务"}
                </Button>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
