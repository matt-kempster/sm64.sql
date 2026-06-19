"use strict";

// ---------------------------------------------------------------------------
// Treemap tab: a nested treemap showing all three tiers at once, where every
// placement of an object counts, drawn from all three placement tables
// (object + macro_object + special_object), each resolved to a behavior so they
// share the object-list grouping. The three tiers are level, object-list TYPE
// and behavior (object); a toggle flips the nesting order between
//   level ▸ type ▸ object   (levels broken into their object types)
//   type ▸ object ▸ level   (each object's spread across levels)
//
// Colour is always by TYPE (object list): each obj_list gets a stable hue, so
// tiles sharing a type share a colour and nothing reshuffles when you zoom.
// Leaves are vivid, the type frame a soft tint, an object frame a stronger
// tint, a (mixed) level frame neutral. Parents get a taller top band for their
// label and a thin frame on the other three sides. Clicking a region zooms in
// with an animation; the breadcrumb zooms back out; a leaf copies its query.
//
// Navigation is a `path` of plain DATA nodes; each draw builds a FRESH d3
// hierarchy rooted at the focused data (depth 0). d3.treemap indexes padding by
// absolute node.depth, so it must be handed a depth-0 root.
// ---------------------------------------------------------------------------

(function () {
  const el = (id) => document.getElementById(id);
  const sdb = () => window.sm64db();
  let inited = false;
  let rawRows = null; // cached SQL rows: [level, behavior, obj_list, count]
  let treeRootData = null;
  let path = [];

  // The two nesting orders. `order` lists the dimensions outer→inner (the last
  // is the leaf); `root` is the breadcrumb label; `color` is the cross-cutting
  // dimension the palette tracks -- always the manageable dimension that is NOT
  // the outermost grouping, so colour adds information instead of repeating the
  // spatial split: types across levels, or levels across objects.
  const MODES = {
    lto: { order: ["level", "type", "object"], root: "all levels", color: "type" },
    tol: { order: ["type", "object", "level"], root: "all types", color: "level" },
  };
  let mode = "lto";
  let colorDim = "type"; // set from the active mode on each rebuild

  const strip = (s) => String(s).replace(/^bhv/, "");
  const catLabel = (c) => (c ? c.replace(/^OBJ_LIST_/, "").toLowerCase() : "(none)");
  const escapeHtml = (s) =>
    String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const sqlStr = (s) => String(s).replace(/'/g, "''");

  // One cheerful hue per object-list type (12 covers the 11 lists + the empty
  // bucket). Levels (31 of them) get a generated spread of distinct hues. Both
  // domains are seeded once from sorted values, so a given type/level always
  // maps to the same colour, in or out of any zoom. `colorOf` picks the scale
  // for the active mode's cross-cutting dimension.
  const PALETTE = [
    "#ff8787", "#ffa94d", "#ffd43b", "#a9e34b", "#69db7c", "#38d9a9",
    "#3bc9db", "#4dabf7", "#748ffc", "#9775fa", "#da77f2", "#f783ac",
  ];
  const colorScales = {
    type: d3.scaleOrdinal(PALETTE),
    level: d3.scaleOrdinal(),
  };
  const colorOf = (key) => colorScales[colorDim](key);
  const tint = (hex, t) => d3.interpolateRgb(hex, "#ffffff")(t);
  // Neutral frames. When both frames are neutral (level-coloured mode) the
  // inner one is a touch darker so the nesting still reads.
  const OUTER_FRAME = "#e7eaf1";
  const INNER_FRAME = "#d6dbe8";

  function textOn(bg) {
    const c = d3.color(bg).rgb();
    const lum = (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255;
    return lum > 0.62 ? "#1d2330" : "#ffffff";
  }

  // Absolute tier of a node: level=1, object list=2, behavior(leaf)=3.
  const absDepth = (node) => path.length - 1 + node.depth;

  // Top band reserved for a parent's label. The other three sides get a much
  // thinner frame (SIDE_PAD) so most of the area goes to the children.
  const SIDE_PAD = 5;
  function topPad(node) {
    if (!node.children) return 0;
    const ad = absDepth(node);
    if (ad === 1) return 20; // level
    if (ad === 2) return 15; // object list
    return SIDE_PAD; // focus container (no label)
  }

  // Fill by the active cross-cutting dimension: every tile carries its colour
  // key in `ckey` (the value of that dimension, or "" for a frame spanning
  // several). A leaf is vivid; the frame that IS the colour dimension gets a
  // soft tint of its hue; any other frame is neutral (inner ones darker).
  function fillFor(node) {
    const key = node.data.ckey || "";
    if (!node.children) return colorOf(key);
    if (node.data.dim === colorDim) return tint(colorOf(key), 0.62);
    return absDepth(node) >= 2 ? INNER_FRAME : OUTER_FRAME;
  }

  // Label a data node by its dimension, not its depth, so both orders read
  // right: types lose their OBJ_LIST_ prefix, behaviors their bhv prefix,
  // levels show as-is.
  function dataLabel(data) {
    if (data.dim === "type") return catLabel(data.name);
    if (data.dim === "object") return strip(data.name);
    return data.name; // level (or the synthetic root)
  }
  const nodeLabel = (node) => dataLabel(node.data);

  // The value of a given dimension for a leaf, looked up across the live
  // hierarchy (ancestors include the node itself) and then the zoom path above
  // the current focus -- so it works whichever tier we have zoomed to.
  function fieldFor(d, dim) {
    for (const a of d.ancestors()) if (a.data.dim === dim) return a.data.name;
    for (const p of path.slice(0, -1)) if (p.dim === dim) return p.name;
    return "";
  }

  // Every placement, one row per (level, behavior): objects carry their
  // behavior directly; macro/special objects resolve it through their preset
  // table; obj_list (the type) comes from the behavior table. These raw rows
  // feed either nesting order.
  function loadRows() {
    const r = sdb().exec(
      `WITH placements AS (
         SELECT o.level AS level, o.behavior AS behavior FROM object o
         UNION ALL
         SELECT m.level, mp.behavior
           FROM macro_object m JOIN macro_preset mp ON m.macro_name = mp.macro_name
         UNION ALL
         SELECT s.level, sp.behavior
           FROM special_object s JOIN special_preset sp ON s.preset_name = sp.preset_name
       )
       SELECT p.level, p.behavior, COALESCE(b.obj_list, '') AS olist, COUNT(*) c
       FROM placements p LEFT JOIN behavior b ON p.behavior = b.behavior_name
       GROUP BY p.level, p.behavior`
    );
    const rows = (r.length ? r[0].values : []).map(([level, beh, olist, c]) => ({
      level: level || "",
      object: beh || "",
      type: olist || "",
      count: c,
    }));
    const types = Array.from(new Set(rows.map((row) => row.type))).sort();
    const levels = Array.from(new Set(rows.map((row) => row.level))).sort();
    return { rows, types, levels };
  }

  // The value of dimension `dim` shared by a set of rows, or "" when they span
  // several -- the latter marks a frame the colour dimension doesn't pin down,
  // so it is drawn neutral.
  function sharedField(rows, dim) {
    let v = null;
    for (const row of rows) {
      if (v === null) v = row[dim];
      else if (v !== row[dim]) return "";
    }
    return v || "";
  }

  // Group the rows into a 3-tier tree following `order` (outer→inner, last is
  // the leaf). Each node records its `dim` (for labels), its `ckey` (the value
  // of the colour dimension `cdim`, "" if mixed) and -- for leaves -- the
  // placement count as `value`.
  function buildTree(order, cdim) {
    const [d0, d1, d2] = order;
    const m0 = new Map();
    rawRows.forEach((row) => {
      if (!m0.has(row[d0])) m0.set(row[d0], new Map());
      const m1 = m0.get(row[d0]);
      if (!m1.has(row[d1])) m1.set(row[d1], []);
      m1.get(row[d1]).push(row);
    });
    return Array.from(m0, ([k0, m1]) => ({
      name: k0,
      dim: d0,
      ckey: sharedField(Array.from(m1.values()).flat(), cdim),
      children: Array.from(m1, ([k1, rows]) => ({
        name: k1,
        dim: d1,
        ckey: sharedField(rows, cdim),
        children: rows.map((row) => ({
          name: row[d2],
          dim: d2,
          ckey: row[cdim],
          value: row.count,
        })),
      })),
    }));
  }

  function leafQuery(level, beh) {
    const L = sqlStr(level);
    const B = sqlStr(beh);
    return `-- ${strip(beh)} placed in ${level} (object + macro + special)
SELECT 'object' AS source, level, initial_x AS x, initial_y AS y, initial_z AS z, behavior
FROM object WHERE level = '${L}' AND behavior = '${B}'
UNION ALL
SELECT 'macro', m.level, m.pos_x, m.pos_y, m.pos_z, mp.behavior
FROM macro_object m JOIN macro_preset mp ON m.macro_name = mp.macro_name
WHERE m.level = '${L}' AND mp.behavior = '${B}'
UNION ALL
SELECT 'special', s.level, s.pos_x, s.pos_y, s.pos_z, sp.behavior
FROM special_object s JOIN special_preset sp ON s.preset_name = sp.preset_name
WHERE s.level = '${L}' AND sp.behavior = '${B}';`;
  }

  function crumbLabel(node, i) {
    return i === 0 ? MODES[mode].root : dataLabel(node);
  }

  function buildBreadcrumb() {
    const bc = el("tm-breadcrumb");
    bc.innerHTML = "";
    path.forEach((node, i) => {
      if (i) {
        const sep = document.createElement("span");
        sep.className = "tm-sep";
        sep.textContent = "▸";
        bc.appendChild(sep);
      }
      const last = i === path.length - 1;
      const crumb = document.createElement("button");
      crumb.className = "tm-crumb" + (last ? " current" : "");
      crumb.textContent = crumbLabel(node, i);
      if (!last)
        crumb.addEventListener("click", () => {
          const leaving = path[path.length - 1];
          path = path.slice(0, i + 1);
          render({ dir: "out", data: leaving });
        });
      bc.appendChild(crumb);
    });
  }

  // Thin frame on left/right/bottom (paddingOuter), a taller top band for the
  // label (paddingTop overrides just the top), small gaps between siblings.
  const layout = d3
    .treemap()
    .paddingInner(3)
    .paddingOuter(SIDE_PAD)
    .paddingTop((node) => topPad(node))
    .round(true);

  const DURATION = 430;

  function drawTiles(layer, nodes, stage) {
    const tip = el("tm-tooltip");
    const g = layer
      .selectAll("g.tm-tile")
      .data(nodes)
      .enter()
      .append("g")
      .attr("class", "tm-tile")
      .attr("transform", (d) => `translate(${d.x0},${d.y0})`)
      .on("mousemove", (event, d) => {
        const ctx = d.ancestors().slice(1, -1).reverse().map(nodeLabel).join(" · ");
        tip.innerHTML =
          `<strong>${escapeHtml(nodeLabel(d))}</strong> × ${d.value}` +
          (ctx ? `<br><span class="muted">${escapeHtml(ctx)}</span>` : "") +
          (d.children ? `<br><span class="muted">click to zoom in</span>` : "");
        tip.style.display = "block";
        const r = stage.getBoundingClientRect();
        tip.style.left = event.clientX - r.left + 12 + "px";
        tip.style.top = event.clientY - r.top + 12 + "px";
      })
      .on("mouseleave", () => (tip.style.display = "none"))
      .on("click", (event, d) => {
        tip.style.display = "none";
        if (d.children) {
          const rect = { x0: d.x0, y0: d.y0, x1: d.x1, y1: d.y1 };
          path.push(d.data);
          render({ dir: "in", rect });
        } else {
          window.sm64CopyQuery(leafQuery(fieldFor(d, "level"), fieldFor(d, "object")));
        }
      });

    g.append("rect")
      .attr("width", (d) => Math.max(0, d.x1 - d.x0))
      .attr("height", (d) => Math.max(0, d.y1 - d.y0))
      .attr("fill", fillFor); // stroke comes from CSS (.tm-tile rect)
  }

  // Labels via foreignObject for real text wrapping. A parent's label sits in
  // its top frame strip; a leaf's fills the tile and may wrap. If a label
  // cannot fully fit, it is removed entirely rather than shown truncated.
  function addLabels(layer) {
    layer.selectAll("g.tm-tile").each(function (d) {
      const w = d.x1 - d.x0;
      const h = d.y1 - d.y0;
      const isParent = !!d.children;
      const bandH = isParent ? topPad(d) : h;
      if (w < 16 || bandH < 12) return;
      const fo = d3
        .select(this)
        .append("foreignObject")
        .attr("class", "tm-fo")
        .attr("x", 0)
        .attr("y", 0)
        .attr("width", w)
        .attr("height", bandH);
      fo.html(
        `<div class="tm-label ${isParent ? "parent" : "leaf"}" style="color:${textOn(fillFor(d))}">` +
          `<span class="tm-name">${escapeHtml(nodeLabel(d))}</span></div>`
      );
      const div = fo.select(".tm-label").node();
      if (div && (div.scrollHeight > div.clientHeight + 1 || div.scrollWidth > div.clientWidth + 1))
        fo.remove();
    });
  }

  function render(zoom) {
    const stage = el("tm-stage");
    const W = stage.clientWidth;
    const H = stage.clientHeight;
    const svg = el("tm-svg");
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    if (W < 2 || H < 2) {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      return;
    }

    const focusData = path[path.length - 1];
    const local = d3
      .hierarchy(focusData)
      .sum((d) => d.value || 0)
      .sort((a, b) => b.value - a.value);
    layout.size([W, H])(local);

    buildBreadcrumb();
    el("tm-status").textContent =
      `${local.value} placements · ${local.leaves().length} cells`;

    // Parents before children so leaves sit on top (and catch clicks first).
    const nodes = local.descendants().slice(1).sort((a, b) => a.depth - b.depth);
    const oldLayers = Array.from(svg.querySelectorAll("g.tm-layer"));
    const layer = d3.select(svg).append("g").attr("class", "tm-layer");
    drawTiles(layer, nodes, stage);

    if (zoom) animateZoom(layer, oldLayers, zoom, local, W, H);
    else {
      oldLayers.forEach((n) => n.remove());
      addLabels(layer);
    }
  }

  // Zoom in: the new (inner) view grows from the clicked tile's rectangle to
  // fill the stage. Zoom out: the new (outer) view starts with the region we
  // left filling the stage, then pulls back into its place. Labels are added
  // only once the motion settles, so wrapping/measuring stays correct.
  function animateZoom(layer, oldLayers, zoom, local, W, H) {
    let from;
    if (zoom.dir === "in") {
      const sx = (zoom.rect.x1 - zoom.rect.x0) / W;
      const sy = (zoom.rect.y1 - zoom.rect.y0) / H;
      from = `translate(${zoom.rect.x0},${zoom.rect.y0}) scale(${sx},${sy})`;
    } else {
      const t = local.descendants().find((n) => n.data === zoom.data);
      if (!t) {
        oldLayers.forEach((n) => n.remove());
        addLabels(layer);
        return;
      }
      const sx = W / Math.max(1, t.x1 - t.x0);
      const sy = H / Math.max(1, t.y1 - t.y0);
      from = `translate(${-t.x0 * sx},${-t.y0 * sy}) scale(${sx},${sy})`;
    }

    layer.attr("transform", from).style("opacity", 0.35);
    layer
      .transition()
      .duration(DURATION)
      .ease(d3.easeCubicInOut)
      .attr("transform", "translate(0,0) scale(1,1)")
      .style("opacity", 1)
      .on("end", () => {
        oldLayers.forEach((n) => n.remove());
        addLabels(layer);
      });
    oldLayers.forEach((n) =>
      d3.select(n).transition().duration(DURATION * 0.7).ease(d3.easeCubicOut).style("opacity", 0)
    );
  }

  function syncModeButtons() {
    el("tm-groupby")
      .querySelectorAll(".tm-mode")
      .forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  }

  // Rebuild the whole tree for the current mode and reset the zoom to the root.
  function rebuild() {
    colorDim = MODES[mode].color;
    treeRootData = { name: "root", children: buildTree(MODES[mode].order, colorDim) };
    path = [treeRootData];
    syncModeButtons();
    render();
  }

  function setMode(m) {
    if (m === mode || !MODES[m]) return;
    mode = m;
    rebuild();
  }

  function ensureInit() {
    if (inited) return;
    inited = true;
    el("tm-groupby")
      .querySelectorAll(".tm-mode")
      .forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
    let t = null;
    window.addEventListener("resize", () => {
      clearTimeout(t);
      t = setTimeout(() => {
        if (el("tab-treemap").classList.contains("active")) render();
      }, 150);
    });
  }

  window.SM64Treemap = {
    onShow() {
      ensureInit();
      if (!rawRows) {
        const { rows, types, levels } = loadRows();
        rawRows = rows;
        // Stable, deterministic mappings. Types use the hand-picked palette;
        // levels get an evenly-spaced spread of hues (drop the last sample so
        // the rainbow's wrap doesn't repeat the first colour).
        colorScales.type.domain(types);
        colorScales.level
          .domain(levels)
          .range(d3.quantize(d3.interpolateRainbow, levels.length + 1).slice(0, -1));
      }
      rebuild();
    },
  };
})();
