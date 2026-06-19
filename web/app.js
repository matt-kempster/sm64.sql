"use strict";

// ---------------------------------------------------------------------------
// sm64.sql web playground. The database is loaded once into WebAssembly SQLite
// (sql.js) and lives entirely in this page; queries run locally.
// ---------------------------------------------------------------------------

const DB_URL = "sm64.db";
const MAX_DISPLAY_ROWS = 1000;

let db = null; // active sql.js Database
let originalBytes = null; // pristine copy, for "Reload data"
let editor = null; // CodeMirror instance, or null if the CDN failed to load

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
    initEditor();

    // Start with the first example so the page is alive on load.
    setSql(window.SM64_EXAMPLES[0].sql);
    runQuery();
  } catch (err) {
    els.loading.querySelector("p").textContent = "Failed to load: " + err.message;
    console.error(err);
    return;
  }
  els.loading.classList.add("hidden");
}

// --- editor (CodeMirror, with a plain-textarea fallback) -------------------

function getSql() {
  return editor ? editor.getValue() : els.sql.value;
}

function setSql(text) {
  if (editor) editor.setValue(text);
  else els.sql.value = text;
}

// The { table: [columns] } map sql-hint uses for autocomplete, covering every
// table AND view in the database — the same source as the schema sidebar.
function buildHintTables() {
  const tables = {};
  const meta = db.exec(
    "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
  );
  if (!meta.length) return tables;
  meta[0].values.forEach(([name]) => {
    const cols = db.exec(`PRAGMA table_info(${name})`);
    tables[name] = cols.length ? cols[0].values.map((c) => c[1]) : [];
  });
  return tables;
}

function initEditor() {
  if (typeof CodeMirror === "undefined") return; // CDN blocked -> plain textarea
  editor = CodeMirror.fromTextArea(els.sql, {
    mode: "text/x-sql",
    lineNumbers: true,
    lineWrapping: true,
    smartIndent: false,
    extraKeys: {
      "Ctrl-Enter": runQuery,
      "Cmd-Enter": runQuery,
      "Ctrl-Space": "autocomplete",
    },
    hintOptions: { tables: buildHintTables(), completeSingle: false },
  });
  // Pop completions while typing an identifier (not on spaces/punctuation).
  editor.on("inputRead", (cm, change) => {
    if (
      !cm.state.completionActive &&
      change.text.length === 1 &&
      /[\w.]$/.test(change.text[0])
    ) {
      cm.showHint({ hint: CodeMirror.hint.sql, completeSingle: false });
    }
  });
}

// --- query execution -------------------------------------------------------

function runQuery() {
  const sql = getSql().trim();
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

// Visual tabs call this to copy the JOIN behind a chart element to the
// clipboard, so the user can paste it into the Query tab (or anywhere).
let toastTimer = null;
function toast(message) {
  let t = document.getElementById("toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    t.className = "toast";
    document.body.appendChild(t);
  }
  t.textContent = message;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 1600);
}

async function copyQuery(sql) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(sql);
    } else {
      // Fallback for non-secure contexts (e.g. file://).
      const ta = document.createElement("textarea");
      ta.value = sql;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    toast("✓ Query copied to clipboard");
  } catch (err) {
    console.error(err);
    toast("Copy failed — see console");
  }
}
window.sm64CopyQuery = copyQuery;

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
      setSql(ex.sql);
      runQuery();
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
    setSql(`SELECT * FROM ${name} LIMIT 20;`);
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
  // Fallback Ctrl/Cmd+Enter for the plain textarea (when CodeMirror is active
  // the textarea is hidden and the shortcut is handled via extraKeys instead).
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
