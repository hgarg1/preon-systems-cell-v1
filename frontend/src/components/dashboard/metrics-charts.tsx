"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { RunTimeSeriesPoint } from "@/lib/api";

import { formatNumber } from "./format";

interface MetricsChartsProps {
  metrics: RunTimeSeriesPoint[];
}

export function MetricsCharts({ metrics }: MetricsChartsProps) {
  if (!metrics.length) {
    return (
      <div className="flex min-h-72 items-center justify-center rounded-lg border border-white/10 bg-neutral-950/70 text-sm text-neutral-400">
        No metric samples are available for this run.
      </div>
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <ChartPanel title="Population" subtitle="Alive, dead, and divided cells by step">
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={metrics} margin={{ left: 4, right: 12, top: 8, bottom: 0 }}>
            <defs>
              <linearGradient id="aliveFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="5%" stopColor="#86efac" stopOpacity={0.45} />
                <stop offset="95%" stopColor="#86efac" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="deadFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="5%" stopColor="#fb7185" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#fb7185" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
            <XAxis dataKey="step" stroke="rgba(255,255,255,0.45)" tickLine={false} />
            <YAxis stroke="rgba(255,255,255,0.45)" tickLine={false} width={36} />
            <Tooltip content={<MetricTooltip />} />
            <Legend />
            <Area dataKey="alive" name="Alive" stroke="#86efac" fill="url(#aliveFill)" strokeWidth={2} />
            <Area dataKey="dead" name="Dead" stroke="#fb7185" fill="url(#deadFill)" strokeWidth={2} />
            <Line dataKey="divided" name="Divided" dot={false} stroke="#facc15" strokeWidth={2} />
            <Line dataKey="population" name="Total" dot={false} stroke="#f8fafc" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartPanel>

      <ChartPanel title="Energy and biomass" subtitle="Aggregate ATP and biomass across retained cells">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={metrics} margin={{ left: 4, right: 12, top: 8, bottom: 0 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
            <XAxis dataKey="step" stroke="rgba(255,255,255,0.45)" tickLine={false} />
            <YAxis stroke="rgba(255,255,255,0.45)" tickLine={false} width={42} />
            <Tooltip content={<MetricTooltip />} />
            <Legend />
            <Line dataKey="total_atp" name="ATP" dot={false} stroke="#67e8f9" strokeWidth={2} />
            <Line dataKey="atp_per_alive_cell" name="ATP per alive cell" dot={false} stroke="#f0abfc" strokeWidth={2} />
            <Line dataKey="total_biomass" name="Biomass" dot={false} stroke="#a7f3d0" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </ChartPanel>

      <ChartPanel title="Environment" subtitle="Available glucose and terminal electron acceptor">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={metrics} margin={{ left: 4, right: 12, top: 8, bottom: 0 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
            <XAxis dataKey="step" stroke="rgba(255,255,255,0.45)" tickLine={false} />
            <YAxis stroke="rgba(255,255,255,0.45)" tickLine={false} width={42} />
            <Tooltip content={<MetricTooltip />} />
            <Legend />
            <Line dataKey="environment_glucose" name="Glucose" dot={false} stroke="#fde68a" strokeWidth={2} />
            <Line
              dataKey="environment_electron_acceptor"
              name="Electron acceptor"
              dot={false}
              stroke="#93c5fd"
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      </ChartPanel>

      <ChartPanel title="Stress" subtitle="Toxicity accumulation during the run">
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={metrics} margin={{ left: 4, right: 12, top: 8, bottom: 0 }}>
            <defs>
              <linearGradient id="toxicityFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="5%" stopColor="#fb7185" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#fb7185" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
            <XAxis dataKey="step" stroke="rgba(255,255,255,0.45)" tickLine={false} />
            <YAxis stroke="rgba(255,255,255,0.45)" tickLine={false} width={42} />
            <Tooltip content={<MetricTooltip />} />
            <Area dataKey="toxicity" name="Toxicity" stroke="#fb7185" fill="url(#toxicityFill)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartPanel>
    </div>
  );
}

interface ChartPanelProps {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}

function ChartPanel({ title, subtitle, children }: ChartPanelProps) {
  return (
    <section className="rounded-lg border border-white/10 bg-neutral-950/70 p-4">
      <div className="mb-4">
        <h2 className="text-base font-medium text-white">{title}</h2>
        <p className="mt-1 text-sm text-neutral-400">{subtitle}</p>
      </div>
      {children}
    </section>
  );
}

function MetricTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number; color?: string }>;
  label?: number;
}) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="rounded-lg border border-white/10 bg-neutral-950/95 p-3 text-sm shadow-2xl">
      <div className="mb-2 font-mono text-xs text-neutral-400">step {label}</div>
      <div className="grid gap-1">
        {payload.map((item) => (
          <div key={item.name} className="flex items-center justify-between gap-6">
            <span className="flex items-center gap-2 text-neutral-300">
              <span className="size-2 rounded-full" style={{ backgroundColor: item.color }} />
              {item.name}
            </span>
            <span className="font-mono text-white">{formatNumber(item.value, 3)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
