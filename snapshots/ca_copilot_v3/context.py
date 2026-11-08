"""Deterministic context builder: turns raw CRM + chat data into signals the prompt can use.

Doing this in code (not in the LLM) makes timing facts reliable: days since last purchase,
whether the client is waiting for an answer, contact restrictions, etc.
"""
from __future__ import annotations

from datetime import date

from .schema import Request


def _d(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


BOUTIQUES = {"上海": "上海静安恒汇店", "北京": "北京国贸丽庭店", "杭州": "杭州湖滨店", "成都": "成都店", "深圳": "深圳店"}
PENDING_WINDOW_DAYS = 3  # v2: a client message older than this is a closed thread, not a pending question


def pronoun(req: Request) -> str:
    casual = any("轻松" in p for p in req.client.preferences)
    return "你" if casual else "您"


def salutation(req: Request) -> str:
    c = req.client
    if c.preferred_name:
        return c.preferred_name
    return f"{c.surname}{'女士' if c.gender == 'F' else '先生'}"


def build_signals(req: Request) -> dict:
    c = req.client
    today = _d(req.today)
    wd = "一二三四五六日"[today.weekday()] if today else ""
    sig: dict = {"称呼": salutation(req), "人称": pronoun(req) + "（全文统一，不要混用你/您）", "今天": f"{req.today}（周{wd}）"}
    if today and today.weekday() < 5 and any("周末" in p for p in c.preferences):
        sig["发送时机"] = f"今天是周{wd}，客户只接受周末联系——timing_ok 必须为 false，建议CA周末再发送；消息内容按周末发送来写"
    if c.city in BOUTIQUES:
        sig["CA所在门店"] = BOUTIQUES[c.city] + f"（CA与客户同在{c.city}，不要写得像身在日内瓦或外地）"

    if c.purchases:
        last = max(c.purchases, key=lambda p: p.date)
        d = _d(last.date)
        if d and today:
            sig["距最近一次购买天数"] = (today - d).days
        sig["最近一次购买"] = last.item + (f"（{last.note}）" if last.note else "")
    else:
        sig["购买记录"] = "无（尚未购买）"

    if c.last_visit and today and _d(c.last_visit):
        sig["距最近一次到店天数"] = (today - _d(c.last_visit)).days

    if c.birthday and today:
        try:
            m, dd = map(int, c.birthday.split("-"))
            bday = date(today.year, m, dd)
            delta = (bday - today).days
            if -3 <= delta <= 7:
                sig["生日"] = "今天" if delta == 0 else (f"{delta}天后" if delta > 0 else f"{-delta}天前（已过）")
        except ValueError:
            pass

    if req.history:
        last_turn = req.history[-1]
        sig["最后一条消息来自"] = "客户" if last_turn.speaker == "client" else "CA"
        lt = _d(last_turn.time)
        gap = (today - lt).days if lt and today else None
        if gap is not None:
            sig["距上次对话天数"] = gap
        if last_turn.speaker == "client" and gap is not None and gap <= PENDING_WINDOW_DAYS:
            sig["待回应"] = f"客户{gap}天前说：「{last_turn.text}」——本条消息必须先回应这句话"
        elif gap is not None and gap > PENDING_WINDOW_DAYS:
            sig["对话状态"] = (f"上一段对话已在{gap}天前自然结束。不要把旧消息当成正在进行的对话来回应，"
                           f"不要为“迟回”道歉；可以引用其中的内容作为话题，但要明确那是过去的事。")
        # register: does the client write formally or casually?
        client_turns = [t.text for t in req.history if t.speaker == "client"]
        if client_turns:
            avg = sum(len(t) for t in client_turns) / len(client_turns)
            sig["客户消息平均长度"] = round(avg)
    else:
        sig["对话历史"] = "无（首次在微信上联系或无记录）"

    if c.preferences:
        sig["必须遵守的客户偏好"] = c.preferences

    formal = ("典藏" in c.tier) or any("正式" in p for p in c.preferences)
    sig["emoji"] = "不使用" if formal else "最多1个，可不用"
    return sig


# ── v3: numbered fact sheet ────────────────────────────────────────────────
POLICY_FACTS = [
    "全球统一价格体系，不打折",
    "免费刻字；礼盒与手写卡片",
    "珠宝终身免费清洁抛光",
    "戒指30天内免费改圈（仅限戒指）",
    "腕表标准保修2年，注册瓦洛蕾会员计划后延长至8年",
    "腕表建议每4-5年保养一次；会员计划首次保养免费",
    "私人预约/私享时段；同城CA送达；可发图片或视频",
    "作品最多保留7天（需门店确认）",
    "官方渠道提供真品证书与全球保修",
]


def fact_sheet(req: Request) -> list[str]:
    """Every specific fact a message may cite, with an ID. Anything else is off-limits."""
    c = req.client
    facts: list[str] = []
    add = lambda tag, text: facts.append(f"[{tag}{sum(1 for f in facts if f.startswith('[' + tag)) + 1}] {text}")  # noqa: E731
    for label, val in [("城市", c.city), ("职业", c.occupation), ("生日", c.birthday), ("家庭", c.family),
                       ("风格/偏好", c.style_notes), ("CA备注", c.ca_notes)]:
        if val:
            add("C", f"{label}：{val}（CRM记录，可用“我记得/您之前提过”等自然表达，但不要编成客户原话）" if label == "CA备注" else f"{label}：{val}")
    if c.interests:
        add("C", "兴趣：" + "、".join(c.interests))
    for p in c.purchases:
        add("C", f"购买：{p.date} {p.item}" + (f"（{p.note}）" if p.note else ""))
    for t in req.history:
        add("H", f"{t.time[:10]} {'CA' if t.speaker == 'CA' else '客户'}说：「{t.text}」")
    for p in req.products:
        for label, val in [("名称", p.name), ("材质", p.material), ("价格", f"¥{p.price}" if p.price else None),
                           ("故事", p.story), ("保养", p.care)]:
            if val:
                add("P", f"{p.name.split(' ')[0]} {label}：{val}")
    if req.context:
        for line in [x.strip() for x in req.context.splitlines() if x.strip()]:
            add("X", line)
    for f in POLICY_FACTS:
        add("S", f)
    return facts


def preference_rules(req: Request) -> list[str]:
    """v3: translate CRM preferences into explicit, non-negotiable instructions."""
    rules = []
    prefs = " ".join(req.client.preferences)
    if "不接受活动邀约" in prefs:
        rules.append("客户不接受活动邀约：不要邀请参加任何活动（包括“如果想去”“那天来”），只能提供一对一私人预约看同类作品")
    if "不喜欢频繁" in prefs or "不喜欢频繁收到消息" in prefs:
        rules.append("客户不喜欢频繁消息：消息要短（60字以内为宜），明确无需回复")
    if "简短" in prefs:
        rules.append("客户偏好简短：每条不超过80字")
    if "过世" in prefs or "服丧" in prefs:
        rules.append("客户在服丧期：不用“快乐”“喜庆”字眼，不提任何回忆细节以外的事，不邀约到店")
    return rules
