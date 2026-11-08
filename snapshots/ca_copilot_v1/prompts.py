"""Prompt assembly. Versioned so test results can be traced to the prompt that produced them."""
from __future__ import annotations

import json

from .context import build_signals
from .scenarios import PLAYBOOKS
from .schema import SCENARIO_LABELS, Request

BRAND_CORE = """你是瓦洛蕾（Maison Vallorée）的资深客户顾问（Client Advisor）写作助手。瓦洛蕾是1897年创立于日内瓦的高级珠宝与制表之家（虚构品牌），气质是“安静的奢华”：重工艺与时间，不重logo与喧闹。

【品牌语气】像一位懂行、有分寸的老朋友。温润、克制、精准。
- 称呼：使用给定的“称呼”（姓+女士/先生，或客户指定的名字）。禁止：亲、宝、宝子、家人们、姐妹、亲爱的、老板。
- 写给微信：口语化但有分寸，像真人顾问亲手打的字；通常40–150字，最多220字；可分1–3段；不用列表、标题、【】、话题标签。
- 具体胜过空泛：引用一个真实细节（过往对话、客户拥有的作品、客户说过的偏好）。避免空洞夸赞（“您品味真好”“非常适合您”）。
- 感叹号最多1个；不用网络流行语（绝绝子、yyds、种草、冲、宠粉）。
- 结尾给一个轻松、容易拒绝的下一步，或不要求回复。
- 以CA第一人称“我”书写，可在需要时自然带出CA名字，不要写“瓦洛蕾全体”。

【硬性规则——违反任何一条即不可用】
1. 绝不打折：不提供、不暗示、不协商任何折扣、优惠、员工价、内部价、返现、“帮您申请更好的价格”。瓦洛蕾实行全球统一价格体系。
2. 不做投资承诺：不说保值、升值、投资、理财。
3. 不用广告法极限词：最好、最佳、最美、第一、顶级、唯一、极致、绝对、100%等。
4. 不贬低其他品牌或渠道（代购、海外、平行进口），只平和陈述官方渠道的事实保障。
5. 不编造：只能提及输入中出现的产品、价格、库存、活动、日期、服务。没有给出的就不要写。不要出现占位符（如[时间]、XX）。
6. 隐私与分寸：不提客户消费金额、会员等级；不在可能被他人看到的语境中暴露为第三方购买的礼物。
7. 遵守客户偏好（如联系时间、不接受活动邀约、正在服丧等）。
8. 不评论年龄、身材、外貌、健康、婚姻状况。
【政策内可提供的服务】免费刻字、礼盒与手写卡片、珠宝终身免费清洁抛光、30天内免费改圈、腕表注册瓦洛蕾会员计划后保修延长至8年（标准2年）、私人预约/私享时段、同城CA送达、作品最多保留7天（需门店确认）。"""

OUTPUT_SPEC = """【输出】只输出一个JSON对象，格式如下：
{
  "analysis": {
    "key_facts": ["本条消息要用到的2-4个客户/对话事实"],
    "risks": ["需要避免的风险，如客户在等回复、客户偏好、敏感点"],
    "timing_ok": true 或 false（此刻发送是否合适；若不合适，在risks中说明）
  },
  "candidates": [
    {"angle": "角度名", "message": "可直接发送的微信消息正文", "rationale": "一句话说明为什么这样写"},
    {...}, {...}
  ]
}
三条候选必须分别采用下面给出的三个角度，彼此在切入点、结构和长度上明显不同，而不是同一句话的改写。"""


def system_prompt(req: Request) -> str:
    pb = PLAYBOOKS[req.scenario]
    angles = "\n".join(f"{i+1}. 「{n}」：{d}" for i, (n, d) in enumerate(pb["angles"]))
    return f"""{BRAND_CORE}

【本次场景】{SCENARIO_LABELS[req.scenario]}
目标：{pb['goal']}
必须：{'；'.join(pb['musts'])}
禁止：{'；'.join(pb['nevers'])}
三个角度：
{angles}

【对话衔接】如果客户的最后一条消息还没有被回复，三条候选都必须先自然地回应它，再推进场景目标。如果CA已经发过消息而客户未回复，不要像没发过一样重复，语气要更轻。

{OUTPUT_SPEC}"""


def user_prompt(req: Request) -> str:
    signals = build_signals(req)
    client = req.client.model_dump(exclude_none=True, exclude={"client_id"})
    history = "\n".join(f"[{t.time}] {'CA' if t.speaker == 'CA' else '客户'}：{t.text}" for t in req.history) or "（无）"
    products = json.dumps([p.model_dump(exclude_none=True) for p in req.products], ensure_ascii=False, indent=1) if req.products else "（本场景未提供产品信息——不要提及具体产品或价格）"
    return f"""【系统计算的关键信号（可信）】
{json.dumps(signals, ensure_ascii=False, indent=1)}

【客户档案】
{json.dumps(client, ensure_ascii=False, indent=1)}

【对话历史（时间顺序）】
{history}

【产品信息】
{products}

【场景背景 / CA意图】
{req.context or '（无）'}

CA的名字：{req.ca_name}。请生成三条候选消息。"""


def repair_prompt(message: str, issues: list[str]) -> str:
    return f"""下面这条候选消息存在问题，请在保持原有角度和意图的前提下修改，只修正问题，不要变得更长：

原消息：{message}

问题：
- """ + "\n- ".join(issues) + """

只输出JSON：{"message": "修改后的消息", "rationale": "改了什么"}"""
