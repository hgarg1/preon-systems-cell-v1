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
const cellModalEl = document.getElementById("cell-modal");
const closeCellModalBtn = document.getElementById("close-cell-modal");
const cellModalTitleEl = document.getElementById("cell-modal-title");
const cellModalSubtitleEl = document.getElementById("cell-modal-subtitle");
const cellModalBodyEl = document.getElementById("cell-modal-body");

let viewer;
let editorSyncTimer = null;
let currentPayload = null;
let selectedCellId = null;
let lineageViewer = null;
let lineageRenderToken = 0;

// Initialization
document.getElementById("load-default").addEventListener("click", loadDefaultScenario);
document.getElementById("create-cell").addEventListener("click", createCell);
document.getElementById("validate").addEventListener("click", () => submit("/api/validate"));
document.getElementById("run").addEventListener("click", () => submit("/api/run"));
scenarioInput.addEventListener("input", handleScenarioEditorInput);
vizFullscreenButton.addEventListener("click", toggleVisualizationFullscreen);
document.addEventListener("fullscreenchange", handleFullscreenChange);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && cellModalEl.classList.contains("active")) closeCellModal();
});

// Modal Logic
openJsonBtn.addEventListener("click", () => jsonModalEl.classList.add("active"));
closeJsonBtn.addEventListener("click", () => jsonModalEl.classList.remove("active"));
jsonModalEl.addEventListener("click", (e) => { if (e.target === jsonModalEl) jsonModalEl.classList.remove("active"); });
closeCellModalBtn.addEventListener("click", closeCellModal);
cellModalEl.addEventListener("click", (e) => { if (e.target === cellModalEl) closeCellModal(); });
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
      viewer.frames = [];
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
  window.clearTimeout(editorSyncTimer);
  editorSyncTimer = null;
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
    viewer.frames = [];
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
  window.clearTimeout(editorSyncTimer);
  editorSyncTimer = null;
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
    const syncedCell = payload.state?.cells?.[0] || payload.state?.cell;
    setActivity(`Cell synced at [${syncedCell ? formatPosition(syncedCell) : "0.00, 0.00, 0.00"}].`);
  } catch (error) {
    renderEmptySummary();
    renderOutput({ error: String(error) });
    setStatus("error", "Sync Fault");
    updateRequestMeta("/api/cells", "Error");
  }
}

function updateAppState(payload, label = "State Updated") {
  currentPayload = payload;
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
  if (payload.final_state?.cells) items.push(["Cells", payload.final_state.cells.length]);
  if (payload.events) items.push(["Events", payload.events.length]);
  if (typeof payload.valid === "boolean") items.push(["Validation", payload.valid ? "PASSED" : "FAILED"]);
  if (payload.error) items.push(["Error", payload.error]);

  structuredOutputEl.innerHTML = items.length === 0 ? '<div class="empty-results">No summary available.</div>' : 
    items.map(([k, v]) => `<div class="output-item"><span class="key">${k}</span><span class="val">${v}</span></div>`).join("");
}

function renderSummary(payload) {
  const metrics = [];
  let selectorHtml = "";
  const scenario = payload.scenario || payload.resolved_scenario;
  const latestMetric = payload.metrics?.[payload.metrics.length - 1] ?? null;
  if (payload.loaded && scenario?.cell) {
    metrics.push(["Position", formatPosition(scenario.cell)]);
    metrics.push(["Initial ATP", formatValue(scenario.cell.initial_atp)]);
    metrics.push(["Cytosol Glucose", formatValue(scenario.cell.cytosol?.glucose ?? 0)]);
    metrics.push(["NAD+", formatValue(scenario.cell.cytosol?.nad_plus ?? 0)]);
    metrics.push(["FAD", formatValue(scenario.cell.cytosol?.fad ?? 0)]);
    metrics.push(["Membrane Gradient", formatValue(scenario.cell.cytosol?.membrane_gradient ?? 0)]);
    metrics.push(["Max Population", scenario.cell.max_population ?? 0]);
    metrics.push(["Biomass", formatValue(scenario.cell.biomass)]);
  } else if (payload.state?.cells || payload.final_state?.cells) {
    const state = payload.state || payload.final_state;
    const cells = state.cells || [];
    if (!selectedCellId || !cells.some(cell => cell.id === selectedCellId)) {
      selectedCellId = cells.find(cell => cell.alive)?.id || cells[0]?.id || null;
    }
    const selectedCell = cells.find(cell => cell.id === selectedCellId) || cells[0];
    selectorHtml = renderCellSelector(cells);
    const aliveCount = latestMetric?.alive_count ?? cells.filter(cell => cell.alive).length;
    const deadCount = latestMetric?.dead_count ?? cells.filter(cell => cell.status === "dead").length;
    const dividedCount = latestMetric?.divided_count ?? cells.filter(cell => cell.status === "divided").length;

    metrics.push(["Cells", cells.length]);
    metrics.push(["Alive", aliveCount]);
    metrics.push(["Dead", deadCount]);
    metrics.push(["Divided", dividedCount]);
    metrics.push(["Total ATP", formatValue(latestMetric?.total_atp ?? sumCells(cells, cell => cell.energy?.atp ?? 0))]);
    metrics.push(["Total Biomass", formatValue(latestMetric?.total_biomass ?? sumCells(cells, cell => cell.biomass ?? 0))]);
    metrics.push(["Env Glucose", formatValue(state.environment?.glucose_concentration ?? 0)]);
    metrics.push(["Electron Acceptor", formatValue(state.environment?.electron_acceptor_concentration ?? 0)]);
    metrics.push(["Steps", state.step]);

    if (selectedCell) {
      metrics.push(["Selected Cell", selectedCell.id]);
      metrics.push(["Status", selectedCell.status || (selectedCell.alive ? "alive" : "dead")]);
      metrics.push(["Parent", selectedCell.parent_id || "-"]);
      metrics.push(["Generation", selectedCell.generation ?? 0]);
      metrics.push(["Cell Position", formatPosition(selectedCell)]);
      metrics.push(["ATP Level", formatValue(selectedCell.energy?.atp ?? 0)]);
      metrics.push(["ADP Level", formatValue(selectedCell.energy?.adp ?? 0)]);
      metrics.push(["Cytosol Glucose", formatValue(selectedCell.cytosol?.glucose ?? 0)]);
      metrics.push(["Pyruvate", formatValue(selectedCell.cytosol?.pyruvate ?? 0)]);
      metrics.push(["NADH", formatValue(selectedCell.cytosol?.nadh ?? 0)]);
      metrics.push(["Acetyl-CoA", formatValue(selectedCell.cytosol?.acetyl_coa ?? 0)]);
      metrics.push(["NAD+", formatValue(selectedCell.cytosol?.nad_plus ?? 0)]);
      metrics.push(["FADH2", formatValue(selectedCell.cytosol?.fadh2 ?? 0)]);
      metrics.push(["Membrane Gradient", formatValue(selectedCell.cytosol?.membrane_gradient ?? 0)]);
      metrics.push(["CO2", formatValue(selectedCell.cytosol?.co2 ?? 0)]);
      metrics.push(["Biomass", formatValue(selectedCell.biomass)]);
    }
  }

  if (!metrics.length) {
    renderEmptySummary();
    return;
  }

  summaryEl.innerHTML = `${selectorHtml}${metrics.map(renderMetric).join("")}`;
  
  // Attach event listeners to coordinate inputs in the metrics panel
  summaryEl.querySelectorAll(".coord-input-mini").forEach(input => {
    input.addEventListener("change", handleMetricCoordChange);
  });
  summaryEl.querySelectorAll(".cell-select-btn").forEach(button => {
    button.addEventListener("click", () => {
      selectedCellId = button.dataset.cellId;
      if (viewer) viewer.selectCell(selectedCellId);
      renderSummary(currentPayload || payload);
    });
    button.addEventListener("dblclick", () => {
      selectedCellId = button.dataset.cellId;
      if (viewer) viewer.selectCell(selectedCellId);
      renderSummary(currentPayload || payload);
      openCellModal(selectedCellId);
    });
  });
}

