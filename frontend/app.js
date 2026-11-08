/* Vallorée CA Copilot — single-page frontend (no build step). */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let META = null;
let EVAL = null;
const state = { scenario: "greeting", clientId: null, products: new Set(), history: [], drafts: [], speaker: "client" };

/* ── helpers ─────────────────────────────────────────── */
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 1600);
}
function salutation(c) { return c.preferred_name || `${c.surname}${c.gender === "F" ? "女士" : "先生"}`; }
const toLocal = (s) => (s || "").replace(" ", "T").slice(0, 16);
const fromLocal = (s) => (s || "").replace("T", " ");
function scenLabel(id) { return (META.scenarios.find((s) => s.id === id) || {}).label || id; }
async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  if (!r.ok) { let d = ""; try { d = (await r.json()).detail; } catch {} throw new Error(d || `${r.status} ${r.statusText}`); }
  return r.json();
}

/* ── init ────────────────────────────────────────────── */
async function init() {
  META = await api("/api/meta");
  $("#ver").textContent = `tool ${META.version}`;

  $("#caseSel").insertAdjacentHTML("beforeend", META.cases.map((c) =>
    `<option value="${c.id}">${c.id} · ${esc(scenLabel(c.request.scenario).replace(/^\d /, ""))} · ${esc(c.focus.slice(0, 22))}</option>`).join(""));
  $("#scenPills").innerHTML = META.scenarios.map((s) => `<button class="pill-btn" data-s="${s.id}">${esc(s.label)}</button>`).join("");
  $("#clientSel").innerHTML = Object.entries(META.clients).map(([id, c]) =>
    `<option value="${id}">${id} · ${esc(salutation(c))} · ${esc(c.tier)} · ${esc(c.city || "")}</option>`).join("");
  $("#fScen").insertAdjacentHTML("beforeend", META.scenarios.map((s) => `<option value="${s.id}">${esc(s.label)}</option>`).join(""));

  bind();
  loadCase("G01");
}

function bind() {
  $$(".tab").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  $("#caseSel").addEventListener("change", (e) => (e.target.value ? loadCase(e.target.value) : null));
  $("#resetBtn").addEventListener("click", resetForm);
  $("#scenPills").addEventListener("click", (e) => { const b = e.target.closest(".pill-btn"); if (b) { state.scenario = b.dataset.s; renderScen(); markCustom(); } });
  $("#clientSel").addEventListener("change", (e) => { state.clientId = e.target.value; renderProfile(); renderChat(); markCustom(); });
  $("#prodChips").addEventListener("click", (e) => {
    const c = e.target.closest(".chip"); if (!c) return;
    state.products.has(c.dataset.sku) ? state.products.delete(c.dataset.sku) : state.products.add(c.dataset.sku);
    renderProducts(); markCustom();
  });
  $("#speakerSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    state.speaker = b.dataset.sp; $$("#speakerSeg button").forEach((x) => x.classList.toggle("on", x === b));
  });
  $("#addTurn").addEventListener("click", addTurn);
  $("#turnText").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) addTurn(); });
  $("#chatBody").addEventListener("click", (e) => {
    const d = e.target.closest(".del"); if (!d) return;
    const i = +d.dataset.i;
    d.dataset.kind === "draft" ? state.drafts.splice(i, 1) : state.history.splice(i, 1);
    renderChat(); if (d.dataset.kind !== "draft") markCustom();
  });
  ["#today", "#context", "#caName"].forEach((s) => $(s).addEventListener("input", markCustom));
  $("#today").addEventListener("change", nextTurnTime);
  $("#genBtn").addEventListener("click", generate);
  $("#cands").addEventListener("click", onCandClick);
  $("#cands").addEventListener("input", (e) => { if (e.target.tagName === "TEXTAREA") updateCount(e.target); });
  ["#fScen", "#fType", "#fBad"].forEach((s) => $(s).addEventListener("change", renderCaseList));
  $("#caseList").addEventListener("click", (e) => { const it = e.target.closest(".citem"); if (it) renderEvalDetail(it.dataset.id); });
}

function markCustom() { /* editing a loaded case turns it into a custom input */
  if ($("#caseSel").value) { $("#caseSel").value = ""; $("#caseFocus").textContent = ""; }
}

