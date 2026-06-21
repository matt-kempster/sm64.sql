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

// Pan/zoom view transform, applied to the content group on top of the auto-fit.
// Pan translates; wheel zooms about the cursor; double-click (or a new
// level/area/plane) resets it. Identity == the fitted view.
const view = { k: 1, tx: 0, ty: 0 };
const viewTransform = () => `translate(${view.tx} ${view.ty}) scale(${view.k})`;
function resetView() {
  view.k = 1;
  view.tx = 0;
  view.ty = 0;
}

const m = {
  level: () => document.getElementById("map-level"),
  area: () => document.getElementById("map-area"),
  plane: () => document.getElementById("map-plane"),
  bg: () => document.getElementById("map-bg"),
  bgLabel: () => document.getElementById("map-bg-label"),
  cam: () => document.getElementById("map-cam"),
  camLabel: () => document.getElementById("map-cam-label"),
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

const CAM_SQL = `
  SELECT area, event, center_x, center_y, center_z,
         bounds_x, bounds_y, bounds_z, bounds_yaw, doc, file, line
  FROM camera_trigger WHERE level = $lvl AND bounds_x > 0`;

// Camera-trigger zones for a level, or [] if the table is absent (e.g. an older
// database). Wrapped so the Map tab still works against a db without it.
function queryCamTriggers(level) {
  try {
    const stmt = currentDb().prepare(CAM_SQL);
    stmt.bind({ $lvl: level });
    const rows = [];
    while (stmt.step()) rows.push(stmt.getAsObject());
    stmt.free();
    return rows;
  } catch (e) {
    return [];
  }
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

// Which world axes / half-extents a camera box projects onto in each plane, and
// the yaw to apply. bounds_yaw rotates the box about the vertical (Y) axis, so
// it only orients the box in the top-down x/z view; the height views draw the
// axis-aligned silhouette.
function camFields(t, plane) {
  if (plane.h === "x" && plane.v === "z")
    return { hc: t.center_x, vc: t.center_z, hh: t.bounds_x, vh: t.bounds_z, yaw: t.bounds_yaw };
  if (plane.h === "x" && plane.v === "y")
    return { hc: t.center_x, vc: t.center_y, hh: t.bounds_x, vh: t.bounds_y, yaw: 0 };
  return { hc: t.center_z, vc: t.center_y, hh: t.bounds_z, vh: t.bounds_y, yaw: 0 };
}

function drawCamZones(svg, triggers, plane, sx, sy, scale) {
  const tip = m.tip();
  triggers.forEach((t) => {
    const f = camFields(t, plane);
    if (!(f.hh > 0 && f.vh > 0)) return; // degenerate in this projection
    const cxs = sx(f.hc);
    const cys = sy(f.vc);
    const w = f.hh * 2 * scale;
    const h = f.vh * 2 * scale;

    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "cam-zone-g");
    const deg = (f.yaw / 65536) * 360; // s16 angle: 0x10000 == 360 degrees
    if (deg)
      g.setAttribute(
        "transform",
        `rotate(${deg.toFixed(2)} ${cxs.toFixed(1)} ${cys.toFixed(1)})`
      );

    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", (cxs - w / 2).toFixed(1));
    rect.setAttribute("y", (cys - h / 2).toFixed(1));
    rect.setAttribute("width", w.toFixed(1));
    rect.setAttribute("height", h.toFixed(1));
    rect.setAttribute("class", "cam-zone");
    rect.setAttribute("vector-effect", "non-scaling-stroke");
    g.appendChild(rect);

    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", cxs.toFixed(1));
    label.setAttribute("y", cys.toFixed(1));
    label.setAttribute("class", "cam-zone-label");
    label.textContent = t.event.replace(/^cam_/, "");
    g.appendChild(label);

    g.addEventListener("mouseenter", (e) => {
      tip.innerHTML =
        `<strong>${t.event}</strong><br>` +
        `<span class="muted">camera zone</span> · area ${t.area}` +
        (t.doc ? `<br>${t.doc}` : "") +
        `<br>center ${t.center_x}, ${t.center_y}, ${t.center_z}` +
        `<br>bounds ±${t.bounds_x}, ±${t.bounds_y}, ±${t.bounds_z}` +
        (t.bounds_yaw ? ` · yaw ${t.bounds_yaw}` : "");
      tip.style.display = "block";
      const r = m.stage().getBoundingClientRect();
      tip.style.left = e.clientX - r.left + 12 + "px";
      tip.style.top = e.clientY - r.top + 12 + "px";
    });
    g.addEventListener("mouseleave", () => (tip.style.display = "none"));
    svg.appendChild(g);
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

  // Camera-trigger zones for this level, filtered to the selected area (an area
  // of -1 is a whole-level default that applies to every area).
  const camTriggers = queryCamTriggers(level).filter(
    (t) => areaSel === "all" || String(t.area) === areaSel || t.area === -1
  );
  m.cam().disabled = !camTriggers.length;
  m.camLabel().classList.toggle("disabled", !camTriggers.length);
  const showCam = camTriggers.length > 0 && m.cam().checked;

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

  // Everything is drawn into one group so pan/zoom is just a transform on it.
  const content = document.createElementNS(SVG_NS, "g");
  content.setAttribute("id", "map-view");
  content.setAttribute("transform", viewTransform());
  svg.appendChild(content);

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
    content.appendChild(img);
  }

  // Camera zones sit above the level image but below the object dots.
  if (showCam) {
    drawCamZones(content, camTriggers, plane, sx, sy, scale);
    const n = camTriggers.length;
    m.status().textContent += ` · ${n} camera zone${n === 1 ? "" : "s"}`;
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
    c.setAttribute("vector-effect", "non-scaling-stroke");
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
    content.appendChild(c);
  });
}

// Pan (drag), zoom (wheel, anchored at the cursor) and reset (double-click) on
// the map SVG, all by transforming the #map-view content group in place — no
// re-query, no re-layout. Dot/box outlines use non-scaling-stroke so they stay
// crisp at any zoom.
function setupPanZoom(svg) {
  const apply = () => {
    const g = document.getElementById("map-view");
    if (g) g.setAttribute("transform", viewTransform());
  };
  const at = (e) => {
    const r = svg.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };

  svg.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const p = at(e);
      const f = Math.exp(-e.deltaY * 0.0015); // scroll up -> zoom in
      const k = Math.min(40, Math.max(0.25, view.k * f));
      const ff = k / view.k;
      view.tx = p.x - ff * (p.x - view.tx);
      view.ty = p.y - ff * (p.y - view.ty);
      view.k = k;
      apply();
    },
    { passive: false }
  );

  let panning = false,
    lastX = 0,
    lastY = 0;
  svg.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    panning = true;
    lastX = e.clientX;
    lastY = e.clientY;
    m.tip().style.display = "none";
    svg.classList.add("panning");
    try {
      svg.setPointerCapture(e.pointerId);
    } catch (_) {}
  });
  svg.addEventListener("pointermove", (e) => {
    if (!panning) return;
    view.tx += e.clientX - lastX;
    view.ty += e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    apply();
  });
  const end = (e) => {
    if (!panning) return;
    panning = false;
    svg.classList.remove("panning");
    try {
      svg.releasePointerCapture(e.pointerId);
    } catch (_) {}
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);

  svg.addEventListener("dblclick", (e) => {
    e.preventDefault();
    resetView();
    apply();
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
  // Changing what's shown re-fits the view, so drop any pan/zoom first; toggling
  // camera zones doesn't change the extent, so it keeps the current view.
  const refit = () => {
    resetView();
    render();
  };
  select.addEventListener("change", () => {
    populateAreas(select.value);
    refit();
  });
  m.area().addEventListener("change", refit);
  m.plane().addEventListener("change", refit);
  m.bg().addEventListener("change", refit);
  m.cam().addEventListener("change", render);

  setupPanZoom(m.svg());

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
