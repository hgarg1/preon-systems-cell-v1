"use client";

import { AlertTriangle, Database, HardDrive, ServerOff } from "lucide-react";

import type { StorageStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

interface StorageModeRibbonProps {
  storage: StorageStatus | null | undefined;
}

export function StorageModeRibbon({ storage }: StorageModeRibbonProps) {
  if (!storage) {
    return (
      <StatusShell tone="offline" icon={ServerOff} title="API status unavailable" summary="Storage mode cannot be verified." />
    );
  }

  if (storage.mode === "postgres" && !storage.degraded) {
    return (
      <StatusShell
        tone="healthy"
        icon={Database}
        title="Postgres connected"
        summary="Durable storage is active."
        details={[
          ["Active", storage.mode],
          ["Primary", storage.primary],
        ]}
      />
    );
  }

  return (
    <StatusShell
      tone="fallback"
      icon={AlertTriangle}
      title="Memory fallback active"
      summary="Runs reset when the API restarts."
      details={[
        ["Active", storage.mode],
        ["Fallback", storage.fallback],
      ]}
      reason={storage.reason}
    />
  );
}

export function storageRunCopy(storage: StorageStatus | null | undefined): string {
  if (storage?.mode === "postgres" && !storage.degraded) {
    return "persisted in Postgres";
  }
  if (storage?.mode === "memory") {
    return "in memory fallback";
  }
  return "with storage unverified";
}

type Tone = "healthy" | "fallback" | "offline";

const toneClasses: Record<Tone, { shell: string; rail: string; icon: string; text: string; muted: string; chip: string }> = {
  healthy: {
    shell: "border-emerald-300/25 bg-emerald-300/8",
    rail: "bg-emerald-300",
    icon: "text-emerald-200",
    text: "text-emerald-50",
    muted: "text-emerald-100/75",
    chip: "border-emerald-300/20 bg-emerald-300/10 text-emerald-100",
  },
  fallback: {
    shell: "border-amber-300/30 bg-amber-300/10",
    rail: "bg-amber-300",
    icon: "text-amber-200",
    text: "text-amber-50",
    muted: "text-amber-100/75",
    chip: "border-amber-300/25 bg-amber-300/10 text-amber-100",
  },
  offline: {
    shell: "border-rose-300/30 bg-rose-300/10",
    rail: "bg-rose-300",
    icon: "text-rose-200",
    text: "text-rose-50",
    muted: "text-rose-100/75",
    chip: "border-rose-300/25 bg-rose-300/10 text-rose-100",
  },
};

function StatusShell({
  tone,
  icon: Icon,
  title,
  summary,
  details = [],
  reason,
}: {
  tone: Tone;
  icon: typeof Database;
  title: string;
  summary: string;
  details?: Array<[string, string]>;
  reason?: string | null;
}) {
  const classes = toneClasses[tone];
  return (
    <section className={cn("relative overflow-hidden rounded-lg border px-4 py-3", classes.shell)}>
      <div className={cn("absolute inset-y-0 left-0 w-1", classes.rail)} />
      <div className="flex flex-col gap-3 pl-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <Icon className={cn("mt-0.5 size-4 shrink-0", classes.icon)} aria-hidden="true" />
          <div className="min-w-0">
            <div className={cn("font-medium", classes.text)}>{title}</div>
            <div className={cn("mt-1 text-sm leading-5", classes.muted)}>{summary}</div>
            {reason ? (
              <div className={cn("mt-2 flex min-w-0 items-start gap-2 text-xs", classes.muted)}>
                <HardDrive className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
                <span className="break-words font-mono">{reason}</span>
              </div>
            ) : null}
          </div>
        </div>
        {details.length ? (
          <div className="flex flex-wrap gap-2 lg:justify-end">
            {details.map(([label, value]) => (
              <span key={label} className={cn("rounded-md border px-2.5 py-1 text-xs", classes.chip)}>
                <span className="text-white/55">{label}</span>
                <span className="ml-2 font-mono">{value}</span>
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
