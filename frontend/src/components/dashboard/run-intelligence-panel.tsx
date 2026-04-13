"use client";

import { Activity, Gauge, HeartPulse, TrendingUp } from "lucide-react";

import type { RunIntelligence } from "@/lib/api";

import { formatNumber } from "./format";

interface RunIntelligencePanelProps {
  intelligence: RunIntelligence | null;
}

export function RunIntelligencePanel({ intelligence }: RunIntelligencePanelProps) {
  if (!intelligence) {
    return null;
  }

  const metrics = [
    {
      icon: Activity,
      label: "Peak population",
      value: formatNumber(intelligence.peak_population, 0),
      detail: intelligence.time_to_peak_step === null ? "No peak step" : `Reached at step ${intelligence.time_to_peak_step}`,
    },
    {
      icon: TrendingUp,
      label: "Growth shift",
      value: formatSigned(intelligence.growth_rate_delta),
      detail: `Early ${formatNumber(intelligence.early_growth_rate, 3)} / late ${formatNumber(intelligence.late_growth_rate, 3)}`,
    },
    {
      icon: HeartPulse,
      label: "Efficiency",
      value: `${formatNumber(intelligence.survival_ratio * 100, 1)}%`,
      detail: `ATP per alive cell ${formatNumber(intelligence.energy_per_alive_cell_final, 2)}`,
    },
  ];

  return (
    <section className="rounded-lg border border-white/10 bg-neutral-950/72 p-4">
      <div className="grid gap-4 lg:grid-cols-[0.95fr_2fr]">
        <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
          <div className="flex items-center gap-2 text-sm text-neutral-400">
            <Gauge className="size-4 text-sky-200" aria-hidden="true" />
            Run diagnosis
          </div>
          <div className="mt-4 text-2xl font-medium text-white">{humanizeCause(intelligence.collapse_cause)}</div>
          <div className="mt-3 grid gap-2 text-sm">
            <SignalRow label="Lifespan" value={`${formatNumber(intelligence.lifespan_steps, 0)} steps`} />
            <SignalRow label="Run id" value={intelligence.run_id} />
          </div>
        </div>

        <div>
          <div className="mb-4 flex flex-col gap-1">
            <div className="text-sm text-neutral-400">Run intelligence</div>
            <h2 className="text-lg font-medium text-white">Growth and efficiency signals</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {metrics.map((metric) => (
              <div key={metric.label} className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
                <div className="flex items-center gap-2 text-sm text-neutral-400">
                  <metric.icon className="size-4 text-sky-200" aria-hidden="true" />
                  {metric.label}
                </div>
                <div className="mt-3 break-words font-mono text-2xl text-white">{metric.value}</div>
                <div className="mt-2 break-words text-xs text-neutral-500">{metric.detail}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function SignalRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="shrink-0 text-neutral-500">{label}</span>
      <span className="break-all text-right font-mono text-neutral-100">{value}</span>
    </div>
  );
}

function humanizeCause(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatSigned(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, 3)}`;
}
