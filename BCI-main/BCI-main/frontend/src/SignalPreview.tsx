import { useEffect, useRef, useState } from "react";
import {
  AudioLines, ChartNoAxesColumn, ChevronRight, CircleHelp, Clock3,
  Layers3, ScanFace, ScatterChart, Zap,
} from "lucide-react";
import type { Metadata } from "./generated/api";
import type { WaveformPreview } from "./api";
import { Waveform, channelColors } from "./Waveform";
import scalpCap from "./assets/photos/scalp-cap.webp";
import "./signal-preview.css";

const views = [
  { id: "wave", label: "波形", icon: AudioLines, title: "信号如何随时间变化",
    help: "沿横轴从左往右看。每条线对应一个通道，起伏表示记录到的信号在变化。" },
  { id: "points", label: "采样散点", icon: ScatterChart, title: "查看单个采样点",
    help: "每个点表示一个显示出来的采样值。放大局部可以看到点的位置，并用鼠标读取数值。" },
  { id: "channels", label: "通道对比", icon: ChartNoAxesColumn, title: "各通道的幅值大小",
    help: "按整段记录的均方根幅值，从大到小排列。点击一行可查看该通道的波形。" },
  { id: "scalp", label: "头皮电极", icon: ScanFace, title: "信号来自哪些电极位置",
    help: "从头顶俯视，鼻尖朝上。圆点越大，该电极记录的幅值越大，点击可查看波形。" },
] as const;
type View = typeof views[number]["id"];

// Approximate 10–20 layout for a schematic top view. Only exact names and legacy aliases map.
const sites = new Map<string, [number, number]>([
  ["fp1", [39, 19]], ["fp2", [61, 19]],
  ["f7", [26, 34]], ["f3", [38, 34]], ["fz", [50, 33]], ["f4", [62, 34]], ["f8", [74, 34]],
  ["t7", [22, 50]], ["c3", [36, 50]], ["cz", [50, 50]], ["c4", [64, 50]], ["t8", [78, 50]],
  ["p7", [26, 68]], ["p3", [38, 68]], ["pz", [50, 69]], ["p4", [62, 68]], ["p8", [74, 68]],
  ["o1", [39, 84]], ["oz", [50, 85]], ["o2", [61, 84]],
]);
const legacySites = new Map([["t3", "t7"], ["t4", "t8"], ["t5", "p7"], ["t6", "p8"]]);
const countFormat = new Intl.NumberFormat("zh-CN");
const valueFormat = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
const formatValue = (value: number) =>
  Math.abs(value) >= 10000 || (value !== 0 && Math.abs(value) < 0.01)
    ? value.toExponential(2)
    : valueFormat.format(value);

function ChannelTrace({ points, color }: {
  points: WaveformPreview["series"][number]["points"];
  color: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const target = canvas.current;
    const ctx = target?.getContext("2d");
    if (!target || !ctx || !points.length) return;
    const { width, height } = target;
    const first = points[0][0];
    const span = points[points.length - 1][0] - first || 1;
    const scale = Math.max(...points.map(([, amplitude]) => Math.abs(amplitude))) || 1;
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();
    for (const [time, amplitude] of points) {
      ctx.lineTo(2 + (width - 4) * ((time - first) / span), height / 2 - (height / 2 - 3) * (amplitude / scale));
    }
    if (points.length === 1) ctx.lineTo(4, height / 2 - (height / 2 - 3) * (points[0][1] / scale));
    ctx.stroke();
  }, [points, color]);
  return <canvas ref={canvas} className="signal-channel-trace" width={136} height={44} aria-hidden="true" />;
}

