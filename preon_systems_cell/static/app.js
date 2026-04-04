const scenarioInput = document.getElementById("scenario");
const seedInput = document.getElementById("seed");
const maxStepsInput = document.getElementById("max-steps");
const dtInput = document.getElementById("dt");
const cellXInput = document.getElementById("cell-x");
const cellYInput = document.getElementById("cell-y");
const cellZInput = document.getElementById("cell-z");
const responseRawEl = document.getElementById("response-raw");
const structuredOutputEl = document.getElementById("structured-output");
const summaryEl = document.getElementById("summary");
const statusEl = document.getElementById("status");
const activityEl = document.getElementById("activity");
const requestMetaEl = document.getElementById("request-meta");
const responseLabelEl = document.getElementById("response-label");
const vizLabelEl = document.getElementById("viz-label");
const vizNameEl = document.getElementById("viz-name");
const vizCoordsEl = document.getElementById("viz-coords");
const canvasEl = document.getElementById("space-view");
const vizFullscreenButton = document.getElementById("viz-fullscreen");
const visualizerPanelEl = document.querySelector(".visualizer-panel");
const jsonModalEl = document.getElementById("json-modal");
const openJsonBtn = document.getElementById("open-raw-json");
const closeJsonBtn = document.getElementById("close-json-modal");
const copyJsonBtn = document.getElementById("copy-json");

let viewer;
let editorSyncTimer = null;

// Initialization
document.getElementById("load-default").addEventListener("click", loadDefaultScenario);
document.getElementById("create-cell").addEventListener("click", createCell);
document.getElementById("validate").addEventListener("click", () => submit("/api/validate"));
document.getElementById("run").addEventListener("click", () => submit("/api/run"));
scenarioInput.addEventListener("input", handleScenarioEditorInput);
vizFullscreenButton.addEventListener("click", toggleVisualizationFullscreen);
document.addEventListener("fullscreenchange", handleFullscreenChange);

// Modal Logic
openJsonBtn.addEventListener("click", () => jsonModalEl.classList.add("active"));
closeJsonBtn.addEventListener("click", () => jsonModalEl.classList.remove("active"));
jsonModalEl.addEventListener("click", (e) => { if (e.target === jsonModalEl) jsonModalEl.classList.remove("active"); });
copyJsonBtn.addEventListener("click", () => {
  navigator.clipboard.writeText(responseRawEl.textContent).then(() => {
    const originalText = copyJsonBtn.textContent;
    copyJsonBtn.textContent = "Copied!";
    setTimeout(() => { copyJsonBtn.textContent = originalText; }, 2000);
  });
});

// Tab Switching
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  });
});

async function loadDefaultScenario() {
  setStatus("busy", "Loading Defaults...");
  setActivity("Fetching engine defaults from the server.");
  try {
    // Clear trail immediately when loading defaults
    if (viewer) {
      viewer.trajectory = [];
      viewer.playbackActive = false;
    }
    const response = await fetch("/api/default-scenario");
    const payload = await response.json();
    updateAppState(payload, "Engine Defaults Loaded");
    setStatus("ok", "Defaults Loaded");
    setActivity("Engine defaults loaded. The workspace is ready for simulation.");
  } catch (error) {
    setStatus("error", "Init Failure");
    renderOutput({ error: String(error) });
    setActivity("Failed to load engine defaults.");
  }
}

async function submit(url) {
  let scenario;
  try {
    scenario = JSON.parse(scenarioInput.value);
  } catch (error) {
    setStatus("error", "JSON Syntax Error");
    renderOutput({ error: `Scenario JSON could not be parsed: ${error}` });
    return;
  }

  const body = {
    scenario,
    seed: Number(seedInput.value || 7),
  };
  if (maxStepsInput.value) body.max_steps = Number(maxStepsInput.value);
  if (dtInput.value) body.dt = Number(dtInput.value);

  const isRun = url.endsWith("/run");
  
  // Clear old trajectory if starting a new run
  if (isRun && viewer) {
    viewer.trajectory = [];
    viewer.playbackActive = false;
  }

  setStatus("busy", isRun ? "Running Simulation..." : "Validating...");
  setActivity(isRun ? "Executing simulation steps." : "Validating scenario configuration.");
  updateRequestMeta(url, "Pending");

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(payload, null, 2));
    
    updateAppState(payload, responseTitleFor(url, payload));
    updateRequestMeta(url, "OK");
    setStatus("ok", isRun ? "Simulation Complete" : "Validation OK");
    setActivity(activityMessageFor(url, payload));
  } catch (error) {
    renderEmptySummary();
    renderOutput({ error: String(error) });
    setStatus("error", "Engine Fault");
    updateRequestMeta(url, "Error");
    setActivity("Request failed. Inspect the output panel.");
  }
}