function renderCellSelector(cells) {
  if (!cells.length) return "";
  const aliveCount = cells.filter(cell => cell.alive).length;
  const dividedCount = cells.filter(cell => cell.status === "divided").length;
  const deadCount = cells.filter(cell => cell.status === "dead").length;
  const visibleCells = cells.slice(0, 80);
  const overflow = cells.length > visibleCells.length
    ? `<span class="cell-overflow">${visibleCells.length} of ${cells.length} shown</span>`
    : "";
  const buttons = visibleCells.map((cell) => {
    const status = cell.status || (cell.alive ? "alive" : "dead");
    const active = cell.id === selectedCellId ? " active" : "";
    const parent = cell.parent_id ? `Parent ${escapeHtml(cell.parent_id)}` : "Founder";
    return `
      <button class="cell-select-btn${active}" data-cell-id="${escapeHtml(cell.id)}" type="button" style="${lineageColorStyle(cell.id)}">
        <span class="cell-swatch" aria-hidden="true"></span>
        <span class="cell-select-main">
          <span class="cell-select-id">${escapeHtml(cell.id)}</span>
          <span class="cell-select-meta">Gen ${cell.generation ?? lineageDepth(cell.id)} - ${parent}</span>
        </span>
        <span class="cell-select-status">${escapeHtml(status)}</span>
      </button>
    `;
  }).join("");
  return `
    <div class="cell-selector">
      <div class="cell-selector-head">
        <div>
          <div class="cell-selector-title">Cells</div>
          <div class="cell-selector-subtitle">${cells.length} records across ${Math.max(...cells.map(cell => cell.generation ?? lineageDepth(cell.id)), 0) + 1} generations</div>
        </div>
        <div class="cell-selector-counts">
          <span>Alive ${aliveCount}</span>
          <span>Divided ${dividedCount}</span>
          <span>Dead ${deadCount}</span>
        </div>
      </div>
      <div class="cell-selector-list">${buttons}${overflow}</div>
    </div>
  `;
}

function openCellModal(cellId) {
  disposeLineageViewer();
  const renderToken = ++lineageRenderToken;
  const state = currentPayload?.final_state || currentPayload?.state;
  const cells = state?.cells || [];
  const cell = cells.find(candidate => candidate.id === cellId);
  if (!cell) return;

  const cellEvents = getCellEvents(cell.id);

  cellModalTitleEl.textContent = cell.id;
  cellModalSubtitleEl.textContent = `${cell.status || (cell.alive ? "alive" : "dead")} - generation ${cell.generation ?? lineageDepth(cell.id)}`;
  cellModalBodyEl.innerHTML = `
    <section class="cell-modal-hero" style="${lineageColorStyle(cell.id)}">
      <div class="cell-modal-swatch" aria-hidden="true"></div>
      <div>
        <div class="cell-modal-eyebrow">Lineage Map</div>
        ${renderLineageMap(cell, cells)}
      </div>
    </section>

    <section class="cell-modal-section">
      <h3>Lifecycle</h3>
      <div class="cell-modal-grid">
        ${renderModalFact("Status", cell.status || (cell.alive ? "alive" : "dead"))}
        ${renderModalFact("Parent", cell.parent_id || "Founder")}
        ${renderModalFact("Generation", cell.generation ?? lineageDepth(cell.id))}
        ${renderModalFact("Born Step", cell.birth_step ?? 0)}
        ${renderModalFact("Death Step", cell.death_step ?? "-")}
        ${renderModalFact("Divisions", cell.division_count ?? 0)}
      </div>
    </section>

    <section class="cell-modal-section">
      <h3>Position and Structure</h3>
      <div class="cell-modal-grid">
        ${renderModalFact("Position", formatPosition(cell))}
        ${renderModalFact("Biomass", formatValue(cell.biomass ?? 0))}
        ${renderModalFact("Membrane", formatValue(cell.membrane_integrity ?? 0))}
        ${renderModalFact("Transporters", formatValue(cell.glucose_transporter_density ?? 0))}
        ${renderModalFact("Waste", formatValue(cell.waste ?? 0))}
      </div>
    </section>

    <section class="cell-modal-section">
      <h3>Energy and Cytosol</h3>
      <div class="cell-modal-grid">
        ${renderModalFact("ATP", formatValue(cell.energy?.atp ?? 0))}
        ${renderModalFact("ADP", formatValue(cell.energy?.adp ?? 0))}
        ${renderModalFact("Glucose", formatValue(cell.cytosol?.glucose ?? 0))}
        ${renderModalFact("Pyruvate", formatValue(cell.cytosol?.pyruvate ?? 0))}
        ${renderModalFact("Acetyl-CoA", formatValue(cell.cytosol?.acetyl_coa ?? 0))}
        ${renderModalFact("NADH", formatValue(cell.cytosol?.nadh ?? 0))}
        ${renderModalFact("NAD+", formatValue(cell.cytosol?.nad_plus ?? 0))}
        ${renderModalFact("FADH2", formatValue(cell.cytosol?.fadh2 ?? 0))}
        ${renderModalFact("FAD", formatValue(cell.cytosol?.fad ?? 0))}
        ${renderModalFact("CO2", formatValue(cell.cytosol?.co2 ?? 0))}
        ${renderModalFact("Gradient", formatValue(cell.cytosol?.membrane_gradient ?? 0))}
      </div>
    </section>

    <section class="cell-modal-section">
      <h3>Cell Events</h3>
      ${renderCellEventList(cell.id, cellEvents)}
    </section>
  `;
  cellModalEl.classList.add("active");
  attachCellModalListeners(cell.id);
  window.requestAnimationFrame(() => {
    if (renderToken === lineageRenderToken && cellModalEl.classList.contains("active")) {
      renderLineageThreeScene(cell, cells);
    }
  });
}

