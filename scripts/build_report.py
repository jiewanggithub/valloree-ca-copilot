"""Aggregate results/<version>/*.json into metrics + the deliverable Excel workbook.

    python scripts/build_report.py v1            # one version
    python scripts/build_report.py v1 v2         # compare; Excel 'Test cases' sheet uses the last version
"""
from __future__ import annotations

import json
import sys
from collections import Counter

import yaml
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
DIMS = ["personalization", "brand_voice", "naturalness", "appropriateness", "goal", "faithfulness"]
SCEN = {"greeting": "1 Greeting", "recommendation": "2 Recommendation", "aftercare": "3 Post-purchase care",
        "reactivation": "4 Reactivation", "event": "5 Event invitation", "price_objection": "6 Price objection"}


def load(version: str) -> list[dict]:
    files = sorted((ROOT / "results" / version).glob("*.json"))
    order = {p: i for i, p in enumerate(["G", "R", "A", "RA", "E", "P"])}
    recs = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    return sorted(recs, key=lambda r: (order[r["case_id"].rstrip("0123456789")], r["case_id"]))


def human(version: str) -> dict:
    f = ROOT / "data" / f"human_review_{version}.yaml"
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.exists() else {}


def human_lines(version: str, recs: list[dict]) -> list[str]:
    h = human(version)
    if not h:
        return []
    n = sum(len(r["result"]["candidates"]) for r in recs)
    un = [k for k, v in h.items() if v["verdict"] == "UNACCEPTABLE"]
    ed = [k for k, v in h.items() if v["verdict"] == "EDIT"]
    bad_cases = {k.rsplit("-", 1)[0] for k in un}
    ok_cases = {r["case_id"] for r in recs} - {k.rsplit("-", 1)[0] for k in h}
    codes = Counter(v["code"] for v in h.values() if v["verdict"] == "UNACCEPTABLE")
    return [f"-- manual review ({version}) --",
            f"OK (send as-is): {n-len(un)-len(ed)}/{n} = {(n-len(un)-len(ed))/n:.0%}   EDIT: {len(ed)}   UNACCEPTABLE: {len(un)} = {len(un)/n:.0%}",
            f"cases with an unacceptable candidate: {len(bad_cases)}/{len(recs)}   cases where all 3 are OK: {len(ok_cases)}/{len(recs)}",
            "unacceptable by defect: " + ", ".join(f"{k}={v}" for k, v in codes.most_common())]


def clean_scores(jc: dict) -> dict:
    sc = jc.get("scores", {}) or {}
    return {d: int(sc[d]) for d in DIMS if str(sc.get(d, "")).strip().isdigit()}


def cand_rows(recs):
    for r in recs:
        j = r.get("judge", {}).get("candidates", [])
        for i, c in enumerate(r["result"]["candidates"]):
            jc = j[i] if i < len(j) else {}
            yield r, i, c, jc


def metrics(recs: list[dict]) -> dict:
    m = {"cases": len(recs), "candidates": 0, "rule_hard": 0, "judge_hard": 0, "acceptable": 0,
         "send_ready": 0, "repaired": 0, "cases_all3_ok": 0, "cases_ge1_send_ready": 0,
         "dims": defaultdict(list), "by_scen": defaultdict(lambda: defaultdict(list)), "diversity": [], "sim": []}
    per_case_ok = defaultdict(list)
    per_case_ready = defaultdict(list)
    for r, i, c, jc in cand_rows(recs):
        m["candidates"] += 1
        rule_hard = any(x.startswith("[HARD") for x in c["issues"])
        jh = bool(jc.get("hard_fail"))
        sc = clean_scores(jc)
        avg = sum(sc.get(d, 0) for d in DIMS) / len(DIMS) if sc else 0
        ok = not rule_hard and not jh and min(sc.values() or [0]) >= 3
        ready = ok and avg >= 4.0
        m["rule_hard"] += rule_hard
        m["judge_hard"] += jh
        m["acceptable"] += ok
        m["send_ready"] += ready
        m["repaired"] += c.get("repaired", False)
        for d in DIMS:
            if d in sc:
                m["dims"][d].append(sc[d])
        s = r["request"]["scenario"]
        m["by_scen"][s]["avg"].append(avg)
        m["by_scen"][s]["ok"].append(ok)
        m["by_scen"][s]["hard"].append(rule_hard or jh)
        per_case_ok[r["case_id"]].append(ok)
        per_case_ready[r["case_id"]].append(ready)
    for r in recs:
        if "judge" in r:
            m["diversity"].append(r["judge"].get("set", {}).get("diversity", 0))
        m["sim"].append(r["result"]["analysis"].get("max_similarity", 0))
    m["cases_all3_ok"] = sum(all(v) for v in per_case_ok.values())
    m["cases_ge1_send_ready"] = sum(any(v) for v in per_case_ready.values())
    return m


