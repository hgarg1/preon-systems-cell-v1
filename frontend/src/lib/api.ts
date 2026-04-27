export type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface RunRecord {
  run_id: string;
  scenario_name: string;
  scenario_hash: string;
  seed: number;
  status: RunStatus;
  started_at: string;
  completed_at: string | null;
  max_steps: number;
  final_step: number | null;
  termination_reason: string | null;
}

export interface HealthResponse {
  status: string;
  engine_version: string;
  storage: StorageStatus;
}

export interface StorageStatus {
  mode: "postgres" | "memory" | string;
  primary: string;
  fallback: string;
  degraded: boolean;
  reason: string | null;
}

export interface PopulationMetrics {
  step: number;
  time: number;
  population_count: number;
  alive_count: number;
  dead_count: number;
  divided_count: number;
  division_count_total: number;
  total_atp: number;
  total_biomass: number;
  environment_glucose: number;
  environment_electron_acceptor: number;
  toxicity: number;
}

export interface LineageNode {
  id: string;
  parent_id: string | null;
  generation: number;
  status: "alive" | "divided" | "dead" | string;
  birth_step: number;
  death_step: number | null;
}

export interface LineageEdge {
  source: string;
  target: string;
}

export interface LineageResponse {
  run_id: string;
  root: string | null;
  nodes: LineageNode[];
  edges: LineageEdge[];
}

export interface CellState {
  id: string;
  parent_id: string | null;
  generation: number;
  birth_step: number;
  death_step: number | null;
  status: string;
  name: string;
  energy: {
    atp: number;
    adp: number;
  };
  cytosol: {
    glucose: number;
    pyruvate: number;
    nadh: number;
    acetyl_coa: number;
    nad_plus: number;
    fad: number;
    fadh2: number;
    co2: number;
    membrane_gradient: number;
  };
  waste: number;
  membrane_integrity: number;
  glucose_transporter_density: number;
  biomass: number;
  x: number;
  y: number;
  z: number;
}

export interface CellEvent {
  step: number;
  time: number;
  type: string;
  message: string;
  values: Record<string, unknown>;
}

export interface DefaultScenarioResponse {
  scenario: Record<string, unknown>;
}

export interface CreateRunResponse {
  run: RunRecord;
  final_state: unknown;
  termination_reason: string;
}

export interface MetricsResponse {
  run_id: string;
  resolution: number;
  series: PopulationMetrics[];
}

export interface RunTimeSeriesPoint {
  step: number;
  time: number;
  population: number;
  alive: number;
  dead: number;
  divided: number;
  division_count_total: number;
  total_atp: number;
  total_biomass: number;
  atp_per_alive_cell: number | null;
  atp_per_population_cell: number | null;
  environment_glucose: number;
  environment_electron_acceptor: number;
  toxicity: number;
}

export interface RunTimeSeriesResponse {
  run_id: string;
  resolution: number;
  points: RunTimeSeriesPoint[];
}

export interface RunIntelligence {
  run_id: string;
  peak_population: number;
  time_to_peak_step: number | null;
  lifespan_steps: number;
  collapse_cause: string;
  early_growth_rate: number;
  late_growth_rate: number;
  growth_rate_delta: number;
  survival_ratio: number;
  energy_per_alive_cell_final: number | null;
  energy_per_population_cell_final: number | null;
  division_intensity: number;
}

export interface MetricDelta {
  baseline: number | null;
  value: number | null;
  absolute_delta: number | null;
  percent_delta: number | null;
}

export interface ComparedRun {
  run_id: string;
  scenario_name: string;
  seed: number;
  status: string;
  role: "baseline" | "comparison" | string;
  intelligence: RunIntelligence;
}

export interface ComparisonPoint {
  step: number;
  population: Record<string, number | null>;
  total_atp: Record<string, number | null>;
  atp_per_alive_cell: Record<string, number | null>;
}

export interface RunComparisonResponse {
  baseline_run_id: string;
  runs: ComparedRun[];
  deltas: Record<string, Record<string, MetricDelta>>;
  aligned_series: ComparisonPoint[];
}

export interface CellResponse {
  run_id: string;
  cell: CellState;
}

export interface CellEventsResponse {
  run_id: string;
  cell_id: string;
  scope: "self" | "lineage" | "descendants";
  events: CellEvent[];
}

export interface ExportFormatInfo {
  format: "parquet" | "powerbi" | "tableau";
  label: string;
  native: boolean;
  available: boolean;
  description: string;
}

export interface ExportedFile {
  path: string;
  bytes: number;
}

export interface ExportManifest {
  run_id: string;
  schema_version: string;
  generated_at: string;
  formats: string[];
  row_counts: Record<string, number>;
  files: Record<string, ExportedFile[]>;
}

export interface RunExportsResponse {
  run_id: string;
  formats: ExportFormatInfo[];
  manifest: ExportManifest | null;
}