function closeCellModal() {
  disposeLineageViewer();
  lineageRenderToken += 1;
  cellModalEl.classList.remove("active");
}

function renderModalFact(label, value) {
  return `<div class="cell-modal-fact"><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></div>`;
}

function getCellEvents(cellId) {
  const state = currentPayload?.final_state || currentPayload?.state;
  const relatedIds = relatedCellIdsFor(cellId, state?.cells || []);
  return (currentPayload?.events || [])
    .filter(event => eventPertainsToCell(event, relatedIds))
    .sort((a, b) => (a.step - b.step) || (a.time - b.time));
}

function relatedCellIdsFor(cellId, cells) {
  const byId = new Map(cells.map(cell => [cell.id, cell]));
  const related = new Set();
  let cursor = byId.get(cellId);
  while (cursor) {
    related.add(cursor.id);
    cursor = cursor.parent_id ? byId.get(cursor.parent_id) : null;
  }
  const collectDescendants = (id) => {
    cells.filter(cell => cell.parent_id === id).forEach(child => {
      related.add(child.id);
      collectDescendants(child.id);
    });
  };
  collectDescendants(cellId);
  return related;
}

function eventPertainsToCell(event, relatedIds) {
  const values = event?.values || {};
  return relatedIds.has(values.cell_id)
    || relatedIds.has(values.parent_id)
    || (Array.isArray(values.daughter_ids) && values.daughter_ids.some(id => relatedIds.has(id)));
}

function renderCellEventList(cellId, events) {
  if (!events.length) return '<div class="cell-modal-empty">No recorded events for this cell in the current payload.</div>';
  return `
    <div class="cell-event-list-meta">${events.length} lineage-relevant events, ordered from earliest to latest.</div>
    <div class="cell-event-list" style="${lineageColorStyle(cellId)}">
      ${events.map((event, index) => `
        <button class="cell-event-row" data-cell-id="${escapeHtml(cellId)}" data-event-index="${index}" type="button">
          <span class="cell-event-step">Step ${escapeHtml(String(event.step))}</span>
          <span class="cell-event-scope">${escapeHtml(eventScopeLabel(event, cellId))}</span>
          <span class="cell-event-type">${escapeHtml(event.type)}</span>
          <span class="cell-event-message">${escapeHtml(event.message)}</span>
        </button>
      `).join("")}
    </div>
  `;
}

function eventScopeLabel(event, cellId) {
  const values = event?.values || {};
  if (values.cell_id === cellId) return "Self";
  if (values.parent_id === cellId) return "Child";
  if (Array.isArray(values.daughter_ids) && values.daughter_ids.includes(cellId)) return "Birth";
  return "Lineage";
}

function attachCellModalListeners(cellId) {
  cellModalBodyEl.querySelectorAll(".cell-event-row").forEach(row => {
    row.addEventListener("click", () => {
      openCellEventDetail(cellId, Number(row.dataset.eventIndex));
    });
  });
  cellModalBodyEl.querySelectorAll(".cell-modal-cell-link").forEach(button => {
    button.addEventListener("click", () => openCellModal(button.dataset.cellId));
  });
  const backButton = cellModalBodyEl.querySelector(".cell-event-back");
  if (backButton) backButton.addEventListener("click", () => openCellModal(cellId));
}

function openCellEventDetail(cellId, eventIndex) {
  disposeLineageViewer();
  const events = getCellEvents(cellId);
  const event = events[eventIndex];
  if (!event) return;

  cellModalSubtitleEl.textContent = `${event.type} - step ${event.step}`;
  cellModalBodyEl.innerHTML = `
    <button class="cell-event-back" type="button">Back to cell details</button>
    <section class="cell-modal-section cell-event-detail">
      <h3>${escapeHtml(event.type)}</h3>
      <div class="cell-modal-grid">
        ${renderModalFact("Step", event.step)}
        ${renderModalFact("Time", formatValue(event.time))}
        ${renderModalFact("Message", event.message)}
      </div>
    </section>
    <section class="cell-modal-section">
      <h3>Event Values</h3>
      <div class="cell-modal-grid">
        ${Object.entries(event.values || {}).map(([key, value]) => renderModalFact(key, formatEventValue(value))).join("")}
      </div>
    </section>
    ${renderEventLinkedCells(event)}
  `;
  attachCellModalListeners(cellId);
}

function formatEventValue(value) {
  if (typeof value === "number") return formatValue(value);
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return value ?? "-";
}