def summary_lines(version: str, m: dict) -> list[str]:
    avg = lambda xs: round(sum(xs) / len(xs), 2) if xs else 0  # noqa: E731
    n = m["candidates"] or 1
    lines = [
        f"== {version} ==  cases={m['cases']} candidates={m['candidates']}",
        f"acceptable (no hard fail, all dims>=3): {m['acceptable']}/{n} = {m['acceptable']/n:.0%}",
        f"send-ready (acceptable & avg>=4):       {m['send_ready']}/{n} = {m['send_ready']/n:.0%}",
        f"cases where all 3 acceptable:            {m['cases_all3_ok']}/{m['cases']}",
        f"cases with >=1 send-ready option:        {m['cases_ge1_send_ready']}/{m['cases']}",
        f"rule HARD flags after repair: {m['rule_hard']}   judge hard_fail: {m['judge_hard']}   auto-repaired: {m['repaired']}",
        f"set diversity (judge 1-5): {avg(m['diversity'])}   max pairwise text similarity: {avg(m['sim'])}",
        "dimension means: " + "  ".join(f"{d}={avg(m['dims'][d])}" for d in DIMS),
    ]
    for s, v in m["by_scen"].items():
        lines.append(f"  {SCEN[s]:<22} avg={avg(v['avg'])}  acceptable={sum(v['ok'])}/{len(v['ok'])}  hard={sum(v['hard'])}")
    return lines


