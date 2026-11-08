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