function renderEventLinkedCells(event) {
  const cells = currentPayload?.final_state?.cells || currentPayload?.state?.cells || [];
  const values = event.values || {};
  const ids = new Set();
  if (values.cell_id) ids.add(values.cell_id);
  if (values.parent_id) ids.add(values.parent_id);
  if (Array.isArray(values.daughter_ids)) values.daughter_ids.forEach(id => ids.add(id));
  const linked = [...ids].filter(id => cells.some(cell => cell.id === id));
  if (!linked.length) return "";
  return `
    <section class="cell-modal-section">
      <h3>Linked Cells</h3>
      <div class="linked-cell-list">
        ${linked.map(id => `<button class="cell-modal-cell-link" data-cell-id="${escapeHtml(id)}" type="button" style="${lineageColorStyle(id)}">${escapeHtml(id)}</button>`).join("")}
      </div>
    </section>
  `;
}

function renderLineageMap(cell, cells) {
  const childCount = cells.filter(candidate => candidate.parent_id === cell.id).length;
  return `
    <div id="lineage-three-view" class="lineage-three-view" style="${lineageColorStyle(cell.id)}">
      <div class="lineage-three-fallback">Loading 3D lineage map...</div>
    </div>
    <div class="lineage-three-caption">Root path, selected cell, and ${childCount} direct child${childCount === 1 ? "" : "ren"}.</div>
  `;
}

function lineagePathForCell(cell, cells) {
  const byId = new Map(cells.map(candidate => [candidate.id, candidate]));
  const path = [];
  let cursor = cell;
  while (cursor) {
    path.unshift(cursor);
    cursor = cursor.parent_id ? byId.get(cursor.parent_id) : null;
  }
  return path;
}

function renderLineageThreeScene(cell, cells) {
  const container = document.getElementById("lineage-three-view");
  if (!container || !window.THREE) return;

  const path = lineagePathForCell(cell, cells);
  const children = cells.filter(candidate => candidate.parent_id === cell.id);
  const nodes = [
    ...path.map((pathCell, index) => ({
      cell: pathCell,
      role: pathCell.id === cell.id ? "selected" : "ancestor",
      position: new THREE.Vector3((index - (path.length - 1) / 2) * 2.25, 0.45, Math.sin(index * 0.9) * 0.32),
    })),
    ...children.map((child, index) => {
      const angle = (index / Math.max(children.length, 1)) * Math.PI * 2;
      return {
        cell: child,
        role: "child",
        position: new THREE.Vector3((path.length - 1) * 1.12 + 1.6 + Math.cos(angle) * 0.65, -0.92 + (index % 2) * 0.42, Math.sin(angle) * 0.74),
      };
    }),
  ];

  container.innerHTML = "";
  const width = Math.max(container.clientWidth, 320);
  const height = Math.max(container.clientHeight, 260);
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x08111f, 6, 16);

  const camera = new THREE.PerspectiveCamera(36, width / height, 0.1, 100);
  camera.position.set(0, 1.0, 5.7);
  camera.lookAt(0, -0.1, 0);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  container.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0x9db7ff, 1.25));
  const key = new THREE.PointLight(0xffffff, 2.8, 18);
  key.position.set(2.5, 4, 5);
  scene.add(key);
  const rim = new THREE.PointLight(0x60a5fa, 1.8, 12);
  rim.position.set(-4, 1.5, -2);
  scene.add(rim);

  const group = new THREE.Group();
  scene.add(group);
  const nodeMeshes = [];
  const selectedNode = nodes.find(node => node.role === "selected");
  const links = [];
  for (let index = 0; index < path.length - 1; index += 1) {
    links.push([path[index].id, path[index + 1].id]);
  }
  children.forEach(child => links.push([cell.id, child.id]));

  nodes.forEach((node) => {
    const hue = lineageHue(node.cell.id) / 360;
    const color = new THREE.Color().setHSL(hue, 0.72, node.role === "selected" ? 0.58 : 0.47);
    const radius = node.role === "selected" ? 0.32 : node.role === "child" ? 0.21 : 0.24;
    const material = new THREE.MeshStandardMaterial({
      color,
      emissive: color.clone().multiplyScalar(node.role === "selected" ? 0.55 : 0.28),
      metalness: 0.18,
      roughness: 0.32,
    });
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 32, 18), material);
    mesh.position.copy(node.position);
    mesh.userData = { cellId: node.cell.id, baseY: node.position.y };
    group.add(mesh);
    nodeMeshes.push(mesh);

    const halo = new THREE.Mesh(
      new THREE.SphereGeometry(radius * 1.45, 32, 12),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: node.role === "selected" ? 0.18 : 0.08, depthWrite: false })
    );
    halo.position.copy(node.position);
    group.add(halo);

    const label = makeLineageLabel(`${node.cell.id}\ngen ${node.cell.generation ?? lineageDepth(node.cell.id)}`, color, {
      prominent: node.role === "selected",
    });
    label.position.copy(node.position).add(new THREE.Vector3(0, node.role === "selected" ? -0.86 : -0.76, 0.04));
    label.renderOrder = 25;
    group.add(label);
  });

  const byId = new Map(nodes.map(node => [node.cell.id, node]));
  links.forEach(([fromId, toId]) => {
    const from = byId.get(fromId);
    const to = byId.get(toId);
    if (!from || !to) return;
    const color = new THREE.Color().setHSL(lineageHue(to.cell.id) / 360, 0.72, 0.55);
    const line = makeTubeBetween(from.position, to.position, color);
    group.add(line);
  });

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  renderer.domElement.addEventListener("pointerdown", (event) => {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(nodeMeshes, false)[0];
    if (hit?.object?.userData?.cellId) openCellModal(hit.object.userData.cellId);
  });

  let animationId = null;
  const animate = () => {
    animationId = window.requestAnimationFrame(animate);
    const t = performance.now() * 0.001;
    group.rotation.y = Math.sin(t * 0.45) * 0.16;
    group.rotation.x = Math.sin(t * 0.32) * 0.04;
    nodeMeshes.forEach((mesh, index) => {
      mesh.position.y = mesh.userData.baseY + Math.sin(t * 1.8 + index) * 0.035;
    });
    if (selectedNode) camera.lookAt(selectedNode.position.x * 0.2, 0, 0);
    renderer.render(scene, camera);
  };
  animate();

  lineageViewer = {
    renderer,
    scene,
    animationId: () => animationId,
    dispose() {
      if (animationId) window.cancelAnimationFrame(animationId);
      renderer.dispose();
      scene.traverse(object => {
        if (object.geometry) object.geometry.dispose();
        if (object.material) {
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach(material => {
            if (material.map) material.map.dispose();
            material.dispose();
          });
        }
      });
      container.innerHTML = "";
    },
  };
}

