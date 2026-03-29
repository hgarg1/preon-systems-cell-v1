const scenarioInput = document.getElementById("scenario");
const seedInput = document.getElementById("seed");
const maxStepsInput = document.getElementById("max-steps");
const dtInput = document.getElementById("dt");
const cellXInput = document.getElementById("cell-x");
const cellYInput = document.getElementById("cell-y");
const cellZInput = document.getElementById("cell-z");
const responseEl = document.getElementById("response");
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
const visualizerPanelEl = document.querySelector(".visualizer");
let viewer;
let editorSyncTimer = null;

document.getElementById("load-default").addEventListener("click", loadDefaultScenario);
document.getElementById("create-cell").addEventListener("click", createCell);
document.getElementById("validate").addEventListener("click", () => submit("/api/validate"));
document.getElementById("run").addEventListener("click", () => submit("/api/run"));
scenarioInput.addEventListener("input", handleScenarioEditorInput);
vizFullscreenButton.addEventListener("click", toggleVisualizationFullscreen);
document.addEventListener("fullscreenchange", handleFullscreenChange);

async function loadDefaultScenario() {
  setStatus("busy", "Loading");
  setActivity("Fetching the bundled default scenario.");
  try {
    const response = await fetch("/api/default-scenario");
    const payload = await response.json();
    scenarioInput.value = JSON.stringify(payload.scenario, null, 2);
    responseEl.textContent = JSON.stringify(payload, null, 2);
    renderSummary({ scenario: payload.scenario, loaded: true });
    updateVisualizationFromScenario(payload.scenario, "Scenario defaults");
    updateRequestMeta("/api/default-scenario", "Loaded");
    responseLabelEl.textContent = "Default scenario payload";
    setStatus("ok", "Ready");
    setActivity("Default scenario loaded. You can now edit JSON, create a cell, validate, or run.");
  } catch (error) {
    setStatus("error", "Load failed");
    responseEl.textContent = String(error);
    responseLabelEl.textContent = "Load failed";
    updateRequestMeta("/api/default-scenario", "Error");
    setActivity("The default scenario could not be loaded.");
  }
}

async function submit(url) {
  let scenario;
  try {
    scenario = JSON.parse(scenarioInput.value);
  } catch (error) {
    setStatus("error", "Bad JSON");
    responseEl.textContent = `Scenario JSON could not be parsed: ${error}`;
    return;
  }

  const body = {
    scenario,
    seed: Number(seedInput.value || 7),
  };
  if (maxStepsInput.value) {
    body.max_steps = Number(maxStepsInput.value);
  }
  if (dtInput.value) {
    body.dt = Number(dtInput.value);
  }

  setStatus("busy", url.endsWith("/run") ? "Running" : "Validating");
  setActivity(url.endsWith("/run") ? "Submitting scenario to the run endpoint." : "Submitting scenario validation.");
  updateRequestMeta(url, "Pending");
  responseLabelEl.textContent = `Awaiting response from ${url}`;
  responseEl.textContent = "";

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(JSON.stringify(payload, null, 2));
    }
    responseEl.textContent = JSON.stringify(payload, null, 2);
    renderSummary(payload);
    syncVisualizationWithPayload(payload, responseTitleFor(url, payload));
    updateRequestMeta(url, "OK");
    responseLabelEl.textContent = responseTitleFor(url, payload);
    setStatus("ok", "Complete");
    setActivity(activityMessageFor(url, payload));
  } catch (error) {
    renderEmptySummary();
    responseEl.textContent = String(error);
    setStatus("error", "Request failed");
    updateRequestMeta(url, "Error");
    responseLabelEl.textContent = `Error from ${url}`;
    setActivity("The request failed. Inspect the response panel for details.");
  }
}

