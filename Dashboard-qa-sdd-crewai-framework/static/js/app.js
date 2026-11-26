/* SDD QA Automation Dashboard - front end (no build step). */
(() => {
  "use strict";

  // ------------------------------------------------------------------ state
  const S = {
    meta: null, cases: { framework: [], simulated: [] }, byId: {}, selected: new Set(),
    es: null, runId: null, running: false, t0: 0, timer: null,
    perCase: {}, order: [], currentTc: null, viewTc: null, viewAgent: null, follow: true,
    logs: [], counts: { passed: 0, failed: 0, error: 0, blocked: 0 }, agentSecs: {}, summary: null,
    charts: {}, mermaidDone: false, snapshot: null,
  };
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const storage = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
  };
  const OUTCOME_ICON = { passed: "✔", failed: "✖", error: "⚠", blocked: "⛔", skipped: "↷", queued: "•", running: "⟳" };
  const STATUS_LABEL = { idle: "Waiting", running: "Running", done: "Done", failed: "Failed", blocked: "Blocked", skipped: "Skipped" };

  async function getJSON(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.json();
  }

  // ------------------------------------------------------------------ theme
  function applyTheme(t) {
    if (t) document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
  }
  function currentTheme() {
    const t = document.documentElement.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  applyTheme(storage.get("sdd-theme"));
  $("#theme-btn").addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    applyTheme(next); storage.set("sdd-theme", next);
    rebuildCharts(); S.mermaidDone = false; if (!$("#tab-features").hidden) renderMermaid();
  });

  // ------------------------------------------------------------------ tabs
  $$(".tab").forEach((b) => b.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.toggle("active", x === b));
    $$(".tab-panel").forEach((p) => { p.hidden = p.id !== `tab-${b.dataset.tab}`; });
    if (b.dataset.tab === "features") renderMermaid();
    if (b.dataset.tab === "reports") loadReports();
    storage.set("sdd-tab", b.dataset.tab);
  }));

  // ------------------------------------------------------------------ picker
  const picker = { btn: $("#picker-btn"), panel: $("#picker-panel"), list: $("#picker-list"), search: $("#picker-search") };
  picker.btn.addEventListener("click", () => {
    const open = picker.panel.hidden;
    picker.panel.hidden = !open; picker.btn.setAttribute("aria-expanded", String(open));
    if (open) picker.search.focus();
  });
  document.addEventListener("click", (e) => {
    if (!$("#picker").contains(e.target)) { picker.panel.hidden = true; picker.btn.setAttribute("aria-expanded", "false"); }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { picker.panel.hidden = true; picker.btn.setAttribute("aria-expanded", "false"); } });
  picker.search.addEventListener("input", renderPicker);
  $$("[data-preset]").forEach((b) => b.addEventListener("click", () => applyPreset(b.dataset.preset)));

  function outcomeHint(c) {
    if (c.source === "framework") return "";
    const map = { passed: "→ passes", failed: "→ fails", error: "→ env error", blocked: "→ blocked at gate" };
    return `<span class="hint">${map[c.expected_outcome] || ""}</span>`;
  }

  function renderPicker() {
    const q = picker.search.value.trim().toLowerCase();
    const all = [...S.cases.simulated, ...S.cases.framework];
    const groups = {};
    all.filter((c) => !q || `${c.id} ${c.title} ${c.feature} ${c.group}`.toLowerCase().includes(q))
      .forEach((c) => (groups[c.group] ||= []).push(c));
    const html = Object.entries(groups).map(([g, items]) => {
      const src = items[0].source;
      return `<div class="pick-group"><span>${esc(g)}</span><span class="src ${src === "framework" ? "src-real" : "src-sim"}">${src === "framework" ? "REAL" : "SIMULATED"}</span></div>` +
        items.map((c) => `
        <label class="pick-item" role="option" aria-selected="${S.selected.has(c.id)}">
          <input type="checkbox" data-id="${esc(c.id)}" ${S.selected.has(c.id) ? "checked" : ""}>
          <span><span class="pid">${esc(c.id)}</span><br><span class="ptitle">${esc(c.title)}</span></span>
          <span class="pmeta"><span class="ch ch-${c.channel}">${c.channel.toUpperCase()}</span>${outcomeHint(c)}</span>
        </label>`).join("");
    }).join("") || `<p class="muted" style="padding:10px">No test case matches.</p>`;
    picker.list.innerHTML = html;
    $$("input[type=checkbox]", picker.list).forEach((cb) => cb.addEventListener("change", () => {
      cb.checked ? S.selected.add(cb.dataset.id) : S.selected.delete(cb.dataset.id);
      renderSelected();
    }));
  }

  function renderSelected() {
    $("#picker-count").textContent = S.selected.size;
    $("#selected-chips").innerHTML = [...S.selected].map((id) => {
      const c = S.byId[id]; if (!c) return "";
      return `<span class="sel-chip" title="${esc(c.title)}">${esc(id)} <span class="src ${c.source === "framework" ? "src-real" : "src-sim"}">${c.source === "framework" ? "REAL" : "SIM"}</span><button aria-label="Remove ${esc(id)}" data-rm="${esc(id)}">×</button></span>`;
    }).join("");
    $$("[data-rm]").forEach((b) => b.addEventListener("click", () => { S.selected.delete(b.dataset.rm); renderSelected(); renderPicker(); }));
    if (!S.running) { $("#k-total").textContent = S.selected.size; $("#k-total-sub").textContent = "selected"; }
    $("#run-btn").disabled = S.running || S.selected.size === 0;
    storage.set("sdd-selected", JSON.stringify([...S.selected]));
  }

  function applyPreset(p) {
    const sim = S.cases.simulated.map((c) => c.id), real = S.cases.framework.map((c) => c.id);
    if (p === "clear") S.selected.clear();
    if (p === "demo") sim.forEach((i) => S.selected.add(i));
    if (p === "real") real.forEach((i) => S.selected.add(i));
    if (p === "ui") S.cases.framework.filter((c) => c.channel === "ui").forEach((c) => S.selected.add(c.id));
    if (p === "mix") {
      S.selected.clear();
      const want = ["DEMO-CART-001", "DEMO-CART-002", "DEMO-RESET-001", "DEMO-INV-001", "DEMO-CHK-002", "DEMO-NOTIF-001"];
      want.filter((i) => S.byId[i]).forEach((i) => S.selected.add(i));
      ["TC-LOGIN-003", "TC-LOGIN-002"].filter((i) => S.byId[i]).forEach((i) => S.selected.add(i));
      if (!S.byId["TC-LOGIN-003"] && real[0]) S.selected.add(real[0]);
    }
    renderPicker(); renderSelected();
  }

  // ------------------------------------------------------------------ pipeline cards
  function pipelineAgents() {
    const keys = [...S.meta.pipeline, "change_impact_analyst"];
    return keys.map((k) => S.meta.agents.find((a) => a.key === k)).filter(Boolean);
  }
  function renderPipeline() {
    $("#pipeline").innerHTML = pipelineAgents().map((a, i) => {
      const offline = a.key === "change_impact_analyst";
      return `<div class="agent st-idle ${offline ? "offline" : ""}" data-agent="${a.key}" tabindex="0" role="button"
        aria-label="${esc(a.name)} agent" title="${esc(a.goal || "")}">
        <div class="a-top"><span class="a-icon">${a.icon}</span><span class="a-step">${offline ? "Flow 5" : `#${i + 1}`}</span></div>
        <div class="a-name">${esc(a.name)}</div>
        <div class="a-flow">${esc(a.flow)} · ${esc(a.output)}</div>
        <div class="a-act">${offline ? "Runs when a specification changes (main.py change)" : "Waiting"}</div>
        <div class="a-bar"><i></i></div>
        <div class="a-foot"><span class="a-status">${offline ? "Not in this flow" : "Waiting"}</span><span class="a-dur"></span></div>
      </div>`;
    }).join("");
    $$("#pipeline .agent:not(.offline)").forEach((el) => {
      const pick = () => { S.follow = false; S.viewAgent = el.dataset.agent; showOutput(); highlightCard(); };
      el.addEventListener("click", pick);
      el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
    });
  }
  function resetCards() {
    $$("#pipeline .agent:not(.offline)").forEach((el) => {
      el.className = "agent st-idle";
      $(".a-act", el).textContent = "Waiting"; $(".a-status", el).textContent = "Waiting";
      $(".a-dur", el).textContent = ""; $(".a-bar > i", el).style.width = "0";
    });
  }
  function paintCard(key, st) {
    const el = $(`#pipeline .agent[data-agent="${key}"]`); if (!el || !st) return;
    el.className = `agent st-${st.status}` + (S.viewAgent === key ? " selected" : "");
    $(".a-act", el).textContent = st.activity || STATUS_LABEL[st.status];
    $(".a-status", el).textContent = STATUS_LABEL[st.status];
    $(".a-dur", el).textContent = st.duration ? `${st.duration.toFixed(1)}s` : "";
    $(".a-bar > i", el).style.width = `${st.progress || 0}%`;
  }
  function paintAllCards(tc) {
    const pc = S.perCase[tc]; if (!pc) return;
    resetCards();
    Object.entries(pc.agents).forEach(([k, st]) => paintCard(k, st));
    highlightCard();
  }
  function highlightCard() { $$("#pipeline .agent").forEach((el) => el.classList.toggle("selected", el.dataset.agent === S.viewAgent)); }

  // ------------------------------------------------------------------ agent output
  function highlightCode(text) {
    const re = /(#.*$)|('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")|(@[\w.]+)|\b(def|return|import|from|assert|None|True|False|with|for|in|if)\b/gm;
    let out = "", last = 0, m;
    while ((m = re.exec(text))) {
      out += esc(text.slice(last, m.index));
      const cls = m[1] ? "c" : m[2] ? "s" : m[3] ? "d" : "k";
      out += `<span class="${cls}">${esc(m[0])}</span>`;
      last = re.lastIndex;
    }
    return out + esc(text.slice(last));
  }
  function showOutput() {
    const tc = S.viewTc, key = S.viewAgent, box = $("#agent-output");
    const st = tc && key ? S.perCase[tc]?.agents[key] : null;
    const agent = S.meta.agents.find((a) => a.key === key);
    $("#output-ctx").textContent = tc && agent ? `${tc} · ${agent.name}${S.follow ? " · following live" : " · pinned (click another card or a queue item)"}` : "Click an agent card to inspect its output";
    if (!st || !st.output || !Object.keys(st.output).length) {
      box.innerHTML = `<p class="muted">${st ? (st.status === "running" ? "Agent is working… " + esc(st.activity || "") : "No output recorded.") : "Nothing yet."}</p>`;
      return;
    }
    const o = st.output;
    let html = `<div class="ao-title"><span style="font-size:20px">${agent?.icon || ""}</span><h3>${esc(o.title || agent?.name)}</h3>`;
    if (o.badge) html += `<span class="badge badge-${o.badge.tone}">${o.badge.tone === "good" ? "✔ " : o.badge.tone === "critical" ? "✖ " : "! "}${esc(o.badge.text)}</span>`;
    html += `<span class="src ${S.perCase[tc].source === "framework" ? "src-real" : "src-sim"}">${S.perCase[tc].source === "framework" ? "REAL" : "SIMULATED"}</span>`;
    if (st.duration) html += `<span class="muted">${st.duration.toFixed(2)}s</span>`;
    html += `</div>`;
    if (o.fields?.length) html += `<dl class="kv">${o.fields.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
    if (o.list?.length) html += `<ul class="ao-list">${o.list.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
    if (o.table?.rows?.length) html += `<div class="table-wrap" style="margin-top:10px"><table><thead><tr>${o.table.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${o.table.rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    if (o.code?.text) html += `<pre class="code"><code>${highlightCode(o.code.text)}</code></pre>`;
    box.innerHTML = html;
  }

  // ------------------------------------------------------------------ queue
  function renderQueue() {
    const q = $("#queue");
    if (!S.order.length) { q.innerHTML = `<li class="muted empty">Queue is empty.</li>`; return; }
    q.innerHTML = S.order.map((id) => {
      const pc = S.perCase[id];
      const o = pc.outcome || "queued";
      const ic = o === "running" ? `<span class="spin">⟳</span>` : OUTCOME_ICON[o] || "•";
      return `<li data-tc="${esc(id)}" class="${S.viewTc === id ? "current" : ""}" title="${esc(pc.title)}">
        <span class="q-ic">${ic}</span>
        <span style="min-width:0"><span class="q-id">${esc(id)}</span> <span class="src ${pc.source === "framework" ? "src-real" : "src-sim"}">${pc.source === "framework" ? "REAL" : "SIM"}</span> <span class="ch ch-${pc.channel}">${pc.channel.toUpperCase()}</span><br><span class="q-title">${esc(pc.title)}</span></span>
        <span class="q-meta"><span class="out out-${o}">${o.toUpperCase()}</span><span>${pc.duration ? pc.duration.toFixed(1) + "s" : ""}</span></span>
      </li>`;
    }).join("");
    $("#queue-count").textContent = `${Object.values(S.perCase).filter((p) => p.done).length} / ${S.order.length} done`;
    $$("#queue li[data-tc]").forEach((li) => li.addEventListener("click", () => {
      S.viewTc = li.dataset.tc; S.follow = false;
      const keys = Object.keys(S.perCase[S.viewTc].agents);
      if (!S.viewAgent || !S.perCase[S.viewTc].agents[S.viewAgent]) S.viewAgent = keys[keys.length - 1] || null;
      $("#pipeline-case").textContent = `Viewing ${S.viewTc}: ${S.perCase[S.viewTc].title}`;
      paintAllCards(S.viewTc); showOutput(); renderQueue();
    }));
  }

  // ------------------------------------------------------------------ log
  const AG_SHORT = () => Object.fromEntries((S.meta?.agents || []).map((a) => [a.key, a.name]));
  function log(level, tc, agent, msg) {
    const t = new Date();
    const entry = { level, tc: tc || "", agent: agent || "", msg, time: t.toTimeString().slice(0, 8) };
    S.logs.push(entry);
    if (S.logs.length > 3000) S.logs.splice(0, S.logs.length - 3000);
    if (matchesLog(entry)) appendLog(entry);
  }
  function matchesLog(e) {
    const lv = $("#log-level").value, ag = $("#log-agent").value, q = $("#log-search").value.trim().toLowerCase();
    return (!lv || e.level === lv) && (!ag || e.agent === ag) && (!q || `${e.tc} ${e.msg}`.toLowerCase().includes(q));
  }
  function appendLog(e) {
    const box = $("#log");
    const names = AG_SHORT();
    const div = document.createElement("div");
    div.className = `ln ${e.level}`;
    div.innerHTML = `<span class="l-time">${e.time}</span><span class="l-tc">${esc(e.tc)}</span><span class="l-ag">${esc(names[e.agent] || e.agent)}</span><span class="l-msg">${esc(e.msg)}</span>`;
    box.appendChild(div);
    while (box.childElementCount > 1500) box.firstElementChild.remove();
    if ($("#log-follow").checked) box.scrollTop = box.scrollHeight;
  }
  function rerenderLog() { $("#log").innerHTML = ""; S.logs.filter(matchesLog).slice(-1500).forEach(appendLog); }
  ["#log-level", "#log-agent"].forEach((s) => $(s).addEventListener("change", rerenderLog));
  $("#log-search").addEventListener("input", rerenderLog);
  $("#log-clear").addEventListener("click", () => { S.logs = []; $("#log").innerHTML = ""; });

  // ------------------------------------------------------------------ KPIs
  function renderKpis() {
    const c = S.counts, done = c.passed + c.failed + c.error + c.blocked;
    $("#k-passed").textContent = c.passed; $("#k-failed").textContent = c.failed;
    $("#k-error").textContent = c.error; $("#k-blocked").textContent = c.blocked;
    $("#k-rate").textContent = done ? `pass rate ${Math.round((c.passed / done) * 100)}%` : "pass rate -";
    const pct = S.order.length ? Math.round((done / S.order.length) * 100) : 0;
    $("#prog-bar").style.width = `${pct}%`; $("#prog-pct").textContent = `${pct}%`;
  }
  function tick() { $("#k-elapsed").textContent = `${((performance.now() - S.t0) / 1000).toFixed(1)}s`; }

  // ------------------------------------------------------------------ charts
  Chart.defaults.font.family = '"Segoe UI", system-ui, sans-serif';
  function baseOpts(horizontal = false, stacked = false) {
    const grid = css("--grid"), text = css("--text-2");
    return {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      indexAxis: horizontal ? "y" : "x",
      plugins: { legend: { labels: { color: text, boxWidth: 12, boxHeight: 12 } }, tooltip: { mode: "index", intersect: false } },
      scales: {
        x: { stacked, grid: { color: horizontal ? grid : "transparent" }, ticks: { color: text }, border: { color: grid } },
        y: { stacked, grid: { color: horizontal ? "transparent" : grid }, ticks: { color: text, precision: 0 }, border: { color: grid }, beginAtZero: true },
      },
    };
  }
  function bar(ctx, labels, datasets, opts) { return new Chart(ctx, { type: "bar", data: { labels, datasets }, options: opts }); }
  const STATUS_SERIES = () => [
    { label: "✔ Passed", key: "passed", color: css("--good") },
    { label: "✖ Failed", key: "failed", color: css("--critical") },
    { label: "⚠ Error", key: "error", color: css("--serious") },
    { label: "⛔ Blocked", key: "blocked", color: css("--warning") },
  ];
  function rebuildCharts() {
    Object.values(S.charts).forEach((c) => c.destroy()); S.charts = {};
    const ss = STATUS_SERIES();
    const oo = baseOpts(); oo.plugins.legend.display = false;
    S.charts.outcome = bar($("#outcome-chart"), ss.map((s) => s.label),
      [{ data: ss.map((s) => S.counts[s.key]), backgroundColor: ss.map((s) => s.color), borderRadius: 4, maxBarThickness: 46 }], oo);
    const ao = baseOpts(true); ao.plugins.legend.display = false;
    ao.scales.x.title = { display: true, text: "seconds", color: css("--text-2") };
    const names = AG_SHORT();
    const keys = S.meta ? S.meta.pipeline : [];
    S.charts.agent = bar($("#agent-chart"), keys.map((k) => names[k] || k),
      [{ label: "seconds", data: keys.map((k) => +(S.agentSecs[k] || 0).toFixed(2)), backgroundColor: css("--s1"), borderRadius: 4, maxBarThickness: 18 }], ao);
    renderHistoryCharts();
  }
  function updateCharts() {
    if (S.charts.outcome) { S.charts.outcome.data.datasets[0].data = STATUS_SERIES().map((s) => S.counts[s.key]); S.charts.outcome.update(); }
    if (S.charts.agent) { S.charts.agent.data.datasets[0].data = S.meta.pipeline.map((k) => +(S.agentSecs[k] || 0).toFixed(2)); S.charts.agent.update(); }
  }

  // ------------------------------------------------------------------ run
  $("#run-btn").addEventListener("click", startRun);
  $("#stop-btn").addEventListener("click", async () => {
    if (!S.runId) return;
    $("#stop-btn").disabled = true; $("#prog-label").textContent = "Stopping…";
    try { await getJSON(`/api/run/${S.runId}/stop`, { method: "POST" }); } catch { /* stream close handles it */ }
  });

  function startRun() {
    if (S.running || !S.selected.size) return;
    const ids = [...S.selected];
    const url = `/api/run/stream?ids=${encodeURIComponent(ids.join(","))}&speed=${$("#speed").value}&headed=${$("#headed").checked}`;
    Object.assign(S, { perCase: {}, order: [], currentTc: null, viewTc: null, viewAgent: null, follow: true, summary: null,
      counts: { passed: 0, failed: 0, error: 0, blocked: 0 }, agentSecs: {} });
    S.running = true; S.t0 = performance.now();
    $("#run-btn").disabled = true; $("#stop-btn").disabled = false; $("#summary-card").hidden = true;
    $("#prog-bar").classList.add("running");
    $("#fa-table tbody").innerHTML = `<tr><td colspan="4" class="muted">No failures yet.</td></tr>`;
    resetCards(); renderKpis(); updateCharts();
    clearInterval(S.timer); S.timer = setInterval(tick, 100);
    S.es = new EventSource(url);
    S.es.onmessage = (m) => { try { handle(JSON.parse(m.data)); } catch (e) { console.error(e); } };
    S.es.onerror = () => { if (S.running) { log("error", "", "", "Event stream closed unexpectedly."); finishRun(); } };
  }

  function finishRun() {
    S.running = false;
    if (S.es) { S.es.close(); S.es = null; }
    clearInterval(S.timer); tick();
    $("#prog-bar").classList.remove("running");
    $("#stop-btn").disabled = true; $("#run-btn").disabled = S.selected.size === 0;
  }

  function handle(ev) {
    switch (ev.type) {
      case "run_start": {
        S.runId = ev.run_id;
        S.order = ev.cases.map((c) => c.id);
        ev.cases.forEach((c) => { S.perCase[c.id] = { ...c, agents: {}, outcome: "queued" }; });
        $("#k-total").textContent = ev.total; $("#k-total-sub").textContent = "in this run";
        $("#k-run").textContent = ev.run_id;
        $("#prog-label").textContent = `${ev.run_id} started: ${ev.total} test case(s)`;
        log("event", "", "", `▶ ${ev.run_id} started with ${ev.total} test case(s)${ev.headed ? " (headed browser)" : ""}`);
        renderQueue(); break;
      }
      case "case_start": {
        S.currentTc = ev.tc;
        const pc = S.perCase[ev.tc]; pc.outcome = "running";
        if (S.follow || !S.viewTc) { S.viewTc = ev.tc; S.follow = true; S.viewAgent = null; resetCards(); }
        $("#pipeline-case").textContent = `Running ${ev.tc}: ${ev.title}`;
        $("#prog-label").textContent = `Test case ${ev.index + 1} / ${S.order.length}: ${ev.tc} (${ev.source === "framework" ? "REAL" : "SIMULATED"})`;
        log("event", ev.tc, "", `── ${ev.tc} ${ev.title} [${ev.source === "framework" ? "REAL" : "SIMULATED"}]`);
        renderQueue(); showOutput(); break;
      }
      case "agent_start": {
        const st = (S.perCase[ev.tc].agents[ev.agent] = { status: "running", activity: "Starting…", progress: 3 });
        if (S.viewTc === ev.tc) { paintCard(ev.agent, st); if (S.follow) { S.viewAgent = ev.agent; highlightCard(); showOutput(); } }
        log("info", ev.tc, ev.agent, `${ev.name} agent started`); break;
      }
      case "agent_log": {
        const st = S.perCase[ev.tc].agents[ev.agent] ||= { status: "running" };
        st.activity = ev.msg; st.progress = ev.progress ?? st.progress;
        if (S.viewTc === ev.tc) { paintCard(ev.agent, st); if (S.viewAgent === ev.agent) showOutput(); }
        log(ev.level || "info", ev.tc, ev.agent, ev.msg); break;
      }
      case "agent_done": {
        const st = (S.perCase[ev.tc].agents[ev.agent] = { ...(S.perCase[ev.tc].agents[ev.agent] || {}),
          status: ev.status, output: ev.output, duration: ev.duration, progress: 100,
          activity: ev.output?.title || STATUS_LABEL[ev.status] });
        if (ev.duration) S.agentSecs[ev.agent] = (S.agentSecs[ev.agent] || 0) + ev.duration;
        if (S.viewTc === ev.tc) {
          paintCard(ev.agent, st);
          if (S.follow && ev.status !== "skipped") { S.viewAgent = ev.agent; highlightCard(); }
          showOutput();
        }
        if (ev.status !== "skipped") log(ev.status === "done" ? "ok" : "error", ev.tc, ev.agent, `${STATUS_LABEL[ev.status]}: ${ev.output?.title || ""} (${(ev.duration || 0).toFixed(1)}s)`);
        updateCharts(); break;
      }
      case "case_done": {
        const pc = S.perCase[ev.tc];
        Object.assign(pc, { outcome: ev.outcome, duration: ev.duration, category: ev.category, message: ev.message, done: true });
        if (S.counts[ev.outcome] !== undefined) S.counts[ev.outcome] += 1;
        log(ev.outcome === "passed" ? "ok" : "error", ev.tc, "", `${OUTCOME_ICON[ev.outcome] || ""} ${ev.tc} ${ev.outcome.toUpperCase()}${ev.category ? " · " + ev.category : ""} (${ev.duration.toFixed(1)}s)`);
        if (ev.outcome !== "passed") addFailure(ev, pc);
        renderQueue(); renderKpis(); updateCharts(); break;
      }
      case "run_done": {
        S.summary = ev;
        $("#prog-label").textContent = ev.stopped ? `${ev.run_id} stopped by user` : `${ev.run_id} finished in ${ev.duration.toFixed(1)}s`;
        log("event", "", "", `■ ${ev.run_id} ${ev.stopped ? "stopped" : "finished"}: ${ev.passed} passed, ${ev.failed} failed, ${ev.error} error, ${ev.blocked} blocked`);
        finishRun(); renderSummary(ev); loadReports(); break;
      }
      default: break;
    }
  }

  function addFailure(ev, pc) {
    const tb = $("#fa-table tbody");
    if (tb.querySelector(".muted")) tb.innerHTML = "";
    const tone = ev.outcome === "blocked" ? "warning" : ev.outcome === "error" ? "serious" : "critical";
    tb.insertAdjacentHTML("beforeend", `<tr><td><b>${esc(ev.tc)}</b><br><span class="out out-${ev.outcome}">${OUTCOME_ICON[ev.outcome]} ${ev.outcome.toUpperCase()}</span></td>
      <td><span class="badge badge-${tone}">${esc(ev.category || "-")}</span></td>
      <td><span class="src ${pc.source === "framework" ? "src-real" : "src-sim"}">${pc.source === "framework" ? "REAL" : "SIM"}</span></td>
      <td style="max-width:420px;word-break:break-word">${esc((ev.message || "").slice(0, 300))}</td></tr>`);
  }

  function renderSummary(ev) {
    $("#summary-card").hidden = false;
    $("#summary-run").textContent = `${ev.run_id} · ${ev.real} real / ${ev.simulated} simulated`;
    const ok = !ev.failed && !ev.error && !ev.blocked && !ev.stopped;
    const b = $("#summary-banner");
    b.className = `banner ${ok ? "good" : "bad"}`;
    b.textContent = `${ok ? "✔ All test cases passed." : ev.stopped ? "■ Run stopped before completion." : "✖ Some test cases did not pass."} ` +
      `${ev.passed} passed · ${ev.failed} failed · ${ev.error} error · ${ev.blocked} blocked · ${ev.duration.toFixed(1)}s total.`;
    $("#summary-table tbody").innerHTML = ev.cases.map((c) => `<tr>
      <td><b>${esc(c.id)}</b></td><td>${esc(c.title)}</td><td><span class="ch ch-${c.channel}">${c.channel.toUpperCase()}</span></td>
      <td><span class="src ${c.source === "framework" ? "src-real" : "src-sim"}">${c.source === "framework" ? "REAL" : "SIMULATED"}</span></td>
      <td><span class="out out-${c.outcome}">${OUTCOME_ICON[c.outcome] || ""} ${esc(c.outcome.toUpperCase())}</span></td>
      <td>${esc(c.category || "-")}</td><td class="num">${(c.duration || 0).toFixed(1)}s</td></tr>`).join("");
  }
  $("#download-btn").addEventListener("click", () => {
    if (!S.summary) return;
    const blob = new Blob([JSON.stringify(S.summary, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `${S.summary.run_id}.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  // ------------------------------------------------------------------ features tab
  const PRINCIPLES = [
    ["📜", "Specification first", "Test design reads only an approved snapshot; automation reads only approved test cases.", "--s1"],
    ["🎯", "Single source of truth", "spec.yaml + acceptance_criteria.yaml. Every artifact stores spec ID, version and AC hash.", "--s7"],
    ["🔗", "Traceability", "REQ → SPEC → AC → TS → TC → script → EXEC, enforced by pytest markers on every test.", "--s3"],
    ["🛡️", "Deterministic validation", "Rule gates block vague, conflicting, invented or dropped acceptance criteria.", "--s4"],
    ["👤", "Human approvals", "Three human-only gates (spec, test cases, scripts), each bound to a content hash.", "--s6"],
    ["♻️", "Change impact", "Only impacted test cases and script regions are regenerated and re-executed.", "--s2"],
    ["🚫", "No fabricated results", "Pass/fail comes only from the pytest plugin; AI analysis is labelled probable.", "--s8"],
    ["🔐", "Secrets stay out", "Credentials come from .env via ${env:VAR}; masked in audit and API logs.", "--s5"],
  ];
  const SAFETY = [
    ["👤", "Human-only approvals", "Approvers named like an AI/agent/system are refused; edits after approval invalidate it."],
    ["🔒", "Restricted execution", "A script runs only if approved and its region hash is unchanged."],
    ["⏱", "Timeouts", "Whole-run and per-test timeouts."],
    ["🏭", "Production guard", "Production environments are blocked unless --allow-production is passed."],
    ["🗑", "Destructive operations", "DELETE tests are skipped unless the environment or --allow-destructive allows them."],
    ["🧹", "Code validation", "Syntax, forbidden imports/calls (subprocess, eval, os.system), hard-coded secrets, trace markers."],
    ["📝", "Audit log", "Every agent, crew, flow, approval and execution event in audit.jsonl, secrets masked."],
  ];
  const AGENT_COLORS = ["--s1", "--s1", "--s1", "--s3", "--s3", "--s3", "--s7", "--s7", "--s6", "--s8", "--s5", "--s2"];
  const FLOW_COLORS = ["--s1", "--s3", "--s7", "--s6", "--s2"];

  function renderFeatures() {
    $("#principles").innerHTML = PRINCIPLES.map(([ic, t, d, c]) => `<div class="principle" style="--c:var(${c})"><h3>${ic} ${esc(t)}</h3><p>${esc(d)}</p></div>`).join("");
    $("#agent-cards").innerHTML = S.meta.agents.map((a, i) => `<div class="agent-card" style="--c:var(${AGENT_COLORS[i] || "--s7"})">
      <div class="ac-head"><span style="font-size:20px">${a.icon}</span><div><span class="ac-num">AGENT ${i + 1} · ${esc(a.flow)}</span><h3>${esc(a.role || a.name)}</h3></div></div>
      <p>${esc(a.goal || "")}</p><div class="ac-out">Output contract: <b>${esc(a.output)}</b></div></div>`).join("");
    $("#flow-cards").innerHTML = S.meta.flows.map((f, i) => `<div class="flow-card" style="--c:var(${FLOW_COLORS[i]})">
      <span class="fc-num">${f.id}</span><h3>Flow ${f.id} · ${esc(f.name)}</h3>
      <ol>${f.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
      <div class="st">${f.statuses.map((s, j) => `<span class="out ${j === 0 ? "out-passed" : "out-blocked"}">${esc(s)}</span>`).join("")}</div>
      <div class="cmd"><code>${esc(f.command)}</code><button data-copy="${esc(f.command)}">Copy</button></div></div>`).join("");
    $$("[data-copy]").forEach((b) => b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = "Copied"; } catch { b.textContent = "Select & copy"; }
      setTimeout(() => (b.textContent = "Copy"), 1500);
    }));
    $("#safety-list").innerHTML = SAFETY.map(([ic, t, d]) => `<li><span style="font-size:18px">${ic}</span><div><b>${esc(t)}</b><span>${esc(d)}</span></div></li>`).join("");
  }

  const LIFECYCLE = `flowchart LR
  R["📄 Requirement"]:::input --> A["🤖 Requirement Analysis"]:::agent --> S["🤖 Spec Architect"]:::agent
  S --> V{"🛡️ Spec validation"}:::gate
  V -- errors --> C["❓ Clarification"]:::stop
  V -- passed --> H1{{"👤 Approve spec"}}:::human
  H1 --> TD["🤖 Test Design + Cases + Data"]:::agent --> CV{"🛡️ Coverage"}:::gate
  CV --> H2{{"👤 Approve test cases"}}:::human
  H2 --> AD["🤖 UI + API Automation Design"]:::agent --> G["⚙️ Code renderer"]:::engine --> CK{"🛡️ Code validation"}:::gate
  CK --> H3{{"👤 Approve scripts"}}:::human
  H3 --> X["▶️ Pytest + Playwright + HTTPX"]:::run --> FA["🤖 Failure Analysis"]:::agent --> RP["📊 Reporting"]:::report
  classDef input fill:#dbeafe,stroke:#2563eb,color:#0f172a
  classDef agent fill:#ede9fe,stroke:#7c3aed,color:#0f172a
  classDef gate fill:#fef3c7,stroke:#d97706,color:#0f172a
  classDef human fill:#dcfce7,stroke:#16a34a,color:#0f172a
  classDef stop fill:#fee2e2,stroke:#dc2626,color:#0f172a
  classDef engine fill:#e0f2fe,stroke:#0284c7,color:#0f172a
  classDef run fill:#ccfbf1,stroke:#0d9488,color:#0f172a
  classDef report fill:#fce7f3,stroke:#db2777,color:#0f172a`;

  async function renderMermaid() {
    if (S.mermaidDone || !window.mermaid) return;
    try {
      mermaid.initialize({ startOnLoad: false, theme: currentTheme() === "dark" ? "dark" : "default", securityLevel: "strict" });
      const { svg } = await mermaid.render(`lc${Date.now()}`, LIFECYCLE);
      $("#lifecycle-diagram").innerHTML = svg; S.mermaidDone = true;
    } catch (e) { $("#lifecycle-diagram").textContent = `Diagram unavailable (${e.message || e}). Mermaid loads from a CDN.`; }
  }

  function renderSnapshot(snap) {
    S.snapshot = snap;
    const pill = $("#fw-pill");
    if (!snap.available) { pill.className = "pill pill-bad"; pill.textContent = "Framework not found"; pill.title = snap.path; return; }
    pill.className = "pill pill-ok"; pill.textContent = `● Framework connected · ${snap.specs.length} specs`; pill.title = snap.path;
    $("#snap-path").textContent = snap.path;
    $("#spec-table tbody").innerHTML = snap.specs.map((s) => `<tr><td><b>${esc(s.id)}</b></td><td>${esc(s.title)}</td><td>v${esc(s.version)}</td>
      <td><span class="out ${s.status === "APPROVED" ? "out-passed" : "out-blocked"}">${esc(s.status)}</span></td><td class="num">${s.acs}</td><td class="num">${s.test_cases}</td>
      <td>${["spec", "test_cases", "scripts"].map((st) => `<span class="out ${s.approvals.includes(st) ? "out-passed" : "out-queued"}">${s.approvals.includes(st) ? "✔" : "–"} ${st}</span>`).join(" ")}</td>
      <td>${s.validation_passed ? '<span class="out out-passed">✔ passed</span>' : '<span class="out out-failed">✖ blocked</span>'} <span class="muted">${s.findings} finding(s)</span></td></tr>`).join("");
  }

  // ------------------------------------------------------------------ reports tab
  let reportData = { runs: [], execs: [] };
  async function loadReports() {
    try {
      const [runs, snap] = await Promise.all([getJSON("/api/runs"), getJSON("/api/snapshot")]);
      reportData = { runs, execs: snap.executions || [] };
      $("#runs-table tbody").innerHTML = runs.length ? runs.map((r) => `<tr><td><b>${esc(r.run_id)}</b></td><td>${esc((r.started_at || "").replace("T", " ").slice(0, 19))}</td>
        <td class="num">${r.total}</td><td>${r.real} / ${r.simulated}</td><td class="num">${r.passed}</td><td class="num">${r.failed}</td><td class="num">${r.error}</td><td class="num">${r.blocked}</td>
        <td class="num">${(r.duration || 0).toFixed(1)}s</td><td>${r.stopped ? '<span class="out out-blocked">stopped</span>' : '<span class="out out-passed">complete</span>'}</td></tr>`).join("")
        : `<tr><td colspan="10" class="muted">No dashboard runs yet.</td></tr>`;
      $("#exec-table tbody").innerHTML = reportData.execs.length ? [...reportData.execs].reverse().map((e) => `<tr><td><b>${esc(e.id)}</b></td><td>${esc((e.started_at || "").replace("T", " ").slice(0, 19))}</td>
        <td class="num">${e.total}</td><td class="num">${e.passed}</td><td class="num">${e.failed}</td><td class="num">${e.skipped}</td><td class="num">${e.error}</td></tr>`).join("")
        : `<tr><td colspan="7" class="muted">No framework executions found.</td></tr>`;
      renderHistoryCharts();
    } catch (e) { console.error(e); }
  }
  $("#refresh-reports").addEventListener("click", loadReports);
  function renderHistoryCharts() {
    ["runs", "exec"].forEach((k) => { if (S.charts[k]) { S.charts[k].destroy(); delete S.charts[k]; } });
    const ss = STATUS_SERIES();
    const runs = [...reportData.runs].reverse().slice(-15);
    S.charts.runs = bar($("#runs-chart"), runs.map((r) => r.run_id),
      ss.map((s) => ({ label: s.label, data: runs.map((r) => r[s.key] || 0), backgroundColor: s.color, borderColor: css("--surface"), borderWidth: 1, borderRadius: 3, maxBarThickness: 34 })), baseOpts(false, true));
    const ex = reportData.execs;
    const xs = [ss[0], ss[1], ss[2]];
    S.charts.exec = bar($("#exec-chart"), ex.map((e) => e.id),
      xs.map((s) => ({ label: s.label, data: ex.map((e) => e[s.key] || 0), backgroundColor: s.color, borderColor: css("--surface"), borderWidth: 1, borderRadius: 3, maxBarThickness: 34 })), baseOpts(false, true));
  }

  // ------------------------------------------------------------------ init
  async function init() {
    try {
      const [meta, cases, snap] = await Promise.all([getJSON("/api/meta"), getJSON("/api/testcases"), getJSON("/api/snapshot")]);
      S.meta = meta; S.cases = cases;
      [...cases.framework, ...cases.simulated].forEach((c) => { S.byId[c.id] = c; });
      $("#log-agent").innerHTML += meta.pipeline.map((k) => `<option value="${k}">${esc(meta.agents.find((a) => a.key === k)?.name || k)}</option>`).join("");
      renderPipeline(); renderFeatures(); renderSnapshot(snap);
      let saved = [];
      try { saved = JSON.parse(storage.get("sdd-selected") || "[]"); } catch { saved = []; }
      saved.filter((i) => S.byId[i]).forEach((i) => S.selected.add(i));
      if (!S.selected.size) applyPreset("mix");
      renderPicker(); renderSelected(); rebuildCharts(); loadReports();
      log("event", "", "", `Dashboard ready: ${cases.framework.length} real + ${cases.simulated.length} simulated test cases available.`);
      const tab = storage.get("sdd-tab");
      if (tab && tab !== "live") $(`.tab[data-tab="${tab}"]`)?.click();
    } catch (e) {
      $("#fw-pill").className = "pill pill-bad"; $("#fw-pill").textContent = "Server unavailable";
      log("error", "", "", `Initialisation failed: ${e.message}`);
    }
  }
  init();
})();
