import { useCallback, useEffect, useRef, useState } from "react";
import type { ErrorResponse } from "./generated/api";

const BASE = "/api/v1";
export class ServiceError extends Error {
  code: string;
  requestId: string;
  details: unknown;
  constructor(body: ErrorResponse) {
    super(body.message);
    this.code = body.code;
    this.requestId = body.request_id;
    this.details = body.details;
  }
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(BASE + path, {
    ...options,
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let error: ErrorResponse;
    try {
      error = await response.json();
    } catch {
      error = {
        message: `服务请求失败（HTTP ${response.status}）`,
        code: "http_error",
        request_id: response.headers.get("X-Request-ID") ?? "未返回",
      };
    }
    throw new ServiceError(error);
  }
  return response.json() as Promise<T>;
}
export function post<T>(path: string, body: unknown, signal?: AbortSignal) {
  return request<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}
export function describeError(value: unknown): string {
  return value instanceof ServiceError
    ? `${value.message} · 请求编号：${value.requestId}${value.details ? " · " + JSON.stringify(value.details) : ""}`
    : value instanceof Error
      ? value.message === "Failed to fetch"
        ? "无法连接本地服务。请检查启动窗口和端口，再重试。"
        : value.message
      : "操作失败，请重试。";
}

/** 一个查询键对应一个请求控制器。新版本/路由卸载中止旧请求，迟到响应不能覆盖当前查询。 */
export function useResource<T>(path: string | null, interval = 0) {
  const [state, setState] = useState<{
    key: string | null;
    data?: T;
    error?: unknown;
    loading: boolean;
  }>({ key: path, loading: !!path });
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    if (!path) return;
    let active = true;
    let current: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const fetchData = async () => {
      current?.abort();
      current = new AbortController();
      try {
        const data = await request<T>(path, { signal: current.signal });
        if (active) setState({ key: path, data, loading: false });
      } catch (error) {
        if (active && !current.signal.aborted)
          setState((previous) => ({
            key: path,
            data: previous.key === path ? previous.data : undefined,
            error,
            loading: false,
          }));
      }
      if (active && interval) timer = setTimeout(fetchData, interval);
    };
    void fetchData();
    return () => {
      active = false;
      current?.abort();
      if (timer) clearTimeout(timer);
    };
  }, [path, interval, revision]);
  return {
    ...(state.key === path
      ? state
      : { data: undefined, error: undefined, loading: !!path }),
    refresh,
  };
}

export function useAction() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const active = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      generation.current += 1;
      controller.current?.abort();
      controller.current = null;
    };
  }, []);
  const run = async (action: (signal: AbortSignal) => Promise<void>) => {
    if (controller.current) return;
    const localController = new AbortController();
    const requestGeneration = ++generation.current;
    controller.current = localController;
    setPending(true);
    setError(undefined);
    try {
      await action(localController.signal);
    } catch (failure) {
      if (
        active.current &&
        generation.current === requestGeneration &&
        !localController.signal.aborted
      )
        setError(describeError(failure));
    } finally {
      // 旧请求结束时不得清除新请求的控制器或等待状态。
      if (
        controller.current === localController &&
        generation.current === requestGeneration
      ) {
        controller.current = null;
        if (active.current) setPending(false);
      }
    }
  };
  const cancel = useCallback(() => {
    generation.current += 1;
    controller.current?.abort();
    controller.current = null;
    if (active.current) {
      setPending(false);
      setError(undefined);
    }
  }, []);
  return { pending, error, run, cancel, clearError: () => setError(undefined) };
}
export async function download(
  path: string,
  fallbackName: string,
  signal?: AbortSignal,
) {
  const response = await fetch(BASE + path, { signal });
  if (!response.ok) throw new ServiceError(await response.json());
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download =
    response.headers
      .get("Content-Disposition")
      ?.match(/filename="?([^";]+)"?/)?.[1] ?? fallbackName;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// 对应 routes.py 中目前没有 response_model 的真实序列化返回；领域实体由 OpenAPI 生成。
export type Capabilities = {
  real: { available: boolean; reason: string; provider_version: string | null };
  demo: { available: boolean; notice: string; label_space: string[] };
  acquisition: { available: boolean; reason: string };
  electrode_coordinates: { available: boolean; reason: string };
  research: { id: string; name: string; status: string; entry: string }[];
  import_formats: string[];
};
export type Settings = {
  effective: Record<string, unknown>;
  config_version: string;
  priority: string;
  version: string;
  privacy: string;
  pdf_available: boolean;
  legacy_entry: string;
};
type PreviewIdentity = {
  unit: string | null;
  method: string;
  original_shape: number[];
  data_mode: "real" | "demo";
  dataset_id: string;
  dataset_version: number;
  source_hash: string;
};
export type WaveformPreview = PreviewIdentity & {
  kind: "waveform";
  series: { name: string; points: [number, number][]; rms: number }[];
  x_unit: "s" | "sample index";
  channel_count: number;
  sample_count: number;
};
export type Preview =
  | WaveformPreview
  | (PreviewIdentity & { kind: "table"; values: number[][] });
export const go = (path: string) => {
  window.location.hash = path;
};
export const idempotencyKey = () => crypto.randomUUID();