export interface RunCreatedEvent {
  type: "run_created";
  run: RunRecord;
  storage: StorageStatus;
}

export type RunUpdateEvent = RunCreatedEvent;

const API_PREFIX = "/backend";
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health", { signal });
}

export async function listRuns(signal?: AbortSignal): Promise<RunRecord[]> {
  const payload = await apiFetch<{ runs: RunRecord[] }>("/api/runs", { signal });
  return payload.runs;
}

export async function getDefaultScenario(signal?: AbortSignal): Promise<Record<string, unknown>> {
  const payload = await apiFetch<DefaultScenarioResponse>("/api/default-scenario", { signal });
  return payload.scenario;
}

export async function createRun(input: {
  scenario: Record<string, unknown>;
  seed: number;
  maxSteps: number;
}): Promise<CreateRunResponse> {
  return apiFetch<CreateRunResponse>("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scenario: input.scenario,
      seed: input.seed,
      max_steps: input.maxSteps,
    }),
  });
}

export async function createDemoRun(input: {
  seed: number;
  maxSteps: number;
}): Promise<CreateRunResponse> {
  const scenario = await getDefaultScenario();
  return createRun({ scenario, seed: input.seed, maxSteps: input.maxSteps });
}

export async function getRun(runId: string, signal?: AbortSignal): Promise<RunRecord> {
  const payload = await apiFetch<{ run: RunRecord }>(`/api/runs/${encodeURIComponent(runId)}`, {
    signal,
  });
  return payload.run;
}

export async function getRunMetrics(
  runId: string,
  signal?: AbortSignal,
): Promise<PopulationMetrics[]> {
  const payload = await apiFetch<MetricsResponse>(
    `/api/runs/${encodeURIComponent(runId)}/metrics?resolution=1`,
    { signal },
  );
  return payload.series;
}

export async function getRunTimeSeries(
  runId: string,
  signal?: AbortSignal,
): Promise<RunTimeSeriesPoint[]> {
  const payload = await apiFetch<RunTimeSeriesResponse>(
    `/api/runs/${encodeURIComponent(runId)}/timeseries?resolution=1`,
    { signal },
  );
  return payload.points;
}

export async function getRunIntelligence(
  runId: string,
  signal?: AbortSignal,
): Promise<RunIntelligence> {
  return apiFetch<RunIntelligence>(`/api/runs/${encodeURIComponent(runId)}/intelligence`, {
    signal,
  });
}

export async function compareRuns(
  runIds: string[],
  signal?: AbortSignal,
): Promise<RunComparisonResponse> {
  return apiFetch<RunComparisonResponse>(
    `/api/runs/compare?runs=${encodeURIComponent(runIds.join(","))}&resolution=1`,
    { signal },
  );
}

export async function getLineage(runId: string, signal?: AbortSignal): Promise<LineageResponse> {
  return apiFetch<LineageResponse>(`/api/runs/${encodeURIComponent(runId)}/lineage`, {
    signal,
  });
}

export async function getCell(
  runId: string,
  cellId: string,
  signal?: AbortSignal,
): Promise<CellState> {
  const payload = await apiFetch<CellResponse>(
    `/api/runs/${encodeURIComponent(runId)}/cells/${encodeURIComponent(cellId)}`,
    { signal },
  );
  return payload.cell;
}

export async function getCellEvents(
  runId: string,
  cellId: string,
  scope: "self" | "lineage" | "descendants" = "lineage",
  signal?: AbortSignal,
): Promise<CellEvent[]> {
  const payload = await apiFetch<CellEventsResponse>(
    `/api/runs/${encodeURIComponent(runId)}/cells/${encodeURIComponent(cellId)}/events?scope=${scope}`,
    { signal },
  );
  return payload.events;
}

export async function getRunExports(
  runId: string,
  signal?: AbortSignal,
): Promise<RunExportsResponse> {
  return apiFetch<RunExportsResponse>(`/api/runs/${encodeURIComponent(runId)}/exports`, {
    signal,
  });
}

export async function createRunExport(
  runId: string,
  formats: string[],
): Promise<ExportManifest> {
  const payload = await apiFetch<{ run_id: string; manifest: ExportManifest }>(
    `/api/runs/${encodeURIComponent(runId)}/exports`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ formats }),
    },
  );
  return payload.manifest;
}

export function getRunExportDownloadUrl(runId: string, format: string): string {
  return `${API_PREFIX}/api/runs/${encodeURIComponent(runId)}/exports/${encodeURIComponent(format)}/download`;
}

export function getRunUpdatesWebSocketUrl(): string {
  const url = new URL("/api/runs/updates", API_BASE_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    cache: "no-store",
  });

  if (!response.ok) {
    const message = await readError(response);
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      return body.detail.join(", ");
    }
  } catch {
    return `${response.status} ${response.statusText}`;
  }

  return `${response.status} ${response.statusText}`;
}
