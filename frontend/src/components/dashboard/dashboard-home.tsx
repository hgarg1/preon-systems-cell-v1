"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Activity, Database, FlaskConical, GitCompare, RefreshCw, Route, Search, Server, Sigma, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { createDemoRun, getHealth, listRuns, type HealthResponse, type RunRecord } from "@/lib/api";

import { formatDate, formatNumber, pluralize } from "./format";
import { StatusBadge } from "./status-badge";
import { StorageModeRibbon, storageRunCopy } from "./storage-mode-ribbon";

export function DashboardHome() {
  const router = useRouter();
  const pathname = usePathname();
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [seed, setSeed] = useState(7);
  const [maxSteps, setMaxSteps] = useState(80);
  const [query, setQuery] = useState("");
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshRuns = useCallback(async (signal?: AbortSignal) => {
    setRefreshing(true);
    setError(null);
    try {
      const [nextRuns, nextHealth] = await Promise.all([listRuns(signal), getHealth(signal)]);
      setRuns(nextRuns);
      setHealth(nextHealth);
      setLastRefreshedAt(new Date());
    } catch (caught) {
      if (!signal?.aborted) {
        setHealth(null);
        setError(caught instanceof Error ? caught.message : "Unable to load runs");
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    setSelectedRunIds((current) => current.filter((runId) => runs.some((run) => run.run_id === runId)));
  }, [runs]);

  useEffect(() => {
    if (pathname !== "/") {
      return;
    }
    const controller = new AbortController();
    void refreshRuns(controller.signal);
    return () => controller.abort();
  }, [pathname, refreshRuns]);

  const totals = useMemo(() => {
    const completed = runs.filter((run) => run.status === "completed").length;
    const failed = runs.filter((run) => run.status === "failed").length;
    const steps = runs.reduce((sum, run) => sum + (run.final_step ?? 0), 0);
    const maxStep = Math.max(0, ...runs.map((run) => run.final_step ?? 0));
    return { completed, failed, steps, maxStep };
  }, [runs]);

  const filteredRuns = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return runs;
    }
    return runs.filter((run) =>
      [run.run_id, run.scenario_name, run.status, run.termination_reason ?? "", run.seed.toString()]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [query, runs]);

  const canCreate = Number.isFinite(seed) && Number.isFinite(maxSteps) && maxSteps > 0 && !creating;
  const canCompare = selectedRunIds.length >= 2 && selectedRunIds.length <= 8;

  const toggleRunSelection = useCallback((runId: string) => {
    setSelectedRunIds((current) => {
      if (current.includes(runId)) {
        return current.filter((selectedRunId) => selectedRunId !== runId);
      }
      if (current.length >= 8) {
        return current;
      }
      return [...current, runId];
    });
  }, []);

  const clearSelection = useCallback(() => setSelectedRunIds([]), []);

  const openComparison = useCallback(() => {
    if (!canCompare) {
      return;
    }
    router.push(`/runs/compare?runs=${encodeURIComponent(selectedRunIds.join(","))}`);
  }, [canCompare, router, selectedRunIds]);

  async function handleCreateRun() {
    setCreating(true);
    setError(null);
    try {
      const response = await createDemoRun({
        seed,
        maxSteps,
      });
      router.push(`/runs/${response.run.run_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create run");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(79,230,164,0.16),transparent_32rem),linear-gradient(135deg,rgba(255,255,255,0.04),transparent_30rem)]">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-8 px-5 py-6 sm:px-8 lg:px-10">
        <header className="flex flex-col gap-5 border-b border-white/10 pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-emerald-200">
              <span className="flex items-center gap-2">
                <Database className="size-4" aria-hidden="true" />
                Preon Systems Analytics
              </span>
              <span className="flex items-center gap-2 rounded-md border border-white/10 bg-white/5 px-2 py-1 font-mono text-xs text-neutral-300">
                <Server className="size-3 text-emerald-200" aria-hidden="true" />
                {health ? `API ${health.engine_version}` : "API offline"}
              </span>
            </div>
            <h1 className="max-w-4xl text-4xl font-semibold leading-tight tracking-normal text-white sm:text-5xl">
              Multi-cell run analytics
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-neutral-300">
              Create runs from the default scenario, inspect population curves, and drill into lineage events for each cell.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="grid gap-2">
              <Label htmlFor="seed" className="text-neutral-300">
                Seed
              </Label>
              <Input
                id="seed"
                type="number"
                value={seed}
                onChange={(event) => setSeed(Number(event.target.value))}
                className="h-9 w-28 rounded-lg border-white/10 bg-white/8 font-mono text-white"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="max-steps" className="text-neutral-300">
                Max steps
              </Label>
              <Input
                id="max-steps"
                min={1}
                type="number"
                value={maxSteps}
                onChange={(event) => setMaxSteps(Math.max(1, Number(event.target.value)))}
                className="h-9 w-32 rounded-lg border-white/10 bg-white/8 font-mono text-white"
              />
            </div>
            <Button
              className="h-9 rounded-lg bg-emerald-300 px-4 text-neutral-950 hover:bg-emerald-200"
              disabled={!canCreate}
              onClick={handleCreateRun}
            >
              <FlaskConical className="size-4" aria-hidden="true" />
              {creating ? "Creating" : "Create Demo Run"}
            </Button>
          </div>
        </header>

        <StorageModeRibbon storage={health?.storage} />

        <section className="grid gap-4 md:grid-cols-3">
          <MetricTile icon={Activity} label="Completed runs" value={formatNumber(totals.completed, 0)} />
          <MetricTile icon={Sigma} label="Steps recorded" value={formatNumber(totals.steps, 0)} />
          <MetricTile icon={Route} label="Longest run" value={`${formatNumber(totals.maxStep, 0)} steps`} />
        </section>

        <section className="min-h-[28rem] overflow-hidden rounded-lg border border-white/10 bg-neutral-950/72">
          <div className="flex flex-col gap-4 border-b border-white/10 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-lg font-medium text-white">Run history</h2>
              <p className="text-sm text-neutral-400">
                {pluralize(runs.length, "run")} {storageRunCopy(health?.storage)}
                {totals.failed ? `, ${pluralize(totals.failed, "failed run")}` : ""}.
                {selectedRunIds.length ? ` ${selectedRunIds.length}/8 selected for comparison.` : ""}
                {lastRefreshedAt ? ` Refreshed ${formatDate(lastRefreshedAt.toISOString())}.` : ""}
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-neutral-500" aria-hidden="true" />
                <Input
                  aria-label="Search runs"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search runs"
                  className="h-9 w-full rounded-lg border-white/10 bg-white/8 pl-9 text-white placeholder:text-neutral-500 sm:w-64"
                />
              </div>
              <Button
                variant="outline"
                className="w-fit rounded-lg border-white/10 bg-white/5 text-white hover:bg-white/10"
                disabled={refreshing}
                onClick={() => void refreshRuns()}
              >
                <RefreshCw className={refreshing ? "size-4 animate-spin" : "size-4"} aria-hidden="true" />
                Refresh
              </Button>
              <Button
                className="w-fit rounded-lg bg-sky-300 text-neutral-950 hover:bg-sky-200"
                disabled={!canCompare}
                onClick={openComparison}
              >
                <GitCompare className="size-4" aria-hidden="true" />
                Compare {selectedRunIds.length ? `(${selectedRunIds.length})` : ""}
              </Button>
              {selectedRunIds.length ? (
                <Button
                  variant="ghost"
                  className="w-fit rounded-lg text-neutral-300 hover:bg-white/5 hover:text-white"
                  onClick={clearSelection}
                >
                  <X className="size-4" aria-hidden="true" />
                  Clear
                </Button>
              ) : null}
            </div>
          </div>

          {error ? (
            <div className="m-4 rounded-lg border border-rose-300/30 bg-rose-300/10 p-4 text-sm text-rose-100">
              {error}
            </div>
          ) : null}

          {loading ? (
            <div className="grid gap-3 p-4">
              <Skeleton className="h-11 rounded-lg bg-white/8" />
              <Skeleton className="h-11 rounded-lg bg-white/8" />
              <Skeleton className="h-11 rounded-lg bg-white/8" />
            </div>
          ) : filteredRuns.length ? (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-white/10 hover:bg-transparent">
                    <TableHead className="w-24 text-neutral-300">Compare</TableHead>
                    <TableHead className="text-neutral-300">Run</TableHead>
                    <TableHead className="text-neutral-300">Status</TableHead>
                    <TableHead className="text-neutral-300">Seed</TableHead>
                    <TableHead className="text-neutral-300">Steps</TableHead>
                    <TableHead className="text-neutral-300">Started</TableHead>
                    <TableHead className="text-neutral-300">Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredRuns.map((run) => (
                    <TableRow key={run.run_id} className="border-white/10 hover:bg-white/5">
                      <TableCell>
                        <label className="flex items-center gap-2 text-xs uppercase text-neutral-400">
                          <input
                            aria-label={`Select ${run.run_id}`}
                            type="checkbox"
                            checked={selectedRunIds.includes(run.run_id)}
                            onChange={() => toggleRunSelection(run.run_id)}
                            className="size-4 accent-sky-300"
                          />
                          {selectedRunIds[0] === run.run_id ? "Base" : ""}
                        </label>
                      </TableCell>
                      <TableCell>
                        <Link
                          href={`/runs/${run.run_id}`}
                          className="font-mono text-sm text-emerald-200 underline-offset-4 hover:underline"
                        >
                          {run.run_id}
                        </Link>
                        <div className="mt-1 text-xs text-neutral-500">{run.scenario_name}</div>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={run.status} />
                      </TableCell>
                      <TableCell className="font-mono text-neutral-200">{run.seed}</TableCell>
                      <TableCell className="font-mono text-neutral-200">
                        {formatNumber(run.final_step ?? 0, 0)} / {formatNumber(run.max_steps, 0)}
                      </TableCell>
                      <TableCell className="text-neutral-300">{formatDate(run.started_at)}</TableCell>
                      <TableCell className="max-w-52 truncate text-neutral-300">
                        {run.termination_reason ?? "-"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : runs.length ? (
            <div className="flex min-h-80 flex-col items-center justify-center px-6 text-center">
              <Separator className="mb-6 w-16 bg-amber-300/40" />
              <h2 className="text-xl font-medium text-white">No runs match that search</h2>
              <p className="mt-2 max-w-md text-sm leading-6 text-neutral-400">
                Clear the search field or create a new demo run with a different seed.
              </p>
            </div>
          ) : (
            <div className="flex min-h-80 flex-col items-center justify-center px-6 text-center">
              <Separator className="mb-6 w-16 bg-emerald-300/40" />
              <h2 className="text-xl font-medium text-white">No runs recorded</h2>
              <p className="mt-2 max-w-md text-sm leading-6 text-neutral-400">
                Create a demo run, then open the run detail page for charts, lineage, and exports.
              </p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

interface MetricTileProps {
  icon: typeof Activity;
  label: string;
  value: string;
}

function MetricTile({ icon: Icon, label, value }: MetricTileProps) {
  return (
    <div className="rounded-lg border border-white/10 bg-neutral-950/70 p-4">
      <div className="flex items-center gap-2 text-sm text-neutral-400">
        <Icon className="size-4 text-emerald-200" aria-hidden="true" />
        {label}
      </div>
      <div className="mt-3 font-mono text-2xl text-white">{value}</div>
    </div>
  );
}
