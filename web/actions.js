"use strict";

// ---------------------------------------------------------------------------
// Actions tab: Mario's action state machine. Each ACT_* is a node; each arrow
// is a transition (a set_mario_action-family call) mined from the action's
// handler and the helpers it reaches (mario_transition over mario_action_call).
// Nodes are clustered and coloured by their group (stationary, moving, airborne,
// submerged, cutscene, automatic, object); size is the transition degree, so the
// hubs (FREEFALL, IDLE) are biggest. Dashed-ring nodes have no handler of their
// own -- the zero state and engine remap targets. Hover to focus a node's
// neighbourhood; click for a dossier (id, flags, handler, transitions in/out)
// with links straight to the decomp source.
//
// d3 force layout with a per-group cluster pull, lazily built the first time the
// tab is shown (an SVG in a hidden panel has no measurable size). Mirrors
// graph.js and reuses its CSS (.graph-* classes).
// ---------------------------------------------------------------------------

(function () {
  const el = (id) => document.getElementById(id);
  const sdb = () => window.sm64db();
  const strip = (s) => String(s).replace(/^ACT_/, "");
  const escapeHtml = (s) =>
    String(s).replace(
      /[&<>]/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])
    );
  const sqlStr = (s) => String(s).replace(/'/g, "''");
  const GH = "https://github.com/n64decomp/sm64/blob/master/";

  // The seven action groups: legend label + colour, in dispatch order. A node
  // with no group (ACT_UNINITIALIZED) falls back to "other".
  const GROUPS = [
    { key: "STATIONARY", label: "stationary", color: "#4dabf7" },
    { key: "MOVING", label: "moving", color: "#69db7c" },
    { key: "AIRBORNE", label: "airborne", color: "#ffa94d" },
    { key: "SUBMERGED", label: "submerged", color: "#3bc9db" },
    { key: "CUTSCENE", label: "cutscene", color: "#da77f2" },
    { key: "AUTOMATIC", label: "automatic", color: "#f783ac" },
    { key: "OBJECT", label: "object", color: "#ffd43b" },
    { key: "", label: "other", color: "#adb5bd" },
  ];
  const GROUP = new Map(GROUPS.map((g) => [g.key, g]));
  const groupColor = (g) => (GROUP.get(g || "") || GROUP.get("")).color;

  let inited = false;
  let rendered = false;
  let data = null; // { nodes, links, byId, adj }
  let sim = null;
  let sel = null; // selected node id, or null
  let nodeSel, linkSel, labelSel, edgeLabelSel;
  let svgSel = null;
  const short = (s, n = 30) => (s && s.length > n ? s.slice(0, n - 1) + "…" : s);
  let zoomBehavior = null;
  const enabled = {}; // group key -> shown
  GROUPS.forEach((g) => (enabled[g.key] = true));

  // --- data ----------------------------------------------------------------

  function rowsOf(sql) {
    const r = sdb().exec(sql);
    if (!r.length) return [];
    const cols = r[0].columns;
    return r[0].values.map((v) =>
      Object.fromEntries(v.map((x, i) => [cols[i], x]))
    );
  }

  function loadGraph() {
    const actionRows = rowsOf(
      "SELECT action_name, id, group_name, flags_json, handler FROM mario_action"
    );
    // Every transition: literal-target edges plus the runtime ones resolved to a
    // literal action (forwarded land actions, ternary branches).
    const links = rowsOf(
      "SELECT action_name AS src, to_action AS dst FROM mario_all_transitions"
    ).map((r) => ({ source: r.src, target: r.dst }));

    // The trigger condition per edge (the enclosing if-guard), from the literal
    // backbone and the resolved runtime transitions. One representative per edge.
    const cond = new Map();
    rowsOf(`
      SELECT action_name AS s, target AS d, condition AS c FROM mario_action_call
      WHERE target IN (SELECT action_name FROM mario_action) AND condition IS NOT NULL
      UNION
      SELECT action_name, to_action, condition FROM mario_action_data_transition
      WHERE condition IS NOT NULL`).forEach((r) => {
      const k = r.s + "\t" + r.d;
      if (!cond.has(k)) cond.set(k, r.c);
    });
    links.forEach((l) => (l.condition = cond.get(l.source + "\t" + l.target) || null));

    // Degree (in + out) drives node size; a self-loop counts once.
    const deg = new Map(actionRows.map((r) => [r.action_name, 0]));
    links.forEach((l) => {
      deg.set(l.source, (deg.get(l.source) || 0) + 1);
      if (l.target !== l.source)
        deg.set(l.target, (deg.get(l.target) || 0) + 1);
    });

    const nodes = actionRows.map((r) => {
      const d = deg.get(r.action_name) || 0;
      return {
        id: r.action_name,
        group: r.group_name || "",
        flags: JSON.parse(r.flags_json || "[]"),
        handler: r.handler,
        degree: d,
        r: Math.max(3.5, Math.min(22, 4 + Math.sqrt(d) * 1.5)),
      };
    });

    const byId = new Map(nodes.map((n) => [n.id, n]));
    const adj = new Map(nodes.map((n) => [n.id, new Set()]));
    links.forEach((l) => {
      if (adj.has(l.source)) adj.get(l.source).add(l.target);
      if (adj.has(l.target)) adj.get(l.target).add(l.source);
    });
    return { nodes, links, byId, adj };
  }

  // --- rendering -----------------------------------------------------------

  const nodeFill = (n) => groupColor(n.group);
  const shown = (n) => enabled[GROUP.has(n.group) ? n.group : ""];

  function buildLegend() {
    const legend = el("act-legend");
    legend.innerHTML = "";
    const counts = new Map();
    data.nodes.forEach((n) => {
      const k = GROUP.has(n.group) ? n.group : "";
      counts.set(k, (counts.get(k) || 0) + 1);
    });
    GROUPS.forEach((g) => {
      if (!counts.get(g.key)) return; // skip empty groups (e.g. no "other")
      const item = document.createElement("button");
      item.className = "legend-item" + (enabled[g.key] ? "" : " off");
      item.innerHTML =
        `<span class="swatch" style="background:${g.color}"></span>` +
        `${g.label} <span class="muted">${counts.get(g.key)}</span>`;
      item.addEventListener("click", () => {
        enabled[g.key] = !enabled[g.key];
        item.classList.toggle("off", !enabled[g.key]);
        styleGroups();
      });
      legend.appendChild(item);
    });
  }

  function defs(svg) {
    const d = svg.append("defs");
    GROUPS.forEach((g) => {
      d.append("marker")
        .attr("id", "aarr-" + (g.key || "other"))
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 9)
        .attr("refY", 0)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-4L9,0L0,4")
        .attr("fill", g.color);
    });
  }

  // An edge is shown only when both endpoints' groups are enabled; it is
  // coloured by its source action's group.
  function edgeVisible(l) {
    const s = data.byId.get(l.source.id || l.source);
    const t = data.byId.get(l.target.id || l.target);
    return s && t && shown(s) && shown(t);
  }
  function styleGroups() {
    if (!nodeSel) return;
    nodeSel.style("display", (n) => (shown(n) ? null : "none"));
    labelSel.style("display", (n) =>
      shown(n) && (n.degree >= 12 || (sel && inFocusOf(sel, n.id)))
        ? null
        : "none"
    );
    linkSel.style("display", (l) => (edgeVisible(l) ? null : "none"));
    styleEdgeLabels();
  }

  // Edge labels show only for the SELECTED node's outgoing, visible edges.
  function styleEdgeLabels() {
    if (!edgeLabelSel) return;
    edgeLabelSel.style("display", (l) => {
      const sid = l.source.id || l.source;
      return sel && sid === sel && edgeVisible(l) ? null : "none";
    });
  }

  function render() {
    rendered = true;
    const stage = el("act-stage");
    const W = stage.clientWidth;
    const H = stage.clientHeight;
    const svgEl = el("act-svg");
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);
    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${W} ${H}`);
    defs(svg);

    const viewport = svg.append("g").attr("class", "graph-viewport");
    const gLink = viewport.append("g");
    const gNode = viewport.append("g");
    const gLabel = viewport.append("g");

    linkSel = gLink
      .selectAll("line")
      .data(data.links)
      .join("line")
      .attr("class", "graph-link")
      .attr("stroke", (l) => groupColor(data.byId.get(l.source).group))
      .attr("stroke-width", 1.1)
      .attr("marker-end", (l) => {
        const g = data.byId.get(l.source).group;
        return `url(#aarr-${g || "other"})`;
      });

    nodeSel = gNode
      .selectAll("circle")
      .data(data.nodes)
      .join("circle")
      .attr("class", (n) => "graph-node" + (n.handler ? "" : " ghost"))
      .attr("r", (n) => n.r)
      .attr("fill", nodeFill)
      .on("mouseenter", (e, n) => {
        if (!sel) focus(n.id);
        showTip(e, n);
      })
      .on("mousemove", moveTip)
      .on("mouseleave", () => {
        hideTip();
        if (!sel) focus(null);
      })
      .on("click", (e, n) => {
        e.stopPropagation();
        select(n.id);
      })
      .call(drag());

    labelSel = gLabel
      .selectAll("text")
      .data(data.nodes)
      .join("text")
      .attr("class", "graph-label")
      .attr("text-anchor", "middle")
      .text((n) => strip(n.id));

    // Edge labels = the transition trigger (the guard condition). Only the
    // selected node's OUTGOING edges are labelled -- out-degree maxes at 17, so
    // this stays readable even on the in-degree hubs like IDLE / FREEFALL.
    const gEdge = viewport.append("g");
    edgeLabelSel = gEdge
      .selectAll("text")
      .data(data.links.filter((l) => l.condition))
      .join("text")
      .attr("class", "graph-edge-label")
      .attr("text-anchor", "middle")
      .text((l) => short(l.condition))
      .on("mouseenter", (e, l) => showEdgeTip(e, l))
      .on("mousemove", moveTip)
      .on("mouseleave", hideTip);

    applyFocus(null);
    styleGroups();
    svgEl.addEventListener("click", () => select(null));

    svgSel = svg;
    zoomBehavior = d3
      .zoom()
      .scaleExtent([0.2, 6])
      .on("zoom", (e) => viewport.attr("transform", e.transform));
    svg.call(zoomBehavior);

    // A cluster centre per group, placed around an ellipse; forceX/Y pull each
    // node toward its group's centre so the seven groups separate visually.
    const used = GROUPS.filter((g) => data.nodes.some((n) => n.group === g.key));
    const centers = new Map();
    used.forEach((g, i) => {
      const a = (i / used.length) * 2 * Math.PI - Math.PI / 2;
      centers.set(g.key, {
        x: W / 2 + Math.cos(a) * W * 0.31,
        y: H / 2 + Math.sin(a) * H * 0.34,
      });
    });
    const cx = (n) => (centers.get(n.group) || { x: W / 2 }).x;
    const cy = (n) => (centers.get(n.group) || { y: H / 2 }).y;

    sim = d3
      .forceSimulation(data.nodes)
      .force(
        "link",
        d3
          .forceLink(data.links)
          .id((d) => d.id)
          .distance(34)
          .strength(0.12)
      )
      .force("charge", d3.forceManyBody().strength(-70))
      .force("collide", d3.forceCollide((d) => d.r + 2.5))
      .force("x", d3.forceX(cx).strength(0.22))
      .force("y", d3.forceY(cy).strength(0.22))
      .on("tick", tick);

    el("act-status").textContent =
      `${data.nodes.length} actions · ${data.links.length} transitions`;
  }

  function tick() {
    linkSel
      .attr("x1", (l) => l.source.x)
      .attr("y1", (l) => l.source.y)
      .attr("x2", (l) => {
        const dx = l.target.x - l.source.x,
          dy = l.target.y - l.source.y,
          d = Math.hypot(dx, dy) || 1;
        return l.target.x - (dx / d) * (l.target.r + 5);
      })
      .attr("y2", (l) => {
        const dx = l.target.x - l.source.x,
          dy = l.target.y - l.source.y,
          d = Math.hypot(dx, dy) || 1;
        return l.target.y - (dy / d) * (l.target.r + 5);
      });
    nodeSel.attr("cx", (n) => n.x).attr("cy", (n) => n.y);
    labelSel.attr("x", (n) => n.x).attr("y", (n) => n.y - n.r - 3);
    if (edgeLabelSel)
      edgeLabelSel
        .attr("x", (l) => (l.source.x + l.target.x) / 2)
        .attr("y", (l) => (l.source.y + l.target.y) / 2);
  }

  function drag() {
    return d3
      .drag()
      .on("start", (e, d) => {
        if (e.sourceEvent) e.sourceEvent.stopPropagation();
        if (!e.active) sim.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (e, d) => {
        d.fx = e.x;
        d.fy = e.y;
      })
      .on("end", (e, d) => {
        if (!e.active) sim.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });
  }

  // --- focus / selection ---------------------------------------------------

  const inFocusOf = (id, nid) =>
    !id || nid === id || (data.adj.get(id) && data.adj.get(id).has(nid));

  function applyFocus(id) {
    nodeSel.classed("graph-dim", (n) => !inFocusOf(id, n.id));
    linkSel.classed(
      "graph-dim",
      (l) => id && l.source.id !== id && l.target.id !== id
    );
    labelSel
      .classed("graph-dim", (n) => !inFocusOf(id, n.id))
      .style("display", (n) =>
        shown(n) && (n.degree >= 12 || (id && inFocusOf(id, n.id)))
          ? null
          : "none"
      );
  }
  function focus(id) {
    applyFocus(sel || id);
  }

  function select(id) {
    sel = id;
    nodeSel.classed("selected", (n) => n.id === id);
    applyFocus(id);
    styleEdgeLabels();
    if (id) dossier(id);
    else el("act-dossier").hidden = true;
  }
  // Exposed so dossier links can jump between actions.
  window.SM64ActionSelect = (id) => {
    if (data && data.byId.has(id)) select(id);
  };

  // --- tooltip -------------------------------------------------------------

  function showEdgeTip(e, l) {
    const tip = el("act-tooltip");
    const sid = l.source.id || l.source;
    const tid = l.target.id || l.target;
    tip.innerHTML =
      `<strong>${escapeHtml(strip(sid))} → ${escapeHtml(strip(tid))}</strong>` +
      (l.condition
        ? `<br><span class="muted">if</span> ${escapeHtml(l.condition)}`
        : "");
    tip.style.display = "block";
    moveTip(e);
  }

  function showTip(e, n) {
    const tip = el("act-tooltip");
    const g = GROUP.get(n.group) || GROUP.get("");
    tip.innerHTML =
      `<strong>${escapeHtml(strip(n.id))}</strong><br>` +
      `<span class="muted">${g.label}</span><br>` +
      `${n.degree} transition${n.degree === 1 ? "" : "s"}` +
      (n.handler ? "" : `<br><span class="muted">no handler</span>`);
    tip.style.display = "block";
    moveTip(e);
  }
  function moveTip(e) {
    const tip = el("act-tooltip");
    const r = el("act-stage").getBoundingClientRect();
    tip.style.left = e.clientX - r.left + 12 + "px";
    tip.style.top = e.clientY - r.top + 12 + "px";
  }
  const hideTip = () => (el("act-tooltip").style.display = "none");

  // --- dossier -------------------------------------------------------------

  const src = (f, l) =>
    f
      ? ` <a class="src" href="${GH}${f}#L${l}" target="_blank" rel="noopener">${f
          .split("/")
          .pop()}:${l}</a>`
      : "";
  const goto = (id) =>
    `<span class="dossier-link" onclick="SM64ActionSelect('${sqlStr(
      id
    )}')">${escapeHtml(strip(id))}</span>`;
  const guard = (c) =>
    c ? ` <span class="cond">if ${escapeHtml(c)}</span>` : "";

  function listSection(title, items) {
    if (!items.length) return "";
    return (
      `<section><h4>${title} <span class="muted">${items.length}</span></h4>` +
      `<ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul></section>`
    );
  }

  function dossier(id) {
    const A = sqlStr(id);
    const node = data.byId.get(id);
    const meta = rowsOf(
      `SELECT id, group_name, handler, file, line FROM mario_action WHERE action_name='${A}'`
    )[0] || {};

    // Outgoing: literal-at-site targets (one representative call site each),
    // then runtime ones resolved to a literal action (with a source pill). Each
    // shows its trigger condition (the enclosing if-guard).
    const out = [];
    const outSeen = new Set();
    rowsOf(`
      SELECT target d, condition c, file, line FROM mario_action_call
      WHERE action_name='${A}' AND target IN (SELECT action_name FROM mario_action)
      ORDER BY target, line`).forEach((r) => {
      if (outSeen.has(r.d)) return;
      outSeen.add(r.d);
      out.push(goto(r.d) + guard(r.c) + src(r.file, r.line));
    });
    rowsOf(`
      SELECT to_action d, source, condition c, file, line
      FROM mario_action_data_transition
      WHERE action_name='${A}' ORDER BY to_action`).forEach((r) => {
      if (outSeen.has(r.d)) return;
      outSeen.add(r.d);
      out.push(
        goto(r.d) +
          guard(r.c) +
          src(r.file, r.line) +
          ` <span class="pill">${escapeHtml(r.source)}</span>`
      );
    });

    // Incoming: which actions can transition into this one (any origin), each
    // with the condition under which that source enters this action.
    const incCond = new Map();
    rowsOf(`
      SELECT action_name s, condition c FROM mario_action_call
      WHERE target='${A}' AND condition IS NOT NULL
      UNION
      SELECT action_name, condition FROM mario_action_data_transition
      WHERE to_action='${A}' AND condition IS NOT NULL`).forEach((r) => {
      if (!incCond.has(r.s)) incCond.set(r.s, r.c);
    });
    const inc = rowsOf(
      `SELECT DISTINCT action_name s FROM mario_all_transitions WHERE to_action='${A}' ORDER BY action_name`
    ).map((r) => goto(r.s) + guard(incCond.get(r.s)));

    // Genuinely-unresolved transitions: a struct-table landing or a computed
    // target we cannot pin to a literal action -- shown honestly, not hidden.
    // (Excludes targets resolved above: literals in expressions and the
    // forwarded params that became a source pill.)
    const runtime = rowsOf(`
      SELECT DISTINCT target t, file, line FROM mario_action_call
      WHERE action_name='${A}' AND target IS NOT NULL
        AND target NOT IN (SELECT action_name FROM mario_action)
        AND target NOT GLOB '*ACT_*'
        AND target NOT IN (
          SELECT source FROM mario_action_data_transition WHERE action_name='${A}')
      ORDER BY target`).map(
      (r) => `<span class="src">${escapeHtml(r.t)}</span>${src(r.file, r.line)}`
    );

    const g = GROUP.get(node ? node.group : "") || GROUP.get("");
    const flags = node && node.flags.length ? node.flags : [];
    const handlerLine = meta.handler
      ? `<span class="src">${escapeHtml(meta.handler)}</span>${src(
          meta.file,
          meta.line
        )}`
      : `<span class="muted">no handler (engine remap / zero state)</span>`;

    const html =
      `<button class="dossier-close" title="Close">×</button>` +
      `<h3>${escapeHtml(strip(id))}</h3>` +
      `<div class="dossier-sub">${escapeHtml(g.label)} · <span class="src">${escapeHtml(
        meta.id || ""
      )}</span></div>` +
      (flags.length
        ? `<div class="dossier-sub">${flags
            .map((f) => `<span class="pill">${escapeHtml(f)}</span>`)
            .join(" ")}</div>`
        : "") +
      `<section><h4>Handler</h4><ul><li>${handlerLine}</li></ul></section>` +
      listSection("Transitions to", out) +
      listSection("Reached from", inc) +
      listSection("Runtime target (unresolved)", runtime);

    const box = el("act-dossier");
    box.innerHTML = html;
    box.hidden = false;
    box.querySelector(".dossier-close").addEventListener("click", (e) => {
      e.stopPropagation();
      select(null);
    });
  }

  // --- lifecycle -----------------------------------------------------------

  function resize() {
    if (!sim) return;
    const stage = el("act-stage");
    const W = stage.clientWidth;
    const H = stage.clientHeight;
    el("act-svg").setAttribute("viewBox", `0 0 ${W} ${H}`);
    sim.alpha(0.2).restart();
  }

  function ensureInit() {
    if (inited) return;
    inited = true;
    const zoomBy = (k) => {
      if (svgSel && zoomBehavior)
        svgSel.transition().duration(200).call(zoomBehavior.scaleBy, k);
    };
    el("act-zoom-in").addEventListener("click", () => zoomBy(1.4));
    el("act-zoom-out").addEventListener("click", () => zoomBy(1 / 1.4));
    el("act-zoom-reset").addEventListener("click", () => {
      if (svgSel && zoomBehavior)
        svgSel
          .transition()
          .duration(250)
          .call(zoomBehavior.transform, d3.zoomIdentity);
    });
    el("act-search").addEventListener("input", (e) => {
      const q = e.target.value.trim().toLowerCase();
      if (!q) {
        select(null);
        return;
      }
      const hit = data.nodes.find((n) => strip(n.id).toLowerCase().includes(q));
      if (hit) select(hit.id);
    });
    let t = null;
    window.addEventListener("resize", () => {
      clearTimeout(t);
      t = setTimeout(() => {
        if (el("tab-actions").classList.contains("active")) resize();
      }, 150);
    });
  }

  window.SM64Actions = {
    onShow() {
      ensureInit();
      if (!data) data = loadGraph();
      if (!rendered) {
        buildLegend();
        render();
      } else {
        resize();
      }
    },
  };
})();
