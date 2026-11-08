"""Build docs/report.html (+ PDF via headless Chrome) from results/ and data/.

    python scripts/build_docs.py
Prompt screenshots for the work log go in docs/screenshots/N.png (optional; missing ones show a placeholder).
"""
from __future__ import annotations

import html
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_report import DIMS, load, metrics  # noqa: E402

DOCS = ROOT / "docs"
VERS = ["v1", "v2", "v3"]
SCEN = {"greeting": "1 Birthday & festive greeting", "recommendation": "2 Product recommendation",
        "aftercare": "3 Post-purchase care", "reactivation": "4 Reactivation", "event": "5 Event invitation",
        "price_objection": "6 Price objection"}
e = html.escape

R = {v: {r["case_id"]: r for r in load(v)} for v in VERS}
H = {v: yaml.safe_load((ROOT / f"data/human_review_{v}.yaml").read_text(encoding="utf-8")) or {} for v in VERS}
M = {v: metrics(list(R[v].values())) for v in VERS}


def msg(v, cid, i):
    return R[v][cid]["result"]["candidates"][i - 1]["message"]


def verdict(v, cid, i):
    h = H[v].get(f"{cid}-{i}")
    return ("OK", "") if not h else (h["verdict"], h["note"])


def pill(vd):
    cls = {"OK": "ok", "EDIT": "edit", "UNACCEPTABLE": "bad"}[vd]
    return f'<span class="pill {cls}">{vd.title() if vd != "OK" else "OK"}</span>'


def counts(v):
    un = sum(1 for x in H[v].values() if x["verdict"] == "UNACCEPTABLE")
    ed = sum(1 for x in H[v].values() if x["verdict"] == "EDIT")
    cases_ok = 50 - len({k.rsplit("-", 1)[0] for k in H[v]})
    return 150 - un - ed, ed, un, cases_ok


def avg(xs):
    return sum(xs) / len(xs) if xs else 0


def judge_agree(v):
    tp = fp = fn = tn = 0
    for cid, r in R[v].items():
        for i, j in enumerate(r["judge"]["candidates"][:3], 1):
            h = H[v].get(f"{cid}-{i}", {}).get("verdict") == "UNACCEPTABLE"
            jh = bool(j.get("hard_fail"))
            tp += h and jh; fp += jh and not h; fn += h and not jh; tn += (not h and not jh)  # noqa: E702
    return tp, fp, fn, tn


def by_type(v):
    out = {}
    for cid, r in R[v].items():
        t = r["meta"]["type"]
        a, b = out.get(t, (0, 0))
        out[t] = (a + sum(1 for i in range(1, 4) if f"{cid}-{i}" not in H[v]), b + 3)
    return out


def latency(v):
    xs = sorted(r["result"]["latency_s"] for r in R[v].values())
    return avg(xs), xs[int(0.9 * len(xs))]


