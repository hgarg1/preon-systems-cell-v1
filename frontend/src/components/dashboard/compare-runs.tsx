"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Eye, EyeOff, GitCompare, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  compareRuns,
  getHealth,
  listRuns,
  type HealthResponse,
  type MetricDelta,
  type RunComparisonResponse,
  type RunRecord,
} from "@/lib/api";

import { formatNumber } from "./format";
import { StatusBadge } from "./status-badge";
import { StorageModeRibbon } from "./storage-mode-ribbon";

interface CompareRunsProps {
  initialRunIds: string[];
}

const DELTA_METRICS = [
  ["peak_population", "Peak population"],
  ["time_to_peak_step", "Time to peak"],
  ["lifespan_steps", "Lifespan"],
  ["survival_ratio", "Survival ratio"],
  ["energy_per_alive_cell_final", "ATP per alive cell"],
  ["early_growth_rate", "Early growth"],
  ["late_growth_rate", "Late growth"],
  ["growth_rate_delta", "Growth shift"],
  ["division_intensity", "Division intensity"],
] as const;

const RUN_COMPARE_LIMIT = 8;

export function CompareRuns({ initialRunIds }: CompareRunsProps) {
  const router = useRouter();
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>(() => uniqueRunIds(initialRunIds).slice(0, RUN_COMPARE_LIMIT));
  const [comparison, setComparison] = useState<RunComparisonResponse | null>(null);
  const [hiddenRunIds, setHiddenRunIds] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const canCompare = selectedRunIds.length >= 2 && selectedRunIds.length <= RUN_COMPARE_LIMIT;

  const loadRuns = useCallback(async (signal?: AbortSignal) => {
    try {
      const [nextRuns, nextHealth] = await Promise.all([listRuns(signal), getHealth(signal)]);
      setRuns(nextRuns);
      setHealth(nextHealth);
    } catch (caught) {
      if (!signal?.aborted) {
        setHealth(null);
        setError(caught instanceof Error ? caught.message : "Unable to load runs");
      }
    }
  }, []);

  const loadComparison = useCallback(async (signal?: AbortSignal) => {
    if (!canCompare) {
      setComparison(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const nextComparison = await compareRuns(selectedRunIds, signal);
      setComparison(nextComparison);
      router.replace(`/runs/compare?runs=${encodeURIComponent(selectedRunIds.join(","))}`);
    } catch (caught) {
      if (!signal?.aborted) {
        setComparison(null);
        setError(caught instanceof Error ? caught.message : "Unable to compare runs");
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, [canCompare, router, selectedRunIds]);

  useEffect(() => {
    const controller = new AbortController();
    void loadRuns(controller.signal);
    return () => controller.abort();
  }, [loadRuns]);

  useEffect(() => {
    const controller = new AbortController();
    void loadComparison(controller.signal);
    return () => controller.abort();
  }, [loadComparison]);

  useEffect(() => {
    setHiddenRunIds((current) => new Set([...current].filter((runId) => selectedRunIds.includes(runId))));
  }, [selectedRunIds]);

  const visibleRunIds = useMemo(
    () => selectedRunIds.filter((runId) => !hiddenRunIds.has(runId)),
    [hiddenRunIds, selectedRunIds],
  );
  const chartRows = useMemo(() => buildChartRows(comparison), [comparison]);

  const toggleRunSelection = useCallback((runId: string) => {
    setSelectedRunIds((current) => {
      if (current.includes(runId)) {
        return current.filter((selectedRunId) => selectedRunId !== runId);
      }
      if (current.length >= RUN_COMPARE_LIMIT) {
        return current;
      }
      return [...current, runId];
    });
  }, []);

  const toggleVisibility = useCallback((runId: string) => {
    setHiddenRunIds((current) => {
      const next = new Set(current);
      if (next.has(runId)) {
        next.delete(runId);
      } else {
        next.add(runId);
      }
      return next;
    });
  }, []);

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(125,211,252,0.14),transparent_30rem),linear-gradient(135deg,rgba(255,255,255,0.035),transparent_36rem)]">
      <div className="mx-auto grid min-h-screen w-full max-w-7xl gap-6 px-5 py-6 sm:px-8 lg:px-10">
        <header className="flex flex-col gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <Button asChild variant="ghost" className="mb-3 rounded-lg px-0 text-neutral-300 hover:bg-transparent hover:text-white">
              <Link href="/">
                <ArrowLeft className="size-4" aria-hidden="true" />
                Runs
              </Link>
            </Button>
            <div className="flex items-center gap-3">
              <GitCompare className="size-5 text-sky-200" aria-hidden="true" />
              <h1 className="text-2xl font-semibold text-white sm:text-3xl">Compare runs</h1>
            </div>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-neutral-400">
              Compare 2 to 8 runs. The first selected run is the baseline for deltas.
            </p>
          </div>
          <Button
            variant="outline"
            className="w-fit rounded-lg border-white/10 bg-white/5 text-white hover:bg-white/10"
            disabled={!canCompare || loading}
            onClick={() => void loadComparison()}
          >
            <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} aria-hidden="true" />
            Refresh
          </Button>
        </header>

        <StorageModeRibbon storage={health?.storage} />

        <RunSelector
          runs={runs}
          selectedRunIds={selectedRunIds}
          onToggleRun={toggleRunSelection}
        />

        {error ? (
          <section className="rounded-lg border border-rose-300/30 bg-rose-300/10 p-5 text-sm leading-6 text-rose-100">
            {error}
          </section>
        ) : null}

        {!canCompare ? (
          <section className="rounded-lg border border-white/10 bg-neutral-950/72 p-6 text-sm leading-6 text-neutral-300">
            Select at least two runs from the run history, or use the picker above.
          </section>
        ) : loading ? (
          <div className="grid gap-4">
            <Skeleton className="h-36 rounded-lg bg-white/8" />
            <Skeleton className="h-80 rounded-lg bg-white/8" />
            <Skeleton className="h-80 rounded-lg bg-white/8" />
          </div>
        ) : comparison ? (
          <>
            <ComparisonRunStrip comparison={comparison} hiddenRunIds={hiddenRunIds} onToggleVisibility={toggleVisibility} />
            <section className="grid gap-4 xl:grid-cols-2">
              <ComparisonChart
                title="Population overlay"
                data={chartRows}
                metric="population"
                runIds={visibleRunIds}
                valueLabel="population"
              />
              <ComparisonChart
                title="ATP overlay"
                data={chartRows}
                metric="total_atp"
                runIds={visibleRunIds}
                valueLabel="ATP"
              />
            </section>
            <DeltaMatrix comparison={comparison} />
          </>
        ) : null}
      </div>
    </main>
  );
}

