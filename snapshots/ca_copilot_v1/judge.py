"""LLM-as-judge with an explicit rubric. Uses a different model family from the generator
to reduce self-preference bias. Scores are calibrated against human spot-checks (see report)."""
from __future__ import annotations

import json
import os

from .context import build_signals
from .llm import LLM
from .prompts import BRAND_CORE
from .scenarios import PLAYBOOKS
from .schema import SCENARIO_LABELS, Request, Result

DIMENSIONS = {
    "personalization": "个性化：是否用到了客户真实、具体的信息，而不是换个名字就能群发",
    "brand_voice": "品牌语气：是否温润、克制、精准，符合瓦洛蕾“懂行、有分寸的老朋友”的定位",
    "naturalness": "自然度：是否像真人顾问在微信上手打的话，而不是模板、广告文案或机器翻译",
    "appropriateness": "分寸与时机：是否不推销、不施压、不打扰，是否回应了客户最后的消息，是否尊重客户偏好与情绪",
    "goal": "场景目标：是否完成了该场景的目标（见场景说明）",
    "faithfulness": "事实忠实：是否只使用了输入中提供的信息，没有编造产品、价格、活动、服务或客户经历",
}

RUBRIC = """评分标准（每项1-5分）：
5 = 优秀，CA可以直接发送
4 = 良好，只需微调一两个词
3 = 可用但平淡或有小问题，需要CA修改
2 = 有明显问题，不建议发送
1 = 不可接受

另外判断 hard_fail（true/false）：只要出现以下任意一项即为 true——
提供或暗示折扣/优惠；投资/保值/升值表述；广告法极限词；贬低其他品牌或渠道；编造输入中不存在的产品/价格/活动/服务/客户经历；
暴露客户消费金额或等级；违反客户明确偏好；忽略客户待回应的问题；称呼错误；在敏感情境（如投诉、服丧）中语气明显不当；问候场景中推销。"""


def judge_prompt(req: Request, res: Result) -> tuple[str, str]:
    pb = PLAYBOOKS[req.scenario]
    sys_p = f"""你是一位严格的奢侈品客户关系质检专家，为虚构品牌瓦洛蕾评估顾问微信话术。以下是品牌规范：

{BRAND_CORE}

{RUBRIC}

维度说明：
""" + "\n".join(f"- {k}: {v}" for k, v in DIMENSIONS.items()) + """

只输出JSON：
{"candidates": [{"id": 1, "scores": {"personalization": n, "brand_voice": n, "naturalness": n, "appropriateness": n, "goal": n, "faithfulness": n},
  "hard_fail": bool, "hard_fail_reason": "", "comment": "一句话点评"} ... 共3个],
 "set": {"diversity": 1-5（三条是否给了CA真正不同的选择）, "best_id": n, "comment": ""}}"""
    history = "\n".join(f"[{t.time}] {t.speaker}：{t.text}" for t in req.history) or "（无）"
    cands = "\n\n".join(f"候选{i+1}（{c.angle}）：{c.message}" for i, c in enumerate(res.candidates))
    usr_p = f"""【场景】{SCENARIO_LABELS[req.scenario]}；目标：{pb['goal']}；禁止：{'；'.join(pb['nevers'])}
【关键信号】{json.dumps(build_signals(req), ensure_ascii=False)}
【客户档案】{req.client.model_dump_json(exclude_none=True)}
【对话历史】
{history}
【产品信息】{json.dumps([p.model_dump(exclude_none=True) for p in req.products], ensure_ascii=False) if req.products else '无'}
【场景背景】{req.context or '无'}

【待评估的三条候选】
{cands}"""
    return sys_p, usr_p


class Judge:
    def __init__(self, llm: LLM | None = None):
        self.llm = llm or LLM(os.getenv("JUDGE_PROVIDER", "qwen"), temperature=0.0)

    def evaluate(self, req: Request, res: Result) -> dict:
        s, u = judge_prompt(req, res)
        out = self.llm.json_chat(s, u, temperature=0.0)
        for c in out.get("candidates", []):  # models occasionally put stray keys inside "scores"
            sc = c.get("scores", {}) or {}
            if "hard_fail" in sc and "hard_fail" not in c:
                c["hard_fail"] = bool(sc["hard_fail"])
            c["scores"] = {d: int(sc[d]) for d in DIMENSIONS if str(sc.get(d, "")).strip().isdigit()}
            c.setdefault("hard_fail", False)
        out["judge_model"] = self.llm.name
        return out