# ── work log ───────────────────────────────────────────────────────────────
WORKLOG = [
    ("Briefed the AI as an engineering partner: goal, fixed decisions (DeepSeek via OpenAI-compatible API with the key kept in .env; fictional high-jewellery & watch brand; conda env; deliverables), and working rules (stop after each stage to report; deterministic logic in code, not the LLM; freeze each version in snapshots/; human labels drafted by AI are marked “to be checked by me”). Asked for its understanding, open questions and a staged plan before any code.",
     "Brief PDF", "Requirements summary, open questions, staged plan with outputs and acceptance criteria per stage", "Claude Code (Claude Opus 5.5) in VS Code"),
    ("Had the brand bible written: history, voice (3 keywords, each with do/don't examples), client segments, hard rules (no discounts, no value-retention promises, Advertising Law absolute terms, no disparaging competitors, no invention, privacy, respect client preferences), and CA services. Reviewed the voice examples before moving on.",
     "Own assumptions about luxury CRM practice and China's Advertising Law", "brand/brand_bible.md, brand/products.yaml (10 SKUs with prices)", "Claude Code; reviewed and edited by me"),
    ("Asked for a design proposal before implementation: data contracts (Client / Turn / Product / Request / Candidate), 3 distinct angles per scenario with must-do and must-not rules, which signals code computes vs. the LLM, and what the rule-check layer blocks. Approved the data flow, then had it built.",
     "Brand bible, brief", "Design and data-flow diagram; ca_copilot/ package (v1)", "Claude Code"),
    ("Designed the test set: 20 client personas and 50 cases covering all 6 scenarios, split about 5:3:2 core / edge / adversarial (26 / 13 / 11), each with a focus field. Adversarial cases target discount requests, investment-value questions, competitor bait, preference conflicts, stale chat history and mourning. Reviewed the distribution table and the 10 hardest cases.",
     "Coverage matrix (scenario × difficulty × context type)", "data/clients.yaml, data/cases.yaml", "Claude Code; reviewed by me"),
    ("Defined the evaluation framework before running anything: definitions of good / edit / not acceptable with 2 examples each, LLM-judge dimensions (1–5) plus hard-fail conditions, a defect-code taxonomy, and validating the judge by precision and recall against human labels.",
     "Brand bible, test set", "Rubric (section B4), judge prompt, defect codes", "Claude Code"),
    ("Connected DeepSeek and smoke-tested the 2 hardest cases (G04 mourning birthday, P02 staff-price request); found a guardrail false positive on refusals (‘员工价…确实没有’). Ran all 50 cases (150 drafts) for v1, scored them with the judge, and had 150 human labels drafted, then checked them. Asked for root-cause hypotheses before any fix.",
     "DeepSeek API key, data/cases.yaml", "results/v1, data/human_review_v1.yaml: 19 unacceptable, 17 edit; judge recall on unacceptable only 11%", "DeepSeek (generator + judge), Claude Code"),
    ("Fix loop used for each version, one prompt per defect: propose a fix that targets the root cause, freeze the current version, rerun all cases with the same frozen judge, and report before/after (what was fixed, what broke, latency and cost). v2: stale-history detection, CA location, pronouns, timing rules, fact boundaries, cliché ban, guardrail unit tests (13 unacceptable left; root cause: content-hungry angles invent details). v3: numbered fact sheet, fact-check critic step, preferences as hard rules, new guardrails.",
     "Defect taxonomy and root-cause hypotheses", "snapshots/ v1–v2, ca_copilot v2 and v3, tests/, results/v2, results/v3: 1 unacceptable / 150", "Claude Code, DeepSeek, pytest"),
    ("Calibrated the judge against the human labels: listed every disagreement and decided whether the judge or the label was wrong; tuned the rubric for 100% recall on unacceptable outputs with precision as high as possible (too lenient → too strict → balanced). Froze it and re-scored v1, v2 and v3 with the same judge so versions are comparable.",
     "Human labels v1–v3", "Frozen judge; recall on unacceptable 11% → 100%; comparison table", "Claude Code, DeepSeek"),
    ("Built the deliverables: Excel with sheet C in the brief's exact columns plus a score sheet and a version comparison; this English report (A–E, charts, screenshots, architecture); then checked everything against the brief's “what to submit” list.",
     "results/v1–v3", "deliverables/, docs/", "Claude Code, matplotlib, Playwright, Chrome"),
    ("Added a local web front end (FastAPI + plain JS, no build step): a generate page with editable input showing the 3 drafts, the facts each one cites and compliance flags; an evaluation page that reads saved results (no API calls) and compares v1/v2/v3 side by side. Tested end to end and fixed a message-ordering bug.",
     "ca_copilot/, results/", "server.py, frontend/, start.sh", "Claude Code, FastAPI, Playwright"),
]


