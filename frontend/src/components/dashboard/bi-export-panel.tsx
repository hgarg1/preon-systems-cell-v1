"use client";

import { Download, FileArchive, RefreshCw, Warehouse } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  createRunExport,
  getRunExportDownloadUrl,
  getRunExports,
  type ExportFormatInfo,
  type ExportManifest,
} from "@/lib/api";

import { formatDate, formatNumber } from "./format";

interface BIExportPanelProps {
  runId: string;
}

export function BIExportPanel({ runId }: BIExportPanelProps) {
  const [formats, setFormats] = useState<ExportFormatInfo[]>([]);
  const [manifest, setManifest] = useState<ExportManifest | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeFormat, setActiveFormat] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshExports = useCallback(async (signal?: AbortSignal) => {
    setError(null);
    try {
      const payload = await getRunExports(runId, signal);
      setFormats(payload.formats);
      setManifest(payload.manifest);
    } catch (caught) {
      if (!signal?.aborted) {
        setError(caught instanceof Error ? caught.message : "Unable to load export metadata");
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, [runId]);

  useEffect(() => {
    const controller = new AbortController();
    void refreshExports(controller.signal);
    return () => controller.abort();
  }, [refreshExports]);

  const generatedFormats = useMemo(() => new Set(manifest?.formats ?? []), [manifest]);

  async function handleExport(format: string) {
    setActiveFormat(format);
    setError(null);
    try {
      const nextManifest = await createRunExport(runId, [format]);
      setManifest(nextManifest);
      window.open(getRunExportDownloadUrl(runId, format), "_self");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create export");
    } finally {
      setActiveFormat(null);
    }
  }

  return (
    <section className="rounded-lg border border-white/10 bg-neutral-950/72">
      <div className="flex flex-col gap-3 border-b border-white/10 px-4 py-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm text-neutral-400">
            <Warehouse className="size-4 text-sky-200" aria-hidden="true" />
            BI exports
          </div>
          <h2 className="mt-2 text-lg font-medium text-white">Native analytics handoff</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-neutral-400">
            Download Parquet datasets, Power BI project files, and Tableau packaged extracts from the same run tables.
          </p>
        </div>
        <Button
          variant="outline"
          className="w-fit rounded-lg border-white/10 bg-white/5 text-white hover:bg-white/10"
          disabled={loading}
          onClick={() => void refreshExports()}
        >
          <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} aria-hidden="true" />
          Refresh
        </Button>
      </div>

      {error ? (
        <div className="m-4 rounded-lg border border-rose-300/30 bg-rose-300/10 p-4 text-sm leading-6 text-rose-100">
          {error}
        </div>
      ) : null}

      <div className="grid gap-3 p-4 lg:grid-cols-3">
        {formats.length ? (
          formats.map((item) => (
            <ExportCard
              key={item.format}
              format={item}
              generated={generatedFormats.has(item.format)}
              fileCount={manifest?.files[item.format]?.length ?? 0}
              busy={activeFormat === item.format}
              anyBusy={activeFormat !== null}
              onExport={() => void handleExport(item.format)}
            />
          ))
        ) : (
          <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4 text-sm text-neutral-400 lg:col-span-3">
            {loading ? "Loading export formats." : "No export formats are available."}
          </div>
        )}
      </div>

      <div className="grid gap-4 border-t border-white/10 px-4 py-4 text-sm lg:grid-cols-[1fr_1fr]">
        <div>
          <div className="text-xs uppercase text-neutral-500">Generated</div>
          <div className="mt-2 font-mono text-neutral-100">
            {manifest ? formatDate(manifest.generated_at) : "No export bundle yet"}
          </div>
        </div>
        <div>
          <div className="text-xs uppercase text-neutral-500">Rows by table</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {manifest
              ? Object.entries(manifest.row_counts).map(([table, rows]) => (
                  <span key={table} className="rounded-md border border-white/10 bg-white/5 px-2 py-1 font-mono text-xs text-neutral-200">
                    {table}: {formatNumber(rows, 0)}
                  </span>
                ))
              : <span className="text-neutral-400">Generate an export to inspect row counts.</span>}
          </div>
        </div>
      </div>
    </section>
  );
}

interface ExportCardProps {
  format: ExportFormatInfo;
  generated: boolean;
  fileCount: number;
  busy: boolean;
  anyBusy: boolean;
  onExport: () => void;
}

function ExportCard({ format, generated, fileCount, busy, anyBusy, onExport }: ExportCardProps) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <FileArchive className="size-4 shrink-0 text-sky-200" aria-hidden="true" />
            <h3 className="break-words text-base font-medium text-white">{format.label}</h3>
          </div>
          <p className="mt-2 text-sm leading-6 text-neutral-400">{format.description}</p>
        </div>
        <span className="shrink-0 rounded-md border border-white/10 bg-neutral-900 px-2 py-1 text-xs text-neutral-300">
          {format.native ? "Native" : "Dataset"}
        </span>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs uppercase text-neutral-500">
          {generated ? `${fileCount} files ready` : format.available ? "Ready to generate" : "Dependency missing"}
        </div>
        <Button
          className="rounded-lg bg-sky-300 text-neutral-950 hover:bg-sky-200"
          disabled={!format.available || anyBusy}
          onClick={onExport}
        >
          <Download className="size-4" aria-hidden="true" />
          {busy ? "Preparing" : generated ? "Download" : "Generate"}
        </Button>
      </div>
    </div>
  );
}
