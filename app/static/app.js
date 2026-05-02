const PAGE_SIZE = 25;

let importsOffset = 0;
let activitiesOffset = 0;
let stravaConfigured = false;

function $(sel) {
  return document.querySelector(sel);
}

function showStatus(msg, ok = true) {
  const el = $("#status");
  el.textContent = msg;
  el.className = "visible " + (ok ? "ok" : "err");
}

function clearStatus() {
  const el = $("#status");
  el.className = "";
  el.textContent = "";
}

async function fetchJson(url, opts = {}) {
  const r = await fetch(url, {
    ...opts,
    headers: { Accept: "application/json", ...(opts.headers || {}) },
  });
  const text = await r.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!r.ok) {
    const detail = data?.detail ?? r.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

async function loadConfig() {
  const c = await fetchJson("/api/config");
  stravaConfigured = c.strava_configured;
  $("#import-dir").textContent = c.import_dir;
  $("#strava-uri").textContent = c.strava_redirect_uri || "—";

  const btn = $("#btn-strava");
  if (!c.strava_configured) {
    btn.disabled = true;
    btn.title = "Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET for the API container";
  } else {
    btn.disabled = false;
    btn.title = "";
  }
}

async function loadSummary() {
  const s = await fetchJson("/api/summary");
  $("#stat-imports").textContent = s.imports;
  $("#stat-canonical").textContent = s.canonical_workouts;
  $("#stat-strava").textContent = s.strava_connected ? "Connected" : "Not connected";
  $("#btn-sync-strava").disabled = !stravaConfigured || !s.strava_connected;
}

async function loadImports() {
  const q = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(importsOffset),
  });
  const data = await fetchJson("/imports?" + q);
  const tbody = $("#imports-body");
  tbody.innerHTML = "";
  for (const row of data.items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(row.origin_key)}</td><td>${escapeHtml(row.format)}</td><td>${escapeHtml(
      row.start_time,
    )}</td>`;
    tbody.appendChild(tr);
  }
  $("#imports-pager").textContent =
    data.total === 0
      ? "No imports"
      : `${importsOffset + 1}–${Math.min(importsOffset + data.items.length, data.total)} of ${data.total}`;
  $("#imports-prev").disabled = importsOffset === 0;
  $("#imports-next").disabled = importsOffset + data.items.length >= data.total;
}

async function loadActivities() {
  const q = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(activitiesOffset),
  });
  const data = await fetchJson("/activities?" + q);
  const tbody = $("#activities-body");
  tbody.innerHTML = "";
  for (const row of data.items) {
    const tr = document.createElement("tr");
    const fields = row.merged?.fields
      ? JSON.stringify(row.merged.fields, null, 2)
      : "—";
    tr.innerHTML = `<td>${row.id}</td><td>${escapeHtml(row.start_time)}</td><td>${escapeHtml(
      row.sport || "—",
    )}</td><td><pre class="fields">${escapeHtml(fields)}</pre></td>`;
    tbody.appendChild(tr);
  }
  $("#activities-pager").textContent =
    data.total === 0
      ? "No merged workouts yet — scan imports and run merge."
      : `${activitiesOffset + 1}–${Math.min(
          activitiesOffset + data.items.length,
          data.total,
        )} of ${data.total}`;
  $("#activities-prev").disabled = activitiesOffset === 0;
  $("#activities-next").disabled = activitiesOffset + data.items.length >= data.total;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function init() {
  try {
    await loadConfig();
    await loadSummary();
    await loadImports();
    await loadActivities();
  } catch (e) {
    showStatus(e.message || String(e), false);
  }

  $("#btn-scan").addEventListener("click", async () => {
    clearStatus();
    try {
      const res = await fetchJson("/imports/scan", { method: "POST" });
      showStatus(`Scan complete — ${res.imported} file(s) processed in ${res.directory}`);
      await loadSummary();
      await loadImports();
    } catch (e) {
      showStatus(e.message || String(e), false);
    }
  });

  $("#btn-merge").addEventListener("click", async () => {
    clearStatus();
    try {
      const res = await fetchJson("/merge/rebuild", { method: "POST" });
      showStatus(`Merge rebuilt — ${res.canonical_workouts} canonical workout(s).`);
      await loadSummary();
      await loadActivities();
    } catch (e) {
      showStatus(e.message || String(e), false);
    }
  });

  $("#btn-upload").addEventListener("click", async () => {
    clearStatus();
    const input = $("#file-input");
    if (!input.files?.length) {
      showStatus("Choose a .fit, .gpx, or .tcx file first.", false);
      return;
    }
    const fd = new FormData();
    fd.append("file", input.files[0]);
    try {
      const res = await fetch("/imports/upload", { method: "POST", body: fd });
      const text = await res.text();
      const data = text ? JSON.parse(text) : {};
      if (!res.ok) throw new Error(data.detail || res.statusText);
      showStatus(`Uploaded — ${data.origin_key} (${data.format})`);
      input.value = "";
      await loadSummary();
      await loadImports();
    } catch (e) {
      showStatus(e.message || String(e), false);
    }
  });

  $("#btn-strava").addEventListener("click", () => {
    window.location.href = "/auth/strava";
  });

  $("#btn-sync-strava").addEventListener("click", async () => {
    clearStatus();
    const days = Number($("#strava-days").value || 14);
    try {
      const res = await fetchJson(`/sync/strava?days=${days}`, { method: "POST" });
      showStatus(`Strava sync — ${res.strava_activities_upserted} activit(y/ies) upserted. Run merge to cluster.`);
      await loadSummary();
      await loadImports();
    } catch (e) {
      showStatus(e.message || String(e), false);
    }
  });

  $("#imports-prev").addEventListener("click", () => {
    importsOffset = Math.max(0, importsOffset - PAGE_SIZE);
    loadImports().catch((e) => showStatus(e.message, false));
  });
  $("#imports-next").addEventListener("click", () => {
    importsOffset += PAGE_SIZE;
    loadImports().catch((e) => showStatus(e.message, false));
  });
  $("#activities-prev").addEventListener("click", () => {
    activitiesOffset = Math.max(0, activitiesOffset - PAGE_SIZE);
    loadActivities().catch((e) => showStatus(e.message, false));
  });
  $("#activities-next").addEventListener("click", () => {
    activitiesOffset += PAGE_SIZE;
    loadActivities().catch((e) => showStatus(e.message, false));
  });
}

document.addEventListener("DOMContentLoaded", init);