async function createCell() {
  let scenario;
  try {
    scenario = JSON.parse(scenarioInput.value);
  } catch {
    setStatus("error", "JSON Error");
    return;
  }

  const body = {
    scenario,
    cell: {
      x: Number(cellXInput.value || 0),
      y: Number(cellYInput.value || 0),
      z: Number(cellZInput.value || 0),
    },
  };
  await executeCreateCell(body);
}

async function executeCreateCell(body) {
  setStatus("busy", "Syncing State...");
  updateRequestMeta("/api/cells", "Pending");
  try {
    const response = await fetch("/api/cells", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(payload, null, 2));
    
    updateAppState(payload, "Coordinates Applied");
    updateRequestMeta("/api/cells", "Success");
    setStatus("ok", "State Synchronized");
    setActivity(`Cell synced at [${formatPosition(payload.state.cell)}].`);
  } catch (error) {
    renderEmptySummary();
    renderOutput({ error: String(error) });
    setStatus("error", "Sync Fault");
    updateRequestMeta("/api/cells", "Error");
  }
}

function updateAppState(payload, label = "State Updated") {
  if (payload.scenario) {
    scenarioInput.value = JSON.stringify(payload.scenario, null, 2);
    if (payload.scenario.cell) syncInputsToCell(payload.scenario.cell);
  }
  renderOutput(payload);
  renderSummary(payload);
  syncVisualizationWithPayload(payload, label);
}

function renderOutput(payload) {
  responseRawEl.textContent = JSON.stringify(payload, null, 2);
  if (!payload || Object.keys(payload).length === 0) {
    structuredOutputEl.innerHTML = '<div class="empty-results">Awaiting interaction...</div>';
    return;
  }

  const items = [];
  if (payload.metadata) items.push(["Metadata", `v${payload.metadata.engine_version} | Seed ${payload.metadata.seed}`]);
  if (payload.termination_reason) items.push(["Termination", payload.termination_reason]);
  if (payload.final_state) items.push(["Final Step", payload.final_state.step]);
  if (payload.events) items.push(["Events", payload.events.length]);
  if (typeof payload.valid === "boolean") items.push(["Validation", payload.valid ? "PASSED" : "FAILED"]);
  if (payload.error) items.push(["Error", payload.error]);

  structuredOutputEl.innerHTML = items.length === 0 ? '<div class="empty-results">No summary available.</div>' : 
    items.map(([k, v]) => `<div class="output-item"><span class="key">${k}</span><span class="val">${v}</span></div>`).join("");
}

function renderSummary(payload) {
  const metrics = [];
  const scenario = payload.scenario || payload.resolved_scenario;
  if (payload.loaded && scenario?.cell) {
    metrics.push(["Position", formatPosition(scenario.cell)]);
    metrics.push(["Initial ATP", formatValue(scenario.cell.initial_atp)]);
    metrics.push(["Cytosol Glucose", formatValue(scenario.cell.cytosol?.glucose ?? 0)]);
    metrics.push(["Biomass", formatValue(scenario.cell.biomass)]);
  } else if (payload.state?.cell) {
    metrics.push(["Position", formatPosition(payload.state.cell)]);
    metrics.push(["ATP Level", formatValue(payload.state.cell.energy.atp)]);
    metrics.push(["Cytosol Glucose", formatValue(payload.state.cell.cytosol?.glucose ?? 0)]);
    metrics.push(["Pyruvate", formatValue(payload.state.cell.cytosol?.pyruvate ?? 0)]);
    metrics.push(["NADH", formatValue(payload.state.cell.cytosol?.nadh ?? 0)]);
    metrics.push(["Biomass", formatValue(payload.state.cell.biomass)]);
  } else if (payload.final_state) {
    metrics.push(["Position", formatPosition(payload.final_state.cell)]);
    metrics.push(["Final ATP", formatValue(payload.final_state.cell.energy.atp)]);
    metrics.push(["Cytosol Glucose", formatValue(payload.final_state.cell.cytosol?.glucose ?? 0)]);
    metrics.push(["Pyruvate", formatValue(payload.final_state.cell.cytosol?.pyruvate ?? 0)]);
    metrics.push(["NADH", formatValue(payload.final_state.cell.cytosol?.nadh ?? 0)]);
    metrics.push(["Env Glucose", formatValue(payload.final_state.environment?.glucose_concentration ?? 0)]);
    metrics.push(["Final Biomass", formatValue(payload.final_state.cell.biomass)]);
    metrics.push(["Steps", payload.final_state.step]);
  }

  if (!metrics.length) {
    renderEmptySummary();
    return;
  }

  summaryEl.innerHTML = metrics.map(renderMetric).join("");
  
  // Attach event listeners to coordinate inputs in the metrics panel
  summaryEl.querySelectorAll(".coord-input-mini").forEach(input => {
    input.addEventListener("change", handleMetricCoordChange);
  });
}

