"""End-to-end generation pipeline: context -> generate 3 -> guardrails -> repair -> result."""
from __future__ import annotations

import os
import time

from . import guardrails as G
from .llm import LLM
from .prompts import CRITIC_SYSTEM, critic_prompt, repair_prompt, system_prompt, user_prompt
from .schema import Candidate, Request, Result

VERSION = "v3"  # earlier versions frozen in snapshots/


class Generator:
    def __init__(self, llm: LLM | None = None, max_repairs: int = 1, use_critic: bool = True):
        self.use_critic = use_critic
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

        # v3: fact-check critic — one call reviews all three against the numbered fact sheet
        critic_notes: list[list[str]] = [[] for _ in raw]
        if self.use_critic:
            try:
                rev = self.llm.json_chat(CRITIC_SYSTEM, critic_prompt(req, [c.get("message", "") for c in raw]), temperature=0.0)
                for r in rev.get("reviews", []):
                    i = int(r.get("id", 0)) - 1
                    if 0 <= i < len(raw) and r.get("unsupported") and r.get("revised", "").strip():
                        raw[i]["message"] = r["revised"].strip()
                        critic_notes[i] = r["unsupported"]
            except Exception as e:  # critic is best-effort; guardrails still run
                out.setdefault("analysis", {})["critic_error"] = str(e)

        cands: list[Candidate] = []
        for k, c in enumerate(raw):
            cand = Candidate(angle=c.get("angle", ""), message=c.get("message", "").strip(), rationale=c.get("rationale", ""),
                             facts_used=[str(x) for x in c.get("facts_used", [])], critic_removed=critic_notes[k])
            if critic_notes[k]:
                cand.repaired = True
                cand.rationale += "｜事实核查已删改：" + "；".join(critic_notes[k])
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