function makeTubeBetween(from, to, color) {
  const direction = new THREE.Vector3().subVectors(to, from);
  const length = direction.length();
  const geometry = new THREE.CylinderGeometry(0.035, 0.035, length, 14);
  const material = new THREE.MeshStandardMaterial({
    color,
    emissive: color.clone().multiplyScalar(0.18),
    metalness: 0.1,
    roughness: 0.38,
  });
  const tube = new THREE.Mesh(geometry, material);
  tube.position.copy(from).add(to).multiplyScalar(0.5);
  tube.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
  return tube;
}

function makeLineageLabel(text, color, options = {}) {
  const canvas = document.createElement("canvas");
  canvas.width = 560;
  canvas.height = 216;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  ctx.shadowColor = "rgba(0, 0, 0, 0.58)";
  ctx.shadowBlur = 20;
  ctx.shadowOffsetY = 8;
  ctx.fillStyle = "rgba(2, 6, 23, 0.94)";
  roundRect(ctx, 28, 28, 504, 150, 18);
  ctx.fill();
  ctx.shadowColor = "transparent";

  ctx.strokeStyle = `#${color.getHexString()}`;
  ctx.lineWidth = options.prominent ? 8 : 5;
  roundRect(ctx, 28, 28, 504, 150, 18);
  ctx.stroke();

  const [id, gen] = text.split("\n");
  const displayId = fitCanvasText(ctx, id, 436, 36, "700", "Arial");
  const displayGen = fitCanvasText(ctx, gen, 380, 24, "800", "Arial");

  ctx.strokeStyle = "rgba(2, 6, 23, 0.82)";
  ctx.lineWidth = 7;
  ctx.lineJoin = "round";
  ctx.fillStyle = "#f8fafc";
  ctx.font = `700 ${displayId.size}px Arial`;
  ctx.textAlign = "center";
  ctx.strokeText(displayId.text, 280, 92);
  ctx.fillText(displayId.text, 280, 92);

  ctx.strokeStyle = "rgba(2, 6, 23, 0.7)";
  ctx.lineWidth = 5;
  ctx.fillStyle = "#cbd5e1";
  ctx.font = `800 ${displayGen.size}px Arial`;
  ctx.strokeText(displayGen.text, 280, 132);
  ctx.fillText(displayGen.text, 280, 132);

  const texture = new THREE.CanvasTexture(canvas);
  texture.anisotropy = 8;
  texture.needsUpdate = true;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
    depthWrite: false,
  }));
  sprite.scale.set(options.prominent ? 2.85 : 2.4, options.prominent ? 1.1 : 0.92, 1);
  return sprite;
}

function fitCanvasText(ctx, text, maxWidth, startSize, weight, family) {
  let size = startSize;
  const fullText = String(text || "-");
  let candidate = fullText;
  while (size > 18) {
    ctx.font = `${weight} ${size}px ${family}`;
    if (ctx.measureText(candidate).width <= maxWidth) return { text: candidate, size };
    size -= 2;
  }

  ctx.font = `${weight} ${size}px ${family}`;
  for (let maxChars = fullText.length - 1; maxChars >= 8; maxChars -= 1) {
    const head = Math.ceil(maxChars / 2);
    const tail = Math.floor(maxChars / 2);
    candidate = `${fullText.slice(0, head)}...${fullText.slice(-tail)}`;
    if (ctx.measureText(candidate).width <= maxWidth) break;
  }
  return { text: candidate, size };
}

function roundRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

function disposeLineageViewer() {
  if (lineageViewer) {
    lineageViewer.dispose();
    lineageViewer = null;
  }
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
function sumCells(cells, pick) { return cells.reduce((sum, cell) => sum + Number(pick(cell) || 0), 0); }

function lineageParts(cellId = "") {
  return String(cellId).split(".").filter(Boolean);
}

function lineageDepth(cellId = "") {
  return Math.max(lineageParts(cellId).length - 1, 0);
}

function lineageHue(cellId = "") {
  const parts = lineageParts(cellId);
  const branchPath = parts.slice(1);
  if (!branchPath.length) return 205;
  const firstBranch = Number.parseInt(branchPath[0], 10);
  let hue = Number.isFinite(firstBranch) ? (firstBranch === 1 ? 205 : firstBranch === 2 ? 145 : 25) : 205;
  branchPath.slice(1).forEach((part, index) => {
    const branch = Number.parseInt(part, 10);
    const branchValue = Number.isFinite(branch) ? branch : hashString(part);
    hue += (branchValue - 1) * (42 / (index + 1)) + (index + 1) * 13;
  });
  return ((hue % 360) + 360) % 360;
}

function hashString(value = "") {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) - hash) + value.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash);
}

function lineageColorStyle(cellId = "") {
  const depth = lineageDepth(cellId);
  const hue = lineageHue(cellId);
  const saturation = clamp(78 - depth * 4, 52, 78);
  const lightness = clamp(49 + depth * 5, 42, 68);
  return `--cell-hue:${hue};--cell-saturation:${saturation}%;--cell-lightness:${lightness}%;`;
}

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

function isDivisionEvent(event) {
  return event?.type === "division" || (event?.type === "growth" && event?.message === "Completed a simple division event");
}

function collectDivisionEventsByStep(events = []) {
  const divisionEvents = new Map();
  events.forEach((event) => {
    if (isDivisionEvent(event)) divisionEvents.set(Number(event.step), event);
  });
  return divisionEvents;
}