function handleMetricCoordChange() {
  const x = Number(document.getElementById("metric-coord-x").value);
  const y = Number(document.getElementById("metric-coord-y").value);
  const z = Number(document.getElementById("metric-coord-z").value);
  
  let scenario;
  try {
    scenario = JSON.parse(scenarioInput.value);
  } catch { return; }

  executeCreateCell({
    scenario,
    cell: { x, y, z }
  });
}

function renderMetric([label, value]) {
  if (label === "Position" || label === "Coords") {
    const parts = String(value).split(", ");
    return `
      <div class="metric-card">
        <span class="label">${escapeHtml(label)}</span>
        <div class="coord-grid-mini">
          <input id="metric-coord-x" class="coord-input-mini" type="number" step="0.1" value="${parts[0]}" title="X Coordinate" />
          <input id="metric-coord-y" class="coord-input-mini" type="number" step="0.1" value="${parts[1]}" title="Y Coordinate" />
          <input id="metric-coord-z" class="coord-input-mini" type="number" step="0.1" value="${parts[2]}" title="Z Coordinate" />
        </div>
      </div>
    `;
  }
  return `<div class="metric-card"><span class="label">${escapeHtml(label)}</span><span class="value">${escapeHtml(String(value))}</span></div>`;
}

function renderEmptySummary() {
  summaryEl.innerHTML = '<div class="empty-results">Awaiting simulation results...</div>';
}

function formatValue(v) { return typeof v === "number" ? v.toFixed(2) : v; }
function formatPosition(cell) { return `${formatValue(cell.x)}, ${formatValue(cell.y)}, ${formatValue(cell.z)}`; }

function setStatus(kind, text) {
  statusEl.className = `status-pill ${kind}`;
  statusEl.querySelector(".status-text").textContent = text;
}

function updateRequestMeta(endpoint, outcome) {
  requestMetaEl.innerHTML = `
    <div class="trace-row"><span class="label">Route</span><span class="value">${escapeHtml(endpoint)}</span></div>
    <div class="trace-row"><span class="label">Time</span><span class="value">${new Date().toLocaleTimeString()}</span></div>
    <div class="trace-row"><span class="label">Status</span><span class="value">${escapeHtml(outcome)}</span></div>
  `;
}

function responseTitleFor(url, payload) {
  if (url.endsWith("/validate")) return "Scenario Validated";
  if (url.endsWith("/run")) return "Run Artifacts";
  return "State Synchronized";
}

function activityMessageFor(url, payload) {
  if (url.endsWith("/validate")) return payload.valid ? "Scenario configuration is healthy." : "Validation errors detected.";
  if (url.endsWith("/run")) return `Run finished. Reason: ${payload.termination_reason || "MAX_STEPS"}.`;
  return "State updated successfully.";
}

function setActivity(text) { activityEl.textContent = text; }

async function toggleVisualizationFullscreen() {
  if (!document.fullscreenEnabled) return;
  if (document.fullscreenElement === visualizerPanelEl) await document.exitFullscreen();
  else await visualizerPanelEl.requestFullscreen();
}

function handleFullscreenChange() { viewer.resize(); }

function handleScenarioEditorInput() {
  window.clearTimeout(editorSyncTimer);
  editorSyncTimer = window.setTimeout(() => {
    const scenario = tryParseScenario();
    if (scenario?.cell) {
      syncInputsToCell(scenario.cell);
      updateVisualizationFromScenario(scenario, "Real-time Editor Update");
    }
  }, 500);
}

function tryParseScenario() { try { return JSON.parse(scenarioInput.value); } catch { return null; } }

function syncInputsToCell(cell) {
  if (typeof cell.x === "number") cellXInput.value = String(cell.x);
  if (typeof cell.y === "number") cellYInput.value = String(cell.y);
  if (typeof cell.z === "number") cellZInput.value = String(cell.z);
}

