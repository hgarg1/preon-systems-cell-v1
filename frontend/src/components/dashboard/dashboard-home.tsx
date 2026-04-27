"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Database,
  FlaskConical,
  GitCompare,
  Radio,
  RefreshCw,
  Route,
  Search,
  Server,
  Sigma,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FocusEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  createDemoRun,
  getHealth,
  getRunUpdatesWebSocketUrl,
  listRuns,
  type HealthResponse,
  type RunRecord,
  type RunUpdateEvent,
} from "@/lib/api";

import { formatDate, formatNumber, pluralize } from "./format";
import { StatusBadge } from "./status-badge";
import { StorageModeRibbon, storageRunCopy } from "./storage-mode-ribbon";

const PAGE_SIZE_OPTIONS = [6, 8, 12, 20] as const;
type LiveStatus = "connecting" | "connected" | "offline";
type PageSize = (typeof PAGE_SIZE_OPTIONS)[number];
type DashboardRun = RunRecord & { fresh?: boolean };

export function DashboardHome() {
  const router = useRouter();
  const pathname = usePathname();
  const [runs, setRuns] = useState<DashboardRun[]>([]);
  const [seed, setSeed] = useState(7);
  const [maxSteps, setMaxSteps] = useState(80);
  const [query, setQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(8);
  const [pageMotionKey, setPageMotionKey] = useState(0);
  const [pageDirection, setPageDirection] = useState(1);
  const [pageSizeOpen, setPageSizeOpen] = useState(false);
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const [lastLiveRunId, setLastLiveRunId] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [liveStatus, setLiveStatus] = useState<LiveStatus>("connecting");
  const [error, setError] = useState<string | null>(null);

  const refreshRuns = useCallback(async (signal?: AbortSignal) => {
    setRefreshing(true);
    setError(null);
    try {
      const [nextRuns, nextHealth] = await Promise.all([listRuns(signal), getHealth(signal)]);
      setRuns((current) => preserveFreshRuns(nextRuns, current));
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

  useEffect(() => {
    if (pathname !== "/") {
      return;
    }

    let active = true;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (!active) {
        return;
      }
      setLiveStatus("connecting");
      socket = new WebSocket(getRunUpdatesWebSocketUrl());
      socket.addEventListener("open", () => {
        if (active) {
          setLiveStatus("connected");
        }
      });
      socket.addEventListener("message", (event) => {
        const update = parseRunUpdate(event.data);
        if (!update || update.type !== "run_created") {
          return;
        }
        setRuns((current) => mergeRun(current, { ...update.run, fresh: true }));
        setHealth((current) => (current ? { ...current, storage: update.storage } : current));
        setLastRefreshedAt(new Date());
        setLastLiveRunId(update.run.run_id);
        setPageDirection(-1);
        setCurrentPage(1);
        setPageMotionKey((current) => current + 1);
      });
      socket.addEventListener("close", () => {
        if (!active) {
          return;
        }
        setLiveStatus("offline");
        reconnectTimer = setTimeout(connect, 2500);
      });
      socket.addEventListener("error", () => {
        socket?.close();
      });
    }

    connect();

    return () => {
      active = false;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [pathname]);

  useEffect(() => {
    if (!lastLiveRunId) {
      return;
    }
    const timer = setTimeout(() => {
      setLastLiveRunId((current) => (current === lastLiveRunId ? null : current));
    }, 3600);
    return () => clearTimeout(timer);
  }, [lastLiveRunId]);

  useEffect(() => {
    const freshRunIds = runs.filter((run) => run.fresh).map((run) => run.run_id);
    if (!freshRunIds.length) {
      return;
    }
    const timer = setTimeout(() => {
      setRuns((current) =>
        current.map((run) => (freshRunIds.includes(run.run_id) ? { ...run, fresh: false } : run)),
      );
    }, 3600);
    return () => clearTimeout(timer);
  }, [runs]);

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

  const totalPages = Math.max(1, Math.ceil(filteredRuns.length / pageSize));
  const activePage = Math.min(currentPage, totalPages);
  const pageStart = filteredRuns.length ? (activePage - 1) * pageSize + 1 : 0;
  const pageEnd = Math.min(activePage * pageSize, filteredRuns.length);
  const pageRuns = useMemo(
    () => filteredRuns.slice((activePage - 1) * pageSize, activePage * pageSize),
    [activePage, filteredRuns, pageSize],
  );
  const pageNumbers = useMemo(() => pageWindow(activePage, totalPages), [activePage, totalPages]);

  const canCreate = Number.isFinite(seed) && Number.isFinite(maxSteps) && maxSteps > 0 && !creating;
  const canCompare = selectedRunIds.length >= 2 && selectedRunIds.length <= 8;

  useEffect(() => {
    setCurrentPage(1);
    setPageDirection(1);
    setPageMotionKey((current) => current + 1);
  }, [query, pageSize]);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

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

  const changePage = useCallback(
    (nextPage: number) => {
      const boundedPage = Math.min(Math.max(nextPage, 1), totalPages);
      if (boundedPage === activePage) {
        return;
      }
      setPageDirection(boundedPage > activePage ? 1 : -1);
      setCurrentPage(boundedPage);
      setPageMotionKey((current) => current + 1);
    },
    [activePage, totalPages],
  );

  const changePageSize = useCallback((nextPageSize: PageSize) => {
    setPageSize(nextPageSize);
    setPageSizeOpen(false);
  }, []);

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
              <LiveUpdateIndicator status={liveStatus} />
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
            <>
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
                <TableBody
                  key={pageMotionKey}
                  className={pageDirection < 0 ? "run-table-page-reverse" : "run-table-page"}
                >
                  {pageRuns.map((run) => {
                    const isFresh = Boolean(run.fresh) || run.run_id === lastLiveRunId;
                    return (
                    <TableRow
                      key={run.run_id}
                      className={isFresh ? "run-row-new border-white/10 hover:bg-white/5" : "border-white/10 hover:bg-white/5"}
                    >
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
                        <div className="flex flex-wrap items-center gap-2">
                          <Link
                            href={`/runs/${run.run_id}`}
                            className="font-mono text-sm text-emerald-200 underline-offset-4 hover:underline"
                          >
                            {run.run_id}
                          </Link>
                          {isFresh ? <span className="run-new-badge">New</span> : null}
                        </div>
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
                    );
                  })}
                </TableBody>
              </Table>
            </div>
            <div className="flex flex-col gap-3 border-t border-white/10 px-4 py-3 text-sm text-neutral-400 lg:flex-row lg:items-center lg:justify-between">
              <div className="font-mono text-xs text-neutral-500">
                {pageStart}-{pageEnd} of {filteredRuns.length}
              </div>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <PageSizeSelector
                  open={pageSizeOpen}
                  pageSize={pageSize}
                  onOpenChange={setPageSizeOpen}
                  onSelect={changePageSize}
                />
                <nav className="flex items-center gap-1" aria-label="Run history pages">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-8 rounded-md text-neutral-300 hover:bg-white/5 hover:text-white"
                    disabled={activePage === 1}
                    onClick={() => changePage(activePage - 1)}
                    aria-label="Previous page"
                  >
                    <ChevronLeft className="size-4" aria-hidden="true" />
                  </Button>
                  {pageNumbers.map((pageNumber) => (
                    <Button
                      key={pageNumber}
                      variant="ghost"
                      className={
                        pageNumber === activePage
                          ? "h-8 min-w-8 rounded-md bg-emerald-300/15 px-2 font-mono text-emerald-100 hover:bg-emerald-300/20"
                          : "h-8 min-w-8 rounded-md px-2 font-mono text-neutral-300 hover:bg-white/5 hover:text-white"
                      }
                      onClick={() => changePage(pageNumber)}
                      aria-current={pageNumber === activePage ? "page" : undefined}
                    >
                      {pageNumber}
                    </Button>
                  ))}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-8 rounded-md text-neutral-300 hover:bg-white/5 hover:text-white"
                    disabled={activePage === totalPages}
                    onClick={() => changePage(activePage + 1)}
                    aria-label="Next page"
                  >
                    <ChevronRight className="size-4" aria-hidden="true" />
                  </Button>
                </nav>
              </div>
            </div>
            </>
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

function parseRunUpdate(raw: unknown): RunUpdateEvent | null {
  if (typeof raw !== "string") {
    return null;
  }
  try {
    const payload = JSON.parse(raw) as RunUpdateEvent;
    return payload?.type === "run_created" && typeof payload.run?.run_id === "string" ? payload : null;
  } catch {
    return null;
  }
}

function mergeRun(current: DashboardRun[], nextRun: DashboardRun): DashboardRun[] {
  return [nextRun, ...current.filter((run) => run.run_id !== nextRun.run_id)].sort(
    (left, right) => Date.parse(right.started_at) - Date.parse(left.started_at),
  );
}

function preserveFreshRuns(nextRuns: RunRecord[], current: DashboardRun[]): DashboardRun[] {
  const freshRunIds = new Set(current.filter((run) => run.fresh).map((run) => run.run_id));
  return nextRuns.map((run) => (freshRunIds.has(run.run_id) ? { ...run, fresh: true } : run));
}

function LiveUpdateIndicator({ status }: { status: LiveStatus }) {
  const connected = status === "connected";
  const label = connected ? "Live" : status === "connecting" ? "Connecting" : "Offline";

  return (
    <span
      className={
        connected
          ? "flex w-fit items-center gap-2 rounded-md border border-emerald-300/20 bg-emerald-300/10 px-2.5 py-1.5 text-xs text-emerald-100"
          : "flex w-fit items-center gap-2 rounded-md border border-amber-300/25 bg-amber-300/10 px-2.5 py-1.5 text-xs text-amber-100"
      }
    >
      <Radio className={connected ? "size-3" : "size-3 animate-pulse"} aria-hidden="true" />
      {label}
    </span>
  );
}

function pageWindow(activePage: number, totalPages: number): number[] {
  const size = Math.min(5, totalPages);
  const start = Math.min(Math.max(activePage - 2, 1), Math.max(totalPages - size + 1, 1));
  return Array.from({ length: size }, (_, index) => start + index);
}

function PageSizeSelector({
  open,
  pageSize,
  onOpenChange,
  onSelect,
}: {
  open: boolean;
  pageSize: PageSize;
  onOpenChange: (open: boolean) => void;
  onSelect: (pageSize: PageSize) => void;
}) {
  function handleBlur(event: FocusEvent<HTMLDivElement>) {
    const nextTarget = event.relatedTarget;
    if (!(nextTarget instanceof Node) || !event.currentTarget.contains(nextTarget)) {
      onOpenChange(false);
    }
  }

  return (
    <div className="relative w-fit" onBlur={handleBlur}>
      <button
        type="button"
        className="flex h-8 items-center gap-2 rounded-md border border-white/10 bg-white/5 px-2.5 text-xs text-neutral-200 transition-colors hover:bg-white/10"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => onOpenChange(!open)}
      >
        <span className="text-neutral-500">Rows</span>
        <span className="font-mono text-white">{pageSize}</span>
        <ChevronDown className={open ? "size-3 rotate-180 transition-transform" : "size-3 transition-transform"} aria-hidden="true" />
      </button>
      {open ? (
        <div
          className="run-size-menu absolute bottom-10 right-0 z-20 grid min-w-28 gap-1 rounded-lg border border-white/10 bg-neutral-950 p-1 shadow-2xl shadow-black/40"
          role="listbox"
          aria-label="Rows per page"
        >
          {PAGE_SIZE_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              role="option"
              aria-selected={option === pageSize}
              className={
                option === pageSize
                  ? "rounded-md bg-emerald-300/15 px-3 py-1.5 text-left font-mono text-xs text-emerald-100"
                  : "rounded-md px-3 py-1.5 text-left font-mono text-xs text-neutral-300 hover:bg-white/8 hover:text-white"
              }
              onClick={() => onSelect(option)}
            >
              {option}
            </button>
          ))}
        </div>
      ) : null}
    </div>
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