function activityMessageFor(url, payload) {
  if (url.endsWith("/validate")) return payload.valid ? "Scenario configuration is healthy." : "Validation errors detected.";
  if (url.endsWith("/run")) {
    const divisionCount = (payload.events || []).filter(isDivisionEvent).length;
    const divisionSuffix = divisionCount > 0 ? ` Division events: ${divisionCount}.` : "";
    return `Run finished. Reason: ${payload.termination_reason || "MAX_STEPS"}.${divisionSuffix}`;
  }
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
  const hasSnapshots = !!(payload.snapshots?.length && payload.final_state?.cells);
  const hasMetrics = !!(payload.metrics?.length && payload.final_state?.cell);
  
  if (!hasSnapshots && !hasMetrics && viewer) {
    viewer.frames = [];
    viewer.playbackActive = false;
  }

  if (hasSnapshots) {
    playRunSnapshots(payload, label);
    return;
  }

  if (hasMetrics) {
    playRunTrajectory(payload, label);
    return;
  }
  
  if (payload.state?.cells) {
    updateVisualizationFromCells(payload.state.cells, label);
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
  updateVisualizationFromCells([{
    id: scenario.cell.initial_cell_id ?? "cell-1",
    name: scenario.cell.name,
    x: scenario.cell.x ?? 0,
    y: scenario.cell.y ?? 0,
    z: scenario.cell.z ?? 0,
    biomass: scenario.cell.biomass ?? 1,
    membrane_integrity: scenario.cell.membrane_integrity ?? 1,
    alive: true,
    status: "alive",
    energy: { atp: scenario.cell.initial_atp ?? 0 },
  }], label);
}

function updateVisualizationFromCell(cell, label) {
  updateVisualizationFromCells([{ ...cell, id: cell.id ?? cell.name ?? "cell-1" }], label);
}

function updateVisualizationFromCells(cells, label) {
  if (!selectedCellId || !cells.some(cell => cell.id === selectedCellId)) {
    selectedCellId = cells.find(cell => cell.alive)?.id || cells[0]?.id || null;
  }
  const spatialCells = cells.map(cell => ({
    id: cell.id ?? cell.name ?? "cell",
    name: cell.name ?? cell.id ?? "Unknown",
    x: Number(cell.x ?? 0),
    y: Number(cell.y ?? 0),
    z: Number(cell.z ?? 0),
    biomass: Number(cell.biomass ?? 1),
    membrane_integrity: Number(cell.membrane_integrity ?? 1),
    alive: cell.alive ?? cell.status === "alive",
    status: cell.status ?? (cell.alive ? "alive" : "dead"),
    atp: Number(cell.energy?.atp ?? cell.atp ?? 0),
  }));
  viewer.setCells(spatialCells);
  const selectedCell = spatialCells.find(cell => cell.id === selectedCellId) || spatialCells[0];
  vizNameEl.textContent = selectedCell ? selectedCell.id : "None";
  vizCoordsEl.textContent = selectedCell ? formatPosition(selectedCell) : "0.00, 0.00, 0.00";
  vizLabelEl.textContent = label;
}

function updateVisualizationFromCellLegacy(cell, label) {
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

function playRunSnapshots(payload, label) {
  const divisionCount = (payload.events || []).filter(event => event.type === "division").length;
  const frames = payload.snapshots.map(snapshot => ({
    step: Number(snapshot.step ?? 0),
    cells: (snapshot.state?.cells || []).map(cell => ({
      id: cell.id,
      name: cell.name ?? cell.id,
      x: Number(cell.x ?? 0),
      y: Number(cell.y ?? 0),
      z: Number(cell.z ?? 0),
      biomass: Number(cell.biomass ?? 1),
      membrane_integrity: Number(cell.membrane_integrity ?? 1),
      alive: cell.alive ?? cell.status === "alive",
      status: cell.status ?? (cell.alive ? "alive" : "dead"),
      atp: Number(cell.energy?.atp ?? 0),
    })),
  }));
  if (frames.length) {
    viewer.playSnapshots(frames);
    const finalCells = payload.final_state?.cells || [];
    if (!selectedCellId || !finalCells.some(cell => cell.id === selectedCellId)) {
      selectedCellId = finalCells.find(cell => cell.alive)?.id || finalCells[0]?.id || null;
    }
    vizLabelEl.textContent = `${label} (Population Run${divisionCount ? `, ${divisionCount} division${divisionCount === 1 ? "" : "s"}` : ""})`;
  }
}

function playRunTrajectory(payload, label) {
  const divisionEventsByStep = collectDivisionEventsByStep(payload.events || []);
  const divisionCount = divisionEventsByStep.size;
  const trajectory = payload.metrics.map(m => ({
    step: Number(m.step ?? 0),
    name: payload.final_state.cell.name,
    x: Number(m.x ?? 0),
    y: Number(m.y ?? 0),
    z: Number(m.z ?? 0),
    biomass: Number(m.biomass ?? 1),
    membrane_integrity: Number(m.membrane_integrity ?? 1),
    alive: true,
    atp: Number(m.atp ?? 0),
    divisionEvent: divisionEventsByStep.get(Number(m.step ?? 0)) ?? null,
  }));
  if (trajectory.length) {
    viewer.playTrajectory(trajectory);
    vizLabelEl.textContent = `${label} (Animated Run${divisionCount ? `, ${divisionCount} division${divisionCount === 1 ? "" : "s"}` : ""})`;
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
    this.selectedRenderCellId = null;
    this.cells = [];
    this.renderCells = [];
    this.frames = [];
    this.playbackActive = false;
    this.playbackStart = 0;
    this.segmentDurationMs = 140;
    this.segmentDurations = [];

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
      const hit = this.findCellAt(x, y);

      if (hit) {
        this.selectCell(hit.cell.id);
        selectedCellId = hit.cell.id;
        renderSummary(currentPayload || {});
        this.isDraggingCell = !this.playbackActive && this.renderCells.length === 1;
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
      if (this.isDraggingCell) this.finalizeCellReposition();
      this.dragging = false;
      this.isDraggingCell = false;
      this.canvas.releasePointerCapture(e.pointerId);
    });

    this.canvas.addEventListener("dblclick", (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const hit = this.findCellAt(e.clientX - rect.left, e.clientY - rect.top);
      if (hit && this.renderCells.length === 1) this.repositionCellRandomly();
    });

    this.canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.zoom = clamp(this.zoom * (e.deltaY > 0 ? 0.9 : 1.1), 0.5, 5);
    }, { passive: false });
  }

  normalizeCell(cell) {
    const id = String(cell?.id ?? cell?.name ?? "cell");
    return {
      ...cell,
      id,
      name: String(cell?.name ?? id),
      x: Number(cell?.x ?? 0),
      y: Number(cell?.y ?? 0),
      z: Number(cell?.z ?? 0),
      biomass: Number(cell?.biomass ?? 1),
      membrane_integrity: Number(cell?.membrane_integrity ?? 1),
      alive: cell?.alive ?? cell?.status === "alive",
      status: cell?.status ?? (cell?.alive ? "alive" : "dead"),
      atp: Number(cell?.atp ?? cell?.energy?.atp ?? 0),
    };
  }

  setCell(cell) {
    this.setCells([cell]);
  }

  setCells(cells) {
    this.cells = cells.map(cell => this.normalizeCell(cell));
    this.renderCells = this.cells.map(cell => ({ ...cell }));
    this.frames = [];
    this.segmentDurations = [];
    this.playbackActive = false;
    this.selectCell(selectedCellId || this.renderCells.find(cell => cell.alive)?.id || this.renderCells[0]?.id || null);
  }

  playTrajectory(trajectory) {
    const frames = trajectory.map(point => ({ step: point.step, cells: [point] }));
    this.playSnapshots(frames);
  }

  playSnapshots(frames) {
    this.frames = frames.map(frame => ({
      step: Number(frame.step ?? 0),
      cells: (frame.cells || []).map(cell => this.normalizeCell(cell)),
    })).filter(frame => frame.cells.length);

    if (!this.frames.length) {
      this.setCells([]);
      return;
    }

    this.cells = this.frames[this.frames.length - 1].cells.map(cell => ({ ...cell }));
    this.renderCells = this.frames[0].cells.map(cell => ({ ...cell }));
    this.segmentDurations = this.frames.slice(1).map(() => this.segmentDurationMs);
    this.playbackActive = this.frames.length > 1;
    this.playbackStart = performance.now();
    this.selectCell(selectedCellId || this.cells.find(cell => cell.alive)?.id || this.cells[0]?.id || null);
  }

  selectCell(cellId) {
    this.selectedRenderCellId = cellId || null;
    const selected = this.getSelectedRenderCell();
    vizNameEl.textContent = selected ? selected.id : "None";
    vizCoordsEl.textContent = selected ? formatPosition(selected) : "0.00, 0.00, 0.00";
  }

  getSelectedRenderCell() {
    return this.renderCells.find(cell => cell.id === this.selectedRenderCellId) || this.renderCells[0] || null;
  }

  handleCellDrag(dx, dy) {
    const cell = this.getSelectedRenderCell();
    if (!cell) return;
    const sensitivity = 0.02 / (this.zoom || 1);
    const cos = Math.cos(this.rotationY);
    const sin = Math.sin(this.rotationY);

    cell.x += dx * sensitivity * cos;
    cell.z -= dx * sensitivity * sin;
    cell.y -= dy * sensitivity;
    this.syncUIToRenderCell();
  }

  finalizeCellReposition() {
    const cell = this.getSelectedRenderCell();
    if (!cell) return;

    let scenario;
    try {
      scenario = JSON.parse(scenarioInput.value);
    } catch { return; }

    executeCreateCell({
      scenario,
      cell: {
        x: Number(cell.x.toFixed(2)),
        y: Number(cell.y.toFixed(2)),
        z: Number(cell.z.toFixed(2)),
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

  getCellRadius(cell, projectedScale) {
    const biomass = Math.max(Number(cell?.biomass ?? 1), 0.05);
    const scaledRadius = 15 * Math.sqrt(biomass) * this.zoom * projectedScale;
    return clamp(scaledRadius, 7, 54);
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
    this.drawTrails();
    this.drawCells();
  }

  advancePlayback() {
    if (!this.playbackActive) return;
    const elapsed = performance.now() - this.playbackStart;
    const totalDuration = this.segmentDurations.reduce((sum, duration) => sum + duration, 0);

    if (elapsed >= totalDuration) {
      this.renderCells = this.frames[this.frames.length - 1].cells.map(cell => ({ ...cell }));
      this.playbackActive = false;
      this.syncUIToRenderCell();
      return;
    }

    let remaining = elapsed;
    let index = 0;
    while (index < this.segmentDurations.length && remaining >= this.segmentDurations[index]) {
      remaining -= this.segmentDurations[index];
      index += 1;
    }

    const segmentDuration = this.segmentDurations[index] || this.segmentDurationMs;
    const t = segmentDuration > 0 ? remaining / segmentDuration : 1;
    const currentFrame = this.frames[index];
    const nextFrame = this.frames[index + 1] || currentFrame;
    this.renderCells = this.interpolateCells(currentFrame.cells, nextFrame.cells, t);
    this.syncUIToRenderCell();
  }

  interpolateCells(currentCells, nextCells, t) {
    const currentById = new Map(currentCells.map(cell => [cell.id, cell]));
    const nextById = new Map(nextCells.map(cell => [cell.id, cell]));
    const ids = Array.from(new Set([...currentById.keys(), ...nextById.keys()]));

    return ids.map((id) => {
      const current = currentById.get(id);
      const next = nextById.get(id);
      if (!current) return { ...next, birthAlpha: t };
      if (!next) return { ...current, birthAlpha: 1 - t };
      return {
        ...next,
        x: current.x + (next.x - current.x) * t,
        y: current.y + (next.y - current.y) * t,
        z: current.z + (next.z - current.z) * t,
        atp: current.atp + (next.atp - current.atp) * t,
        biomass: current.biomass + (next.biomass - current.biomass) * t,
        birthAlpha: 1,
      };
    });
  }

  syncUIToRenderCell() {
    const cell = this.getSelectedRenderCell();
    vizNameEl.textContent = cell ? cell.id : "None";
    vizCoordsEl.textContent = cell ? formatPosition(cell) : "0.00, 0.00, 0.00";

    const xIn = document.getElementById("metric-coord-x");
    const yIn = document.getElementById("metric-coord-y");
    const zIn = document.getElementById("metric-coord-z");

    if (cell && xIn) xIn.value = cell.x.toFixed(2);
    if (cell && yIn) yIn.value = cell.y.toFixed(2);
    if (cell && zIn) zIn.value = cell.z.toFixed(2);
  }

  findCellAt(x, y) {
    let nearest = null;
    for (const cell of this.renderCells) {
      const projected = this.project(cell);
      const radius = this.getCellRadius(cell, projected.scale);
      const dist = Math.sqrt((x - projected.x) ** 2 + (y - projected.y) ** 2);
      if (dist < radius * 2.4 && (!nearest || dist < nearest.dist)) {
        nearest = { cell, projected, radius, dist };
      }
    }
    return nearest;
  }

  drawTrails() {
    if (this.frames.length < 2) return;
    const ctx = this.ctx;
    const paths = new Map();

    this.frames.forEach((frame) => {
      frame.cells.forEach((cell) => {
        if (!paths.has(cell.id)) paths.set(cell.id, []);
        paths.get(cell.id).push(cell);
      });
    });

    ctx.save();
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 5]);
    Array.from(paths.values()).slice(0, 80).forEach((path) => {
      if (path.length < 2) return;
      const palette = this.paletteForCell(path[path.length - 1]);
      ctx.beginPath();
      ctx.strokeStyle = palette.trail;
      path.forEach((point, index) => {
        const projected = this.project(point);
        if (index === 0) ctx.moveTo(projected.x, projected.y);
        else ctx.lineTo(projected.x, projected.y);
      });
      ctx.stroke();
    });
    ctx.restore();
  }

  drawGrid() {
    const size = 10, step = 1;
    for (let i = -size; i <= size; i += step) {
      const isCenter = i === 0;
      const alpha = isCenter ? 0.35 : 0.12;
      const color = `rgba(148, 163, 184, ${alpha})`;
      this.drawLine({ x: -size, y: 0, z: i }, { x: size, y: 0, z: i }, color);
      this.drawLine({ x: i, y: 0, z: -size }, { x: i, y: 0, z: size }, color);
    }
    this.drawLine({ x: 0, y: 0, z: 0 }, { x: size, y: 0, z: 0 }, "rgba(239, 68, 68, 0.8)");
    this.drawLine({ x: 0, y: 0, z: 0 }, { x: 0, y: size, z: 0 }, "rgba(34, 197, 94, 0.8)");
    this.drawLine({ x: 0, y: 0, z: 0 }, { x: 0, y: 0, z: 5 }, "rgba(59, 130, 246, 0.8)");
  }

  drawCells() {
    const drawList = this.renderCells
      .map(cell => ({ cell, projected: this.project(cell) }))
      .sort((a, b) => a.projected.scale - b.projected.scale);

    drawList.forEach(({ cell, projected }) => {
      const radius = this.getCellRadius(cell, projected.scale);
      this.drawCellBody(projected, radius, cell);
      this.drawCellLabel(projected, radius, cell);
    });
  }

  drawCellBody(projected, radius, cell) {
    const ctx = this.ctx;
    const isSelected = cell.id === this.selectedRenderCellId;
    const alpha = clamp(cell.birthAlpha ?? 1, 0.15, 1);
    const palette = this.paletteForCell(cell);

    ctx.save();
    ctx.translate(projected.x, projected.y);
    ctx.globalAlpha = alpha;
    ctx.shadowBlur = isSelected ? 24 : 14;
    ctx.shadowColor = palette.shadow;

    const grad = ctx.createRadialGradient(-radius / 3, -radius / 3, radius / 4, 0, 0, radius);
    grad.addColorStop(0, palette.light);
    grad.addColorStop(1, palette.dark);

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(0, 0, radius, 0, Math.PI * 2);
    ctx.fill();

    ctx.shadowBlur = 0;
    ctx.strokeStyle = isSelected ? "#f8fafc" : palette.stroke;
    ctx.lineWidth = isSelected ? 2.5 : 1;
    ctx.stroke();

    ctx.fillStyle = "rgba(255,255,255,0.22)";
    ctx.beginPath();
    ctx.arc(-radius / 3, -radius / 3, radius / 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  drawCellLabel(projected, radius, cell) {
    const ctx = this.ctx;
    const isSelected = cell.id === this.selectedRenderCellId;
    if (!isSelected && this.renderCells.length > 18) return;

    ctx.save();
    ctx.fillStyle = isSelected ? "#fff" : "rgba(226, 232, 240, 0.78)";
    ctx.font = `${isSelected ? "bold " : ""}11px var(--font-sans)`;
    ctx.textAlign = "center";
    ctx.fillText(cell.id, projected.x, projected.y + radius + 15);
    ctx.restore();
  }

  paletteForCell(cell) {
    const depth = lineageDepth(cell.id);
    const hue = lineageHue(cell.id);
    const saturation = clamp(78 - depth * 4, 52, 78);
    const light = clamp(49 + depth * 5, 42, 68);
    if (cell.status === "divided") {
      return {
        light: `hsl(${hue} ${Math.max(saturation - 12, 48)}% ${Math.min(light + 13, 76)}%)`,
        dark: `hsl(${hue} ${Math.max(saturation - 16, 42)}% ${Math.max(light - 13, 30)}%)`,
        stroke: `hsla(${hue}, ${Math.max(saturation - 10, 44)}%, ${Math.min(light + 18, 78)}%, 0.48)`,
        shadow: `hsla(${hue}, ${Math.max(saturation - 18, 38)}%, ${light}%, 0.28)`,
        trail: `hsla(${hue}, ${Math.max(saturation - 14, 42)}%, ${light}%, 0.2)`,
      };
    }
    if (cell.status === "dead" || cell.alive === false) {
      return {
        light: `hsl(${hue} ${Math.max(saturation - 34, 28)}% ${Math.min(light + 16, 74)}%)`,
        dark: `hsl(${hue} ${Math.max(saturation - 38, 24)}% ${Math.max(light - 10, 28)}%)`,
        stroke: `hsla(${hue}, ${Math.max(saturation - 30, 26)}%, ${Math.min(light + 18, 78)}%, 0.42)`,
        shadow: `hsla(${hue}, ${Math.max(saturation - 34, 24)}%, ${light}%, 0.24)`,
        trail: `hsla(${hue}, ${Math.max(saturation - 34, 24)}%, ${light}%, 0.16)`,
      };
    }
    return {
      light: `hsl(${hue} ${saturation}% ${Math.min(light + 14, 78)}%)`,
      dark: `hsl(${hue} ${saturation}% ${Math.max(light - 14, 28)}%)`,
      stroke: `hsla(${hue}, ${saturation}%, ${Math.min(light + 20, 82)}%, 0.52)`,
      shadow: `hsla(${hue}, ${saturation}%, ${light}%, 0.38)`,
      trail: `hsla(${hue}, ${saturation}%, ${light}%, 0.28)`,
    };
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