function syncVisualizationWithPayload(payload, label) {
  const hasMetrics = !!(payload.metrics?.length && payload.final_state?.cell);
  
  // If we don't have new metrics, we MUST clear the existing trail
  if (!hasMetrics && viewer) {
    viewer.trajectory = [];
    viewer.playbackActive = false;
  }

  if (hasMetrics) {
    playRunTrajectory(payload, label);
    return;
  }
  
  if (payload.state?.cell) {
    updateVisualizationFromCell(payload.state.cell, label);
    return;
  }
  const scenario = payload.scenario || payload.resolved_scenario;
  if (scenario?.cell) {
    updateVisualizationFromScenario(scenario, label);
  } else {
    // Fallback: update from editor if payload is a generic success (like validation)
    const current = tryParseScenario();
    if (current?.cell) updateVisualizationFromScenario(current, label);
  }
}

function updateVisualizationFromScenario(scenario, label) {
  if (!scenario?.cell) return;
  updateVisualizationFromCell({
    name: scenario.cell.name,
    x: scenario.cell.x ?? 0,
    y: scenario.cell.y ?? 0,
    z: scenario.cell.z ?? 0,
    biomass: scenario.cell.biomass ?? 1,
    membrane_integrity: scenario.cell.membrane_integrity ?? 1,
    alive: true,
    energy: { atp: scenario.cell.initial_atp ?? 0 },
  }, label);
}

function updateVisualizationFromCell(cell, label) {
  const spatialCell = {
    name: cell.name ?? "Unknown",
    x: Number(cell.x ?? 0),
    y: Number(cell.y ?? 0),
    z: Number(cell.z ?? 0),
    biomass: Number(cell.biomass ?? 1),
    membrane_integrity: Number(cell.membrane_integrity ?? 1),
    alive: cell.alive ?? true,
    atp: Number(cell.energy?.atp ?? cell.atp ?? 0),
  };
  viewer.setCell(spatialCell);
  vizNameEl.textContent = spatialCell.name;
  vizCoordsEl.textContent = formatPosition(spatialCell);
  vizLabelEl.textContent = label;
}

function playRunTrajectory(payload, label) {
  const trajectory = payload.metrics.map(m => ({
    name: payload.final_state.cell.name,
    x: Number(m.x ?? 0),
    y: Number(m.y ?? 0),
    z: Number(m.z ?? 0),
    biomass: Number(m.biomass ?? 1),
    membrane_integrity: Number(m.membrane_integrity ?? 1),
    alive: true,
    atp: Number(m.atp ?? 0),
  }));
  if (trajectory.length) {
    viewer.playTrajectory(trajectory);
    vizLabelEl.textContent = `${label} (Animated Run)`;
  }
}

