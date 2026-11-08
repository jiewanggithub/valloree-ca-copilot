"""End-to-end generation pipeline: context -> generate 3 -> guardrails -> repair -> result."""
from __future__ import annotations

import os
import time

from . import guardrails as G
from .llm import LLM
from .prompts import repair_prompt, system_prompt, user_prompt
from .schema import Candidate, Request, Result

VERSION = "v1"


class Generator:
    def __init__(self, llm: LLM | None = None, max_repairs: int = 1):
        self.llm = llm or LLM(os.getenv("GEN_PROVIDER", "deepseek"), temperature=0.9)
        self.max_repairs = max_repairs

    def generate(self, req: Request) -> Result:
        t0 = time.time()
        sys_p, usr_p = system_prompt(req), user_prompt(req)
        out = self.llm.json_chat(sys_p, usr_p)
        raw = out.get("candidates", [])[:3]
        # top up if the model returned fewer than 3
        while len(raw) < 3:
            more = self.llm.json_chat(sys_p, usr_p).get("candidates", [])
            raw += more[: 3 - len(raw)]

        cands: list[Candidate] = []
        for c in raw:
            cand = Candidate(angle=c.get("angle", ""), message=c.get("message", "").strip(), rationale=c.get("rationale", ""))
            issues = G.check(cand.message, req)
            tries = 0
            while G.hard(issues) and tries < self.max_repairs:
                fix = self.llm.json_chat(sys_p, usr_p + "\n\n" + repair_prompt(cand.message, [str(i) for i in G.hard(issues)]), temperature=0.4)
                cand.message = fix.get("message", cand.message).strip()
                cand.repaired = True
                issues = G.check(cand.message, req)
                tries += 1
            cand.issues = [str(i) for i in issues]
            cands.append(cand)

        analysis = out.get("analysis", {})
        analysis["max_similarity"] = round(G.diversity([c.message for c in cands]), 2)
        return Result(case_id=req.case_id, version=VERSION, analysis=analysis, candidates=cands,
                      model=self.llm.name, latency_s=round(time.time() - t0, 1))