def png_width(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return int.from_bytes(head[16:20], "big")


def worklog_rows():
    rows = []
    for n, (what, inp, out, tool) in enumerate(WORKLOG, 1):
        rows.append(f"<tr><td>{n}</td><td>{e(what)}</td><td>{e(inp)}</td><td>{e(out)}</td><td>{e(tool)}</td></tr>")
        shot = DOCS / "screenshots" / f"{n}.png"
        if shot.exists():  # retina screenshots: show at half their pixel width
            img = (f'<img class="shot" src="screenshots/{n}.png" width="{png_width(shot) // 2}" '
                   f'alt="Prompt for step {n}">')
        else:
            img = '<span class="todo">screenshot to add</span>'
        rows.append(f'<tr class="shotrow"><td></td><td colspan="4"><div class="small muted">Prompt for step {n}:</div>{img}</td></tr>')
    return "\n".join(rows)


# ── before / after examples ────────────────────────────────────────────────
EXAMPLES = [
    ("Stale thread treated as live", "G08", 1, ["v1", "v3"],
     "Context builder: a client message older than 3 days is a closed thread; the prompt says so explicitly."),
    ("Invented memory in a sensitive moment", "G04", 1, ["v1", "v2", "v3"],
     "v2 prompt rules were not enough; v3 fact sheet + critic removed the invented detail."),
    ("Invented alternative products", "P06", 3, ["v1", "v3"],
     "Playbook: offer an alternative only if one is in the product list, otherwise policy-level services."),
    ("Selling inside a birthday greeting", "G01", 3, ["v1", "v3"],
     "Greeting angle redefined; guardrail blocks service words in greetings."),
    ("CA writing as if in Geneva", "G09", 2, ["v1", "v3"],
     "Signal: CA works in the client's city boutique; guardrail on ‘日内瓦的秋天’ patterns."),
    ("Policy applied to the wrong product", "A05", 3, ["v1", "v2", "v3"],
     "Fact sheet states ‘ring only’; guardrail checks resizing against rings."),
    ("Invented store exhibition", "RA06", 3, ["v2", "v3"],
     "Fact sheet + critic; guardrail on exhibitions not present in the input."),
    ("Ignoring ‘no event invitations’", "E03", 3, ["v2", "v3"],
     "CRM preference translated into a hard instruction: offer only a one-to-one appointment."),
]


def example_blocks():
    out = []
    for title, cid, i, vs, fix in EXAMPLES:
        cells = []
        for v in vs:
            vd, note = verdict(v, cid, i)
            cells.append(f'<div class="ba"><div class="bah">{v} {pill(vd)}</div><div class="zh">{e(msg(v, cid, i))}</div>'
                         + (f'<div class="note">{e(note)}</div>' if note else "") + "</div>")
        out.append(f'<div class="ex"><h4>{e(title)} <span class="muted">· case {cid}, option {i}</span></h4>'
                   f'<div class="bagrid c{len(vs)}">{"".join(cells)}</div><p class="fix"><b>Change:</b> {e(fix)}</p></div>')
    return "\n".join(out)


def sample_outputs():
    picks = ["G01", "R04", "A02", "RA04", "E06", "P07"]
    out = []
    for cid in picks:
        r = R["v3"][cid]
        q = r["request"]
        last = q["history"][-1] if q["history"] else None
        ctx = f"Last message ({'client' if last and last['speaker'] == 'client' else 'CA'}, {last['time'][:10]}): {last['text']}" if last else "No history"
        opts = "".join(f'<div class="opt"><div class="opth">{i}. {e(c["angle"])}</div><div class="zh">{e(c["message"])}</div></div>'
                       for i, c in enumerate(r["result"]["candidates"], 1))
        out.append(f'<div class="sample"><h4>{cid} · {SCEN[q["scenario"]]}</h4><p class="muted small">{e(r["meta"]["focus"])}<br>{e(ctx)}</p>'
                   f'<div class="opts">{opts}</div></div>')
    return "\n".join(out)


def metrics_table():
    rows = []
    def row(label, f, fmt="{}"):
        rows.append(f"<tr><td>{label}</td>" + "".join(f"<td>{fmt.format(f(v))}</td>" for v in VERS) + "</tr>")
    row("Manual review: OK (send as-is)", lambda v: f"{counts(v)[0]}/150 ({counts(v)[0]/150:.0%})")
    row("Manual review: needs edit", lambda v: counts(v)[1])
    row("Manual review: unacceptable", lambda v: f"{counts(v)[2]} ({counts(v)[2]/150:.0%})")
    row("Cases where all 3 options are OK", lambda v: f"{counts(v)[3]}/50")
    row("Adversarial candidates OK", lambda v: "{}/{}".format(*by_type(v)["adversarial"]))
    row("Edge candidates OK", lambda v: "{}/{}".format(*by_type(v)["edge"]))
    row("Judge: hard fail", lambda v: M[v]["judge_hard"])
    row("Judge: send-ready (no fail, avg ≥ 4)", lambda v: f"{M[v]['send_ready']/150:.0%}")
    for d in DIMS:
        row(f"Judge mean · {d}", lambda v, d=d: f"{avg(M[v]['dims'][d]):.2f}")
    row("Judge: diversity of the 3 options (1–5)", lambda v: f"{avg(M[v]['diversity']):.2f}")
    row("Max text similarity between options", lambda v: f"{avg(M[v]['sim']):.2f}")
    row("Latency per request, mean / p90 (s)", lambda v: "{:.1f} / {:.1f}".format(*latency(v)))
    row("LLM calls per request", lambda v: {"v1": "1 (+repair)", "v2": "1 (+repair)", "v3": "2 (+repair)"}[v])
    return "\n".join(rows)


def defect_table():
    codes = sorted({x["code"] for v in VERS for x in H[v].values()})
    label = {"fabricated_product": "Invented product facts / alternatives", "stale_history": "Old thread treated as live",
             "fabricated_memory": "Invented client memory or behaviour", "fabricated_service": "Invented / misapplied service terms",
             "fabricated_event": "Invented events, exhibitions, new arrivals", "ignores_preference": "Ignores client preference / timing",
             "greeting_soft_sell": "Selling inside a greeting", "ca_location": "CA written as if abroad",
             "invented_pretext": "Invented pretext for contacting", "critic_damage": "Critic edit left text incoherent",
             "date_error": "Date arithmetic error", "soft_sell": "Soft sell in after-care", "other": "Other wording issue"}
    rows = []
    for c in codes:
        cells = []
        for v in VERS:
            u = sum(1 for x in H[v].values() if x["code"] == c and x["verdict"] == "UNACCEPTABLE")
            ed = sum(1 for x in H[v].values() if x["code"] == c and x["verdict"] == "EDIT")
            cells.append(f"<td>{u or '·'} / {ed or '·'}</td>")
        rows.append(f"<tr><td>{label.get(c, c)}</td>{''.join(cells)}</tr>")
    return "\n".join(rows)


def agree_rows():
    rows = []
    for v in VERS:
        tp, fp, fn, tn = judge_agree(v)
        rows.append(f"<tr><td>{v}</td><td>{tp}</td><td>{fp}</td><td>{fn}</td><td>{tn}</td>"
                    f"<td>{tp/max(1, tp+fn):.0%}</td><td>{tp/max(1, tp+fp):.0%}</td><td>{(tp+tn)/150:.0%}</td></tr>")
    return "\n".join(rows)


def case_matrix():
    cases = [r for r in load("v3")]
    c = Counter((r["request"]["scenario"], r["meta"]["type"]) for r in cases)
    rows = "".join(f"<tr><td>{SCEN[s]}</td>" + "".join(f"<td>{c[(s, t)] or '·'}</td>" for t in ["core", "edge", "adversarial"])
                   + f"<td>{sum(c[(s, t)] for t in ['core', 'edge', 'adversarial'])}</td></tr>" for s in SCEN)
    return rows


ok3, ed3, un3, cok3 = counts("v3")
ok1, ed1, un1, cok1 = counts("v1")

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Vallorée CA Copilot</title>
<style>
@page {{ size: A4; margin: 16mm 14mm; }}
:root {{ --ink:#0b0b0b; --ink2:#52514e; --line:#e4e3df; --bg:#fcfcfb; --acc:#2a78d6; }}
* {{ box-sizing:border-box; }}
body {{ font-family: -apple-system, "Helvetica Neue", Helvetica, "PingFang SC", "Hiragino Sans GB", sans-serif; color:var(--ink);
       background:#fff; font-size:10.5pt; line-height:1.5; max-width: 980px; margin: 0 auto; padding: 24px; }}
h1 {{ font-size:22pt; margin:0 0 4px; }} h2 {{ font-size:15pt; margin:28px 0 8px; padding-top:8px; border-top:2px solid var(--ink); }}
h3 {{ font-size:12pt; margin:18px 0 6px; }} h4 {{ font-size:10.5pt; margin:0 0 6px; }}
p {{ margin:6px 0; }} .muted {{ color:var(--ink2); font-weight:400; }} .small {{ font-size:9pt; }}
table {{ border-collapse:collapse; width:100%; margin:8px 0 12px; font-size:9.3pt; }}
th, td {{ border-bottom:1px solid var(--line); padding:5px 6px; text-align:left; vertical-align:top; }}
th {{ background:#f3f2ef; font-weight:600; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:14px 0; }}
.kpi {{ border:1px solid var(--line); border-radius:8px; padding:10px 12px; }} .kpi b {{ font-size:18pt; display:block; }}
.pill {{ display:inline-block; border-radius:10px; padding:0 7px; font-size:8.5pt; font-weight:600; }}
.ok {{ background:#e3f4e3; color:#0a6b0a; }} .edit {{ background:#fff3cd; color:#7a5600; }} .bad {{ background:#f8d7da; color:#9b1c1c; }}
.zh {{ font-family:"PingFang SC","Hiragino Sans GB",sans-serif; white-space:pre-wrap; }}
.ex {{ border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin:10px 0; break-inside:avoid; }}
.bagrid {{ display:grid; gap:8px; }} .bagrid.c2 {{ grid-template-columns:1fr 1fr; }} .bagrid.c3 {{ grid-template-columns:1fr 1fr 1fr; }}
.ba {{ background:var(--bg); border-radius:6px; padding:8px; font-size:9.3pt; }} .bah {{ font-weight:600; margin-bottom:4px; }}
.note {{ color:#9b1c1c; font-size:8.6pt; margin-top:4px; }} .fix {{ font-size:9.3pt; margin:6px 0 0; }}
.sample {{ border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin:10px 0; break-inside:avoid; }}
.opts {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; }} .opt {{ background:var(--bg); border-radius:6px; padding:8px; font-size:9.2pt; }}
.opth {{ font-weight:600; margin-bottom:4px; }}
img.fig {{ width:100%; border:1px solid var(--line); border-radius:6px; margin:6px 0; }}
img.shot {{ display:block; max-width:100%; height:auto; border:1px solid var(--line); border-radius:4px; margin:4px 0 2px; }}
.worklog tr:not(.shotrow) td {{ border-bottom:none; }} .shotrow {{ break-inside:avoid; }} .todo {{ color:#b45309; font-size:8.5pt; }}
.cols {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
.box {{ border-left:3px solid var(--acc); padding:4px 10px; background:#f4f8fd; margin:8px 0; }}
.badbox {{ border-left-color:#d03b3b; background:#fdf3f3; }}
code {{ font-size:9pt; background:#f3f2ef; padding:0 3px; border-radius:3px; }}
.pb {{ break-before:page; }}
</style></head><body>

<h1>Vallorée CA Copilot</h1>
<p class="muted">Applied AI Engineer written challenge · a tool that drafts three on-brand WeChat messages for luxury Client Advisors · November 2026</p>

<div class="kpis">
<div class="kpi"><b>{ok3/150:.0%}</b>of v3 options are OK to send as-is (v1: {ok1/150:.0%})</div>
<div class="kpi"><b>{un3}/150</b>unacceptable in v3 (v1: {un1}/150)</div>
<div class="kpi"><b>{cok3}/50</b>cases where all three options are OK (v1: {cok1}/50)</div>
<div class="kpi"><b>6 / 50</b>scenarios / test cases, 26 core · 13 edge · 11 adversarial</div>
</div>

<p><b>What it is.</b> A Python tool (<code>ca_copilot/</code>) with a local web app (FastAPI + single-page frontend). Input: a CRM client record, the scenario, the WeChat history,
product information and the occasion. Output: three Chinese WeChat drafts that take <i>different angles</i>, each with a rationale, any remaining
compliance flags, and a timing warning when sending now would break a client preference. The brand, Maison Vallorée (瓦洛蕾), is a fictional
Geneva high-jewellery and watch house. Everything in this submission is fictional.</p>
<p><b>How it got here.</b> Three tested versions. v1 worked on the happy path but invented details and misread old conversations. v2 fixed the
context problems. v3 added a numbered fact sheet and a fact-check step, which cut unacceptable drafts from {un1} to {un3} out of 150.
The same frozen LLM judge and the same manual rubric scored all three versions.</p>

<p class="small muted">Files: <code>deliverables/test_cases_v3.xlsx</code> (C: 50 cases with outputs; D: per-option scores; E: v1 vs v2 vs v3) ·
<code>docs/architecture.svg</code> · code and data in the repository · run it: <code>./start.sh</code> → http://localhost:8000.</p>

<h2>A. Work log</h2>
<p class="small muted">The AI assistant was Claude Code (Claude Opus 5.5) in VS Code for design, coding and analysis. DeepSeek (<code>deepseek-chat</code>) is the
model inside the tool. Under each step is the prompt I gave Claude Code for it.</p>
<table class="worklog"><tr><th>Step</th><th>What I did</th><th>Input</th><th>Output</th><th>Tool or agent used</th></tr>
{worklog_rows()}
</table>

<h2 class="pb">B. Methodology</h2>
<h3>B1. Brand assumptions</h3>
<p>Maison Vallorée: founded 1897 in Geneva, high jewellery and fine watchmaking, “quiet luxury”. Clients are mostly 30–55 year-old
self-purchasers in Tier-1 cities, plus gift buyers and a small group of watch collectors. The voice is <b>温润 · 克制 · 精准</b>
(warm, restrained, precise), like a knowledgeable old friend. Full rules are in <code>brand/brand_bible.md</code>. The ones that drive the design:</p>
<div class="cols"><div>
<p><b>Eight hard rules</b> (breaking any one makes a draft unacceptable): no discounts or hints of one (global price policy) · no investment or
“保值/升值” claims · no Advertising-Law absolutes (最好, 顶级, 唯一…) · no disparaging other brands or daigou · <b>no fabrication</b> ·
privacy (no spend or tier, discreet gifts) · respect stated preferences · no remarks on age, looks or health.</p>
</div><div>
<p><b>Allowed gestures</b>, never framed as a price concession: engraving, gift box and card, lifetime jewellery cleaning, 30-day ring resizing,
warranty extended to 8 years, private appointments, same-city delivery, a 7-day hold.<br><b>Style</b>: address by surname + 女士/先生 or a
preferred name; 40–150 characters; at most one emoji (none for the top tier); one low-pressure next step.</p>
</div></div>

<h3>B2. Tool design</h3>
<img class="fig" src="img/architecture.png">
<p><b>Design principles.</b> (1) <b>Do in code what code does reliably.</b> Dates, weekdays, whether the client is waiting for a reply, the CA's
city and which preferences apply are computed deterministically, not left to the LLM. (2) <b>The three options must be real choices.</b> Each
scenario playbook defines three angles: for a price objection, empathy + value / policy + guarantees / alternatives or services. The CA picks a
strategy, not a paraphrase. (3) <b>The model may only say what the input supports.</b> v3 turns the input into a numbered fact sheet; the generator
cites fact IDs, and a separate critic removes unsupported specifics. (4) <b>Defence in depth.</b> The critic catches semantic fabrication, unit-tested
rules catch compliance words that must never appear, and a single repair pass handles what is left. (5) <b>The CA stays in the loop.</b> The tool
drafts and warns; it never sends.</p>

<h3>B3. Test set design</h3>
<table><tr><th>Scenario</th><th>Core</th><th>Edge</th><th>Adversarial</th><th>Total</th></tr>{case_matrix()}</table>
<p>The 20 personas are reused across scenarios, so one client appears in different moments; this also catches inconsistent tone. Cases vary
deliberately along: <b>relationship stage</b> (new, active, dormant 1–4 years) · <b>history state</b> (pending question, closed old thread, CA
message left unanswered, no history) · <b>product info</b> (none, one, several including an unsuitable trap such as a ¥520k watch for a
budget-sensitive client) · <b>sensitive context</b> (mourning, complaint, discreet gift, weekend-only contact, “no event invitations”) ·
<b>register</b> (formal collector, mixed Chinese–English) · <b>adversarial pressure</b> (11-11 discount, staff price, Hong Kong price,
daigou, competitor comparison, compensation discount after a defect). Each case records what it tests (column “Test design” in the Excel).</p>

<h3>B4. What “good” and “not acceptable” mean</h3>
<div class="cols"><div class="box">
<p><b>Good (OK to send as-is)</b><br>Breaks no hard rule · uses at least one true, specific detail about the client · answers the client's pending
message first · fits the scenario goal and the moment · sounds like a person typing on WeChat, in the brand voice · one easy-to-decline next step ·
the three options differ in approach. A CA would send it with at most a word changed.</p>
<p><b>Needs edit</b><br>Safe, but a CA should touch it: a stock phrase, a small invented pretext (“前几天整理资料时看到…”), awkward wording.</p>
</div><div class="box badbox">
<p><b>Not acceptable</b><br>Any of the eight hard rules, plus: ignoring the client's question · treating a months-old thread as live · selling inside a
greeting or a complaint reply · wrong name or gender · misapplying a policy (resizing for a bracelet) · inviting a client who refuses invitations ·
inventing memories, products, events or stock. <b>Fabrication is the most dangerous failure</b>: an invented memory reads as warm, so it passes a
quick glance, but it breaks trust the moment the client notices.</p>
</div></div>

<h3>B5. How results were evaluated</h3>
<p><b>Three layers.</b> (1) <b>Rule checks</b> on every draft (deterministic, unit-tested). (2) <b>LLM judge</b>: six 1–5 dimensions
(personalisation, brand voice, naturalness, appropriateness, scenario goal, faithfulness), a <code>hard_fail</code> flag, and a set-level diversity score.
The judge must fact-check first. (3) <b>Manual review</b> of all 150 options per version (450 in total) as OK / Edit / Unacceptable, with a defect code.
Manual review is the primary measure; the judge is the scalable screen.</p>
<p><b>Judge calibration.</b> The first judge passed almost everything (it caught 2 of 19 unacceptable drafts). I tightened it in two rounds against the
manual labels, then <b>froze it and re-scored every version with the same judge</b>, so differences between versions come from the tool, not the
ruler. Agreement with the manual labels:</p>
<table><tr><th>Version</th><th>Both fail</th><th>Judge only</th><th>Manual only</th><th>Both pass</th><th>Recall</th><th>Precision</th><th>Agreement</th></tr>{agree_rows()}</table>
<p class="small muted">The final judge never misses an unacceptable draft in v2–v3, and is deliberately strict: most “judge only” flags are drafts
the manual review rated Edit. A conservative gate is the right trade-off for client-facing text. Caveat: the generator and the judge are the same model
family (only a DeepSeek key was available); the code can switch the judge to Qwen with one environment variable.</p>
<p class="small muted">Manual review labels were drafted in Claude Code by reading every output against the rubric, then checked by me. They are in
<code>data/human_review_v*.yaml</code> and in the Excel.</p>

<h2 class="pb">C. 50 test cases</h2>
<p>All 50 cases with their inputs and the three outputs are in <b><code>deliverables/test_cases_v3.xlsx</code></b>, sheet “C. 50 test cases”, using the
exact columns of the brief plus a <b>Tool version</b> column (all final results are <b>v3</b>). Sheet “E. v1 vs v2 vs v3” shows every option in all
three versions side by side with its review verdict. A sample of v3 outputs, one per scenario:</p>
{sample_outputs()}

<h2 class="pb">D. Evaluation report</h2>
<div class="cols"><img class="fig" src="img/human_verdicts.png"><img class="fig" src="img/judge_dimensions.png"></div>
<table><tr><th>Metric</th><th>v1</th><th>v2</th><th>v3</th></tr>{metrics_table()}</table>
<h3>Findings</h3>
<p><b>1. Fabrication is the core risk, and prompting alone does not remove it.</b> In v1, 13 of 19 unacceptable drafts were invented facts; in v2,
after explicit “do not invent” rules, it was still 12 of 13. The cause is structural: angles such as “warm memory” or “light share” demand content,
and when the record is thin the model fills the gap. Making facts explicit and checkable (fact sheet + critic) cut unacceptable drafts to 1.</p>
<p><b>2. Time is where LLMs slip.</b> v1 answered a March message in November as if it were live (all three options in G08 and A08). Pre-computed
signals fixed this completely. One date-arithmetic slip (“四年多” for 5 years 8 months) remains.</p>
<p><b>3. Compliance words are the easy part.</b> No draft in any version offered a discount, used an investment claim or an Advertising-Law absolute
after guardrails; adversarial cases (staff price, daigou, compensation) are handled well from v1. The hard part is <i>judgement</i>: preferences,
timing, tone in sensitive moments.</p>
<p><b>4. Templated feel is measurable.</b> In v1, 8 of 9 greetings told the client to dress warmly and 21% of drafts said “我一直记着”. Banning
these by name reduced the repetition; across 50 cases, cross-case repetition is a better signal of “scripted” than any single message.</p>
<p><b>5. Trade-offs of v3.</b> The critic adds one LLM call (mean latency 4.8 s → 6.7 s) and edits 71 of 150 drafts, occasionally leaving a
sentence without its point (2 drafts). Personalisation is still the lowest judge dimension (3.93): being stricter about facts makes some drafts plainer.</p>
<h3>Demo screenshots</h3>
<p class="small muted">Local web app, live v3 runs. <b>A08</b>: the tool warns that today is Tuesday and this client accepts messages only at weekends;
each draft lists the fact IDs it cites and what the fact-check removed. <b>P02</b>: a staff-price request on 11-11; all three options decline
clearly and still help with the gift. <b>Evaluation page</b>: the saved test-set results for G04 (birthday during mourning) side by side for v1, v2
and v3, with review verdicts and judge scores. Live runs vary between runs, so they can differ from the evaluated outputs (see E3).</p>
<img class="fig" src="img/web_generate_A08.png">
<img class="fig pb" src="img/web_generate_P02.png">
<img class="fig" src="img/web_eval_G04.png">

<h2 class="pb">E. Defects and next steps</h2>
<h3>E1. Defects found, by version</h3>
<p class="small muted">Count of options per defect: unacceptable / needs edit (manual review).</p>
<table><tr><th>Defect</th><th>v1</th><th>v2</th><th>v3</th></tr>{defect_table()}</table>
<h3>E2. Changes made, with before and after</h3>
<table><tr><th>Version</th><th>Changes</th></tr>
<tr><td>v1 → v2</td><td>Context builder: closed-thread detection (client message older than 3 days is not “pending”), CA boutique city, weekday and
weekend-only check, pronoun 您/你 · Prompt: explicit fact boundaries, banned stock phrases, no sign-off · Playbooks: greeting angle without services,
price-objection alternatives only from the product list, event-time conflict check · Guardrails: fixed 3 false positives found in v1 (refusals read as
discount offers, “灯火可亲” read as slang, “3万8” price parsing), new checks for service words in greetings, CA location, pronoun mixing, clichés ·
7 unit tests.</td></tr>
<tr><td>v2 → v3</td><td>Numbered fact sheet ([C] client, [H] history, [P] product, [X] context, [S] policy) and <code>facts_used</code> per option ·
fact-check critic (one LLM call per request) · CRM preferences turned into hard instructions · guardrails for invented new arrivals and exhibitions,
ring-only resizing, unlisted plus-ones, “1万6千8” parsing · 11 unit tests in total.</td></tr>
<tr><td>Evaluation</td><td>Judge v1 (lenient) → v2 (too strict) → v3 (calibrated, consistency rule) → final (given the full policy list), then frozen. All
versions re-scored with the final judge.</td></tr></table>
{example_blocks()}

<h3>E3. What remains to be fine-tuned</h3>
<table><tr><th>Remaining issue</th><th>Evidence</th><th>Next step</th></tr>
<tr><td>Critic edits can leave a sentence without its point</td><td>A06-1, RA02-3</td><td>Critic returns a fluent rewrite and the result is checked again; if the
fix would remove the angle's core, regenerate that option instead of deleting phrases.</td></tr>
<tr><td>Critic removes legitimate boutique names</td><td>R01, RA08 (“湖滨店”, “静安”)</td><td>Put the boutique and CA facts in the fact sheet.</td></tr>
<tr><td>Date arithmetic</td><td>RA03-2 “四年多” (5 years 8 months)</td><td>Pre-compute durations for every purchase and conversation in the fact sheet.</td></tr>
<tr><td>Small invented pretexts</td><td>R08-1, RA05-3</td><td>A whitelist of honest openers (“想到您…”) and a soft rule; measure with the pretext detector.</td></tr>
<tr><td>Old thread referenced ambiguously</td><td>A08-3</td><td>Pass only the gist of closed threads, not their wording.</td></tr>
<tr><td>Personalisation is the weakest dimension</td><td>judge 3.93 / 5</td><td>Richer CRM memory (past chats, occasions, family dates) through retrieval;
few-shot examples from real top-performing CAs; ultimately fine-tune on approved messages.</td></tr>
<tr><td>Evaluation bias</td><td>Same model family judges; test set written by the tool's author</td><td>Second judge family (Qwen), a panel of real CAs for
inter-rater agreement, cases sampled from anonymised CA logs, a larger red-team set.</td></tr>
<tr><td>Single sample per case</td><td>Live re-runs of the same case produce different drafts</td><td>Evaluate 3–5 samples per case and report the
worst case and variance, not one draw; consider a lower temperature for sensitive scenarios.</td></tr>
<tr><td>No real-world signal yet</td><td>—</td><td>Online metrics: which option the CA picks, edit distance before sending, client reply rate, opt-outs.</td></tr>
<tr><td>Latency and cost</td><td>6.7 s mean, 2 calls</td><td>Stream the first option; run the critic in parallel per option; cache the brand and system prompt.</td></tr>
<tr><td>Timing only warns</td><td>A08</td><td>Schedule the send for the next allowed window.</td></tr>
</table>

<h2>Bonus. Architecture</h2>
<p>See the diagram in B2 (source: <code>docs/architecture.svg</code>). Code map: <code>context.py</code> (step 1) · <code>prompts.py</code>,
<code>scenarios.py</code> (2) · <code>pipeline.py</code> (2–4, repair) · <code>guardrails.py</code> (4) · <code>judge.py</code>, <code>scripts/</code> (offline loop).
Earlier versions are frozen in <code>snapshots/</code>.</p>
</body></html>"""

out = DOCS / "report.html"
out.write_text(HTML, encoding="utf-8")
print("wrote", out)
chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
pdf = ROOT / "deliverables" / "Valloree_CA_Copilot_report.pdf"
subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", out.as_uri()],
               check=False, capture_output=True)
print("wrote", pdf, pdf.exists())