function escapeHtml(v) {
  return v.toString().replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function clamp(v, min, max) { return Math.min(max, Math.max(min, v)); }

function rotateY(p, a) {
  const cos = Math.cos(a), sin = Math.sin(a);
  return { x: p.x * cos - p.z * sin, y: p.y, z: p.x * sin + p.z * cos };
}

function rotateX(p, a) {
  const cos = Math.cos(a), sin = Math.sin(a);
  return { x: p.x, y: p.y * cos - p.z * sin, z: p.y * sin + p.z * cos };
}

class SpaceViewer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    this.rotationX = -0.4;
    this.rotationY = 0.8;
    this.zoom = 1;
    this.dragging = false;
    this.isDraggingCell = false;
    this.lastPoint = null;
    this.cell = { name: "None", x: 0, y: 0, z: 0, biomass: 1, membrane_integrity: 1, alive: true, atp: 0 };
    this.trajectory = [];
    this.playbackActive = false;
    this.playbackStart = 0;
    this.segmentDurationMs = 100;
    this.renderCell = { ...this.cell };

    this.bindEvents();
    this.resize();
    this.animate = this.animate.bind(this);
    window.requestAnimationFrame(this.animate);
  }

  bindEvents() {
    window.addEventListener("resize", () => this.resize());
    
    this.canvas.addEventListener("pointerdown", (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      
      const projected = this.project(this.renderCell);
      const radius = Math.max(12, 20 * this.zoom * projected.scale);
      const dist = Math.sqrt((x - projected.x)**2 + (y - projected.y)**2);

      // Tight locking: prioritize cell interaction if anywhere near the cell
      if (dist < radius * 3.5) {
        this.isDraggingCell = true;
        this.dragging = false;
      } else {
        this.dragging = true;
        this.isDraggingCell = false;
      }
      
      this.lastPoint = { x: e.clientX, y: e.clientY };
      this.canvas.setPointerCapture(e.pointerId);
    });
    
    this.canvas.addEventListener("pointermove", (e) => {
      if (!this.lastPoint) return;
      const dx = e.clientX - this.lastPoint.x;
      const dy = e.clientY - this.lastPoint.y;

      if (this.isDraggingCell) {
        this.handleCellDrag(dx, dy);
      } else if (this.dragging) {
        this.rotationY += dx * 0.01;
        this.rotationX = clamp(this.rotationX + dy * 0.01, -1.5, 1.5);
      }
      
      this.lastPoint = { x: e.clientX, y: e.clientY };
    });
    
    this.canvas.addEventListener("pointerup", (e) => {
      if (this.isDraggingCell) {
        this.finalizeCellReposition();
      }
      this.dragging = false;
      this.isDraggingCell = false;
      this.canvas.releasePointerCapture(e.pointerId);
    });

    this.canvas.addEventListener("dblclick", (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const projected = this.project(this.renderCell);
      const radius = Math.max(12, 20 * this.zoom * projected.scale);
      const dist = Math.sqrt((x - projected.x)**2 + (y - projected.y)**2);
      
      if (dist < radius * 2.5) {
        this.repositionCellRandomly();
      }
    });

    this.canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.zoom = clamp(this.zoom * (e.deltaY > 0 ? 0.9 : 1.1), 0.5, 5);
    }, { passive: false });
  }

  handleCellDrag(dx, dy) {
    // Approximate movement in 3D space based on 2D screen delta
    const sensitivity = 0.02 / (this.zoom || 1);
    const cos = Math.cos(this.rotationY);
    const sin = Math.sin(this.rotationY);
    
    this.renderCell.x += dx * sensitivity * cos;
    this.renderCell.z -= dx * sensitivity * sin;
    this.renderCell.y -= dy * sensitivity;
    
    this.syncUIToRenderCell();
  }

  finalizeCellReposition() {
    let scenario;
    try {
      scenario = JSON.parse(scenarioInput.value);
    } catch { return; }

    executeCreateCell({
      scenario,
      cell: {
        x: Number(this.renderCell.x.toFixed(2)),
        y: Number(this.renderCell.y.toFixed(2)),
        z: Number(this.renderCell.z.toFixed(2)),
      }
    });
  }

  repositionCellRandomly() {
    const newX = Number((Math.random() * 10 - 5).toFixed(2));
    const newY = Number((Math.random() * 10 - 5).toFixed(2));
    const newZ = Number((Math.random() * 10 - 5).toFixed(2));
    
    let scenario;
    try { scenario = JSON.parse(scenarioInput.value); } catch { return; }
    
    executeCreateCell({
      scenario,
      cell: { x: newX, y: newY, z: newZ }
    });
  }

  resize() {
    const bounds = this.canvas.parentElement.getBoundingClientRect();
    this.width = Math.max(1, Math.floor(bounds.width));
    this.height = Math.max(1, Math.floor(bounds.height));
    this.canvas.width = Math.floor(this.width * this.pixelRatio);
    this.canvas.height = Math.floor(this.height * this.pixelRatio);
    this.ctx.setTransform(this.pixelRatio, 0, 0, this.pixelRatio, 0, 0);
  }

  setCell(cell) {
    this.cell = { ...cell };
    this.renderCell = { ...cell };
    this.trajectory = [];
    this.playbackActive = false;
  }

  playTrajectory(trajectory) {
    this.trajectory = trajectory.map(p => ({ ...p }));
    this.cell = { ...this.trajectory[this.trajectory.length - 1] };
    this.renderCell = { ...this.trajectory[0] };
    this.playbackActive = this.trajectory.length > 1;
    this.playbackStart = performance.now();
  }

  animate() {
    this.draw();
    window.requestAnimationFrame(this.animate);
  }

  draw() {
    this.advancePlayback();
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);
    this.drawGrid();
    this.drawTrail();
    this.drawCell();
  }

  advancePlayback() {
    if (!this.playbackActive) return;
    const elapsed = performance.now() - this.playbackStart;
    const totalDuration = (this.trajectory.length - 1) * this.segmentDurationMs;
    
    if (elapsed >= totalDuration) {
      this.renderCell = { ...this.trajectory[this.trajectory.length - 1] };
      this.playbackActive = false;
      this.syncUIToRenderCell();
      return;
    }

    const rawIndex = elapsed / this.segmentDurationMs;
    const index = Math.floor(rawIndex);
    const t = rawIndex - index;
    const curr = this.trajectory[index];
    const next = this.trajectory[index + 1];
    
    this.renderCell = {
      ...next,
      x: curr.x + (next.x - curr.x) * t,
      y: curr.y + (next.y - curr.y) * t,
      z: curr.z + (next.z - curr.z) * t,
      atp: curr.atp + (next.atp - curr.atp) * t,
    };

    this.syncUIToRenderCell();
  }

  syncUIToRenderCell() {
    // Update HUD
    vizCoordsEl.textContent = formatPosition(this.renderCell);
    
    // Update Sidebar Inputs (X, Y, Z)
    const xIn = document.getElementById("metric-coord-x");
    const yIn = document.getElementById("metric-coord-y");
    const zIn = document.getElementById("metric-coord-z");
    
    if (xIn) xIn.value = this.renderCell.x.toFixed(2);
    if (yIn) yIn.value = this.renderCell.y.toFixed(2);
    if (zIn) zIn.value = this.renderCell.z.toFixed(2);
  }

  drawTrail() {
    if (!this.trajectory.length) return;
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.strokeStyle = "rgba(59, 130, 246, 0.6)";
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);

    this.trajectory.forEach((point, i) => {
      const p = this.project(point);
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();
    ctx.setLineDash([]);
  }

  drawGrid() {
    const ctx = this.ctx;
    const size = 10, step = 1;
    for (let i = -size; i <= size; i += step) {
      const isCenter = i === 0;
      const alpha = isCenter ? 0.35 : 0.12;
      const color = `rgba(148, 163, 184, ${alpha})`;
      this.drawLine({ x: -size, y: 0, z: i }, { x: size, y: 0, z: i }, color);
      this.drawLine({ x: i, y: 0, z: -size }, { x: i, y: 0, z: size }, color);
    }
    this.drawLine({ x: 0, y: 0, z: 0 }, { x: size, y: 0, z: 0 }, "rgba(239, 68, 68, 0.8)"); // X
    this.drawLine({ x: 0, y: 0, z: 0 }, { x: 0, y: size, z: 0 }, "rgba(34, 197, 94, 0.8)"); // Y
    this.drawLine({ x: 0, y: 0, z: 0 }, { x: 0, y: 0, z: 5 }, "rgba(59, 130, 246, 0.8)"); // Z
  }

  drawCell() {
    const ctx = this.ctx;
    const cell = this.renderCell;
    const projected = this.project(cell);
    const radius = Math.max(8, 15 * this.zoom * projected.scale);
    
    ctx.shadowBlur = 20;
    ctx.shadowColor = cell.alive ? "rgba(37, 99, 235, 0.4)" : "rgba(100, 116, 139, 0.4)";
    
    const grad = ctx.createRadialGradient(projected.x - radius/3, projected.y - radius/3, radius/4, projected.x, projected.y, radius);
    if (cell.alive) {
      grad.addColorStop(0, "#60a5fa");
      grad.addColorStop(1, "#1d4ed8");
    } else {
      grad.addColorStop(0, "#94a3b8");
      grad.addColorStop(1, "#475569");
    }
    
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(projected.x, projected.y, radius, 0, Math.PI * 2);
    ctx.fill();
    
    ctx.shadowBlur = 0;
    ctx.fillStyle = "rgba(255,255,255,0.2)";
    ctx.beginPath();
    ctx.arc(projected.x - radius/3, projected.y - radius/3, radius/4, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#fff";
    ctx.font = "bold 11px var(--font-sans)";
    ctx.textAlign = "center";
    ctx.fillText(cell.name, projected.x, projected.y + radius + 15);
  }

  project(p) {
    const scaleBase = Math.min(this.width, this.height) * 0.1 * this.zoom;
    const rotatedY = rotateY(p, this.rotationY);
    const rotated = rotateX(rotatedY, this.rotationX);
    const perspective = 20 / (20 + rotated.z);
    return {
      x: this.width * 0.5 + rotated.x * scaleBase * perspective,
      y: this.height * 0.5 - rotated.y * scaleBase * perspective,
      scale: perspective,
    };
  }

  drawLine(from, to, color) {
    const ctx = this.ctx;
    const p1 = this.project(from), p2 = this.project(to);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.stroke();
  }
}

viewer = new SpaceViewer(canvasEl);
void loadDefaultScenario();
