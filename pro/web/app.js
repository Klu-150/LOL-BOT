"use strict";
// LOL Pro terminal front end. All external text (news, alerts) is inserted with textContent.

const $ = (id) => document.getElementById(id);
const S = { state: null, token: null, page: "overview", newsFilter: "all", chat: [], busy: false };
const TITLES = { overview: "Overview", markets: "Markets", news: "Live news", assistant: "Assistant",
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
  const r = await fetch("/api/session"); S.token = (await r.json()).token;
}
async function post(path, body) {
  if (!S.token) await session();
  let r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Session-Token": S.token }, body: JSON.stringify(body || {}) });
  if (r.status === 403) { await session(); r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Session-Token": S.token }, body: JSON.stringify(body || {}) }); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.json();
}
async function load() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    if (!r.ok) throw new Error(r.statusText);
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

  $("kEquity").textContent = inr(opt.equity);
  $("kEquitySub").textContent = opt.return_pct != null ? `${pct(opt.return_pct)} since ${opt.started || "start"}` : "Starts on the first run";
  $("kEquitySub").className = sign(opt.return_pct);
  const m = opt.position?.mark;
  $("kOpen").textContent = m ? inr(m.pnl_rs) : "No position"; $("kOpen").className = m ? sign(m.pnl_rs) : "";
  $("kOpenSub").textContent = opt.position ? `max loss ${inr(opt.position.max_loss_rs)}` : "";
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
    const mk = pos.mark || {}, lo = -pos.max_loss_rs, hi = pos.credit_pts * 65 * pos.lots;
    const at = Math.max(0, Math.min(100, ((mk.pnl_rs - lo) / (hi - lo)) * 100));
    fill($("positionBody"),
      el("strong", { text: pos.label }),
      el("div", { class: "position-grid" },
        el("div", {}, el("span", { text: "Credit received" }), el("b", { text: `${num(pos.credit_pts)} pts · ${inr(pos.credit_pts * 65 * pos.lots)}` })),
        el("div", {}, el("span", { text: "Current P&L" }), el("b", { class: sign(mk.pnl_rs), text: inr(mk.pnl_rs) })),
        el("div", {}, el("span", { text: "Opened" }), el("b", { text: `${pos.opened} at Nifty ${num(pos.spot_at_entry, 0)}` })),
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

function renderMarkets(st) {
  const rows = st.daily_chart || [];
  lineChart($("dailyChart"), [
    { values: rows.map((r) => r.e200), color: cssVar("--c-ema200"), width: 1.5 },
    { values: rows.map((r) => r.e50), color: cssVar("--c-ema50"), width: 1.5 },
    { values: rows.map((r) => r.c), color: cssVar("--c-price"), area: true },
  ], { labels: rows.map((r) => r.d), label: "Nifty daily with EMA 50 and EMA 200", empty: "Run the daily decision to load history" });
  fill($("regimeStrip"), rows.map((r) => el("i", { class: "r-" + r.g, title: `${r.d}: ${REGIME_LABEL[r.g] || r.g}` })));
  fill($("regimeLegend"), Object.entries(REGIME_LABEL).filter(([k]) => k !== "warmup").map(([k, v]) => el("span", {}, el("i", { class: "reg r-" + k }), " " + v)));
  const b = st.market?.breadth;
  $("breadth").textContent = b ? `${b.advancing} advancing · ${b.declining} declining` : "";
  const stocks = st.market?.stocks || [];
  fill($("stocks").tBodies[0], stocks.length ? stocks.map((s) => {
    const span = s.high - s.low, at = span > 0 ? ((s.price - s.low) / span) * 100 : 50;
    return el("tr", {},
      el("td", {}, el("b", { text: s.name }), el("div", { class: "small muted", text: s.symbol.replace(".NS", "") })),
      el("td", { class: "num", text: num(s.price) }),
      el("td", { class: "num " + sign(s.change_pct), text: pct(s.change_pct) }),
      el("td", { class: "hide-sm" }, el("div", { class: "range-bar", title: `${num(s.low)} – ${num(s.high)}` }, el("i", { style: `left:calc(${at}% - 2px)` }))),
      el("td", { class: "num" }, el("button", { class: "news-btn", text: "News", onclick: () => { location.hash = "news"; $("companySelect").value = s.name; loadCompany(s.name); } })));
  }) : el("tr", {}, el("td", { colspan: 5, class: "muted", text: "Loading quotes…" })));
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
  if (!sel.options.length) {
    sel.append(el("option", { value: "", text: "Choose a company…" }));
    for (const s of [...(st.market?.stocks || [])].sort((a, b) => a.name.localeCompare(b.name))) sel.append(el("option", { value: s.name, text: s.name }));
  }
}
function newsItem(i) {
  return el("li", {}, el("a", { href: i.link, target: "_blank", rel: "noopener noreferrer", text: i.title }),
    el("div", { class: "meta" }, el("span", { text: i.source }), el("span", { text: ago(i.published) }),
      i.sentiment !== "neutral" ? el("span", { class: "tag " + i.sentiment, text: i.sentiment }) : null,
      i.impact >= 3 ? el("span", { class: "tag impact", text: i.macro ? "macro · high impact" : "high impact" }) : null,
      ...(i.companies || []).map((c) => el("span", { class: "tag co", text: c }))));
}
async function loadCompany(name) {
  if (!name) return;
  fill($("companyNews"), el("li", { class: "muted", text: "Loading…" }));
  try {
    const r = await fetch("/api/company-news?name=" + encodeURIComponent(name));
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
    const r = await post("/api/chat", { question: text, history });
    S.chat.pop(); S.chat.push({ role: "assistant", content: r.answer, source: r.source });
  } catch (e) {
    S.chat.pop(); S.chat.push({ role: "assistant", content: "Sorry, I could not answer: " + e.message, source: "error" });
  }
  S.busy = false; $("sendBtn").disabled = false; chatRender();
}

// ---------------------------------------------------------------- routing
function route() {
  const page = (location.hash || "#overview").slice(1);
  S.page = TITLES[page] ? page : "overview";
  for (const p of Object.keys(TITLES)) $("page-" + p).hidden = p !== S.page;
  document.querySelectorAll("[data-page]").forEach((a) => a.classList.toggle("on", a.dataset.page === S.page));
  $("pageTitle").textContent = TITLES[S.page];
  if (S.page === "alerts" && S.state?.alerts?.some((a) => !a.read)) post("/api/alerts/read").then(load).catch(() => {});
  render();
  window.scrollTo(0, 0);
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
  $("refreshBtn").onclick = () => post("/api/refresh").then(() => setTimeout(load, 4000)).catch(() => {});
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
  $("markRead").onclick = () => post("/api/alerts/read").then(load).catch(() => {});
  $("runDaily").onclick = async () => {
    $("runDaily").disabled = true; $("runMsg").textContent = "Running the engine…";
    try { const r = await post("/api/run-daily"); $("runMsg").textContent = r.status === "ok" ? `Done: ${r.plan.action.replaceAll("_", " ").toLowerCase()}` : r.status === "busy" ? "Already running" : "Failed: " + r.error; }
    catch (e) { $("runMsg").textContent = "Failed: " + e.message; }
    $("runDaily").disabled = false; load();
  };
  window.addEventListener("hashchange", route);
  let resize; window.addEventListener("resize", () => { clearTimeout(resize); resize = setTimeout(render, 150); });
  chatRender(); route(); load();
  setInterval(load, 15000);
}
init();
