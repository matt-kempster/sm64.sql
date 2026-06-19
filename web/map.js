"use strict";

// ---------------------------------------------------------------------------
// Map tab: a top-down (x/z) scatter of every placed object in a level, drawn
// straight from the database. Three placement tables are unioned, colored by
// source. Lazily initialised the first time the tab is shown, because an SVG in
// a hidden panel has no measurable size.
// ---------------------------------------------------------------------------

const SVG_NS = "http://www.w3.org/2000/svg";
const KINDS = [
  { key: "object", label: "object", color: "#e4000f" },
  { key: "macro", label: "macro", color: "#0a64c8" },
  { key: "special", label: "special", color: "#1aa64b" },
];
const PAD = 28;

const POINTS_SQL = `
  SELECT 'object' AS kind, initial_x AS x, initial_y AS y, initial_z AS z,
         behavior AS label, model_name AS model
  FROM object WHERE level = $lvl
  UNION ALL
  SELECT 'macro', mo.pos_x, mo.pos_y, mo.pos_z,
         COALESCE(mp.behavior, mo.macro_name), mp.model_name
  FROM macro_object mo
  LEFT JOIN macro_preset mp ON mp.macro_name = mo.macro_name
  WHERE mo.level = $lvl
  UNION ALL
  SELECT 'special', so.pos_x, so.pos_y, so.pos_z,
         COALESCE(sp.behavior, so.preset_name), sp.model_name
  FROM special_object so
  LEFT JOIN special_preset sp ON sp.preset_id = so.preset_id
  WHERE so.level = $lvl`;

let initialised = false;
const hidden = new Set(); // kinds toggled off via the legend

const m = {
  level: () => document.getElementById("map-level"),
  legend: () => document.getElementById("map-legend"),
  status: () => document.getElementById("map-status"),
  stage: () => document.getElementById("map-stage"),
  svg: () => document.getElementById("map-svg"),
  tip: () => document.getElementById("map-tooltip"),
};

function db() {
  return window.sm64db();
}

function queryLevels() {
  const r = db().exec(
    `SELECT level FROM object
     UNION SELECT level FROM macro_object
     UNION SELECT level FROM special_object
     ORDER BY level`
  );
  return r.length ? r[0].values.map((v) => v[0]) : [];
}

function queryPoints(level) {
  const stmt = db().prepare(POINTS_SQL);
  stmt.bind({ $lvl: level });
  const pts = [];
  while (stmt.step()) pts.push(stmt.getAsObject());
  stmt.free();
  return pts;
}

function buildLegend(counts) {
  const legend = m.legend();
  legend.innerHTML = "";
  KINDS.forEach((k) => {
    const item = document.createElement("button");
    item.className = "legend-item" + (hidden.has(k.key) ? " off" : "");
    item.innerHTML =
      `<span class="swatch" style="background:${k.color}"></span>` +
      `${k.label} <span class="muted">${counts[k.key] || 0}</span>`;
    item.addEventListener("click", () => {
      if (hidden.has(k.key)) hidden.delete(k.key);
      else hidden.add(k.key);
      render(); // cheap; re-reads the current dropdown selection
    });
    legend.appendChild(item);
  });
}

function render() {
  const level = m.level().value;
  if (!level) return;
  const all = queryPoints(level);

  const counts = {};
  all.forEach((p) => (counts[p.kind] = (counts[p.kind] || 0) + 1));
  buildLegend(counts);

  const pts = all.filter((p) => !hidden.has(p.kind));
  const svg = m.svg();
  const stage = m.stage();
  const W = stage.clientWidth;
  const H = stage.clientHeight;
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  m.status().textContent = `${pts.length} shown of ${all.length} placements`;
  if (!pts.length) return;

  const xs = pts.map((p) => p.x);
  const zs = pts.map((p) => p.z);
  const minX = Math.min(...xs),
    maxX = Math.max(...xs);
  const minZ = Math.min(...zs),
    maxZ = Math.max(...zs);
  const rangeX = maxX - minX || 1;
  const rangeZ = maxZ - minZ || 1;
  // Equal scale on both axes so the layout is not distorted.
  const scale = Math.min((W - 2 * PAD) / rangeX, (H - 2 * PAD) / rangeZ);
  const offX = (W - rangeX * scale) / 2;
  const offZ = (H - rangeZ * scale) / 2;
  const sx = (x) => offX + (x - minX) * scale;
  const sy = (z) => offZ + (z - minZ) * scale;

  const colorOf = {};
  KINDS.forEach((k) => (colorOf[k.key] = k.color));

  const tip = m.tip();
  pts.forEach((p) => {
    const c = document.createElementNS(SVG_NS, "circle");
    c.setAttribute("cx", sx(p.x).toFixed(1));
    c.setAttribute("cy", sy(p.z).toFixed(1));
    c.setAttribute("r", "4.5");
    c.setAttribute("fill", colorOf[p.kind]);
    c.setAttribute("fill-opacity", "0.85");
    c.setAttribute("stroke", "#fff");
    c.setAttribute("stroke-width", "1");
    c.addEventListener("mouseenter", (e) => {
      tip.innerHTML =
        `<strong>${p.label || "(unnamed)"}</strong><br>` +
        `<span class="muted">${p.kind}</span>` +
        (p.model ? ` · ${p.model}` : "") +
        `<br>x ${p.x}, y ${p.y}, z ${p.z}`;
      tip.style.display = "block";
      const r = m.stage().getBoundingClientRect();
      tip.style.left = e.clientX - r.left + 12 + "px";
      tip.style.top = e.clientY - r.top + 12 + "px";
    });
    c.addEventListener("mouseleave", () => (tip.style.display = "none"));
    svg.appendChild(c);
  });
}

function ensureInit() {
  if (initialised) return;
  initialised = true;
  const select = m.level();
  const levels = queryLevels();
  levels.forEach((lv) => {
    const opt = document.createElement("option");
    opt.value = lv;
    opt.textContent = lv;
    select.appendChild(opt);
  });
  if (levels.includes("bob")) select.value = "bob";
  select.addEventListener("change", render);

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (document.getElementById("tab-map").classList.contains("active")) render();
    }, 150);
  });
}

window.SM64Map = {
  onShow() {
    ensureInit();
    render();
  },
};
