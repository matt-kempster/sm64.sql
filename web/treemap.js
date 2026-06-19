"use strict";

// ---------------------------------------------------------------------------
// Treemap tab: a nested treemap showing all three tiers at once -- level →
// object list → behavior -- where every placement of an object counts, drawn
// from all three placement tables (object + macro_object + special_object),
// each resolved to a behavior so they share the object-list grouping.
//
// Colour is by TYPE (object list): each obj_list gets a stable hue, so leaves
// in the same list share a colour and nothing reshuffles when you zoom. Object
// lists are a soft tint of that hue, levels a neutral frame. Parents show as a
// UNIFORM frame on all four sides (uniform paddingOuter, no fat top band).
// Clicking a region zooms into it with an animation; the breadcrumb zooms back
// out; clicking a behavior leaf copies its placements query.
//
// Navigation is a `path` of plain DATA nodes; each draw builds a FRESH d3
// hierarchy rooted at the focused data (depth 0). d3.treemap indexes padding by
// absolute node.depth, so it must be handed a depth-0 root.
// ---------------------------------------------------------------------------

(function () {
  const el = (id) => document.getElementById(id);
  const sdb = () => window.sm64db();
  let inited = false;
  let treeRootData = null;
  let path = [];

  const strip = (s) => String(s).replace(/^bhv/, "");
  const catLabel = (c) => (c ? c.replace(/^OBJ_LIST_/, "").toLowerCase() : "(none)");
  const escapeHtml = (s) =>
    String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const sqlStr = (s) => String(s).replace(/'/g, "''");

  // One cheerful hue per object-list type. The domain is seeded once (sorted)
  // so a given type always maps to the same colour, in or out of any zoom.
  const PALETTE = [
    "#ff8787", "#ffa94d", "#ffd43b", "#a9e34b", "#69db7c", "#38d9a9",
    "#3bc9db", "#4dabf7", "#748ffc", "#9775fa", "#da77f2", "#f783ac",
  ];
  const colorByType = d3.scaleOrdinal(PALETTE);
  const tint = (hex, t) => d3.interpolateRgb(hex, "#ffffff")(t);
  const LEVEL_FRAME = "#e7eaf1";

  function textOn(bg) {
    const c = d3.color(bg).rgb();
    const lum = (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255;
    return lum > 0.62 ? "#1d2330" : "#ffffff";
  }

  // Absolute tier of a node: level=1, object list=2, behavior(leaf)=3.
  const absDepth = (node) => path.length - 1 + node.depth;

  // Uniform frame thickness reserved around a parent's children (all 4 sides).
  function framePad(node) {
    if (!node.children) return 0;
    const ad = absDepth(node);
    if (ad === 1) return 20; // level
    if (ad === 2) return 15; // object list
    return 3; // focus container
  }

  // Fill by type: vivid leaf in its list's hue, soft tint for the list frame,
  // neutral for the level frame. Keyed on the (stable) type name.
  function fillFor(node) {
    if (!node.children) return colorByType(node.data.cat || "");
    if (absDepth(node) === 2) return tint(colorByType(node.data.cat || ""), 0.62);
    return LEVEL_FRAME;
  }

  function nodeLabel(node) {
    if (!node.children) return strip(node.data.name);
    return absDepth(node) === 2 ? catLabel(node.data.name) : node.data.name;
  }

  // The level a leaf belongs to, whatever the current zoom.
  function levelOf(d) {
    for (const a of d.ancestors()) if (absDepth(a) === 1) return a.data.name;
    return path.length > 1 ? path[1].name : "";
  }

  // level → object list → behaviors (leaves). Every placement counts: objects
  // carry their behavior directly; macro/special objects resolve it through
  // their preset table. obj_list comes from the behavior table.
  function loadTree() {
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
    const rows = r.length ? r[0].values : [];
    const levels = new Map();
    const cats = new Set();
    rows.forEach(([level, beh, olist, c]) => {
      cats.add(olist);
      if (!levels.has(level)) levels.set(level, new Map());
      const m = levels.get(level);
      if (!m.has(olist)) m.set(olist, []);
      m.get(olist).push({ name: beh || "", value: c, cat: olist });
    });
    const tree = Array.from(levels, ([name, m]) => ({
      name,
      children: Array.from(m, ([cname, behs]) => ({ name: cname, cat: cname, children: behs })),
    }));
    return { tree, cats: Array.from(cats).sort() };
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
    if (i === 0) return "all levels";
    if (i === 2) return catLabel(node.name);
    return strip(node.name);
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

  // Uniform frame on all four sides (no fat top band): paddingOuter is a per-
  // node function and paddingTop is left to follow it.
  const layout = d3
    .treemap()
    .paddingInner(3)
    .paddingOuter((node) => framePad(node))
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
          window.sm64CopyQuery(leafQuery(levelOf(d), d.data.name));
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
      const bandH = isParent ? framePad(d) : h;
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
      `${local.leaves().length} behaviors · ${local.value} placements`;

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

  function ensureInit() {
    if (inited) return;
    inited = true;
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
      if (!treeRootData) {
        const { tree, cats } = loadTree();
        treeRootData = { name: "root", children: tree };
        colorByType.domain(cats); // deterministic, stable type→colour mapping
      }
      path = [treeRootData];
      render();
    },
  };
})();
