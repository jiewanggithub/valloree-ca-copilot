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
暴露客户消费金额或等级；违反客户明确偏好；忽略客户待回应的问题；称呼错误；在敏感情境（如投诉、服丧）中语气明显不当；问候场景中推销。

【事实核查——必须先做】（judge v3，经人工标注校准）
对每条候选，先找出所有“具体事实性陈述”，并在输入中核对。

以下都算“有依据”，不是编造：
- 客户档案中的任何字段（包括 ca_notes、style_notes、family、preferences），即使客户没在对话里说过
- 品牌政策与正常的CA动作：私人预约/另约时段、发图片/视频/资料、到店试戴、同城送达、官方证书与全球保修、刻字礼盒
- 常识与一般性情感表达（如“冬天到了”“想来她已经适应大学”），合理的推测语气
- 产品信息中写明的内容的合理转述

以下是“严重编造”→ faithfulness ≤ 2 且 hard_fail = true：
- 虚构客户过去的具体言行、经历、场景（如“您试戴时多看了几眼镜子”“您说起母亲教您写字”）
- 虚构产品事实：未给出的工艺细节/工序/产地，或“还有其他尺寸/材质/款式”而产品信息里没有
- 错误的服务条款（如把戒指的30天改圈用于手镯）、自造与输入矛盾的保养周期
- 虚构的活动、展讯、新品、库存
- CA声称已经完成、并影响客户的动作（如“已经反馈上去”“已经帮您留好”）
- 把很久以前已结束的对话当作正在进行的对话来回应
- CA写得像身在日内瓦/外地

以下是“轻微问题”→ 只扣分（faithfulness 或 naturalness 3），不判 hard_fail：
- 虚构的小由头（如“前几天整理资料时看到…”“和制表师聊到…”）
- 套话（“我一直记着”“安静的时段”“添衣”）——扣 naturalness
- 天气类泛泛而谈

不要因为文笔好而放过严重编造，也不要把轻微问题判为 hard_fail。
一致性要求：如果你的 comment 或 unsupported_claims 中指出了任何一项“严重”问题或 hard_fail 清单中的问题（包括“旧对话当作进行中”“问候中推销服务”“服务条款误用”），hard_fail 必须为 true，并在 hard_fail_reason 中写明。"""


def judge_prompt(req: Request, res: Result) -> tuple[str, str]:
    pb = PLAYBOOKS[req.scenario]
    sys_p = f"""你是一位严格的奢侈品客户关系质检专家，为虚构品牌瓦洛蕾评估顾问微信话术。以下是品牌规范：

{BRAND_CORE}

{RUBRIC}

维度说明：
""" + "\n".join(f"- {k}: {v}" for k, v in DIMENSIONS.items()) + """

只输出JSON：
{"candidates": [{"id": 1, "unsupported_claims": ["输入中找不到依据的具体陈述，没有则为空"], "scores": {"personalization": n, "brand_voice": n, "naturalness": n, "appropriateness": n, "goal": n, "faithfulness": n},
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