function RunSelector({
  runs,
  selectedRunIds,
  onToggleRun,
}: {
  runs: RunRecord[];
  selectedRunIds: string[];
  onToggleRun: (runId: string) => void;
}) {
  const runById = new Map(runs.map((run) => [run.run_id, run]));
  const availableRuns = runs.filter((run) => !selectedRunIds.includes(run.run_id));

  return (
    <section className="grid gap-4 rounded-lg border border-white/10 bg-neutral-950/72 p-4 lg:grid-cols-[1.05fr_1fr]">
      <div>
        <div className="flex flex-col gap-1">
          <h2 className="text-base font-medium text-white">Selected runs</h2>
          <p className="text-sm text-neutral-400">
            {selectedRunIds.length}/{RUN_COMPARE_LIMIT} selected. The first selected run is the baseline.
          </p>
        </div>
        <div className="mt-4 grid gap-2">
          {selectedRunIds.length ? (
            selectedRunIds.map((runId, index) => {
              const run = runById.get(runId);
              return (
                <div
                  key={runId}
                  className="flex min-h-12 items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      {index === 0 ? (
                        <span className="rounded-md bg-sky-300 px-2 py-0.5 text-[0.68rem] font-semibold uppercase tracking-normal text-neutral-950">
                          Baseline
                        </span>
                      ) : null}
                      <span className="break-all font-mono text-xs text-sky-200">{runId}</span>
                    </div>
                    {run ? (
                      <div className="mt-1 text-xs text-neutral-500">
                        seed {run.seed} / {run.scenario_name}
                      </div>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    aria-label={`Remove ${runId}`}
                    className="shrink-0 rounded-md border border-white/10 p-1 text-neutral-400 hover:bg-white/5 hover:text-white"
                    onClick={() => onToggleRun(runId)}
                  >
                    <X className="size-4" />
                  </button>
                </div>
              );
            })
          ) : (
            <div className="rounded-lg border border-dashed border-white/10 px-4 py-6 text-sm text-neutral-400">
              Choose runs from the list to start a comparison.
            </div>
          )}
        </div>
      </div>

      <div className="min-w-0">
        <div className="flex flex-col gap-1">
          <h2 className="text-base font-medium text-white">Available runs</h2>
          <p className="text-sm text-neutral-400">Add more runs to compare population and energy curves.</p>
        </div>
        <div className="mt-4 max-h-72 overflow-y-auto pr-1">
          {availableRuns.length ? (
            <div className="grid gap-2">
              {availableRuns.map((run) => (
                <button
                  key={run.run_id}
                  type="button"
                  disabled={selectedRunIds.length >= RUN_COMPARE_LIMIT}
                  className="flex min-h-11 items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/[0.025] px-3 py-2 text-left hover:bg-white/[0.055] disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => onToggleRun(run.run_id)}
                >
                  <span className="min-w-0">
                    <span className="block break-all font-mono text-xs text-neutral-200">{run.run_id}</span>
                    <span className="mt-1 block text-xs text-neutral-500">
                      seed {run.seed} / {run.scenario_name}
                    </span>
                  </span>
                  <span className="shrink-0 rounded-md border border-white/10 px-2 py-1 text-xs text-neutral-300">
                    Add
                  </span>
                </button>
              ))}
            </div>
          ) : runs.length ? (
            <div className="rounded-lg border border-dashed border-white/10 px-4 py-6 text-sm text-neutral-400">
              Every loaded run is already selected.
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-white/10 px-4 py-6 text-sm text-neutral-400">
              No run records loaded yet.
            </div>
          )}
        </div>
        {selectedRunIds.length >= RUN_COMPARE_LIMIT ? (
          <p className="mt-3 text-xs text-amber-200">Comparison is capped at {RUN_COMPARE_LIMIT} runs for chart readability.</p>
        ) : null}
      </div>
    </section>
  );
}

