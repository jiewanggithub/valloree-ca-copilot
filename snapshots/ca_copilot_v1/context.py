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


def salutation(req: Request) -> str:
    c = req.client
    if c.preferred_name:
        return c.preferred_name
    return f"{c.surname}{'女士' if c.gender == 'F' else '先生'}"


def build_signals(req: Request) -> dict:
    c = req.client
    today = _d(req.today)
    sig: dict = {"称呼": salutation(req), "今天": req.today}

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
        if last_turn.speaker == "client":
            sig["待回应"] = f"客户最后说：「{last_turn.text}」——本条消息必须先回应这句话"
        lt = _d(last_turn.time)
        if lt and today:
            sig["距上次对话天数"] = (today - lt).days
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