export default function SignalPreview({
  preview, metadata,
}: {
  preview: WaveformPreview;
  metadata: Metadata;
}) {
  const [view, setView] = useState<View>("wave");
  const [selected, setSelected] = useState<number | null>(null);
  const viewHeading = useRef<HTMLHeadingElement>(null);
  const readingTrace = view === "wave" || view === "points";
  const active = views.find(({ id }) => id === view) ?? views[0];
  const unit = preview.unit === "uV" ? "μV" : preview.unit;
  const unitDescription = unit === "μV" ? "微伏" : unit === "mV" ? "毫伏" : unit === "V" ? "伏" : null;
  const { series, channel_count: channelCount, sample_count: sampleCount } = preview;
  const peakRms = Math.max(0, ...series.map(({ rms }) => rms));
  const ranked = series.map((channel, index) => ({ ...channel, index })).sort((left, right) => right.rms - left.rms);
  const ratio = (rms: number) => peakRms > 0 ? rms / peakRms : 0;
  const amplitude = (rms: number) => `${formatValue(rms)}${unit ? ` ${unit}` : ""}`;
  const sampled = series.some(({ points }) => points.length < sampleCount);
  const namesConfirmed = metadata.channels?.length === channelCount;
  const mappedNames = series.map(({ name }) => {
    const normalized = name.trim().toLowerCase();
    return legacySites.get(normalized) ?? normalized;
  });
  const positions = mappedNames.map((name, index) =>
    namesConfirmed && mappedNames.indexOf(name) === index && mappedNames.lastIndexOf(name) === index
      ? sites.get(name)
      : undefined,
  );
  const positionedCount = positions.filter(Boolean).length;
  const selectedName = selected === null ? null : series[selected].name;
  const openWave = (index: number) => {
    setSelected(index);
    setView("wave");
    requestAnimationFrame(() => viewHeading.current?.focus({ preventScroll: true }));
  };

  return (
    <div className="signal-preview">
      <dl className="signal-metrics">
        <div>
          <dt><Layers3 size={15} aria-hidden="true" /> 通道数</dt>
          <dd>{countFormat.format(channelCount)} <small>个</small></dd>
          <dd className="signal-metric-note">{series.length < channelCount ? `绘制前 ${series.length} 个通道` : "已显示全部通道"}</dd>
        </div>
        <div>
          <dt><ScatterChart size={15} aria-hidden="true" /> 每通道采样点</dt>
          <dd>{countFormat.format(sampleCount)} <small>点</small></dd>
          <dd className="signal-metric-note">{sampled ? "图中已抽样，保留各段峰谷" : "图中保留全部采样点"}</dd>
        </div>
        <div>
          <dt><Clock3 size={15} aria-hidden="true" /> 采样率</dt>
          <dd>{metadata.sampling_rate ? <>{formatValue(metadata.sampling_rate)} <small>Hz</small></> : "未确认"}</dd>
          <dd className="signal-metric-note">{metadata.sampling_rate ? "每秒记录的点数" : "横轴按采样点索引显示"}</dd>
        </div>
        <div>
          <dt><Zap size={15} aria-hidden="true" /> 幅值单位</dt>
          <dd>{unit ?? "未确认"}</dd>
          <dd className="signal-metric-note">{unitDescription ?? (unit ? "元信息中记录的单位" : "可返回核对补充")}</dd>
        </div>
      </dl>
      <div className="signal-tabs" role="group" aria-label="数据可视化">
        {views.map(({ id, label, icon: Icon }) => (
          <button key={id} type="button" aria-pressed={view === id} onClick={() => setView(id)}>
            <Icon size={17} aria-hidden="true" /> {label}
          </button>
        ))}
      </div>
      <div className="signal-layout">
        <section className="signal-panel" aria-labelledby="signal-view-title">
          <div className="signal-panel-heading">
            <div>
              <h3 ref={viewHeading} id="signal-view-title" tabIndex={-1}>{active.title}</h3>
              <p>{active.help}</p>
            </div>
            {readingTrace && (
              <span className="signal-scope" title={selectedName ?? undefined}>
                {selectedName ?? `${series.length} 个通道`}
              </span>
            )}
          </div>
          {readingTrace && (
            <Waveform preview={preview} selected={selected} scatter={view === "points"} />
          )}
          {view === "channels" && (
            <div className="signal-bar-chart">
              <div className="signal-bar-scale" aria-hidden="true">
                <span>通道</span>
                <span className="signal-bar-ticks">
                  <span>0</span>
                  {peakRms > 0 && <>
                    <span>{formatValue(peakRms / 2)}</span>
                    <span>{formatValue(peakRms)}</span>
                  </>}
                </span>
                <span>幅值{unit ? `（${unit}）` : ""}</span>
              </div>
              <ul className="signal-bars" aria-label="各通道均方根幅值">
                {ranked.map(({ name, rms, index }) => (
                  <li key={index}>
                    <button type="button" onClick={() => openWave(index)} aria-label={`查看 ${name} 波形，均方根幅值 ${amplitude(rms)}`}>
                      <strong title={name}>{name}</strong>
                      <span className="signal-bar-track" aria-hidden="true">
                        <span style={{ width: `${100 * ratio(rms)}%`, backgroundColor: channelColors[index] }} />
                      </span>
                      <span className="signal-value">{amplitude(rms)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {view === "scalp" && (
            <div className="signal-scalp">
              {positionedCount ? (
                <div className="scalp-stage">
                  <div className="scalp-diagram" role="group" aria-label="头皮电极位置示意图">
                    <img className="scalp-image" src={scalpCap} width={860} height={860} alt="" />
                    <span className="scalp-guide" aria-hidden="true" />
                    <span className="scalp-side left" aria-hidden="true">左</span>
                    <span className="scalp-side right" aria-hidden="true">右</span>
                    {series.map(({ name, rms }, index) => {
                      const position = positions[index];
                      if (!position) return null;
                      const [left, top] = position;
                      const size = 8 + 13 * Math.sqrt(ratio(rms));
                      return (
                        <button key={index} type="button" className="scalp-point"
                          style={{ left: `${left}%`, top: `${top}%`, color: channelColors[index] }}
                          title={`${name} · ${amplitude(rms)}`}
                          aria-label={`电极 ${name}，均方根幅值 ${amplitude(rms)}，查看波形`}
                          onClick={() => openWave(index)}>
                          <span className="scalp-dot" style={{ width: size, height: size }} />
                          <strong>{name.trim()}</strong>
                        </button>
                      );
                    })}
                  </div>
                  <div className="scalp-key">
                    <span className="scalp-key-count">{positionedCount} / {series.length}</span>
                    <span>可定位的显示通道</span>
                    <div className="scalp-key-scale" aria-hidden="true">
                      <span /><span /><span />
                    </div>
                    <p>圆点从小到大对应不同的均方根幅值。点击电极可查看该通道。</p>
                  </div>
                </div>
              ) : (
                <div className="signal-scalp-empty">
                  <ScanFace size={32} strokeWidth={1.4} aria-hidden="true" />
                  <h4>暂无可定位的电极</h4>
                  <p>请核对元信息中的通道名称，例如 F3、Cz、O2。也可在「通道对比」查看各通道的幅值。</p>
                </div>
              )}
              <p className="signal-scalp-caption">
                电极按常见 10–20 位置示意。脑区激活需额外的定位数据与分析。
              </p>
            </div>
          )}
        </section>
        <aside className="signal-panel signal-channels" aria-label="通道明细">
          <div className="signal-channel-heading">
            <h3>通道明细</h3>
            <span>缩略波形 · 均方根幅值</span>
          </div>
          <div className="signal-channel-list">
            <button type="button" aria-pressed={readingTrace && selected === null} onClick={() => {
              setSelected(null);
              if (!readingTrace) setView("wave");
            }}>
              <AudioLines size={16} aria-hidden="true" /> <strong>全部显示通道</strong>
              <ChevronRight size={14} aria-hidden="true" />
            </button>
            {series.map(({ name, rms, points }, index) => (
              <button key={index} type="button" aria-pressed={readingTrace && selected === index}
                title={name} onClick={() => {
                  setSelected(index);
                  if (!readingTrace) setView("wave");
                }}>
                <span className="signal-channel-dot" aria-hidden="true" style={{ backgroundColor: channelColors[index] }} />
                <strong>{name}</strong>
                <ChannelTrace points={points} color={channelColors[index]} />
                <span className="signal-value">{amplitude(rms)}</span>
              </button>
            ))}
          </div>
          <p className="signal-channel-help">
            <CircleHelp size={16} aria-hidden="true" />
            <span>RMS 表示整段记录的信号大小。点击通道可单独查看。</span>
          </p>
        </aside>
      </div>
    </div>
  );
}