async function createCell() {
  let scenario;
  try {
    scenario = JSON.parse(scenarioInput.value);
  } catch (error) {
    setStatus("error", "Bad JSON");
    responseEl.textContent = `Scenario JSON could not be parsed: ${error}`;
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

  setStatus("busy", "Creating cell");
  setActivity("Creating a cell state from the current scenario and x/y/z coordinates.");
  updateRequestMeta("/api/cells", "Pending");
  responseLabelEl.textContent = "Awaiting response from /api/cells";
  try {
    const response = await fetch("/api/cells", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(JSON.stringify(payload, null, 2));
    }
    scenarioInput.value = JSON.stringify(payload.scenario, null, 2);
    responseEl.textContent = JSON.stringify(payload, null, 2);
    renderSummary(payload);
    syncInputsToCell(payload.state.cell);
    updateVisualizationFromCell(payload.state.cell, "Created cell state");
    updateRequestMeta("/api/cells", "OK");
    responseLabelEl.textContent = "Created cell payload";
    setStatus("ok", "Cell ready");
    setActivity(`Cell "${payload.state.cell.name}" is ready at ${formatPosition(payload.state.cell)}.`);
  } catch (error) {
    renderEmptySummary();
    responseEl.textContent = String(error);
    setStatus("error", "Request failed");
    updateRequestMeta("/api/cells", "Error");
    responseLabelEl.textContent = "Error from /api/cells";
    setActivity("Cell creation failed. Inspect the response panel for details.");
  }
}

function renderSummary(payload) {
  const metrics = [];
  if (payload.loaded && payload.scenario?.cell) {
    metrics.push(["Scenario", payload.scenario.scenario_name]);
    metrics.push(["Cell", payload.scenario.cell.name]);
    metrics.push(["Default ATP", formatValue(payload.scenario.cell.initial_atp)]);
    metrics.push(["Coords", formatPosition(payload.scenario.cell)]);
  } else if (payload.state?.cell) {
    metrics.push(["Cell", payload.state.cell.name]);
    metrics.push(["ATP", formatValue(payload.state.cell.energy.atp)]);
    metrics.push(["Position", formatPosition(payload.state.cell)]);
    metrics.push(["Biomass", formatValue(payload.state.cell.biomass)]);
  } else if (payload.final_state) {
    metrics.push(["Steps", payload.final_state.step]);
    metrics.push(["ATP", formatValue(payload.final_state.cell.energy.atp)]);
    metrics.push(["Biomass", formatValue(payload.final_state.cell.biomass)]);
    metrics.push(["Termination", payload.termination_reason ?? "n/a"]);
  } else if (typeof payload.valid === "boolean") {
    metrics.push(["Scenario", payload.valid ? "Valid" : "Invalid"]);
    metrics.push(["Errors", payload.errors?.length ?? 0]);
  }

  if (!metrics.length) {
    renderEmptySummary();
    return;
  }

  summaryEl.innerHTML = metrics.map(renderMetric).join("");
}

function formatValue(value) {
  return typeof value === "number" ? value.toFixed(4) : value;
}

function formatPosition(cell) {
  return `${formatValue(cell.x)}, ${formatValue(cell.y)}, ${formatValue(cell.z)}`;
}

function setStatus(kind, text) {
  statusEl.className = `status ${kind}`;
  statusEl.textContent = text;
}

function renderMetric([label, value]) {
  return `<article class="metric"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(String(value))}</span></article>`;
}

function renderEmptySummary() {
  summaryEl.innerHTML = `
    <article class="empty-state">
      <strong>No run data yet.</strong>
      <span>Validate a scenario, create a cell, or run the engine to populate this panel.</span>
    </article>
  `;
}

function updateRequestMeta(endpoint, outcome) {
  requestMetaEl.innerHTML = `
    <div><dt>Endpoint</dt><dd>${escapeHtml(endpoint)}</dd></div>
    <div><dt>When</dt><dd>${escapeHtml(new Date().toLocaleString())}</dd></div>
    <div><dt>Outcome</dt><dd>${escapeHtml(outcome)}</dd></div>
  `;
}

function responseTitleFor(url, payload) {
  if (url === "/api/validate") {
    return payload.valid ? "Validation report: valid" : "Validation report: invalid";
  }
  if (url === "/api/run") {
    return `Run artifacts for ${payload.metadata?.scenario_name ?? "scenario"}`;
  }
  if (url === "/api/step") {
    return "Single-step simulation result";
  }
  return "API response";
}

function activityMessageFor(url, payload) {
  if (url === "/api/validate") {
    return payload.valid ? "Scenario validation passed." : "Scenario validation failed.";
  }
  if (url === "/api/run") {
    return `Run completed at step ${payload.final_state?.step ?? "n/a"} with termination ${payload.termination_reason ?? "n/a"}.`;
  }
  if (url === "/api/step") {
    return `Single step executed. New time is ${formatValue(payload.state?.time)}.`;
  }
  return "Request completed.";
}

function setActivity(text) {
  activityEl.textContent = text;
}

async function toggleVisualizationFullscreen() {
  if (!document.fullscreenEnabled) {
    vizLabelEl.textContent = "Fullscreen is not available in this browser";
    return;
  }
  if (document.fullscreenElement === visualizerPanelEl) {
    await document.exitFullscreen();
    return;
  }
  await visualizerPanelEl.requestFullscreen();
}

function handleFullscreenChange() {
  const isFullscreen = document.fullscreenElement === visualizerPanelEl;
  vizFullscreenButton.textContent = isFullscreen ? "Exit fullscreen" : "Fullscreen";
  viewer.resize();
}

function handleScenarioEditorInput() {
  window.clearTimeout(editorSyncTimer);
  editorSyncTimer = window.setTimeout(() => {
    const scenario = tryParseScenario();
    if (!scenario?.cell) {
      vizLabelEl.textContent = "Awaiting valid scenario JSON";
      return;
    }
    syncInputsToCell(scenario.cell);
    updateVisualizationFromScenario(scenario, "Scenario editor");
  }, 220);
}

function tryParseScenario() {
  try {
    return JSON.parse(scenarioInput.value);
  } catch {
    return null;
  }
}

function syncInputsToCell(cell) {
  if (typeof cell.x === "number") {
    cellXInput.value = String(cell.x);
  }
  if (typeof cell.y === "number") {
    cellYInput.value = String(cell.y);
  }
  if (typeof cell.z === "number") {
    cellZInput.value = String(cell.z);
  }
}

function syncVisualizationWithPayload(payload, label) {
  if (payload.metrics?.length && payload.final_state?.cell) {
    playRunTrajectory(payload, label);
    return;
  }
  if (payload.final_state?.cell) {
    updateVisualizationFromCell(payload.final_state.cell, label);
    return;
  }
  if (payload.state?.cell) {
    updateVisualizationFromCell(payload.state.cell, label);
    return;
  }
  if (payload.scenario?.cell) {
    updateVisualizationFromScenario(payload.scenario, label);
  }
}

function updateVisualizationFromScenario(scenario, label) {
  if (!scenario?.cell) {
    return;
  }
  updateVisualizationFromCell(
    {
      name: scenario.cell.name,
      x: scenario.cell.x ?? 0,
      y: scenario.cell.y ?? 0,
      z: scenario.cell.z ?? 0,
      biomass: scenario.cell.biomass ?? 0,
      membrane_integrity: scenario.cell.membrane_integrity ?? 1,
      alive: true,
      energy: { atp: scenario.cell.initial_atp ?? 0 },
    },
    label,
  );
}

function updateVisualizationFromCell(cell, label) {
  const spatialCell = {
    name: cell.name ?? "Unnamed cell",
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
  vizCoordsEl.textContent = `x ${formatValue(spatialCell.x)} | y ${formatValue(spatialCell.y)} | z ${formatValue(spatialCell.z)}`;
  vizLabelEl.textContent = `${label} · ATP ${formatValue(spatialCell.atp)} · Biomass ${formatValue(spatialCell.biomass)}`;
}

function playRunTrajectory(payload, label) {
  const trajectory = payload.metrics.map((metric) => ({
    name: payload.final_state.cell.name,
    x: Number(metric.x ?? 0),
    y: Number(metric.y ?? 0),
    z: Number(metric.z ?? 0),
    biomass: Number(metric.biomass ?? payload.final_state.cell.biomass ?? 1),
    membrane_integrity: Number(metric.membrane_integrity ?? payload.final_state.cell.membrane_integrity ?? 1),
    alive: payload.final_state.cell.alive ?? true,
    atp: Number(metric.atp ?? 0),
  }));
  if (!trajectory.length) {
    updateVisualizationFromCell(payload.final_state.cell, label);
    return;
  }

  viewer.playTrajectory(trajectory);
  const last = trajectory[trajectory.length - 1];
  vizNameEl.textContent = last.name;
  vizCoordsEl.textContent = `x ${formatValue(last.x)} | y ${formatValue(last.y)} | z ${formatValue(last.z)}`;
  vizLabelEl.textContent = `${label} · animated ${trajectory.length} recorded steps`;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function rotateY(point, angle) {
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  return {
    x: point.x * cos - point.z * sin,
    y: point.y,
    z: point.x * sin + point.z * cos,
  };
}

function rotateX(point, angle) {
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  return {
    x: point.x,
    y: point.y * cos - point.z * sin,
    z: point.y * sin + point.z * cos,
  };
}

function mixColor(channelA, channelB, ratio) {
  return Math.round(channelA + (channelB - channelA) * ratio);
}

function rgb(values) {
  return `rgb(${values[0]}, ${values[1]}, ${values[2]})`;
}

class SpaceViewer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    this.rotationX = -0.55;
    this.rotationY = 0.72;
    this.zoom = 1;
    this.dragging = false;
    this.lastPoint = null;
    this.cell = {
      name: "No cell loaded",
      x: 0,
      y: 0,
      z: 0,
      biomass: 1,
      membrane_integrity: 1,
      alive: true,
      atp: 0,
    };
    this.trajectory = [];
    this.playbackActive = false;
    this.playbackStart = 0;
    this.segmentDurationMs = 140;
    this.renderCell = { ...this.cell };

    this.bindEvents();
    this.resize();
    this.animate = this.animate.bind(this);
    window.requestAnimationFrame(this.animate);
  }

  bindEvents() {
    window.addEventListener("resize", () => this.resize());
    this.canvas.addEventListener("pointerdown", (event) => {
      this.dragging = true;
      this.lastPoint = { x: event.clientX, y: event.clientY };
      this.canvas.setPointerCapture(event.pointerId);
    });
    this.canvas.addEventListener("pointermove", (event) => {
      if (!this.dragging || !this.lastPoint) {
        return;
      }
      const deltaX = event.clientX - this.lastPoint.x;
      const deltaY = event.clientY - this.lastPoint.y;
      this.rotationY += deltaX * 0.008;
      this.rotationX = clamp(this.rotationX + deltaY * 0.008, -1.35, 1.35);
      this.lastPoint = { x: event.clientX, y: event.clientY };
    });
    this.canvas.addEventListener("pointerup", (event) => {
      this.dragging = false;
      this.lastPoint = null;
      this.canvas.releasePointerCapture(event.pointerId);
    });
    this.canvas.addEventListener("pointerleave", () => {
      this.dragging = false;
      this.lastPoint = null;
    });
    this.canvas.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        this.zoom = clamp(this.zoom * (event.deltaY > 0 ? 0.92 : 1.08), 0.55, 2.4);
      },
      { passive: false },
    );
  }

  resize() {
    const bounds = this.canvas.getBoundingClientRect();
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
    this.trajectory = trajectory.map((point) => ({ ...point }));
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

    this.drawBackdrop();
    this.drawLattice();
    this.drawAxisMarkers();
    this.drawTrail();
    this.drawCell();
  }

  advancePlayback() {
    if (!this.playbackActive || this.trajectory.length < 2) {
      return;
    }
    const elapsed = performance.now() - this.playbackStart;
    const totalDuration = (this.trajectory.length - 1) * this.segmentDurationMs;
    if (elapsed >= totalDuration) {
      this.renderCell = { ...this.trajectory[this.trajectory.length - 1] };
      this.playbackActive = false;
      return;
    }

    const rawIndex = elapsed / this.segmentDurationMs;
    const index = Math.floor(rawIndex);
    const t = rawIndex - index;
    const current = this.trajectory[index];
    const next = this.trajectory[index + 1];
    this.renderCell = {
      ...next,
      x: current.x + (next.x - current.x) * t,
      y: current.y + (next.y - current.y) * t,
      z: current.z + (next.z - current.z) * t,
      biomass: current.biomass + (next.biomass - current.biomass) * t,
      membrane_integrity: current.membrane_integrity + (next.membrane_integrity - current.membrane_integrity) * t,
      atp: current.atp + (next.atp - current.atp) * t,
    };
  }

  drawBackdrop() {
    const ctx = this.ctx;
    const gradient = ctx.createRadialGradient(this.width * 0.5, this.height * 0.1, 20, this.width * 0.5, this.height, this.width);
    gradient.addColorStop(0, "rgba(255,255,255,0.14)");
    gradient.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, this.width, this.height);
  }

  drawLattice() {
    const ctx = this.ctx;
    const size = this.referenceSize();
    const gridHalf = Math.max(5, Math.ceil(size / 2));
    const slices = [-gridHalf, -Math.ceil(gridHalf / 2), 0, Math.ceil(gridHalf / 2), gridHalf];

    slices.forEach((slice, sliceIndex) => {
      const alpha = 0.06 + (sliceIndex / Math.max(slices.length - 1, 1)) * 0.08;
      for (let i = -gridHalf; i <= gridHalf; i += 1) {
        this.drawLine(
          { x: -gridHalf, y: slice, z: i },
          { x: gridHalf, y: slice, z: i },
          `rgba(210, 245, 236, ${alpha})`,
          1,
        );
        this.drawLine(
          { x: i, y: slice, z: -gridHalf },
          { x: i, y: slice, z: gridHalf },
          `rgba(210, 245, 236, ${alpha})`,
          1,
        );
      }
    });

    for (let i = -gridHalf; i <= gridHalf; i += 1) {
      this.drawLine(
        { x: -gridHalf, y: i, z: -gridHalf },
        { x: -gridHalf, y: i, z: gridHalf },
        "rgba(121, 205, 185, 0.08)",
        1,
      );
      this.drawLine(
        { x: gridHalf, y: i, z: -gridHalf },
        { x: gridHalf, y: i, z: gridHalf },
        "rgba(121, 205, 185, 0.08)",
        1,
      );
    }

    this.drawBoundingCube(gridHalf);
  }

  drawBoundingCube(gridHalf) {
    const corners = {
      lbf: { x: -gridHalf, y: -gridHalf, z: -gridHalf },
      lbb: { x: -gridHalf, y: -gridHalf, z: gridHalf },
      ltf: { x: -gridHalf, y: gridHalf, z: -gridHalf },
      ltb: { x: -gridHalf, y: gridHalf, z: gridHalf },
      rbf: { x: gridHalf, y: -gridHalf, z: -gridHalf },
      rbb: { x: gridHalf, y: -gridHalf, z: gridHalf },
      rtf: { x: gridHalf, y: gridHalf, z: -gridHalf },
      rtb: { x: gridHalf, y: gridHalf, z: gridHalf },
    };

    [
      ["lbf", "lbb"],
      ["lbf", "ltf"],
      ["lbf", "rbf"],
      ["rbb", "lbb"],
      ["rbb", "rtb"],
      ["rbb", "rbf"],
      ["ltf", "ltb"],
      ["ltf", "rtf"],
      ["rtf", "rtb"],
      ["rtf", "rbf"],
      ["ltb", "rtb"],
      ["ltb", "lbb"],
    ].forEach(([from, to]) => {
      this.drawLine(corners[from], corners[to], "rgba(255,255,255,0.16)", 1.4);
    });
  }

  drawAxisMarkers() {
    const size = this.referenceSize();
    const anchors = [
      { point: { x: size, y: -size, z: -size }, label: "X", color: "#d06347" },
      { point: { x: -size, y: size, z: -size }, label: "Y", color: "#37a686" },
      { point: { x: -size, y: -size, z: size }, label: "Z", color: "#4d82ff" },
    ];

    anchors.forEach(({ point, label, color }) => {
      const projected = this.project(point);
      const ctx = this.ctx;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(projected.x, projected.y, 4, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "rgba(255,255,255,0.8)";
      ctx.font = '12px "Segoe UI", sans-serif';
      ctx.fillText(label, projected.x + 8, projected.y - 8);
    });
  }

  drawTrail() {
    if (!this.trajectory.length) {
      return;
    }
    const ctx = this.ctx;
    ctx.strokeStyle = "rgba(143, 242, 215, 0.62)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    this.trajectory.forEach((point, index) => {
      const projected = this.project(point);
      if (index === 0) {
        ctx.moveTo(projected.x, projected.y);
      } else {
        ctx.lineTo(projected.x, projected.y);
      }
    });
    ctx.stroke();
  }

  drawCell() {
    const ctx = this.ctx;
    const cell = this.renderCell;
    const projected = this.project(cell);
    const radius = clamp(10 + cell.biomass * 10 * this.zoom + projected.scale * 7, 10, 42);
    const integrity = clamp(cell.membrane_integrity, 0, 1);
    const aliveMix = cell.alive ? integrity : 0;
    const fillColor = [
      mixColor(216, 80, aliveMix),
      mixColor(113, 81, aliveMix),
      mixColor(86, 130, aliveMix),
    ];
    const glow = ctx.createRadialGradient(projected.x - radius * 0.25, projected.y - radius * 0.35, radius * 0.2, projected.x, projected.y, radius * 1.4);
    glow.addColorStop(0, "rgba(255,255,255,0.92)");
    glow.addColorStop(0.3, rgb(fillColor));
    glow.addColorStop(1, "rgba(9, 43, 59, 0.22)");

    ctx.fillStyle = "rgba(130, 222, 196, 0.16)";
    ctx.beginPath();
    ctx.arc(projected.x, projected.y, radius * 1.8, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(projected.x, projected.y, radius, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = `rgba(255,255,255,${0.3 + integrity * 0.5})`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(projected.x, projected.y, radius, 0, Math.PI * 2);
    ctx.stroke();

    ctx.fillStyle = "rgba(255,255,255,0.9)";
    ctx.beginPath();
    ctx.arc(projected.x - radius * 0.25, projected.y - radius * 0.28, Math.max(3, radius * 0.18), 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "rgba(255,255,255,0.72)";
    ctx.font = '13px "Segoe UI", sans-serif';
    ctx.fillText(cell.name, projected.x + radius + 10, projected.y - 6);
    ctx.fillText(`ATP ${formatValue(cell.atp)}`, projected.x + radius + 10, projected.y + 12);
  }

  referenceSize() {
    return Math.max(
      8,
      Math.abs(this.cell.x) * 2.2,
      Math.abs(this.cell.y) * 2.2,
      Math.abs(this.cell.z) * 2.2,
      this.cell.biomass * 4,
      ...this.trajectory.flatMap((point) => [Math.abs(point.x) * 2.2, Math.abs(point.y) * 2.2, Math.abs(point.z) * 2.2]),
    );
  }

  project(point) {
    const scaleBase = Math.min(this.width, this.height) * 0.085 * this.zoom;
    const rotatedY = rotateY(point, this.rotationY);
    const rotated = rotateX(rotatedY, this.rotationX);
    const cameraDepth = 18;
    const perspective = cameraDepth / (cameraDepth + rotated.z + 12);
    return {
      x: this.width * 0.5 + rotated.x * scaleBase * perspective,
      y: this.height * 0.58 - rotated.y * scaleBase * perspective,
      scale: perspective,
    };
  }

  drawLine(from, to, strokeStyle, lineWidth) {
    const ctx = this.ctx;
    const start = this.project(from);
    const end = this.project(to);
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
  }
}

viewer = new SpaceViewer(canvasEl);
void loadDefaultScenario();