/* ── form ────────────────────────────────────────────── */
function loadCase(id) {
  const c = META.cases.find((x) => x.id === id); if (!c) return;
  const q = c.request;
  $("#caseSel").value = id;
  $("#caseFocus").textContent = `测试重点：${c.focus}（${c.type}）`;
  state.scenario = q.scenario;
  state.clientId = q.client.client_id;
  state.products = new Set(q.products.map((p) => p.sku));
  state.history = q.history.map((t) => ({ ...t }));
  state.drafts = [];
  $("#clientSel").value = state.clientId;
  $("#today").value = q.today;
  $("#caName").value = q.ca_name || "Lina";
  $("#context").value = q.context || "";
  renderAll();
  nextTurnTime();
  clearResults();
}

function resetForm() {
  $("#caseSel").value = ""; $("#caseFocus").textContent = "";
  state.history = []; state.drafts = []; state.products = new Set();
  $("#context").value = "";
  renderAll(); nextTurnTime(); clearResults();
}

function renderAll() { renderScen(); renderProfile(); renderProducts(); renderChat(); }
function renderScen() { $$(".pill-btn").forEach((b) => b.classList.toggle("on", b.dataset.s === state.scenario)); }

function renderProfile() {
  const c = META.clients[state.clientId]; if (!c) return;
  const rows = [
    ["城市", c.city], ["职业", c.occupation], ["年龄段", c.age_band], ["生日", c.birthday], ["家庭", c.family],
    ["兴趣", (c.interests || []).join("、")], ["风格", c.style_notes],
    ["购买", (c.purchases || []).map((p) => `${p.date} ${p.item}${p.note ? `（${p.note}）` : ""}`).join("<br>") || "无"],
    ["上次到店", c.last_visit], ["CA备注", c.ca_notes],
  ].filter(([, v]) => v);
  const prefs = (c.preferences || []).map((p) => `<div class="pref">⚑ ${esc(p)}</div>`).join("");
  $("#profile").innerHTML = `<div class="ph"><span class="nm">${esc(salutation(c))}</span><span class="tier">${esc(c.tier)}</span></div>
    <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${k === "购买" ? v.split("<br>").map(esc).join("<br>") : esc(v)}</dd>`).join("")}
    ${prefs ? `<dt>偏好</dt><dd>${prefs}</dd>` : ""}</dl>`;
  $("#chatName").textContent = salutation(c);
}

function renderProducts() {
  $("#prodChips").innerHTML = Object.values(META.products).map((p) =>
    `<span class="chip ${state.products.has(p.sku) ? "on" : ""}" data-sku="${p.sku}" title="${esc(p.material || "")}">${esc(p.name)}<span class="p">¥${(p.price || 0).toLocaleString()}</span></span>`).join("");
}

function renderChat() {
  const body = $("#chatBody");
  const c = META.clients[state.clientId];
  const initial = c ? c.surname : "客";
  if (!state.history.length && !state.drafts.length) {
    body.innerHTML = `<div class="chat-empty">暂无对话记录 · 可在下方添加</div>`;
  } else {
    let lastDay = "";
    const turns = state.history.map((t, i) => {
      const day = (t.time || "").slice(0, 10);
      const sep = day !== lastDay ? `<div class="tsep">${esc(t.time)}</div>` : "";
      lastDay = day;
      return `${sep}<div class="msg ${t.speaker}"><div class="avatar">${t.speaker === "CA" ? "V" : esc(initial)}</div>
        <div class="bubble">${esc(t.text)}</div><button class="del" data-i="${i}" title="删除">×</button></div>`;
    });
    const drafts = state.drafts.map((d, i) => `<div class="tsep">草稿 · 未发送</div><div class="msg CA draft"><div class="avatar">V</div>
        <div class="bubble">${esc(d)}</div><button class="del" data-kind="draft" data-i="${i}" title="移除">×</button></div>`);
    body.innerHTML = turns.join("") + drafts.join("");
  }
  body.scrollTop = body.scrollHeight;
}

function nextTurnTime() {
  /* default for a new message: one minute after the last turn, and never before 09:00 today */
  const today = $("#today").value || "2026-11-07";
  let t = `${today}T09:00`;
  const last = state.history.length ? toLocal(state.history[state.history.length - 1].time) : "";
  if (last && last >= t) {
    const d = new Date(last); d.setMinutes(d.getMinutes() + 1);
    const pad = (n) => String(n).padStart(2, "0");
    t = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  $("#turnTime").value = t;
}

function addTurn() {
  const text = $("#turnText").value.trim(); if (!text) return;
  state.history.push({ speaker: state.speaker, time: fromLocal($("#turnTime").value) || `${$("#today").value} 10:00`, text });
  state.history.sort((a, b) => a.time.localeCompare(b.time));
  $("#turnText").value = ""; renderChat(); nextTurnTime(); markCustom();
}

function buildRequest() {
  return {
    case_id: $("#caseSel").value || null,
    scenario: state.scenario,
    today: $("#today").value,
    ca_name: $("#caName").value.trim() || "Lina",
    client: META.clients[state.clientId],
    history: state.history,
    products: [...state.products].map((s) => META.products[s]),
    context: $("#context").value.trim() || null,
  };
}

/* ── generate ────────────────────────────────────────── */
function clearResults() { $("#cands").innerHTML = ""; $("#alerts").innerHTML = ""; $("#sigBox").hidden = true; $("#genMeta").textContent = ""; }

async function generate() {
  const req = buildRequest();
  if (!req.today) return toast("请填写今天的日期");
  const btn = $("#genBtn"); btn.disabled = true; btn.textContent = "生成中…";
  $("#alerts").innerHTML = ""; $("#genMeta").textContent = "";
  $("#cands").innerHTML = '<div class="skeleton"></div>'.repeat(3);
  const steps = $$("#steps span"); $("#steps").hidden = false;
  steps.forEach((s) => (s.className = ""));
  let k = 0; steps[0].className = "on";
  const timer = setInterval(() => { if (k < steps.length - 1) { steps[k].className = "done"; k += 1; steps[k].className = "on"; } }, 1700);
  const t0 = performance.now();
  try {
    const [sig, gen] = await Promise.all([api("/api/signals", req), api("/api/generate", req)]);
    renderResult(gen.result, sig);
    $("#genMeta").textContent = `${gen.result.model} · ${((performance.now() - t0) / 1000).toFixed(1)}s · ${gen.result.version}`;
  } catch (e) {
    $("#cands").innerHTML = "";
    $("#alerts").innerHTML = `<div class="alert err"><b>生成失败</b><span>${esc(e.message)}（检查 .env 中的 API key 与网络）</span></div>`;
  } finally {
    clearInterval(timer); steps.forEach((s) => (s.className = "done"));
    setTimeout(() => ($("#steps").hidden = true), 900);
    btn.disabled = false; btn.textContent = "重新生成";
  }
}

function renderResult(res, sig) {
  const a = res.analysis || {};
  const factMap = Object.fromEntries((sig.facts || []).map((f) => { const m = f.match(/^\[(\w+)\]\s*(.*)$/); return m ? [m[1], m[2]] : [f, f]; }));

  const alerts = [];
  const timingSig = sig.signals["发送时机"];  // deterministic signal wins over the model's wording
  if (timingSig || a.timing_ok === false) {
    const txt = timingSig ? timingSig.replace(/timing_ok\s*必须为\s*false[，,]?\s*/, "").replace(/；?消息内容按周末发送来写/, "")
      : ((a.risks || []).find((r) => /周|时机|时间|发送/.test(r)) || "此刻发送可能不合适，请查看分析。");
    alerts.push(`<div class="alert warn"><b>⏰ 发送时机</b><span>${esc(txt)}。草稿已按周末发送来写。</span></div>`);
  }
  if (a.critic_error) alerts.push(`<div class="alert err"><b>事实核查未完成</b><span>${esc(a.critic_error)}</span></div>`);
  $("#alerts").innerHTML = alerts.join("");

  $("#cands").innerHTML = res.candidates.map((c, i) => {
    const hard = c.issues.filter((x) => x.startsWith("[HARD"));
    const soft = c.issues.filter((x) => x.startsWith("[SOFT"));
    const flags = [...hard.map((x) => `<span class="tag hard">${esc(x.replace(/^\[HARD:\w+\]\s*/, ""))}</span>`),
                   ...soft.map((x) => `<span class="tag soft">${esc(x.replace(/^\[SOFT:\w+\]\s*/, ""))}</span>`)];
    const facts = (c.facts_used || []).map((id) => `<span class="tag fact" title="${esc(factMap[id] || "")}">${esc(id)}</span>`).join("");
    const removed = (c.critic_removed || []).length
      ? `<div class="critic"><b>事实核查已删改</b><ul>${c.critic_removed.map((x) => `<li>${esc(x.length > 80 ? x.slice(0, 80) + "…" : x)}</li>`).join("")}</ul></div>` : "";
    const why = (c.rationale || "").split("｜")[0];
    return `<article class="cand" data-i="${i}">
      <div class="cand-h"><span class="n">${i + 1}</span><span class="ang">${esc(c.angle)}</span>
        ${hard.length ? '<span class="tag hard">需修改</span>' : '<span class="tag ok">通过检查</span>'}</div>
      <textarea>${esc(c.message)}</textarea><div class="cnt"></div>
      <div class="btns"><button class="ghost" data-act="copy">复制</button><button class="ghost" data-act="draft">放入对话预览</button></div>
      <div class="why">${esc(why)}</div>
      ${facts ? `<div class="tags"><span class="small muted">引用事实</span>${facts}</div>` : ""}
      ${flags.length ? `<div class="tags">${flags.join("")}</div>` : ""}
      ${removed}
    </article>`;
  }).join("");
  $$("#cands textarea").forEach(updateCount);

  // signals + fact sheet + analysis
  const used = new Set(res.candidates.flatMap((c) => c.facts_used || []));
  $("#sigList").innerHTML = Object.entries(sig.signals).map(([k, v]) =>
    `<dt>${esc(k)}</dt><dd>${esc(Array.isArray(v) ? v.join("；") : v)}</dd>`).join("");
  $("#factList").innerHTML = (sig.facts || []).map((f) => {
    const id = (f.match(/^\[(\w+)\]/) || [])[1];
    return `<li class="${used.has(id) ? "used" : ""}">${esc(f)}</li>`;
  }).join("");
  const kf = (a.key_facts || []).map((x) => `<li>${esc(x)}</li>`).join("");
  const rk = (a.risks || []).map((x) => `<li>${esc(x)}</li>`).join("");
  $("#analysisBox").innerHTML = `<div class="sig-grid"><div><h4>模型分析 · 关键事实</h4><ul>${kf}</ul></div><div><h4>模型分析 · 风险</h4><ul>${rk}</ul></div></div>`;
  $("#sigBox").hidden = false;
}

function updateCount(ta) {
  const n = ta.value.replace(/\s/g, "").length;
  ta.nextElementSibling.textContent = `${n} 字${n > 160 ? " · 偏长" : ""}`;
  ta.style.height = "auto"; ta.style.height = Math.max(160, ta.scrollHeight + 4) + "px";
}

async function onCandClick(e) {
  const b = e.target.closest("button[data-act]"); if (!b) return;
  const text = b.closest(".cand").querySelector("textarea").value;
  if (b.dataset.act === "copy") {
    try { await navigator.clipboard.writeText(text); } catch {
      const t = document.createElement("textarea"); t.value = text; document.body.append(t); t.select(); document.execCommand("copy"); t.remove();
    }
    toast("已复制，可粘贴到微信");
  } else {
    state.drafts = [text]; renderChat(); toast("已放入对话预览");
  }
}

/* ── evaluation ──────────────────────────────────────── */
function switchTab(tab) {
  $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $("#gen").hidden = tab !== "gen"; $("#eval").hidden = tab !== "eval";
  if (tab === "eval" && !EVAL) loadEval();
}

async function loadEval() {
  $("#kpis").innerHTML = '<div class="kpi skeleton" style="height:120px"></div>'.repeat(3);
  EVAL = await api("/api/eval");
  renderKpis(); renderCaseList();
}

const VERSIONS = () => Object.keys(EVAL).sort();
const DIMS = ["personalization", "brand_voice", "naturalness", "appropriateness", "goal", "faithfulness"];

function renderKpis() {
  $("#kpis").innerHTML = VERSIONS().map((v) => {
    const cs = Object.values(EVAL[v]).flatMap((c) => c.candidates);
    const n = cs.length;
    const cnt = { OK: 0, EDIT: 0, UNACCEPTABLE: 0 };
    cs.forEach((c) => (cnt[c.verdict] += 1));
    const faith = cs.map((c) => c.scores.faithfulness).filter(Number.isFinite);
    const all3 = Object.values(EVAL[v]).filter((c) => c.candidates.every((x) => x.verdict === "OK")).length;
    const pct = (x) => (x / n * 100).toFixed(1);
    return `<div class="kpi"><h3>${v}</h3>
      <span class="big">${Math.round(cnt.OK / n * 100)}%</span> <span class="muted">可直接发送</span>
      <div class="bar"><i class="o" style="width:${pct(cnt.OK)}%"></i><i class="e" style="width:${pct(cnt.EDIT)}%"></i><i class="u" style="width:${pct(cnt.UNACCEPTABLE)}%"></i></div>
      <div class="nums">OK ${cnt.OK} · 需修改 ${cnt.EDIT} · 不可接受 ${cnt.UNACCEPTABLE} ｜ 三条全部OK ${all3}/${Object.keys(EVAL[v]).length} ｜ 事实忠实 ${(faith.reduce((a, b) => a + b, 0) / faith.length).toFixed(2)}</div></div>`;
  }).join("");
}

function worst(cands) {
  return cands.some((c) => c.verdict === "UNACCEPTABLE") ? "UNACCEPTABLE" : cands.some((c) => c.verdict === "EDIT") ? "EDIT" : "OK";
}

function renderCaseList() {
  const fs = $("#fScen").value, ft = $("#fType").value, fb = $("#fBad").checked;
  const vs = VERSIONS();
  const items = META.cases.filter((c) => (!fs || c.request.scenario === fs) && (!ft || c.type === ft)
    && (!fb || vs.some((v) => EVAL[v][c.id] && worst(EVAL[v][c.id].candidates) !== "OK")));
  $("#caseList").innerHTML = items.map((c) => {
    const dots = vs.map((v) => `<i class="dot ${EVAL[v][c.id] ? worst(EVAL[v][c.id].candidates) : ""}" title="${v}"></i>`).join("");
    return `<div class="citem" data-id="${c.id}"><div class="t"><span>${c.id}<span class="type">${esc(scenLabel(c.request.scenario).replace(/^\d /, "").split(" ")[0])} · ${c.type}</span></span><span class="dots">${dots}</span></div>
      <div class="f">${esc(c.focus)}</div></div>`;
  }).join("") || '<p class="muted small">没有符合条件的用例</p>';
}

function renderEvalDetail(id) {
  $$(".citem").forEach((x) => x.classList.toggle("on", x.dataset.id === id));
  const c = META.cases.find((x) => x.id === id); const q = c.request; const cl = q.client;
  const vs = VERSIONS().filter((v) => EVAL[v][id]);
  const hist = q.history.map((t) => `<div><span class="muted">[${esc(t.time)}] ${t.speaker === "CA" ? "CA" : "客户"}：</span>${esc(t.text)}</div>`).join("") || "<span class='muted'>无</span>";
  const prods = q.products.map((p) => `${esc(p.name)} ¥${(p.price || 0).toLocaleString()}`).join("<br>") || "<span class='muted'>无</span>";
  const rows = [0, 1, 2].map((i) => `<tr>${vs.map((v) => {
    const x = EVAL[v][id].candidates[i]; if (!x) return "<td></td>";
    const sc = DIMS.map((d) => x.scores[d]).filter(Number.isFinite);
    const avg = sc.length ? (sc.reduce((a, b) => a + b, 0) / sc.length).toFixed(1) : "–";
    return `<td class="${x.verdict}"><span class="vpill ${x.verdict}">${x.verdict}</span><span class="ang">${i + 1} · ${esc(x.angle)}</span>
      <div class="m">${esc(x.message)}</div>
      ${x.review_note ? `<div class="rn">复核：${esc(x.review_note)}</div>` : ""}
      <div class="js">Judge 均分 ${avg}${x.hard_fail ? " · hard fail" : ""}${x.judge_comment ? ` · ${esc(x.judge_comment)}` : ""}</div></td>`;
  }).join("")}</tr>`).join("");
  $("#evalDetail").innerHTML = `<h2>${id} · ${esc(scenLabel(q.scenario))}</h2>
    <p class="focus">测试重点：${esc(c.focus)}（${c.type}）</p>
    <div class="ctx">
      <div class="box"><h4>客户 · ${esc(salutation(cl))} · ${esc(cl.tier)}</h4>${esc([cl.city, cl.occupation].filter(Boolean).join(" · "))}
        ${(cl.preferences || []).map((p) => `<div class="pref">⚑ ${esc(p)}</div>`).join("")}
        ${cl.ca_notes ? `<div class="muted">CA备注：${esc(cl.ca_notes)}</div>` : ""}<div class="muted">今天：${esc(q.today)}</div></div>
      <div class="box"><h4>对话历史</h4>${hist}</div>
      <div class="box"><h4>产品</h4>${prods}</div>
      <div class="box"><h4>场景背景</h4><div style="white-space:pre-wrap">${esc(q.context || "无")}</div></div>
    </div>
    <table class="cmp"><thead><tr>${vs.map((v) => `<th>${v}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>
    <p class="small muted" style="margin-top:12px"><button class="ghost" id="tryCase">在生成页用此用例运行 →</button></p>`;
  $("#tryCase").addEventListener("click", () => { switchTab("gen"); loadCase(id); window.scrollTo(0, 0); });
}

init().catch((e) => {
  document.body.insertAdjacentHTML("afterbegin", `<div class="alert err" style="margin:16px"><b>加载失败</b><span>${esc(e.message)}</span></div>`);
});
