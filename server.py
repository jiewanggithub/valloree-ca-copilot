"""Local web app: FastAPI backend + single-page frontend (frontend/index.html).

    uvicorn server:app --port 8000      ->  http://localhost:8000
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ca_copilot.context import build_signals, fact_sheet
from ca_copilot.data import load_cases, load_clients, load_products
from ca_copilot.pipeline import VERSION, Generator
from ca_copilot.schema import SCENARIO_LABELS, Request, Scenario

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Vallorée CA Copilot")
_gen: Generator | None = None


def generator() -> Generator:
    global _gen
    if _gen is None:
        _gen = Generator()  # created lazily so the UI loads even without an API key
    return _gen


@app.get("/api/meta")
def meta():
    clients, products = load_clients(), load_products()
    cases = [{"id": r.case_id, "type": m["type"], "focus": m["focus"], "request": r.model_dump(mode="json")}
             for r, m in load_cases()]
    return {
        "version": VERSION,
        "scenarios": [{"id": s.value, "label": SCENARIO_LABELS[s]} for s in Scenario],
        "clients": {k: v.model_dump(mode="json") for k, v in clients.items()},
        "products": {k: v.model_dump(mode="json") for k, v in products.items()},
        "cases": cases,
    }


@app.post("/api/signals")
def signals(req: Request):
    """Deterministic context only (no LLM): what the tool computes before generation."""
    return {"signals": build_signals(req), "facts": fact_sheet(req)}


@app.post("/api/generate")
def generate(req: Request):
    try:
        res = generator().generate(req)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"result": res.model_dump(mode="json"), "signals": build_signals(req)}


@app.get("/api/eval")
def evaluation():
    """Saved test-set results for every version + manual review labels (no API calls)."""
    out = {}
    for vdir in sorted((ROOT / "results").glob("v[0-9]*")):
        v = vdir.name
        hf = ROOT / "data" / f"human_review_{v}.yaml"
        human = (yaml.safe_load(hf.read_text(encoding="utf-8")) or {}) if hf.exists() else {}
        cases = {}
        for f in vdir.glob("*.json"):
            r = json.loads(f.read_text(encoding="utf-8"))
            cands = []
            for i, c in enumerate(r["result"]["candidates"]):
                jl = r.get("judge", {}).get("candidates", [])
                j = jl[i] if i < len(jl) else {}
                h = human.get(f"{r['case_id']}-{i+1}")
                cands.append({"angle": c["angle"], "message": c["message"], "issues": c["issues"],
                              "critic_removed": c.get("critic_removed", []), "scores": j.get("scores", {}),
                              "hard_fail": bool(j.get("hard_fail")), "judge_comment": j.get("comment", ""),
                              "verdict": h["verdict"] if h else "OK", "review_note": h["note"] if h else ""})
            cases[r["case_id"]] = {"candidates": cands, "analysis": r["result"]["analysis"]}
        out[v] = cases
    return out


app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")
