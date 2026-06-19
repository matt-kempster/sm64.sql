"use strict";

// ---------------------------------------------------------------------------
// Treemap tab: a nested treemap showing all three tiers at once -- level →
// object list → behavior. Each level is a hue; nesting is shown by shade (dark
// header frames, vivid leaf tiles) so the tiers read as one family. Clicking a
// region's header zooms into it (breadcrumb zooms back out); clicking a
// behavior leaf copies its query. Wrapped in an IIFE; app.js owns global `db`.
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

  const PALETTE = [
    "#ff8787", "#ffa94d", "#ffd43b", "#a9e34b", "#69db7c", "#38d9a9",
    "#3bc9db", "#4dabf7", "#748ffc", "#9775fa", "#da77f2", "#f783ac",
  ];
  const colorByName = d3.scaleOrdinal(PALETTE);

  function textOn(bg) {
    const c = d3.color(bg).rgb();
    const lum = (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255;
    return lum > 0.62 ? "#1d2330" : "#ffffff";
  }

  // Absolute tier of a node: level=1, object list=2, behavior=3.
  const absDepth = (node) => path.length - 1 + node.depth;

  // Header band reserved at the top of a parent for its label.
  function topPad(node) {
    if (!node.children) return 0;
    return absDepth(node) === 1 ? 19 : 15;
  }

  // Fill: vivid leaf in the branch's hue; darker shades for the header frames.
  function fillFor(node) {
    const branch = node.ancestors().find((a) => a.depth === 1);
    const base = d3.color(colorByName(branch.data.name));
    if (!node.children) return base.formatHex();
    return base.darker(absDepth(node) === 1 ? 1.1 : 0.55).formatHex();
  }

  function nodeLabel(node) {
    return absDepth(node) === 2 ? catLabel(node.data.name) : strip(node.data.name);
  }

  // level → object list → behaviors (leaves)
  function loadTree() {
    const r = sdb().exec(
      `SELECT o.level, o.behavior, COALESCE(b.obj_list, '') AS olist, COUNT(*) c
       FROM object o LEFT JOIN behavior b ON o.behavior = b.behavior_name
       GROUP BY o.level, o.behavior`
    );
    const rows = r.length ? r[0].values : [];
    const levels = new Map();
    rows.forEach(([level, beh, olist, c]) => {
      if (!levels.has(level)) levels.set(level, new Map());
      const cats = levels.get(level);
      if (!cats.has(olist)) cats.set(olist, []);
      cats.get(olist).push({ name: beh, value: c });
    });
    return Array.from(levels, ([name, cats]) => ({
      name,
      children: Array.from(cats, ([cname, behs]) => ({ name: cname, children: behs })),
    }));
  }

  function leafQuery(level, beh) {
    return `-- ${strip(beh)} placed in ${level}
SELECT level, initial_x AS x, initial_y AS y, initial_z AS z,
       model_name, behavior, bhv_param
FROM object
WHERE level = '${level}' AND behavior = '${beh}'
ORDER BY level;`;
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
      if (!last) crumb.addEventListener("click", () => { path = path.slice(0, i + 1); draw(); });
      bc.appendChild(crumb);
    });
  }

  const layout = d3
    .treemap()
    .paddingInner(2)
    .paddingOuter(2)
    .paddingTop((node) => topPad(node))
    .round(true);

  function draw() {
    const stage = el("tm-stage");
    const W = stage.clientWidth;
    const H = stage.clientHeight;
    const svg = el("tm-svg");
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (W < 2 || H < 2) return;

    const focusData = path[path.length - 1];
    const local = d3
      .hierarchy(focusData)
      .sum((d) => d.value || 0)
      .sort((a, b) => b.value - a.value);
    layout.size([W, H])(local);

    buildBreadcrumb();
    el("tm-status").textContent =
      `${local.leaves().length} behaviors · ${local.value} placements`;

    // Parents before children so leaves sit on top (and catch clicks first;
    // a parent's only exposed area is its header band + gaps).
    const nodes = local.descendants().slice(1).sort((a, b) => a.depth - b.depth);
    const tip = el("tm-tooltip");
    const layer = d3.select(svg).append("g").attr("class", "tm-layer");

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
        if (d.children) {
          path.push(d.data);
          draw();
        } else {
          const level = path[1] ? path[1].name : d.ancestors().find((a) => a.depth === 1).data.name;
          window.sm64CopyQuery(leafQuery(level, d.data.name));
        }
      });

    g.append("rect")
      .attr("width", (d) => Math.max(0, d.x1 - d.x0))
      .attr("height", (d) => Math.max(0, d.y1 - d.y0))
      .attr("rx", 3)
      .attr("ry", 3)
      .attr("fill", fillFor); // stroke comes from CSS (.tm-tile rect)

    // Labels via foreignObject for consistent CSS truncation/ellipsis. A
    // parent's label sits in its header band; a leaf's fills the tile.
    g.each(function (d) {
      const w = d.x1 - d.x0;
      const bandH = d.children ? topPad(d) : d.y1 - d.y0;
      if (w < 28 || bandH < 13) return;
      d3.select(this)
        .append("foreignObject")
        .attr("class", "tm-fo")
        .attr("width", w)
        .attr("height", bandH)
        .html(
          `<div class="tm-label" style="color:${textOn(fillFor(d))}">` +
            `<span class="tm-name">${escapeHtml(nodeLabel(d))}</span>` +
            `<span class="tm-val">${d.value}${d.children ? " ▸" : ""}</span>` +
            `</div>`
        );
    });
  }

  function ensureInit() {
    if (inited) return;
    inited = true;
    let t = null;
    window.addEventListener("resize", () => {
      clearTimeout(t);
      t = setTimeout(() => {
        if (el("tab-treemap").classList.contains("active")) draw();
      }, 150);
    });
  }

  window.SM64Treemap = {
    onShow() {
      ensureInit();
      if (!treeRootData) treeRootData = { name: "root", children: loadTree() };
      path = [treeRootData];
      draw();
    },
  };
})();
