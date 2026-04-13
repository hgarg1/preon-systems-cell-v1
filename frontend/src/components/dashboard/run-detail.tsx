"use client";

import Link from "next/link";
import { ArrowLeft, Gauge, RefreshCw, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  getLineage,
  getHealth,
  getRun,
  getRunIntelligence,
  getRunTimeSeries,
  type HealthResponse,
  type LineageResponse,
  type RunIntelligence,
  type RunRecord,
  type RunTimeSeriesPoint,
} from "@/lib/api";

import { CellInspectorSheet } from "./cell-inspector-sheet";
import { formatDate, formatNumber, lineageColor } from "./format";
import { LineageScene } from "./lineage-scene";
import { MetricsCharts } from "./metrics-charts";
import { StatusBadge } from "./status-badge";
import { BIExportPanel } from "./bi-export-panel";
import { RunIntelligencePanel } from "./run-intelligence-panel";
import { StorageModeRibbon } from "./storage-mode-ribbon";

interface RunDetailProps {
  runId: string;
}

export function RunDetail({ runId }: RunDetailProps) {
  const [run, setRun] = useState<RunRecord | null>(null);
  const [metrics, setMetrics] = useState<RunTimeSeriesPoint[]>([]);
  const [intelligence, setIntelligence] = useState<RunIntelligence | null>(null);
  const [lineage, setLineage] = useState<LineageResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadRun = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const [runResult, metricsResult, lineageResult, intelligenceResult, healthResult] = await Promise.allSettled([
        getRun(runId, signal),
        getRunTimeSeries(runId, signal),
        getLineage(runId, signal),
        getRunIntelligence(runId, signal),
        getHealth(signal),
      ]);
      if (healthResult.status === "fulfilled") {
        setHealth(healthResult.value);
      } else {
        setHealth(null);
      }
      if (
        runResult.status === "rejected" ||
        metricsResult.status === "rejected" ||
        lineageResult.status === "rejected" ||
        intelligenceResult.status === "rejected"
      ) {
        throw firstRejectedReason([runResult, metricsResult, lineageResult, intelligenceResult]);
      }
      const nextRun = runResult.value;
      const nextMetrics = metricsResult.value;
      const nextLineage = lineageResult.value;
      const nextIntelligence = intelligenceResult.value;
      setRun(nextRun);
      setMetrics(nextMetrics);
      setLineage(nextLineage);
      setIntelligence(nextIntelligence);
      setSelectedCellId((current) => current ?? nextLineage.nodes[0]?.id ?? null);
    } catch (caught) {
      if (!signal?.aborted) {
        setError(caught instanceof Error ? caught.message : "Unable to load run");
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, [runId]);

  useEffect(() => {
    const controller = new AbortController();
    void loadRun(controller.signal);
    return () => controller.abort();
  }, [loadRun]);

  const latestMetrics = metrics.at(-1);
  const analytics = useMemo(() => summarizeMetrics(metrics), [metrics]);
  const selectedNode = useMemo(
    () => lineage?.nodes.find((node) => node.id === selectedCellId) ?? null,
    [lineage, selectedCellId],
  );

  const kpis = [
    { label: "Population", value: formatNumber(latestMetrics?.population, 0) },
    { label: "Alive", value: formatNumber(latestMetrics?.alive, 0) },
    { label: "Divisions", value: formatNumber(latestMetrics?.division_count_total, 0) },
    { label: "ATP", value: formatNumber(latestMetrics?.total_atp, 2) },
    { label: "Biomass", value: formatNumber(latestMetrics?.total_biomass, 2) },
    { label: "Toxicity", value: formatNumber(latestMetrics?.toxicity, 3) },
  ];

  const handleSelectCell = useCallback((cellId: string) => {
    setSelectedCellId(cellId);
  }, []);

  const openInspector = useCallback((cellId: string) => {
    setSelectedCellId(cellId);
    setInspectorOpen(true);
  }, []);

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(79,230,164,0.14),transparent_30rem),linear-gradient(135deg,rgba(255,255,255,0.035),transparent_36rem)]">
      <div className="mx-auto grid min-h-screen w-full max-w-7xl gap-6 px-5 py-6 sm:px-8 lg:px-10">
        <header className="flex flex-col gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <Button asChild variant="ghost" className="mb-3 rounded-lg px-0 text-neutral-300 hover:bg-transparent hover:text-white">
              <Link href="/">
                <ArrowLeft className="size-4" aria-hidden="true" />
                Runs
              </Link>
            </Button>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="break-all font-mono text-2xl font-semibold text-white sm:text-3xl">{runId}</h1>
              {run ? <StatusBadge status={run.status} /> : null}
            </div>
            <p className="mt-2 text-sm text-neutral-400">
              Metrics, lineage, and cell event drilldown for one simulation run.
            </p>
          </div>
          <Button
            variant="outline"
            className="w-fit rounded-lg border-white/10 bg-white/5 text-white hover:bg-white/10"
            onClick={() => void loadRun()}
          >
            <RefreshCw className="size-4" aria-hidden="true" />
            Refresh
          </Button>
        </header>

        <StorageModeRibbon storage={health?.storage} />

        {error ? (
          <section className="rounded-lg border border-rose-300/30 bg-rose-300/10 p-5 text-rose-100">
            <h2 className="font-medium">Unable to load run</h2>
            <p className="mt-2 text-sm leading-6">{error}</p>
          </section>
        ) : null}

        {loading ? (
          <div className="grid gap-4">
            <Skeleton className="h-28 rounded-lg bg-white/8" />
            <Skeleton className="h-80 rounded-lg bg-white/8" />
            <Skeleton className="h-80 rounded-lg bg-white/8" />
          </div>
        ) : (
          <>
            <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-lg border border-white/10 bg-neutral-950/72 p-4">
                <div className="mb-4 flex items-center gap-2 text-sm text-neutral-400">
                  <Gauge className="size-4 text-emerald-200" aria-hidden="true" />
                  Final sample
                </div>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {kpis.map((kpi) => (
                    <div key={kpi.label}>
                      <div className="text-xs uppercase text-neutral-500">{kpi.label}</div>
                      <div className="mt-2 font-mono text-2xl text-white">{kpi.value}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-white/10 bg-neutral-950/72 p-4">
                <div className="mb-4 flex items-center gap-2 text-sm text-neutral-400">
                  <TrendingUp className="size-4 text-amber-200" aria-hidden="true" />
                  Run analytics
                </div>
                <div className="grid gap-3 text-sm">
                  <RunFact label="Scenario" value={run?.scenario_name ?? "-"} />
                  <RunFact label="Seed" value={run?.seed.toString() ?? "-"} />
                  <RunFact label="Peak population" value={formatNumber(intelligence?.peak_population ?? analytics.peakPopulation, 0)} />
                  <RunFact label="Peak step" value={intelligence?.time_to_peak_step === null ? "-" : `step ${intelligence?.time_to_peak_step ?? "-"}`} />
                  <RunFact label="Survival rate" value={`${formatNumber((intelligence?.survival_ratio ?? analytics.survivalRate) * 100, 1)}%`} />
                  <RunFact label="Started" value={run ? formatDate(run.started_at) : "-"} />
                  <RunFact label="Reason" value={run?.termination_reason ?? "-"} />
                </div>
              </div>
            </section>

            <RunIntelligencePanel intelligence={intelligence} />

            <MetricsCharts metrics={metrics} />

            <BIExportPanel runId={runId} />

            <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
              <LineageScene
                nodes={lineage?.nodes ?? []}
                edges={lineage?.edges ?? []}
                selectedCellId={selectedCellId}
                onSelectCell={handleSelectCell}
              />

              <section className="overflow-hidden rounded-lg border border-white/10 bg-neutral-950/72">
                <div className="border-b border-white/10 px-4 py-4">
                  <h2 className="text-base font-medium text-white">Cells</h2>
                  <p className="mt-1 text-sm text-neutral-400">
                    Select a lineage node, then open details for state and events.
                  </p>
                </div>
                {selectedNode ? (
                  <div className="border-b border-white/10 px-4 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-xs uppercase text-neutral-500">Selected cell</div>
                        <div className="mt-1 break-all font-mono text-lg text-white">{selectedNode.id}</div>
                      </div>
                      <Button
                        className="rounded-lg bg-emerald-300 text-neutral-950 hover:bg-emerald-200"
                        onClick={() => openInspector(selectedNode.id)}
                      >
                        Open details
                      </Button>
                    </div>
                  </div>
                ) : null}
                <div className="max-h-[27rem] overflow-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/10 hover:bg-transparent">
                        <TableHead className="text-neutral-300">Cell</TableHead>
                        <TableHead className="text-neutral-300">Gen</TableHead>
                        <TableHead className="text-neutral-300">Status</TableHead>
                        <TableHead className="text-neutral-300">Born</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(lineage?.nodes ?? []).map((node) => (
                        <TableRow
                          key={node.id}
                          className="cursor-pointer border-white/10 hover:bg-white/5 data-[selected=true]:bg-emerald-300/10"
                          data-selected={node.id === selectedCellId}
                          onClick={() => handleSelectCell(node.id)}
                          onDoubleClick={() => openInspector(node.id)}
                        >
                          <TableCell>
                            <div className="flex min-w-0 items-center gap-2">
                              <span
                                className="size-2 shrink-0 rounded-full"
                                style={{ backgroundColor: lineageColor(node.id, node.generation) }}
                              />
                              <span className="break-all font-mono text-xs text-emerald-100">{node.id}</span>
                            </div>
                          </TableCell>
                          <TableCell className="font-mono text-neutral-200">{node.generation}</TableCell>
                          <TableCell>
                            <StatusBadge status={node.status} />
                          </TableCell>
                          <TableCell className="font-mono text-neutral-300">{node.birth_step}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </section>
            </section>

            <Separator className="bg-white/10" />
          </>
        )}
      </div>

      <CellInspectorSheet
        runId={runId}
        cellId={selectedCellId}
        open={inspectorOpen}
        onOpenChange={setInspectorOpen}
        onSelectCell={openInspector}
      />
    </main>
  );
}

function RunFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 items-start justify-between gap-4">
      <span className="text-neutral-500">{label}</span>
      <span className="break-words text-right font-mono text-neutral-100">{value}</span>
    </div>
  );
}

function summarizeMetrics(metrics: RunTimeSeriesPoint[]) {
  const peakPopulation = Math.max(0, ...metrics.map((metric) => metric.population));
  const firstDivision = metrics.find((metric) => metric.division_count_total > 0);
  const latest = metrics.at(-1);
  const survivalRate = latest && latest.population > 0 ? latest.alive / latest.population : 0;

  return {
    peakPopulation,
    firstDivisionStep: firstDivision?.step ?? null,
    survivalRate,
  };
}

function firstRejectedReason(results: Array<PromiseSettledResult<unknown>>): unknown {
  return results.find((result) => result.status === "rejected")?.reason ?? new Error("Unable to load run");
}
