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
// Which two world axes map to the horizontal/vertical screen axes. The vertical
// axis is always drawn pointing up, so y (height) reads naturally.
const PLANES = {
  xz: { h: "x", v: "z" },
  xy: { h: "x", v: "y" },
  zy: { h: "z", v: "y" },
};
const PAD = 28;

const POINTS_SQL = `
  SELECT 'object' AS kind, area, initial_x AS x, initial_y AS y, initial_z AS z,
         behavior AS label, model_name AS model
  FROM object WHERE level = $lvl
  UNION ALL
  SELECT 'macro', mo.area, mo.pos_x, mo.pos_y, mo.pos_z,
         COALESCE(mp.behavior, mo.macro_name), mp.model_name
  FROM macro_object mo
  LEFT JOIN macro_preset mp ON mp.macro_name = mo.macro_name
  WHERE mo.level = $lvl
  UNION ALL
  SELECT 'special', so.area, so.pos_x, so.pos_y, so.pos_z,
         COALESCE(sp.behavior, so.preset_name), sp.model_name
  FROM special_object so
  LEFT JOIN special_preset sp ON sp.preset_id = so.preset_id
  WHERE so.level = $lvl`;

let initialised = false;
const hidden = new Set(); // kinds toggled off via the legend

const m = {
  level: () => document.getElementById("map-level"),
  area: () => document.getElementById("map-area"),
  plane: () => document.getElementById("map-plane"),
  bg: () => document.getElementById("map-bg"),
  bgLabel: () => document.getElementById("map-bg-label"),
  legend: () => document.getElementById("map-legend"),
  status: () => document.getElementById("map-status"),
  stage: () => document.getElementById("map-stage"),
  svg: () => document.getElementById("map-svg"),
  tip: () => document.getElementById("map-tooltip"),
  axes: () => document.getElementById("map-axes"),
};

function currentDb() {
  return window.sm64db();
}

function queryLevels() {
  const r = currentDb().exec(
    `SELECT level FROM object
     UNION SELECT level FROM macro_object
     UNION SELECT level FROM special_object
     ORDER BY level`
  );
  return r.length ? r[0].values.map((v) => v[0]) : [];
}

function queryAreas(level) {
  const r = currentDb().exec(
    `SELECT DISTINCT area FROM (
       SELECT area FROM object WHERE level = $lvl
       UNION SELECT area FROM macro_object WHERE level = $lvl
       UNION SELECT area FROM special_object WHERE level = $lvl
     ) ORDER BY area`,
    { $lvl: level }
  );
  return r.length ? r[0].values.map((v) => v[0]) : [];
}

// Rebuild the Area dropdown for a level: "All areas" plus one entry per area.
// Defaults to the lowest area so a level map shows straight away.
function populateAreas(level) {
  const sel = m.area();
  sel.innerHTML = "";
  const all = document.createElement("option");
  all.value = "all";
  all.textContent = "All areas";
  sel.appendChild(all);
  const areas = queryAreas(level);
  areas.forEach((a) => {
    const opt = document.createElement("option");
    opt.value = String(a);
    opt.textContent = "Area " + a;
    sel.appendChild(opt);
  });
  sel.value = areas.length ? String(areas[0]) : "all";
}

function queryPoints(level) {
  const stmt = currentDb().prepare(POINTS_SQL);
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

  // The selected area filters the placements; "all" overlays every area (and
  // gets no background, since each area has its own coordinate system).
  const areaSel = m.area().value || "all";
  const all = queryPoints(level).filter(
    (p) => areaSel === "all" || String(p.area) === areaSel
  );

  const counts = {};
  all.forEach((p) => (counts[p.kind] = (counts[p.kind] || 0) + 1));
  buildLegend(counts);

  const plane = PLANES[m.plane().value] || PLANES.xz;

  // A level-map background exists only for the top-down (x/z) plane, for a
  // single selected area, and only where STROOP shipped an image for it.
  const maps = window.SM64_MAPS || {};
  const mapInfo =
    plane.h === "x" && plane.v === "z" && areaSel !== "all" && maps[level]
      ? maps[level][areaSel]
      : null;
  m.bg().disabled = !mapInfo;
  m.bgLabel().classList.toggle("disabled", !mapInfo);
  const useBg = !!mapInfo && m.bg().checked;

  // The height axis (y) reads naturally pointing up; the top-down z axis is
  // drawn north-up (+z downward) to match the level-map images.
  const flipV = plane.v === "y";
  m.axes().textContent =
    plane.v === "y"
      ? `${plane.h} (horizontal) × y (height, ↑).`
      : `${plane.h} (horizontal) × z (vertical) — north up.`;

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

  // World extent of the view: the map image's world rectangle when shown (so
  // image and points share one transform), else the bounding box of the
  // points (auto-fit, as before).
  let minH, maxH, minV, maxV;
  if (useBg) {
    minH = mapInfo.x1;
    maxH = mapInfo.x2;
    minV = mapInfo.z1;
    maxV = mapInfo.z2;
  } else {
    if (!pts.length) return;
    const hs = pts.map((p) => p[plane.h]);
    const vs = pts.map((p) => p[plane.v]);
    minH = Math.min(...hs);
    maxH = Math.max(...hs);
    minV = Math.min(...vs);
    maxV = Math.max(...vs);
  }
  const rangeH = maxH - minH || 1;
  const rangeV = maxV - minV || 1;
  // Equal scale on both axes so the layout is not distorted.
  const scale = Math.min((W - 2 * PAD) / rangeH, (H - 2 * PAD) / rangeV);
  const offH = (W - rangeH * scale) / 2;
  const offV = (H - rangeV * scale) / 2;
  const sx = (h) => offH + (h - minH) * scale;
  const sy = (v) => (flipV ? offV + (maxV - v) * scale : offV + (v - minV) * scale);

  // The map image fills its world rectangle exactly (corners map to coords, so
  // preserveAspectRatio="none"); it is drawn first so points sit on top.
  if (useBg) {
    const img = document.createElementNS(SVG_NS, "image");
    img.setAttributeNS(null, "href", mapInfo.img);
    img.setAttribute("x", offH.toFixed(1));
    img.setAttribute("y", offV.toFixed(1));
    img.setAttribute("width", (rangeH * scale).toFixed(1));
    img.setAttribute("height", (rangeV * scale).toFixed(1));
    img.setAttribute("preserveAspectRatio", "none");
    img.setAttribute("opacity", "0.9");
    svg.appendChild(img);
  }

  if (!pts.length) return;

  const colorOf = {};
  KINDS.forEach((k) => (colorOf[k.key] = k.color));

  const tip = m.tip();
  pts.forEach((p) => {
    const c = document.createElementNS(SVG_NS, "circle");
    c.setAttribute("cx", sx(p[plane.h]).toFixed(1));
    c.setAttribute("cy", sy(p[plane.v]).toFixed(1));
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
  populateAreas(select.value);
  select.addEventListener("change", () => {
    populateAreas(select.value);
    render();
  });
  m.area().addEventListener("change", render);
  m.plane().addEventListener("change", render);
  m.bg().addEventListener("change", render);

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
