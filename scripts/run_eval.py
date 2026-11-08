"""Run the generator (and optionally the judge) over the 50-case test set.

    python scripts/run_eval.py --version v1            # generate + judge all cases
    python scripts/run_eval.py --version v1 --only G04 P02
    python scripts/run_eval.py --version v1 --no-judge
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ca_copilot import pipeline  # noqa: E402
from ca_copilot.data import load_cases  # noqa: E402
from ca_copilot.judge import Judge  # noqa: E402
from ca_copilot.pipeline import Generator  # noqa: E402
from ca_copilot.schema import Result  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "results"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=pipeline.VERSION)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--rejudge", action="store_true", help="re-score existing results with the current judge only")
    args = ap.parse_args()

    pipeline.VERSION = args.version
    outdir = OUT / args.version
    outdir.mkdir(parents=True, exist_ok=True)
    cases = [c for c in load_cases() if not args.only or c[0].case_id in args.only]
    gen = None if args.rejudge else Generator()
    judge = None if args.no_judge else Judge()

    def rejudge(item):
        req, _ = item
        f = outdir / f"{req.case_id}.json"
        rec = json.loads(f.read_text(encoding="utf-8"))
        res = Result(**rec["result"])
        rec.setdefault("judge_history", []).append(rec.get("judge"))
        rec["judge"] = judge.evaluate(req, res)
        f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        return req.case_id, res

    def work(item):
        req, meta = item
        res = gen.generate(req)
        rec = {"case_id": req.case_id, "meta": meta, "request": req.model_dump(), "result": res.model_dump()}
        if judge:
            rec["judge"] = judge.evaluate(req, res)
        (outdir / f"{req.case_id}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        return req.case_id, res

    with ThreadPoolExecutor(args.workers) as ex:
        futs = [ex.submit(rejudge if args.rejudge else work, c) for c in cases]
        for f in as_completed(futs):
            try:
                cid, res = f.result()
                flags = sum(1 for c in res.candidates if any(i.startswith("[HARD") for i in c.issues))
                print(f"✓ {cid}  {res.latency_s}s  hard-flag candidates: {flags}")
            except Exception as e:
                print("✗", e)


if __name__ == "__main__":
    main()
