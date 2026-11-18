import { useEffect, useRef } from "react";
import { init, use } from "echarts/core";
import type { EChartsType } from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import type { LineSeriesOption, ScatterSeriesOption } from "echarts/charts";
import { GridComponent, TooltipComponent, DataZoomComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { WaveformPreview } from "./api";
import { Focus, RotateCcw } from "lucide-react";

use([LineChart, ScatterChart, GridComponent, TooltipComponent, DataZoomComponent, CanvasRenderer]);

export const channelColors = [
  "#5ce4bd", "#9eb6ff", "#ffbf84", "#d6a9fd",
  "#ff9cb6", "#6dd6ee", "#d4e686", "#e1c8ab",
];
const linePatterns: NonNullable<LineSeriesOption["lineStyle"]>["type"][] = [
  "solid", "dashed", "dotted", [9, 3], [6, 2, 1, 2], [4, 2, 1, 2], [2, 2, 6, 2], [1, 3, 5, 3],
];
const symbols = ["circle", "diamond", "rect", "triangle", "roundRect", "pin", "arrow", "circle"];
const ink = "#e9f5f2";
const muted = "#a0b8ba";
const unitLabel = (unit: string | null) => unit === "uV" ? "μV" : unit ?? "单位未确认";

export function Waveform({
  preview, selected, scatter,
}: {
  preview: WaveformPreview;
  selected: number | null;
  scatter: boolean;
}) {
  const element = useRef<HTMLDivElement>(null);
  const instance = useRef<EChartsType | null>(null);
  const xLabel = preview.x_unit === "s" ? "时间（秒）" : "采样点索引";
  const yLabel = `幅值（${unitLabel(preview.unit)}）`;
  const focused = selected !== null || preview.series.length === 1;
  const visible = preview.series.filter((_, index) => selected === null || index === selected);
  const visibleNames = visible.map((series) => series.name).join("、");
  const lastPoint = Math.max(0, ...visible.map(({ points }) => points.at(-1)?.[0] ?? 0));
  const shortWindow = preview.x_unit === "s" ? 1 : 127;

  useEffect(() => {
    const target = element.current;
    if (!target) return;
    const chart = init(target);
    instance.current = chart;
    chart.setOption({
      animation: false,
      textStyle: { color: ink, fontFamily: getComputedStyle(target).fontFamily },
      tooltip: {
        trigger: "axis",
        renderMode: "richText",
        confine: true,
        axisPointer: { type: "line", lineStyle: { color: "#79c8bc", type: "dashed" } },
        backgroundColor: "#16353c",
        borderColor: "#3e6267",
        padding: [9, 12],
        textStyle: { color: ink, fontSize: 12 },
        valueFormatter: (value: unknown) =>
          typeof value === "number" ? value.toPrecision(4) : String(value),
      },
      grid: {
        left: 51, right: 26, top: 30, bottom: 80,
        outerBounds: { left: 12, right: 12, top: 6, bottom: 43 },
      },
      xAxis: {
        type: "value",
        name: xLabel,
        nameLocation: "middle",
        nameGap: 28,
        nameTextStyle: { color: muted },
        min: 0,
        minInterval: preview.x_unit === "sample index" ? 1 : undefined,
        axisLine: { onZero: false, lineStyle: { color: "#466468" } },
        axisTick: { show: false },
        axisLabel: { color: muted, fontSize: 11, hideOverlap: true },
        splitLine: { lineStyle: { color: "#234349", type: "dashed" } },
      },
      yAxis: {
        type: "value",
        name: yLabel,
        nameTextStyle: { align: "left", color: muted },
        axisLabel: { color: muted, fontSize: 11 },
        splitLine: { lineStyle: { color: "#29464b" } },
        splitArea: { show: true, areaStyle: { color: ["#0c2429", "#102a2e"] } },
      },
      dataZoom: [
        { type: "inside", zoomOnMouseWheel: "ctrl", moveOnMouseWheel: false },
        {
          type: "slider",
          height: 24,
          bottom: 11,
          borderColor: "#315258",
          backgroundColor: "#10292e",
          fillerColor: "rgba(92, 228, 189, 0.13)",
          handleStyle: { color: "#63d9bb", borderColor: "#63d9bb" },
          moveHandleStyle: { color: "#569d8f" },
          showDetail: false,
          brushSelect: false,
          dataBackground: {
            lineStyle: { color: "#577779" },
            areaStyle: { color: "#28474b" },
          },
          selectedDataBackground: {
            lineStyle: { color: "#77bdad" },
            areaStyle: { color: "#416f65" },
          },
        },
      ],
      series: preview.series.flatMap<LineSeriesOption | ScatterSeriesOption>((series, index) => {
        if (selected !== null && selected !== index) return [];
        const color = channelColors[index];
        const common = { name: series.name, data: series.points, itemStyle: { color } };
        if (scatter) {
          return [{
            ...common, type: "scatter", symbol: focused ? "circle" : symbols[index], symbolSize: focused ? 6 : 4.5,
            itemStyle: { color, opacity: focused ? 0.87 : 0.7 },
          }];
        }
        return [{
          ...common, type: "line", showSymbol: series.points.length === 1,
          lineStyle: { color, width: focused ? 1.9 : 1.55, type: focused ? "solid" : linePatterns[index] },
          areaStyle: focused ? { color, opacity: 0.09 } : undefined,
        }];
      }),
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(target);
    return () => {
      observer.disconnect();
      instance.current = null;
      chart.dispose();
    };
  }, [preview, selected, scatter, focused, xLabel, yLabel]);

  return (
    <>
      <div
        ref={element}
        className="waveform"
        role="img"
        aria-label={`${preview.data_mode === "demo" ? "模拟演示" : "真实数据"}${scatter ? "脑电采样散点" : "脑电波形"}，${visibleNames}，横轴${xLabel}，纵轴${yLabel}`}
      />
      <div className="signal-chart-tools">
        <span>拖动滑块查看局部</span>
        <div className="signal-chart-actions">
          {lastPoint > shortWindow && (
            <button type="button" onClick={() => instance.current?.dispatchAction({ type: "dataZoom", startValue: 0, endValue: shortWindow })}>
              <Focus size={14} aria-hidden="true" /> {preview.x_unit === "s" ? "前 1 秒" : "前 128 点"}
            </button>
          )}
          <button type="button" onClick={() => instance.current?.dispatchAction({ type: "dataZoom", start: 0, end: 100 })}>
            <RotateCcw size={13} aria-hidden="true" /> 重置缩放
          </button>
        </div>
      </div>
    </>
  );
}
