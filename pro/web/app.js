"use strict";
// LOL Pro terminal front end. All external text (news, alerts) is inserted with textContent.

const $ = (id) => document.getElementById(id);
const S = { state: null, token: null, page: "overview", newsFilter: "all", chat: [], busy: false,
  index: "nifty50", view: "heat", stock: null, stockData: null, range: "1d",
  acct: null, watch: "stocks", book: "positions", chain: null, chainExpiry: null, ticket: null };
const TITLES = { overview: "Overview", markets: "Markets", trade: "Trade (virtual money)", news: "Live news", assistant: "Assistant",
  performance: "Performance", alerts: "Alerts & health", strategy: "How it works" };
const REGIME_LABEL = { uptrend: "Uptrend", transition: "Transition", range: "Range", downtrend: "Downtrend", stress: "Stress", warmup: "Warm-up" };

function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k === "style") n.style.cssText = v; // CSSOM, allowed by the page's CSP
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) n.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return n;
}
const fill = (node, ...kids) => { node.replaceChildren(...kids.flat().filter((k) => k != null)); };
const inr = (x, d = 0) => x == null || Number.isNaN(x) ? "—" : "₹" + Number(x).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
const num = (x, d = 2) => x == null ? "—" : Number(x).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
const pct = (x) => x == null ? "—" : (x > 0 ? "+" : "") + Number(x).toFixed(2) + "%";
const sign = (x) => x > 0 ? "up" : x < 0 ? "down" : "";
function ago(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return Math.round(s / 60) + " min ago";
  if (s < 86400) return Math.round(s / 3600) + " h ago";
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
const regimeChip = (g) => el("span", { class: `regime r-${g || "warmup"}`, text: REGIME_LABEL[g] || g || "—" });

// ------------------------------------------------------------------ network
async function session() {
  const r = await fetch("api/session"); S.token = (await r.json()).token;
}
async function post(path, body) {
  if (!S.token) await session();
  let r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Session-Token": S.token }, body: JSON.stringify(body || {}) });
  if (r.status === 403) { await session(); r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Session-Token": S.token }, body: JSON.stringify(body || {}) }); }
  if (r.status === 401) { showLogin(true); throw new Error("Please sign in again"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.json();
}
function showLogin(show) {
  $("login").hidden = !show;
  if (show) setTimeout(() => $("loginKey").focus(), 50);
}
async function load() {
  try {
    const r = await fetch("api/state", { cache: "no-store" });
    if (r.status === 401) { showLogin(true); return; }
    if (!r.ok) throw new Error(r.statusText);
    showLogin(false);
    S.state = await r.json();
    $("offline").hidden = true;
    render();
  } catch (e) {
    $("offline").hidden = false;
    $("updated").textContent = "Offline";
  }
}

// ------------------------------------------------------------------- charts
function lineChart(node, series, opts = {}) {
  const data = series.filter((s) => s.values.length > 1);
  if (!data.length) { fill(node, el("div", { class: "empty", text: opts.empty || "No data yet" })); return; }
  const W = Math.max(node.clientWidth, 280), H = node.clientHeight || 220, L = 56, R = 10, T = 10, B = 24;
  const all = data.flatMap((s) => s.values.filter((v) => v != null));
  let lo = Math.min(...all, ...(opts.refs || []).map((r) => r.y)), hi = Math.max(...all, ...(opts.refs || []).map((r) => r.y));
  const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
  const n = Math.max(...data.map((s) => s.values.length));
  const x = (i) => L + (i * (W - L - R)) / (n - 1), y = (v) => T + ((hi - v) * (H - T - B)) / (hi - lo);
  const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", opts.label || "chart");
  const mk = (t, a) => { const e = document.createElementNS(ns, t); for (const k in a) e.setAttribute(k, a[k]); return e; };
  const g = mk("g", { class: "grid" });
  for (let k = 0; k <= 4; k++) {
    const v = lo + ((hi - lo) * k) / 4, yy = y(v);
    g.append(mk("line", { x1: L, x2: W - R, y1: yy, y2: yy }));
    const t = mk("text", { x: L - 8, y: yy + 4, "text-anchor": "end" }); t.textContent = opts.fmt ? opts.fmt(v) : num(v, 0); g.append(t);
  }
  const labels = opts.labels || [];
  [0, Math.floor((n - 1) / 2), n - 1].forEach((i) => {
    if (labels[i] == null) return;
    const t = mk("text", { x: x(i), y: H - 6, "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle" }); t.textContent = labels[i]; g.append(t);
  });
  svg.append(g);
  for (const r of opts.refs || []) {
    svg.append(mk("line", { x1: L, x2: W - R, y1: y(r.y), y2: y(r.y), stroke: r.color, "stroke-dasharray": "4 4", "stroke-width": 1.2 }));
    const t = mk("text", { x: W - R, y: y(r.y) - 4, "text-anchor": "end" }); t.textContent = r.label; svg.append(t);
  }
  for (const s of data) {
    let d = "";
    s.values.forEach((v, i) => { if (v != null) d += (d ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1); });
    if (s.area) {
      svg.append(mk("path", { d: d + `L${x(s.values.length - 1)} ${H - B}L${x(0)} ${H - B}Z`, fill: s.color, opacity: 0.08, stroke: "none" }));
    }
    svg.append(mk("path", { d, fill: "none", stroke: s.color, "stroke-width": s.width || 2, "stroke-linejoin": "round" }));
  }
  fill(node, svg);
}
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

// ------------------------------------------------------------------- render
function render() {
  const st = S.state; if (!st) return;
  $("updated").textContent = "Updated " + new Date(st.now).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
  const sess = st.market?.session || {};
  const open = sess.reason === "regular_session";
  const ms = $("marketStatus");
  ms.textContent = open ? "Market open" : ({ weekend: "Weekend — market closed", holiday: `Holiday${sess.holiday ? " — " + sess.holiday : ""}`, pre_open: "Pre-open", post_close: "Market closed" }[sess.reason] || "Market closed");
  ms.className = "chip " + (open ? "up" : "");
  const unread = (st.alerts || []).filter((a) => !a.read && ["trade", "warning", "error", "critical"].includes(a.level)).length;
  $("alertCount").hidden = !unread; $("alertCount").textContent = unread;
  $("newsDot").hidden = st.news?.risk?.level !== "high";
  renderOverview(st); renderMarkets(st); renderNews(st); renderPerformance(st); renderAlerts(st);
  if (S.page === "trade") renderWatch();
  $("aiMode").textContent = st.health?.assistant ? "Powered by Claude · uses the terminal's live data" : "Basic mode · set ANTHROPIC_API_KEY for the full AI assistant";
}

const ACTION_TEXT = {
  HOLD: ["Holding a position", "accent"], BUY_AT_NEXT_OPEN: ["Opening a trade at the next open", "up"],
  SELL_AT_NEXT_OPEN: ["Closing the trade at the next open", "warn"], SELL_SHORT_AT_NEXT_OPEN: ["Short signal (not traded)", "warn"],
  STAND_ASIDE: ["Waiting in cash", ""],
};

function renderOverview(st) {
  const plan = st.plan || {}, opt = st.options_account || {}, mkt = st.market || {}, risk = st.news?.risk || {};
  const [head, tone] = ACTION_TEXT[plan.action] || ["Waiting for the first decision", ""];
  let headline = head;
  if (plan.action === "HOLD" && opt.position) headline = `Holding ${opt.position.label}`;
  else if (plan.action === "HOLD" && opt.pending === "OPEN") headline = "Trend signal active: opening a bull put spread at the next open";
  else if (plan.action === "HOLD") headline = "Trend signal active";
  $("heroHeadline").textContent = headline;
  $("heroReason").textContent = plan.reason ? plan.reason.charAt(0).toUpperCase() + plan.reason.slice(1) + "." : "The engine runs after the market closes.";
  fill($("heroTags"), regimeChip(plan.regime),
    el("span", { class: "chip " + tone, text: (plan.action || "—").replaceAll("_", " ").toLowerCase() }),
    plan.strategy || plan.position?.strategy ? el("span", { class: "chip", text: "Signal: " + (plan.strategy || plan.position.strategy).replaceAll("_", " ") }) : null,
    opt.pending ? el("span", { class: "chip warn", text: `Pending: ${opt.pending.toLowerCase()} spread at next open` }) : null,
    plan.vetoed_signal ? el("span", { class: "chip down", text: "Entry vetoed by news" }) : null);
  $("asOf").textContent = plan.as_of_bar ? `Last decision on ${plan.as_of_bar} close` : "";
  const now = new Date(st.now), weekday = now.getDay() % 6 !== 0;
  $("nextRun").textContent = weekday && now.getHours() * 60 + now.getMinutes() < 920 ? "Today 15:20 IST" : "Next trading day 15:20";

  const liveM = opt.position?.live_mark, m = liveM || opt.position?.mark;
  const eq = opt.live_equity ?? opt.equity, ret = opt.live_return_pct ?? opt.return_pct;
  $("kEquity").textContent = inr(eq);
  $("kEquitySub").textContent = ret != null ? `${pct(ret)} since ${opt.started || "start"}${liveM ? " · live" : ""}` : "Starts on the first run";
  $("kEquitySub").className = sign(ret);
  $("kOpen").textContent = m ? inr(m.pnl_rs) : opt.pending === "OPEN" ? "Opening at next open" : "No position";
  $("kOpen").className = m ? sign(m.pnl_rs) : "";
  $("kOpenSub").textContent = opt.position ? `${liveM?.session_open ? "live · " : ""}max loss ${inr(opt.position.max_loss_rs)}` : "";
  const n = mkt.nifty || {}, v = mkt.vix || {};
  $("kNifty").textContent = num(n.price); $("kNiftySub").textContent = `${pct(n.change_pct)} · ${n.as_of || ""}`; $("kNiftySub").className = sign(n.change_pct);
  $("kVix").textContent = num(v.price); $("kVixSub").textContent = pct(v.change_pct) + (v.price >= 25 ? " · stress" : v.price < 14 ? " · calm" : " · normal");
  $("kVixSub").className = sign(-v.change_pct);
  $("kRisk").textContent = risk.score == null ? "—" : `${risk.score}/100`;
  $("kRiskSub").textContent = risk.level ? `${risk.level} · ${risk.negative || 0} negative / ${risk.positive || 0} positive (3h)` : "";
  $("kRiskSub").className = risk.level === "high" ? "down" : risk.level === "elevated" ? "" : "up";

  const intr = mkt.nifty_intraday || [];
  const stop = plan.position?.stop;
  lineChart($("intradayChart"), [{ values: intr.map((p) => p.c), color: cssVar("--c-price"), area: true }], {
    labels: intr.map((p) => p.t), label: "Nifty intraday", empty: "Intraday data appears during market hours",
    refs: stop && intr.length && Math.abs(stop / intr[intr.length - 1].c - 1) < 0.04 ? [{ y: stop, color: cssVar("--down"), label: "stop " + num(stop, 0) }] : [],
  });
  $("intradayNote").textContent = intr.length ? `5-minute · ${n.as_of || ""}` : "5-minute";

  const pos = opt.position;
  $("posChip").textContent = pos ? `${pos.lots} lot${pos.lots > 1 ? "s" : ""}` : "Flat"; $("posChip").className = "chip " + (pos ? "accent" : "");
  if (!pos) {
    fill($("positionBody"), el("p", { class: "empty-state", text: opt.pending === "OPEN" ? "A bull put spread will open at the next market open." : "No open spread. The bot opens one only when the trend playbook gives a long signal." }));
  } else {
    const mk = pos.live_mark || pos.mark || {}, lo = -pos.max_loss_rs, hi = pos.credit_pts * 65 * pos.lots;
    const markNote = pos.live_mark
      ? (pos.live_mark.session_open ? `Live · Nifty ${num(mk.spot, 0)}, VIX ${num(mk.vix)} · updated ${new Date(pos.live_mark.updated).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`
        : `Market closed · valued at last Nifty ${num(mk.spot, 0)} and VIX ${num(mk.vix)}`)
      : `Valued at the ${mk.as_of || "last"} close`;
    const at = Math.max(0, Math.min(100, ((mk.pnl_rs - lo) / (hi - lo)) * 100));
    fill($("positionBody"),
      el("strong", { text: pos.label }),
      el("div", { class: "small " + (pos.live_mark?.session_open ? "live" : "muted"), text: markNote }),
      el("div", { class: "position-grid" },
        el("div", {}, el("span", { text: "Credit received" }), el("b", { text: `${num(pos.credit_pts)} pts · ${inr(pos.credit_pts * 65 * pos.lots)}` })),
        el("div", {}, el("span", { text: "Current P&L" }), el("b", { class: sign(mk.pnl_rs), text: inr(mk.pnl_rs) })),
        el("div", {}, el("span", { text: "Opened" }), el("b", { text: `${pos.opened} at Nifty ${num(pos.spot_at_entry, 0)}${pos.filled_live ? " (at the open)" : ""}` })),
        el("div", {}, el("span", { text: "Days to expiry" }), el("b", { text: `${mk.days_to_expiry ?? "—"} (rolls at 7)` })),
        el("div", {}, el("span", { text: "Safe while Nifty stays above" }), el("b", { text: num(pos.legs[0].K, 0) })),
        el("div", {}, el("span", { text: "Engine stop (index)" }), el("b", { text: stop ? num(stop, 0) : "—" }))),
      el("div", { class: "pnl-track", title: "Position between max loss and max profit" }, el("i", { style: `left:calc(${at}% - 2px)` })),
      el("div", { class: "pnl-labels" }, el("span", { text: "Max loss " + inr(lo) }), el("span", { text: "Max profit " + inr(hi) })));
  }
  const alerts = (st.alerts || []).filter((a) => a.level !== "info").slice(0, 4);
  fill($("ovAlerts"), alerts.length ? alerts.map(alertRow) : el("li", { class: "muted", text: "No alerts. Everything is running normally." }));
  const moving = (st.news?.items || []).filter((i) => i.impact >= 2).slice(0, 5);
  fill($("ovNews"), moving.length ? moving.map((i) => el("li", {}, el("i", { class: "lvl " + (i.sentiment === "negative" ? "error" : i.sentiment === "positive" ? "trade" : "") }),
    el("div", { class: "t" }, el("a", { href: i.link, target: "_blank", rel: "noopener noreferrer", text: i.title }), el("span", { text: `${i.source} · ${ago(i.published)}` })))) :
    el("li", { class: "muted", text: "Loading news…" }));
}

function alertRow(a) {
  return el("li", {}, el("i", { class: "lvl " + a.level }), el("div", { class: "t" }, el("b", { text: a.title }), el("span", { text: `${a.message} · ${ago(a.time)}` })));
}

function sparkline(values, up) {
  const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 100 30"); svg.setAttribute("class", "spark"); svg.setAttribute("aria-hidden", "true");
  const v = (values || []).filter((x) => x != null);
  if (v.length > 1) {
    const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
    const d = v.map((x, i) => `${i ? "L" : "M"}${((i * 100) / (v.length - 1)).toFixed(1)} ${(28 - ((x - lo) * 26) / span).toFixed(1)}`).join("");
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", d); path.setAttribute("fill", "none"); path.setAttribute("stroke", up ? cssVar("--up") : cssVar("--down"));
    path.setAttribute("stroke-width", "1.6"); path.setAttribute("vector-effect", "non-scaling-stroke");
    svg.append(path);
  }
  return svg;
}
const S_prev = new Map();
function flashClass(sym, price) {
  const before = S_prev.get(sym); S_prev.set(sym, price);
  return before == null || before === price ? "" : price > before ? " flash-up" : " flash-down";
}
function heatColor(p) {
  const a = Math.min(1, Math.abs(p || 0) / 3);
  return p >= 0 ? `color-mix(in srgb, var(--up) ${Math.round(18 + a * 62)}%, var(--surface))` : `color-mix(in srgb, var(--down) ${Math.round(18 + a * 62)}%, var(--surface))`;
}

function renderMarkets(st) {
  const board = st.board || {}, idx = board.indices || {};
  const open = st.market?.session?.reason === "regular_session";
  fill($("indexCards"), Object.entries(idx).map(([key, x]) => el("button", {
    class: "card index-card" + (S.index === key ? " on" : ""), onclick: () => { S.index = key; renderMarkets(S.state); } },
    el("div", { class: "ic-top" }, el("span", { text: x.name }), open ? el("span", { class: "live", text: "Live" }) : el("span", { class: "muted small", text: "Closed" })),
    el("strong", { text: num(x.price) }),
    el("span", { class: sign(x.change_pct), text: `${x.change > 0 ? "+" : ""}${num(x.change)} (${pct(x.change_pct)})` }),
    sparkline(x.spark, (x.change_pct || 0) >= 0),
    el("div", { class: "ic-breadth" }, el("span", { class: "up", text: `▲ ${x.advancing ?? "—"}` }), el("span", { class: "down", text: `▼ ${x.declining ?? "—"}` }),
      el("span", { class: "muted", text: `${x.members} companies` })))));
  document.querySelectorAll("#indexTabs button").forEach((b) => b.classList.toggle("on", b.dataset.i === S.index));
  const q = $("boardSearch").value.trim().toLowerCase(), sort = $("boardSort").value;
  let list = (board.stocks || []).filter((x) => x.in.includes(S.index) && (!q || x.name.toLowerCase().includes(q) || x.symbol.toLowerCase().includes(q)));
  const by = { change: (a, b) => b.change_pct - a.change_pct, "-change": (a, b) => a.change_pct - b.change_pct,
    name: (a, b) => a.name.localeCompare(b.name), volume: (a, b) => (b.volume || 0) * (b.price || 0) - (a.volume || 0) * (a.price || 0) };
  list.sort(by[sort]);
  const when = board.updated ? new Date(board.updated).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
  $("boardNote").textContent = `${list.length} companies · ${open ? "updates every minute while the market is open" : "market closed: showing the last traded prices"} · refreshed ${when}. Click a company for its live chart.`;
  const flashes = new Map(list.map((x) => [x.symbol, flashClass(x.symbol, x.price)]));
  fill($("heatmap"), list.length ? list.map((x) => el("button", {
    class: "tile" + flashes.get(x.symbol), style: `background:${heatColor(x.change_pct)}`, title: `${x.name}: ${pct(x.change_pct)}`,
    onclick: () => openStock(x.symbol) },
    el("b", { text: x.symbol }), el("span", { text: num(x.price) }), el("em", { text: pct(x.change_pct) }))) :
    el("p", { class: "muted", text: board.updated ? "No companies match." : "Loading live prices…" }));
  fill($("boardTable").tBodies[0], list.map((x) => {
    const span = x.high - x.low, at = span > 0 ? ((x.price - x.low) / span) * 100 : 50;
    return el("tr", { class: "clickable", tabindex: "0", onclick: () => openStock(x.symbol), onkeydown: (e) => { if (e.key === "Enter") openStock(x.symbol); } },
      el("td", {}, el("b", { text: x.name }), el("div", { class: "small muted", text: `${x.symbol} · ${x.industry}` })),
      el("td", { class: "hide-sm" }, sparkline(x.spark, (x.change_pct || 0) >= 0)),
      el("td", { class: "num" + flashes.get(x.symbol), text: num(x.price) }),
      el("td", { class: "num " + sign(x.change_pct) }, el("div", { text: pct(x.change_pct) }), el("div", { class: "small", text: (x.change > 0 ? "+" : "") + num(x.change) })),
      el("td", { class: "hide-sm" }, el("div", { class: "range-bar", title: `${num(x.low)} – ${num(x.high)}` }, el("i", { style: `left:calc(${at}% - 2px)` }))));
  }));
  $("heatmap").hidden = S.view !== "heat"; $("listWrap").hidden = S.view !== "list";

  const rows = st.daily_chart || [];
  lineChart($("dailyChart"), [
    { values: rows.map((r) => r.e200), color: cssVar("--c-ema200"), width: 1.5 },
    { values: rows.map((r) => r.e50), color: cssVar("--c-ema50"), width: 1.5 },
    { values: rows.map((r) => r.c), color: cssVar("--c-price"), area: true },
  ], { labels: rows.map((r) => r.d), label: "Nifty daily with EMA 50 and EMA 200", empty: "Run the daily decision to load history" });
  fill($("regimeStrip"), rows.map((r) => el("i", { class: "r-" + r.g, title: `${r.d}: ${REGIME_LABEL[r.g] || r.g}` })));
  fill($("regimeLegend"), Object.entries(REGIME_LABEL).filter(([k]) => k !== "warmup").map(([k, v]) => el("span", {}, el("i", { class: "reg r-" + k }), " " + v)));
}

// ------------------------------------------------------------ company detail
let stockTimer = null;
async function openStock(symbol) {
  S.stock = symbol; S.stockData = null;
  $("drawer").hidden = false; $("drawerBackdrop").hidden = false; document.body.classList.add("no-scroll");
  const b = (S.state?.board?.stocks || []).find((x) => x.symbol === symbol);
  $("dName").textContent = b ? b.name : symbol; $("dMeta").textContent = b ? `${symbol} · ${b.industry}` : symbol;
  $("dPrice").textContent = b ? num(b.price) : "—"; fill($("dChart"), el("div", { class: "empty", text: "Loading live chart…" }));
  fill($("dNews"), el("li", { class: "muted", text: "Loading…" }));
  history.replaceState(null, "", "#markets/" + symbol);
  loadStock(); loadStockNews(symbol);
  clearInterval(stockTimer); stockTimer = setInterval(loadStock, 15000);
  $("drawerClose").focus();
}
function closeStock() {
  S.stock = null; clearInterval(stockTimer);
  $("drawer").hidden = true; $("drawerBackdrop").hidden = true; document.body.classList.remove("no-scroll");
  if (location.hash.startsWith("#markets/")) history.replaceState(null, "", "#markets");
}
async function loadStock() {
  const sym = S.stock; if (!sym) return;
  try {
    const r = await fetch("api/stock?symbol=" + encodeURIComponent(sym), { cache: "no-store" });
    const d = await r.json(); if (!r.ok) throw new Error(d.error);
    if (S.stock !== sym) return;
    S.stockData = d; renderStock();
  } catch (e) { if (!S.stockData) fill($("dChart"), el("div", { class: "empty", text: "Could not load: " + e.message })); }
}
function renderStock() {
  const d = S.stockData; if (!d) return;
  const open = S.state?.market?.session?.reason === "regular_session";
  $("dName").textContent = d.name;
  $("dMeta").textContent = `${d.symbol} · ${d.industry} · ${d.in.map((k) => (k === "nifty50" ? "Nifty 50" : "Sensex")).join(" & ")}`;
  $("dPrice").textContent = "₹" + num(d.price); $("dPrice").className = flashClass("detail:" + d.symbol, d.price).trim();
  $("dChange").textContent = `${d.change > 0 ? "+" : ""}${num(d.change)} (${pct(d.change_pct)})`; $("dChange").className = sign(d.change_pct);
  $("dLive").textContent = open ? "Live · refreshes every 15 s" : `Market closed · last trade ${d.time ? new Date(d.time).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : ""}`;
  $("dLive").className = open ? "live" : "muted small";
  fill($("dTrade"), el("a", { class: "btn buy-btn", href: "#trade/BUY/EQ:" + d.symbol, text: "Buy" }),
    el("a", { class: "btn sell-btn", href: "#trade/SELL/EQ:" + d.symbol, text: "Sell" }));
  const color = (d.change_pct || 0) >= 0 ? cssVar("--up") : cssVar("--down");
  if (S.range === "1y") {
    lineChart($("dChart"), [{ values: d.daily.map((x) => x.c), color: cssVar("--c-price"), area: true }], { labels: d.daily.map((x) => x.d), label: d.name + " one year" });
  } else {
    lineChart($("dChart"), [{ values: d.intraday.map((x) => x.c), color, area: true }], {
      labels: d.intraday.map((x) => x.t), label: d.name + " today", refs: d.prev_close ? [{ y: d.prev_close, color: cssVar("--muted"), label: "prev close " + num(d.prev_close) }] : [] });
  }
  fill($("dStats"), [["Open", num(d.open)], ["Prev close", num(d.prev_close)], ["Day high", num(d.high)], ["Day low", num(d.low)],
    ["Volume", d.volume != null ? Number(d.volume).toLocaleString("en-IN") : "—"], ["52-wk high", num(d.w52_high)]]
    .map(([k, v]) => el("div", {}, el("span", { text: k }), el("b", { text: v }))));
  const span = d.w52_high - d.w52_low;
  $("d52").style.left = `calc(${span > 0 ? ((d.price - d.w52_low) / span) * 100 : 50}% - 2px)`;
  $("d52lo").textContent = "Low " + num(d.w52_low); $("d52hi").textContent = "High " + num(d.w52_high);
}
async function loadStockNews(symbol) {
  try {
    const r = await fetch("api/company-news?symbol=" + encodeURIComponent(symbol));
    const d = await r.json(); if (!r.ok) throw new Error(d.error);
    if (S.stock === symbol) fill($("dNews"), d.items.length ? d.items.slice(0, 10).map(newsItem) : el("li", { class: "muted", text: "No recent news." }));
  } catch (e) { fill($("dNews"), el("li", { class: "muted", text: "News unavailable: " + e.message })); }
}

function renderNews(st) {
  const news = st.news || {}, risk = news.risk || {};
  const q = $("newsSearch").value.trim().toLowerCase();
  const f = S.newsFilter;
  const items = (news.items || []).filter((i) =>
    (f === "all" || (f === "moving" && i.impact >= 2) || (f === "negative" && i.sentiment === "negative") ||
      (f === "positive" && i.sentiment === "positive") || (f === "company" && i.companies.length)) &&
    (!q || i.title.toLowerCase().includes(q))).slice(0, 80);
  fill($("newsList"), items.length ? items.map(newsItem) : el("li", { class: "muted", text: "No headlines match." }));
  const score = risk.score ?? 0;
  $("riskFill").style.width = score + "%";
  $("riskFill").style.background = risk.level === "high" ? cssVar("--down") : risk.level === "elevated" ? cssVar("--warn") : cssVar("--up");
  $("riskValue").textContent = risk.score == null ? "—" : `${score}`;
  $("riskText").textContent = risk.level ? `${risk.level[0].toUpperCase() + risk.level.slice(1)} · ${risk.headlines} headlines in the last ${risk.window_hours} hours (${risk.negative} negative, ${risk.positive} positive).` : "";
  const errs = st.health?.news_errors || {};
  fill($("sources"), ["Google News", "Economic Times", "Livemint", "Business Standard"].map((s) =>
    el("li", {}, el("i", { class: "lvl " + (errs[s] ? "error" : "trade") }), el("div", { class: "t", text: errs[s] ? `${s}: unavailable` : `${s}: live` }))),
    el("li", { class: "muted", text: `Refreshed ${ago(st.health?.news_updated)} · every 2 minutes` }));
  const sel = $("companySelect");
  if (sel.options.length <= 1 && st.board?.stocks?.length) {
    fill(sel, el("option", { value: "", text: "Choose a company…" }),
      st.board.stocks.map((s) => el("option", { value: s.symbol, text: `${s.name} (${s.symbol})` })));
  }
}
function newsItem(i) {
  return el("li", {}, el("a", { href: i.link, target: "_blank", rel: "noopener noreferrer", text: i.title }),
    el("div", { class: "meta" }, el("span", { text: i.source }), el("span", { text: ago(i.published) }),
      i.sentiment !== "neutral" ? el("span", { class: "tag " + i.sentiment, text: i.sentiment }) : null,
      i.impact >= 3 ? el("span", { class: "tag impact", text: i.macro ? "macro · high impact" : "high impact" }) : null,
      ...(i.companies || []).map((c) => el("span", { class: "tag co", text: c }))));
}
async function loadCompany(symbol) {
  if (!symbol) return;
  fill($("companyNews"), el("li", { class: "muted", text: "Loading…" }));
  try {
    const r = await fetch("api/company-news?symbol=" + encodeURIComponent(symbol));
    const d = await r.json();
    if (!r.ok) throw new Error(d.error);
    fill($("companyNews"), d.items.length ? d.items.slice(0, 15).map(newsItem) : el("li", { class: "muted", text: "No recent news." }));
  } catch (e) { fill($("companyNews"), el("li", { class: "down", text: "Could not load news: " + e.message })); }
}

function renderPerformance(st) {
  const t = st.trial || {}, opt = st.options_account || {}, etf = st.etf_account || {};
  $("trialChip").textContent = t.status === "ready" ? "Checks passed" : t.status === "in_progress" ? `Day ${t.elapsed_days} of ${t.target_days}` : "Not started";
  $("trialChip").className = "chip " + (t.status === "ready" ? "up" : "accent");
  $("trialVerdict").textContent = t.verdict || t.message || "";
  $("trialProgress").style.width = Math.min(100, ((t.elapsed_days || 0) / (t.target_days || 30)) * 100) + "%";
  fill($("trialChecks"), (t.checks || []).map((c) => el("li", { class: c.ok ? "ok" : "no" }, el("span", { text: c.name }), el("b", { text: (c.ok ? "✓ " : "… ") + c.value }))));
  fill($("trialPros"), (t.pros || []).map((p) => el("li", { text: p })));
  fill($("trialCons"), (t.cons || []).map((p) => el("li", { text: p })));
  const h1 = opt.history || [], h2 = etf.history || [];
  const dates = h1.length >= h2.length ? h1.map((h) => h.date) : h2.map((h) => h.date);
  const byDate = (h) => { const m = new Map(h.map((x) => [x.date, x.equity])); return dates.map((d) => m.get(d) ?? null); };
  lineChart($("equityChart"), [{ values: byDate(h2), color: cssVar("--c-ema200"), width: 1.5 }, { values: byDate(h1), color: cssVar("--c-price"), area: true }],
    { labels: dates, fmt: (v) => "₹" + (v / 1e5).toFixed(2) + "L", label: "Paper equity", empty: "Equity history builds up after each daily run" });
  const trades = [...(opt.trades || [])].reverse();
  fill($("tradesTable").tBodies[0], trades.length ? trades.map((x) => el("tr", {}, el("td", { text: x.label }), el("td", { text: x.opened }), el("td", { text: x.closed }),
    el("td", { class: "hide-sm", text: x.reason }), el("td", { class: "num", text: x.lots }), el("td", { class: "num " + sign(x.pnl_rs), text: inr(x.pnl_rs) }))) :
    el("tr", {}, el("td", { colspan: 6, class: "muted", text: opt.position ? "The first spread is still open." : "No closed trades yet." })));
  const a = st.backtest?.adaptive, bh = st.backtest?.buy_and_hold;
  fill($("backtestStats"), a ? [["Trades", a.trades], ["Win rate", a["win_rate_%"] + "%"], ["Profit factor", a.profit_factor],
    ["Total (index pts)", num(a.total_pts, 0)], ["Max drawdown (pts)", num(a.max_dd_pts, 0)], ["Buy & hold drawdown", num(bh?.max_dd_pts, 0)]]
    .map(([k, v]) => el("div", {}, el("span", { text: k }), el("b", { text: v }))) : el("p", { class: "muted", text: "Run python -m pro.backtest to generate research results." }));
}

function renderAlerts(st) {
  const list = st.alerts || [];
  fill($("alertList"), list.length ? list.map((a) => el("li", { class: (a.read ? "" : "unread ") + (a.resolved ? "resolved" : "") },
    el("i", { class: "lvl " + a.level }), el("div", { class: "t" }, el("b", { text: a.title }), el("p", { text: a.message }),
      el("time", { text: `${a.level} · ${new Date(a.time).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}${a.resolved ? " · resolved" : ""}` }))))
    : el("li", { class: "muted", text: "No alerts yet." }));
  const h = st.health || {}, d = h.daily || {};
  const row = (k, v, bad) => el("li", {}, el("span", { text: k }), el("span", { class: bad ? "down" : "", text: v }));
  fill($("health"),
    row("Daily decision", d.running ? "running…" : d.ok === false ? "failed: " + d.error : d.finished ? `ok · ${ago(d.finished)}` : "not run yet", d.ok === false),
    row("Last completed bar", d.as_of_bar || st.plan?.as_of_bar || "—"),
    row("Market data", h.market_failures >= 3 ? `failing (${h.market_failures}×)` : `ok · ${ago(h.market_updated)}`, h.market_failures >= 3),
    row("News feeds", Object.keys(h.news_errors || {}).length ? `${Object.keys(h.news_errors).length} failing` : `ok · ${ago(h.news_updated)}`, Object.keys(h.news_errors || {}).length === 4),
    row("AI assistant", h.assistant ? "Claude connected" : "basic mode (no API key)"),
    row("Engine heartbeat", ago(h.loops?.last_tick)));
  const c = h.channels || {};
  fill($("channels"), row("In the terminal", "on"), row("Mac notifications", c.desktop ? "on" : "off"), row("Telegram", c.telegram ? "on" : "not set up"));
}

// ------------------------------------------------------------- virtual broker
const fmtTime = (iso) => iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
async function loadBroker() {
  try {
    const r = await fetch("api/broker", { cache: "no-store" });
    if (r.status === 401) { showLogin(true); return; }
    if (!r.ok) throw new Error((await r.json()).error);
    S.acct = await r.json(); renderTrade();
  } catch (e) { $("bookNote").textContent = "Could not load account: " + e.message; }
}
async function loadChain() {
  try {
    const r = await fetch("api/broker/chain" + (S.chainExpiry ? "?expiry=" + S.chainExpiry : ""), { cache: "no-store" });
    const d = await r.json(); if (!r.ok) throw new Error(d.error);
    S.chain = d; S.chainExpiry = d.expiry; renderChain();
  } catch (e) { fill($("chainTable").tBodies[0], el("tr", {}, el("td", { colspan: 5, class: "muted", text: e.message }))); }
}
function renderTrade() {
  const a = S.acct; if (!a) return;
  const f = a.funds;
  const tile = (k, v, cls) => el("div", {}, el("span", { text: k }), el("b", { class: cls || "", text: v }));
  fill($("funds"),
    tile("Account value", inr(f.account_value)), tile("Available to trade", inr(f.available)),
    tile("Margin used", inr(f.margin_used)), tile("Unrealised P&L", inr(f.unrealised), sign(f.unrealised)),
    tile("Total P&L", inr(f.total_pnl), sign(f.total_pnl)), tile("Charges paid", inr(f.charges)),
    el("button", { class: "btn ghost", type: "button", text: "Reset funds", onclick: resetAccount }));
  $("mktChip").textContent = a.session_open ? "Market open · orders fill live" : "Market closed · orders queue for the open";
  $("mktChip").className = "chip " + (a.session_open ? "up" : "");
  renderWatch(); renderBook();
}
function renderWatch() {
  const q = $("watchSearch").value.trim().toLowerCase();
  const stocks = (S.state?.board?.stocks || []).filter((x) => !q || x.name.toLowerCase().includes(q) || x.symbol.toLowerCase().includes(q));
  fill($("watchList"), stocks.length ? stocks.map((x) => el("li", {},
    el("div", { class: "w-name" }, el("b", { text: x.symbol }), el("span", { class: "small muted", text: x.name })),
    el("div", { class: "w-px" }, el("b", { class: flashClass("w:" + x.symbol, x.price).trim(), text: num(x.price) }), el("span", { class: "small " + sign(x.change_pct), text: pct(x.change_pct) })),
    el("div", { class: "w-act" }, el("button", { type: "button", class: "bs buy", text: "B", title: "Buy " + x.symbol, onclick: () => openTicket("EQ:" + x.symbol, "BUY") }),
      el("button", { type: "button", class: "bs sell", text: "S", title: "Sell " + x.symbol, onclick: () => openTicket("EQ:" + x.symbol, "SELL") })))) :
    el("li", { class: "muted", text: S.state?.board?.stocks ? "No match" : "Loading prices…" }));
}
function renderChain() {
  const c = S.chain; if (!c) return;
  const sel = $("chainExpiry");
  if (sel.options.length !== c.expiries.length) fill(sel, c.expiries.map((e) => el("option", { value: e, text: new Date(e + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) })));
  sel.value = c.expiry;
  $("chainSpot").textContent = `Nifty ${num(c.spot)} · VIX ${num(c.vix)} · lot ${c.lot_size}`;
  const cell = (leg, side) => leg ? el("td", { class: "num" }, el("div", { class: "chain-px", text: num(leg.ltp) }),
    el("div", { class: "chain-act" }, el("button", { type: "button", class: "bs buy", text: "B", onclick: () => openTicket(leg.instrument, "BUY") }),
      el("button", { type: "button", class: "bs sell", text: "S", onclick: () => openTicket(leg.instrument, "SELL") }))) : el("td", { text: "—" });
  fill($("chainTable").tBodies[0], c.rows.map((r) => el("tr", { class: r.strike === c.atm ? "atm" : (r.strike < c.atm ? "itm-ce" : "itm-pe") },
    cell(r.CE), el("td", { class: "num small muted", text: r.CE ? r.CE.delta.toFixed(2) : "" }),
    el("td", { class: "center strike", text: r.strike }),
    el("td", { class: "num small muted", text: r.PE ? r.PE.delta.toFixed(2) : "" }), cell(r.PE))));
}
const BOOK_HEAD = {
  positions: ["Instrument", "Product", "Qty", "Avg", "LTP", "P&L", ""],
  holdings: ["Stock", "Qty", "Avg cost", "LTP", "Value", "P&L", ""],
  orders: ["Time", "Instrument", "Side", "Type", "Qty", "Price", "Status", ""],
  trades: ["Time", "Instrument", "Side", "Product", "Qty", "Price", "Charges"],
};
function renderBook() {
  const a = S.acct; if (!a) return;
  const t = $("bookTable"), kind = S.book;
  fill(t.tHead, el("tr", {}, BOOK_HEAD[kind].map((h, i) => el("th", { class: i > 1 && kind !== "orders" ? "num" : "", text: h }))));
  const exitBtn = (p) => p.qty ? el("button", { type: "button", class: "btn ghost small-btn", text: "Exit", onclick: () => exitPosition(p) }) : el("span", { class: "small muted", text: "closed" });
  let rows = [];
  if (kind === "positions") rows = a.positions.map((p) => el("tr", {}, el("td", {}, el("b", { text: p.name }), p.model ? el("div", { class: "small muted", text: "model price" }) : null),
    el("td", { text: p.product }), el("td", { class: "num " + sign(p.qty), text: p.qty }), el("td", { class: "num", text: num(p.avg) }),
    el("td", { class: "num", text: num(p.ltp) }), el("td", { class: "num " + sign(p.pnl), text: inr(p.pnl, 2) }), el("td", { class: "num" }, exitBtn(p))));
  if (kind === "holdings") rows = a.holdings.map((p) => el("tr", {}, el("td", {}, el("b", { text: p.name })), el("td", { class: "num", text: p.qty }),
    el("td", { class: "num", text: num(p.avg) }), el("td", { class: "num", text: num(p.ltp) }), el("td", { class: "num", text: inr(p.value) }),
    el("td", { class: "num " + sign(p.pnl), text: inr(p.pnl, 2) }), el("td", { class: "num" }, exitBtn(p))));
  if (kind === "orders") rows = a.orders.map((o) => el("tr", {}, el("td", { class: "small", text: new Date(o.time).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) }),
    el("td", {}, el("b", { text: o.name }), el("div", { class: "small muted", text: o.product + (o.tag ? " · " + o.tag.replaceAll("_", " ") : "") })),
    el("td", { class: o.side === "BUY" ? "up" : "down", text: o.side }), el("td", { text: o.type }), el("td", { class: "num", text: o.qty }),
    el("td", { class: "num", text: o.fill_price != null ? num(o.fill_price) : o.price ? num(o.price) : o.trigger ? "trg " + num(o.trigger) : "MKT" }),
    el("td", {}, el("span", { class: "status s-" + o.status.toLowerCase(), text: o.status.replace("_", " ") }), o.message ? el("div", { class: "small muted", text: o.message }) : null),
    el("td", {}, ["OPEN", "AMO", "TRIGGER_PENDING"].includes(o.status) ? el("button", { type: "button", class: "btn ghost small-btn", text: "Cancel", onclick: () => cancelOrder(o.id) }) : null)));
  if (kind === "trades") rows = a.trades.map((x) => el("tr", {}, el("td", { class: "small", text: new Date(x.time).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) }),
    el("td", {}, el("b", { text: x.name })), el("td", { class: x.side === "BUY" ? "up" : "down", text: x.side }), el("td", { class: "num", text: x.product }),
    el("td", { class: "num", text: x.qty }), el("td", { class: "num", text: num(x.price) }), el("td", { class: "num", text: inr(x.charges, 2) })));
  const empty = { positions: "No open positions. Pick a stock or option on the left and tap B (buy) or S (sell).",
    holdings: "No delivery (CNC) holdings yet.", orders: "No orders yet.", trades: "No trades yet." }[kind];
  fill(t.tBodies[0], rows.length ? rows : el("tr", {}, el("td", { colspan: BOOK_HEAD[kind].length, class: "muted", text: empty })));
  $("bookNote").textContent = "Virtual money only: nothing is sent to an exchange or broker. Stock prices are public quotes (about 1 minute); option prices are model prices. Charges are estimates.";
}
async function exitPosition(p) {
  if (!confirm(`Exit ${p.name}: ${p.qty > 0 ? "sell" : "buy"} ${Math.abs(p.qty)} at market?`)) return;
  try { await post("api/broker/order", { instrument: p.instrument, side: p.qty > 0 ? "SELL" : "BUY", product: p.product, type: "MARKET", qty: Math.abs(p.qty) }); }
  catch (e) { alert(e.message); }
  loadBroker();
}
async function cancelOrder(id) { try { await post("api/broker/cancel", { id }); } catch (e) { alert(e.message); } loadBroker(); }
async function resetAccount() {
  const cap = prompt("Reset the virtual trading account. All positions and orders will be cleared.\nStarting capital in ₹:", "500000");
  if (!cap) return;
  if (prompt('Type RESET to confirm') !== "RESET") return;
  try { await post("api/broker/reset", { capital: Number(cap), confirm: "RESET" }); } catch (e) { alert(e.message); }
  loadBroker();
}

// order ticket
let ticketTimer = null;
function openTicket(instrument, side) {
  const opt = instrument.startsWith("OPT:");
  S.ticket = { instrument, side, opt, product: opt ? "NRML" : "CNC", type: "MARKET", quote: null };
  fill($("tProduct"), (opt ? [["NRML", "Overnight (NRML)"], ["MIS", "Intraday (MIS)"]] : [["CNC", "Delivery (CNC)"], ["MIS", "Intraday (MIS)"]])
    .map(([v, t], i) => el("button", { type: "button", "data-p": v, class: i ? "" : "on", text: t })));
  $("tQtyLabel").textContent = opt ? `Lots (1 lot = ${S.acct?.lot_size || 65})` : "Quantity (shares)";
  $("tQty").value = 1; $("tPrice").value = ""; $("tTrig").value = ""; $("tMsg").textContent = "";
  document.querySelectorAll("#tType button").forEach((b) => b.classList.toggle("on", b.dataset.t === "MARKET"));
  setSide(side); setType("MARKET");
  $("ticket").hidden = false; $("ticketBackdrop").hidden = false;
  refreshTicketQuote(); clearInterval(ticketTimer); ticketTimer = setInterval(refreshTicketQuote, 4000);
  $("tQty").focus();
}
function closeTicket() { clearInterval(ticketTimer); S.ticket = null; $("ticket").hidden = true; $("ticketBackdrop").hidden = true; }
function setSide(side) {
  S.ticket.side = side;
  document.querySelectorAll("#tSide button").forEach((b) => b.classList.toggle("on", b.dataset.s === side));
  $("ticket").classList.toggle("selling", side === "SELL");
  $("tSubmit").textContent = side === "BUY" ? "Buy" : "Sell";
  estimate();
}
function setType(type) {
  S.ticket.type = type;
  $("tPriceWrap").hidden = !["LIMIT", "SL"].includes(type); $("tTrigWrap").hidden = !["SL", "SL-M"].includes(type);
  estimate();
}
async function refreshTicketQuote() {
  const t = S.ticket; if (!t) return;
  try {
    const r = await fetch("api/broker/quote?instrument=" + encodeURIComponent(t.instrument), { cache: "no-store" });
    const q = await r.json(); if (!r.ok) throw new Error(q.error || "no price");
    if (S.ticket !== t) return;
    t.quote = q;
    $("tName").textContent = q.name;
    $("tQuote").textContent = `LTP ${num(q.ltp)} · Bid ${num(q.bid)} · Ask ${num(q.ask)}${q.model ? " · model price" : ""}`;
    if (!$("tPrice").value) $("tPrice").value = q.ltp;
    estimate();
  } catch (e) { $("tQuote").textContent = "Price unavailable: " + e.message; }
}
function ticketQty() { const n = Math.max(1, Math.floor(Number($("tQty").value) || 0)); return S.ticket.opt ? n * (S.acct?.lot_size || 65) : n; }
function estimate() {
  const t = S.ticket; if (!t || !t.quote) return;
  const px = t.type === "MARKET" || t.type === "SL-M" ? (t.side === "BUY" ? t.quote.ask : t.quote.bid) : Number($("tPrice").value) || t.quote.ltp;
  const qty = ticketQty(), value = px * qty;
  const avail = S.acct?.funds?.available;
  $("tEstimate").textContent = `${qty} × ${num(px)} ≈ ${inr(value)}` + (t.side === "SELL" && t.opt ? " premium received; margin is blocked for short options" : "") +
    (avail != null ? ` · available ${inr(avail)}` : "");
}
async function submitTicket(e) {
  e.preventDefault();
  const t = S.ticket; if (!t) return;
  $("tSubmit").disabled = true; $("tMsg").textContent = "Placing order…"; $("tMsg").className = "small";
  try {
    const r = await post("api/broker/order", { instrument: t.instrument, side: t.side, product: t.product, type: t.type, qty: ticketQty(),
      price: ["LIMIT", "SL"].includes(t.type) ? Number($("tPrice").value) : null, trigger: ["SL", "SL-M"].includes(t.type) ? Number($("tTrig").value) : null });
    const o = r.order; S.acct = r.account; renderTrade();
    const ok = o.status !== "REJECTED";
    $("tMsg").textContent = { COMPLETE: `Executed at ${num(o.fill_price)} · charges ${inr(o.charges, 2)}`, OPEN: "Order placed: waiting for your price",
      AMO: "Market closed: order queued for the next open", TRIGGER_PENDING: "Stop order placed: waiting for the trigger", REJECTED: "Rejected: " + o.message }[o.status] || o.status;
    $("tMsg").className = "small " + (ok ? "up" : "down");
    if (ok) { S.book = o.status === "COMPLETE" ? "positions" : "orders"; document.querySelectorAll("#bookTabs button").forEach((b) => b.classList.toggle("on", b.dataset.b === S.book)); renderBook(); }
  } catch (err) { $("tMsg").textContent = err.message; $("tMsg").className = "small down"; }
  $("tSubmit").disabled = false;
}

// --------------------------------------------------------------- assistant
// Minimal safe formatting for assistant text: **bold**, "- " bullets, paragraphs. Built with DOM nodes only.
function richText(text) {
  const frag = document.createDocumentFragment();
  const inline = (line) => line.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part) =>
    part.startsWith("**") && part.endsWith("**") ? el("b", { text: part.slice(2, -2) }) : document.createTextNode(part.replace(/^#+\s*/, "")));
  let list = null;
  for (const raw of String(text).split("\n")) {
    const line = raw.trimEnd();
    if (/^\s*[-*•]\s+/.test(line)) {
      if (!list) { list = el("ul", { class: "md-list" }); frag.append(list); }
      list.append(el("li", {}, inline(line.replace(/^\s*[-*•]\s+/, ""))));
    } else {
      list = null;
      if (line.trim()) frag.append(el("p", { class: "md-p" }, inline(line)));
    }
  }
  return frag;
}

function chatRender() {
  const log = $("chatLog");
  fill(log, S.chat.length ? S.chat.map((m) => el("div", { class: "msg " + (m.role === "user" ? "user" : "bot") + (m.typing ? " typing" : "") },
    m.role === "user" ? m.content : richText(m.content), m.source ? el("small", { text: m.source }) : null)) :
    el("div", { class: "msg bot" }, "Hi! I can explain how the market is doing, what the bot is doing and why, your paper performance, the latest news and any issues. What would you like to know?"));
  log.scrollTop = log.scrollHeight;
  $("suggest").hidden = S.chat.length > 0;
  try { localStorage.setItem("lolpro.chat", JSON.stringify(S.chat.filter((m) => !m.typing).slice(-30))); } catch (e) { /* storage unavailable */ }
}
async function ask(text) {
  text = text.trim(); if (!text || S.busy) return;
  S.busy = true; $("sendBtn").disabled = true;
  const history = S.chat.filter((m) => !m.typing).map(({ role, content }) => ({ role, content }));
  S.chat.push({ role: "user", content: text }, { role: "assistant", content: "Thinking…", typing: true });
  chatRender();
  try {
    const r = await post("api/chat", { question: text, history });
    S.chat.pop(); S.chat.push({ role: "assistant", content: r.answer, source: r.source });
  } catch (e) {
    S.chat.pop(); S.chat.push({ role: "assistant", content: "Sorry, I could not answer: " + e.message, source: "error" });
  }
  S.busy = false; $("sendBtn").disabled = false; chatRender();
}

// ---------------------------------------------------------------- routing
function route() {
  const [page, sub, sub2] = (location.hash || "#overview").slice(1).split("/");
  S.page = TITLES[page] ? page : "overview";
  if (S.page === "markets" && sub && sub !== S.stock) setTimeout(() => openStock(sub.toUpperCase()), 0);
  if (S.page !== "markets" && S.stock) closeStock();
  for (const p of Object.keys(TITLES)) $("page-" + p).hidden = p !== S.page;
  document.querySelectorAll("[data-page]").forEach((a) => a.classList.toggle("on", a.dataset.page === S.page));
  $("pageTitle").textContent = TITLES[S.page];
  if (S.page === "alerts" && S.state?.alerts?.some((a) => !a.read)) post("api/alerts/read").then(load).catch(() => {});
  render();
  if (S.page === "trade") {
    loadBroker(); if (S.watch === "chain") loadChain();
    if ((sub === "BUY" || sub === "SELL") && sub2) {
      history.replaceState(null, "", "#trade");
      setTimeout(() => openTicket(decodeURIComponent(sub2), sub), 0);
    }
  }
  if (!sub || S.page === "trade") window.scrollTo(0, 0);
}

function init() {
  try { const t = localStorage.getItem("lolpro.theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* ignore */ }
  try { S.chat = JSON.parse(localStorage.getItem("lolpro.chat") || "[]"); } catch (e) { S.chat = []; }
  $("themeBtn").onclick = () => {
    const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("lolpro.theme", document.documentElement.dataset.theme); } catch (e) { /* ignore */ }
    render();
  };
  $("refreshBtn").onclick = () => post("api/refresh").then(() => setTimeout(load, 4000)).catch(() => {});
  $("newsFilter").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    S.newsFilter = b.dataset.f;
    document.querySelectorAll("#newsFilter button").forEach((x) => x.classList.toggle("on", x === b));
    renderNews(S.state || {});
  });
  $("newsSearch").addEventListener("input", () => renderNews(S.state || {}));
  $("companySelect").addEventListener("change", (e) => loadCompany(e.target.value));
  $("chatForm").addEventListener("submit", (e) => { e.preventDefault(); const t = $("chatText").value; $("chatText").value = ""; ask(t); });
  $("chatText").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("chatForm").requestSubmit(); } });
  $("suggest").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) ask(b.textContent); });
  $("clearChat").onclick = () => { S.chat = []; chatRender(); };
  $("markRead").onclick = () => post("api/alerts/read").then(load).catch(() => {});
  $("runDaily").onclick = async () => {
    $("runDaily").disabled = true; $("runMsg").textContent = "Running the engine…";
    try { const r = await post("api/run-daily"); $("runMsg").textContent = r.status === "ok" ? `Done: ${r.plan.action.replaceAll("_", " ").toLowerCase()}` : r.status === "busy" ? "Already running" : "Failed: " + r.error; }
    catch (e) { $("runMsg").textContent = "Failed: " + e.message; }
    $("runDaily").disabled = false; load();
  };
  $("indexTabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { S.index = b.dataset.i; renderMarkets(S.state || {}); } });
  $("viewTabs").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return; S.view = b.dataset.v;
    document.querySelectorAll("#viewTabs button").forEach((x) => x.classList.toggle("on", x === b)); renderMarkets(S.state || {});
  });
  $("boardSearch").addEventListener("input", () => renderMarkets(S.state || {}));
  $("boardSort").addEventListener("change", () => renderMarkets(S.state || {}));
  $("rangeTabs").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return; S.range = b.dataset.r;
    document.querySelectorAll("#rangeTabs button").forEach((x) => x.classList.toggle("on", x === b)); renderStock();
  });
  $("drawerClose").onclick = closeStock; $("drawerBackdrop").onclick = closeStock;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && S.stock) closeStock(); });
  $("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("loginBtn").disabled = true; $("loginErr").textContent = "";
    try {
      const r = await fetch("api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: $("loginKey").value }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || "Sign-in failed");
      $("loginKey").value = ""; S.token = null; showLogin(false); load();
    } catch (err) { $("loginErr").textContent = err.message; }
    $("loginBtn").disabled = false;
  });
  fetch("api/auth").then((r) => r.json()).then((a) => { $("signOut").hidden = !a.login_required; }).catch(() => {});
  $("signOut").onclick = async () => { await fetch("api/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); S.state = null; showLogin(true); };
  $("watchTabs").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return; S.watch = b.dataset.w;
    document.querySelectorAll("#watchTabs button").forEach((x) => x.classList.toggle("on", x === b));
    $("watchStocks").hidden = S.watch !== "stocks"; $("watchChain").hidden = S.watch !== "chain";
    if (S.watch === "chain") loadChain();
  });
  $("watchSearch").addEventListener("input", renderWatch);
  $("chainExpiry").addEventListener("change", (e) => { S.chainExpiry = e.target.value; loadChain(); });
  $("bookTabs").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return; S.book = b.dataset.b;
    document.querySelectorAll("#bookTabs button").forEach((x) => x.classList.toggle("on", x === b)); renderBook();
  });
  $("tSide").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) setSide(b.dataset.s); });
  $("tType").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { document.querySelectorAll("#tType button").forEach((x) => x.classList.toggle("on", x === b)); setType(b.dataset.t); } });
  $("tProduct").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { S.ticket.product = b.dataset.p; document.querySelectorAll("#tProduct button").forEach((x) => x.classList.toggle("on", x === b)); } });
  ["tQty", "tPrice"].forEach((id) => $(id).addEventListener("input", estimate));
  $("ticket").addEventListener("submit", submitTicket);
  $("ticketClose").onclick = closeTicket; $("ticketBackdrop").onclick = closeTicket;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && S.ticket) closeTicket(); });
  setInterval(() => { if (S.page === "trade" && !document.hidden) loadBroker(); }, 5000);
  setInterval(() => { if (S.page === "trade" && S.watch === "chain" && !document.hidden) loadChain(); }, 15000);
  window.addEventListener("hashchange", route);
  let resize; window.addEventListener("resize", () => { clearTimeout(resize); resize = setTimeout(render, 150); });
  chatRender(); route(); load();
  setInterval(load, 15000);
}
init();
