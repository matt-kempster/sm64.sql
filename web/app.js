"use strict";

// ---------------------------------------------------------------------------
// sm64.sql web playground. The database is loaded once into WebAssembly SQLite
// (sql.js) and lives entirely in this page; queries run locally.
// ---------------------------------------------------------------------------

const DB_URL = "sm64.db";
const MAX_DISPLAY_ROWS = 1000;

let db = null; // active sql.js Database
let originalBytes = null; // pristine copy, for "Reload data"

const $ = (sel) => document.querySelector(sel);

const els = {
  loading: $("#loading"),
  sql: $("#sql"),
  run: $("#run"),
  reset: $("#reset"),
  status: $("#status"),
  results: $("#results"),
  examples: $("#examples"),
  schema: $("#schema"),
  schemaCount: $("#schema-count"),
};

// --- boot ------------------------------------------------------------------

async function boot() {
  try {
    const SQL = await initSqlJs({
      locateFile: (file) => `https://cdn.jsdelivr.net/npm/sql.js@1.12.0/dist/${file}`,
    });
    const resp = await fetch(DB_URL);
    if (!resp.ok) throw new Error(`could not load ${DB_URL} (${resp.status})`);
    originalBytes = new Uint8Array(await resp.arrayBuffer());
    db = new SQL.Database(originalBytes);
    window.sm64db = () => db; // shared with map.js

    buildExamples();
    buildSchema();
    wireEvents();

    // Start with the first example so the page is alive on load.
    els.sql.value = window.SM64_EXAMPLES[0].sql;
    runQuery();
  } catch (err) {
    els.loading.querySelector("p").textContent = "Failed to load: " + err.message;
    console.error(err);
    return;
  }
  els.loading.classList.add("hidden");
}

// --- query execution -------------------------------------------------------

function runQuery() {
  const sql = els.sql.value.trim();
  if (!sql) return;
  const t0 = performance.now();
  let resultSets;
  try {
    resultSets = db.exec(sql);
  } catch (err) {
    showError(err.message);
    return;
  }
  const ms = (performance.now() - t0).toFixed(1);
  renderResults(resultSets, ms);
}

// Visual tabs call this to hand a JOIN to the Query tab and run it, so every
// chart cell is backed by SQL the user can see and edit.
function showQueryWith(sql) {
  els.sql.value = sql;
  document
    .querySelectorAll(".tab")
    .forEach((t) => t.classList.toggle("active", t.dataset.tab === "query"));
  document
    .querySelectorAll(".panel")
    .forEach((p) => p.classList.toggle("active", p.id === "tab-query"));
  runQuery();
  els.sql.scrollTop = 0;
}
window.sm64RunInQuery = showQueryWith;

function showError(message) {
  els.status.textContent = "";
  els.results.innerHTML = "";
  const box = document.createElement("div");
  box.className = "error";
  box.textContent = "✗ " + message;
  els.results.appendChild(box);
}

function renderResults(resultSets, ms) {
  els.results.innerHTML = "";

  if (!resultSets || resultSets.length === 0) {
    els.status.textContent = `✓ ran in ${ms} ms — no rows returned`;
    const ok = document.createElement("div");
    ok.className = "note";
    ok.textContent = "Statement executed. (No result set — e.g. a non-SELECT.)";
    els.results.appendChild(ok);
    return;
  }

  // Render each result set (a query may contain several statements).
  let totalRows = 0;
  resultSets.forEach((rs) => {
    totalRows += rs.values.length;
    els.results.appendChild(buildTable(rs));
  });
  els.status.textContent = `✓ ${totalRows} row${totalRows === 1 ? "" : "s"} in ${ms} ms`;
}

function buildTable(rs) {
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";

  const rows = rs.values;
  const shown = rows.slice(0, MAX_DISPLAY_ROWS);

  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const htr = document.createElement("tr");
  rs.columns.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = c;
    htr.appendChild(th);
  });
  thead.appendChild(htr);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  shown.forEach((row) => {
    const tr = document.createElement("tr");
    row.forEach((val) => {
      const td = document.createElement("td");
      if (val === null) {
        td.innerHTML = '<span class="null">NULL</span>';
      } else {
        td.textContent = String(val);
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);

  if (rows.length > MAX_DISPLAY_ROWS) {
    const more = document.createElement("div");
    more.className = "note";
    more.textContent = `Showing first ${MAX_DISPLAY_ROWS} of ${rows.length} rows.`;
    wrap.appendChild(more);
  }
  return wrap;
}

// --- sidebar: examples -----------------------------------------------------

function buildExamples() {
  window.SM64_EXAMPLES.forEach((ex) => {
    const btn = document.createElement("button");
    btn.className = "example";
    btn.textContent = ex.title;
    btn.addEventListener("click", () => {
      els.sql.value = ex.sql;
      runQuery();
      els.sql.scrollTop = 0;
    });
    els.examples.appendChild(btn);
  });
}

// --- sidebar: schema -------------------------------------------------------

function buildSchema() {
  const meta = db.exec(
    "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name"
  );
  if (!meta.length) return;
  const entries = meta[0].values; // [name, type]
  const tables = entries.filter((e) => e[1] === "table");
  const views = entries.filter((e) => e[1] === "view");
  els.schemaCount.textContent = `(${tables.length} tables, ${views.length} views)`;

  const addGroup = (label, list) => {
    if (!list.length) return;
    const h = document.createElement("div");
    h.className = "schema-group";
    h.textContent = label;
    els.schema.appendChild(h);
    list.forEach(([name]) => els.schema.appendChild(schemaItem(name)));
  };
  addGroup("Tables", tables);
  addGroup("Views", views);
}

function schemaItem(name) {
  const details = document.createElement("details");
  const summary = document.createElement("summary");

  const nameBtn = document.createElement("span");
  nameBtn.className = "schema-name";
  nameBtn.textContent = name;
  // Clicking the name previews the table.
  nameBtn.addEventListener("click", (e) => {
    e.preventDefault();
    els.sql.value = `SELECT * FROM ${name} LIMIT 20;`;
    runQuery();
  });
  summary.appendChild(nameBtn);
  details.appendChild(summary);

  const cols = db.exec(`PRAGMA table_info(${name})`);
  const list = document.createElement("ul");
  list.className = "cols";
  if (cols.length) {
    cols[0].values.forEach((c) => {
      const li = document.createElement("li");
      const cname = c[1];
      const ctype = c[2] || "";
      li.innerHTML = `<span class="col">${cname}</span> <span class="ctype">${ctype}</span>`;
      list.appendChild(li);
    });
  }
  details.appendChild(list);
  return details;
}

// --- events & tabs ---------------------------------------------------------

function wireEvents() {
  els.run.addEventListener("click", runQuery);
  els.reset.addEventListener("click", () => {
    db = new (db.constructor)(originalBytes);
    els.status.textContent = "↻ database reloaded";
  });
  els.sql.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      runQuery();
    }
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      $("#tab-" + tab.dataset.tab).classList.add("active");
      // Visual tabs need the panel visible to measure themselves, so they
      // render on show rather than on load.
      const mods = { map: "SM64Map", heatmap: "SM64Heatmap", treemap: "SM64Treemap" };
      const mod = window[mods[tab.dataset.tab]];
      if (mod) mod.onShow();
    });
  });
}

boot();
