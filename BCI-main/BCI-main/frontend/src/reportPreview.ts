import { useEffect, useState } from "react";
import type { Report } from "./generated/api";
import { useResource } from "./api";

type Preview = {
  report_id: string;
  dataset_version: number;
  review_revision: number;
  value: unknown;
};
/** 保留预览绑定版本；轮询发现来源或复核修订变化时关闭普通报告预览。 */
export function useReportPreview(reports: Report[] | undefined) {
  const [preview, setPreview] = useState<Preview>();
  const [notice, setNotice] = useState<string>();
  const current = useResource<Report>(
    preview ? `/reports/${preview.report_id}` : null,
    2500,
  );
  useEffect(() => {
    if (!preview) return;
    const candidates = [
      current.data,
      reports?.find((value) => value.id === preview.report_id),
    ];
    if (
      candidates.some(
        (report) =>
          report &&
          (report.stale ||
            (report.current_dataset_version != null &&
              report.current_dataset_version !== preview.dataset_version) ||
            (report.current_review_revision != null &&
              report.current_review_revision !== preview.review_revision)),
      )
    ) {
      setPreview(undefined);
      setNotice("报告版本已变更，已关闭当前预览。请核对版本或下载历史存档。");
    }
  }, [reports, preview, current.data]);
  return {
    preview,
    notice,
    openPreview: (report: Report, value: unknown) => {
      setNotice(undefined);
      setPreview({
        report_id: report.id,
        dataset_version: report.dataset_version,
        review_revision: report.review_revision,
        value,
      });
    },
    closePreview: () => setPreview(undefined),
  };
}