function ComparisonRunStrip({
  comparison,
  hiddenRunIds,
  onToggleVisibility,
}: {
  comparison: RunComparisonResponse;
  hiddenRunIds: Set<string>;
  onToggleVisibility: (runId: string) => void;
}) {
  return (
    <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {comparison.runs.map((run) => (
        <div key={run.run_id} className="rounded-lg border border-white/10 bg-neutral-950/72 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="break-all font-mono text-sm text-sky-200">{run.run_id}</div>
              <div className="mt-1 text-xs uppercase text-neutral-500">{run.role}</div>
            </div>
            <button
              type="button"
              aria-label={hiddenRunIds.has(run.run_id) ? `Show ${run.run_id}` : `Hide ${run.run_id}`}
              className="rounded-md border border-white/10 p-1 text-neutral-300 hover:bg-white/5 hover:text-white"
              onClick={() => onToggleVisibility(run.run_id)}
            >
              {hiddenRunIds.has(run.run_id) ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <StatusBadge status={run.status} />
            <span className="font-mono text-xs text-neutral-400">seed {run.seed}</span>
          </div>
          <div className="mt-4 grid gap-2 text-sm">
            <RunStat label="Peak" value={formatNumber(run.intelligence.peak_population, 0)} />
            <RunStat label="Lifespan" value={`${formatNumber(run.intelligence.lifespan_steps, 0)} steps`} />
            <RunStat label="Survival" value={`${formatNumber(run.intelligence.survival_ratio * 100, 1)}%`} />
          </div>
        </div>
      ))}
    </section>
  );
}

function ComparisonChart({
  title,
  data,
  metric,
  runIds,
  valueLabel,
}: {
  title: string;
  data: ComparisonChartRow[];
  metric: "population" | "total_atp";
  runIds: string[];
  valueLabel: string;
}) {
  return (
    <section className="rounded-lg border border-white/10 bg-neutral-950/72 p-4">
      <div className="mb-4">
        <h2 className="text-base font-medium text-white">{title}</h2>
        <p className="mt-1 text-sm text-neutral-400">
          {runIds.length ? `Step-aligned ${valueLabel} values for ${runIds.length} visible runs.` : "Show at least one run to render this chart."}
        </p>
      </div>
      {runIds.length ? (
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={data} margin={{ left: 4, right: 12, top: 8, bottom: 0 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
            <XAxis dataKey="step" stroke="rgba(255,255,255,0.45)" tickLine={false} />
            <YAxis stroke="rgba(255,255,255,0.45)" tickLine={false} width={42} />
            <Tooltip content={<ComparisonTooltip />} />
            <Legend />
            {runIds.map((runId, index) => (
              <Line
                key={runId}
                dataKey={`${metric}.${runId}`}
                name={shortRunId(runId)}
                dot={false}
                stroke={runColor(runId, index)}
                strokeWidth={2}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="flex h-80 items-center justify-center rounded-lg border border-dashed border-white/10 px-6 text-center text-sm text-neutral-400">
          All selected runs are hidden.
        </div>
      )}
    </section>
  );
}

function DeltaMatrix({ comparison }: { comparison: RunComparisonResponse }) {
  const comparisonRuns = comparison.runs.filter((run) => run.role !== "baseline");
  return (
    <section className="overflow-hidden rounded-lg border border-white/10 bg-neutral-950/72">
      <div className="border-b border-white/10 px-4 py-4">
        <h2 className="text-base font-medium text-white">Delta matrix</h2>
        <p className="mt-1 break-all text-sm text-neutral-400">
          Each value is measured against {comparison.baseline_run_id}.
        </p>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-white/10 hover:bg-transparent">
              <TableHead className="text-neutral-300">Metric</TableHead>
              {comparisonRuns.map((run) => (
                <TableHead key={run.run_id} className="min-w-44 text-neutral-300">
                  <span className="block font-mono text-xs text-sky-200">{shortRunId(run.run_id)}</span>
                  <span className="mt-1 block text-xs font-normal text-neutral-500">seed {run.seed}</span>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {DELTA_METRICS.map(([metricKey, label]) => (
              <TableRow key={metricKey} className="border-white/10 hover:bg-white/5">
                <TableCell className="font-medium text-neutral-200">{label}</TableCell>
                {comparisonRuns.map((run) => {
                  const delta = comparison.deltas[run.run_id]?.[metricKey];
                  return (
                    <TableCell key={run.run_id} className="font-mono text-sm text-neutral-200">
                      <div>{formatSigned(delta?.absolute_delta)}</div>
                      <div className="text-xs text-neutral-500">{formatDeltaPercent(delta)}</div>
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}

function RunStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-neutral-500">{label}</span>
      <span className="font-mono text-neutral-100">{value}</span>
    </div>
  );
}

function ComparisonTooltip({
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

interface ComparisonChartRow {
  step: number;
  population: Record<string, number | null>;
  total_atp: Record<string, number | null>;
}

function buildChartRows(comparison: RunComparisonResponse | null): ComparisonChartRow[] {
  if (!comparison) {
    return [];
  }
  return comparison.aligned_series.map((point) => ({
    step: point.step,
    population: point.population,
    total_atp: point.total_atp,
  }));
}

function uniqueRunIds(runIds: string[]): string[] {
  const result: string[] = [];
  for (const runId of runIds) {
    if (runId && !result.includes(runId)) {
      result.push(runId);
    }
  }
  return result;
}

function shortRunId(runId: string): string {
  if (runId.length <= 18) {
    return runId;
  }
  return `${runId.slice(0, 10)}...${runId.slice(-5)}`;
}

function runColor(runId: string, index: number): string {
  let hash = index * 47;
  for (const char of runId) {
    hash = (hash * 31 + char.charCodeAt(0)) % 360;
  }
  return `hsl(${hash} 78% 68%)`;
}

function formatSigned(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, 3)}`;
}

function formatDeltaPercent(delta: MetricDelta | null | undefined): string {
  if (!delta || delta.percent_delta === null || delta.percent_delta === undefined) {
    return delta?.baseline === 0 ? "baseline zero" : "not comparable";
  }
  const sign = delta.percent_delta > 0 ? "+" : "";
  return `${sign}${formatNumber(delta.percent_delta, 2)}%`;
}