def write_excel(version: str, recs: list[dict], all_metrics: dict[str, dict]):
    wb = Workbook()
    hdr_fill = PatternFill("solid", fgColor="1F2A44")
    hdr_font = Font(color="FFFFFF", bold=True)
    wrap = Alignment(wrap_text=True, vertical="top")

    def sheet(ws, headers, rows, widths):
        ws.append(headers)
        for c in ws[1]:
            c.fill, c.font, c.alignment = hdr_fill, hdr_font, wrap
        for row in rows:
            ws.append(row)
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = wrap
        ws.freeze_panes = "B2"

    # 1. Deliverable C: the brief's exact columns (+ version)
    ws = wb.active
    ws.title = "C. 50 test cases"
    rows = []
    for r in recs:
        q = r["request"]
        cl = q["client"]
        client_txt = "\n".join(filter(None, [
            f"{cl['client_id']} {cl['surname']}{'女士' if cl['gender']=='F' else '先生'}" + (f"（{cl['preferred_name']}）" if cl.get("preferred_name") else ""),
            f"{cl.get('age_band','')} · {cl.get('city','')} · {cl.get('tier','')} · {cl.get('occupation','') or ''}",
            ("生日 " + cl["birthday"]) if cl.get("birthday") else None,
            ("兴趣：" + "、".join(cl["interests"])) if cl.get("interests") else None,
            ("风格：" + cl["style_notes"]) if cl.get("style_notes") else None,
            ("家庭：" + cl["family"]) if cl.get("family") else None,
            "购买：" + ("；".join(f"{p['date']} {p['item']}" + (f"（{p['note']}）" if p.get("note") else "") for p in cl["purchases"]) or "无"),
            ("偏好：" + "；".join(cl["preferences"])) if cl.get("preferences") else None,
            ("CA备注：" + cl["ca_notes"]) if cl.get("ca_notes") else None,
            f"今天：{q['today']}",
            ("背景：" + q["context"]) if q.get("context") else None,
        ]))
        hist = "\n".join(f"[{t['time']}] {'CA' if t['speaker']=='CA' else '客户'}：{t['text']}" for t in q["history"]) or "（无）"
        prod = "\n".join(f"{p['name']} ¥{p.get('price','')}" + (f"｜{p['material']}" if p.get("material") else "") for p in q["products"]) or "N/A"
        outs = [c["message"] for c in r["result"]["candidates"]]
        rows.append([r["case_id"], SCEN[q["scenario"]], client_txt, hist, prod, *outs, r["result"]["version"]])
    sheet(ws, ["Case ID", "Scenario", "Client information", "Conversation history", "Product information",
               "Output 1", "Output 2", "Output 3", "Tool version"], rows, [8, 14, 42, 42, 30, 42, 42, 42, 9])

    # 2. per-candidate evaluation
    ws2 = wb.create_sheet("D. Candidate scores")
    rows = []
    hv = human(version)
    for r, i, c, jc in cand_rows(recs):
        sc = clean_scores(jc)
        hr = hv.get(f"{r['case_id']}-{i+1}", {})
        rows.append([r["case_id"], SCEN[r["request"]["scenario"]], r["meta"]["type"], i + 1, c["angle"], c["message"],
                     hr.get("verdict", "OK"), hr.get("code", ""), hr.get("note", ""),
                     *[sc.get(d) for d in DIMS],
                     round(sum(sc.get(d, 0) for d in DIMS) / 6, 2) if sc else None,
                     "Y" if jc.get("hard_fail") else "", jc.get("hard_fail_reason", ""),
                     "\n".join(c["issues"]), "Y" if c.get("repaired") else "", jc.get("comment", "")])
    sheet(ws2, ["Case", "Scenario", "Type", "#", "Angle", "Message", "Reviewer verdict", "Defect code", "Reviewer note",
                *DIMS, "Avg", "Judge hard fail", "Reason", "Rule flags", "Auto-repaired", "Judge comment"], rows,
          [7, 14, 10, 4, 12, 50, 12, 14, 30, 8, 8, 8, 8, 8, 8, 7, 8, 30, 30, 8, 40])
    red = PatternFill("solid", fgColor="F8D7DA"); amber = PatternFill("solid", fgColor="FFF3CD")
    for row in ws2.iter_rows(min_row=2):
        if row[6].value == "UNACCEPTABLE":
            row[6].fill = red
        elif row[6].value == "EDIT":
            row[6].fill = amber

    # 3. case design
    ws3 = wb.create_sheet("Test design")
    sheet(ws3, ["Case", "Scenario", "Type", "What the case tests", "Generator analysis (key facts / risks / timing)", "Judge set comment"],
          [[r["case_id"], SCEN[r["request"]["scenario"]], r["meta"]["type"], r["meta"]["focus"],
            json.dumps({k: v for k, v in r["result"]["analysis"].items()}, ensure_ascii=False, indent=0),
            r.get("judge", {}).get("set", {}).get("comment", "")] for r in recs],
          [7, 14, 10, 50, 60, 50])

    # 3b. version comparison (deliverable E: before / after)
    if len(all_metrics) > 1:
        ws5 = wb.create_sheet("E. v1 vs v2 vs v3")
        vers = list(all_metrics)
        loaded = {v: {r["case_id"]: r for r in load(v)} for v in vers}
        hums = {v: human(v) for v in vers}
        rows = []
        for r in recs:
            for i in range(3):
                row = [r["case_id"], SCEN[r["request"]["scenario"]], i + 1]
                for v in vers:
                    rv = loaded[v].get(r["case_id"])
                    msg = rv["result"]["candidates"][i]["message"] if rv else ""
                    hv = hums[v].get(f"{r['case_id']}-{i+1}", {})
                    row += [msg, hv.get("verdict", "OK") + (f" · {hv['code']}" if hv else "")]
                rows.append(row)
        heads = ["Case", "Scenario", "#"] + [x for v in vers for x in (f"{v} message", f"{v} reviewer verdict")]
        sheet(ws5, heads, rows, [7, 14, 4] + [45, 16] * len(vers))
        red = PatternFill("solid", fgColor="F8D7DA"); amber = PatternFill("solid", fgColor="FFF3CD")
        for row in ws5.iter_rows(min_row=2):
            for c in row[4::2]:
                if str(c.value).startswith("UNACCEPTABLE"):
                    c.fill = red
                elif str(c.value).startswith("EDIT"):
                    c.fill = amber

    # 4. summary
    ws4 = wb.create_sheet("Summary")
    for v, m in all_metrics.items():
        for line in summary_lines(v, m) + human_lines(v, load(v)):
            ws4.append([line])
        ws4.append([])
    ws4.column_dimensions["A"].width = 120

    out = ROOT / "deliverables" / f"test_cases_{version}.xlsx"
    out.parent.mkdir(exist_ok=True)
    wb.save(out)
    return out


if __name__ == "__main__":
    versions = sys.argv[1:] or ["v1"]
    allm = {}
    for v in versions:
        recs = load(v)
        allm[v] = metrics(recs)
        print("\n".join(summary_lines(v, allm[v]) + human_lines(v, recs)))
    print("Excel:", write_excel(versions[-1], load(versions[-1]), allm))
