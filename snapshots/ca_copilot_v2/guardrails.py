"""Deterministic guardrails. Cheap, explainable, and run on every candidate before it reaches a CA.

Severity:
  HARD  -> candidate is not acceptable; triggers an automatic repair pass
  SOFT  -> style warning, surfaced to the CA / evaluation but does not block
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .context import salutation
from .schema import Request, Scenario

HARD, SOFT = "HARD", "SOFT"


@dataclass
class Issue:
    severity: str
    code: str
    detail: str

    def __str__(self):
        return f"[{self.severity}:{self.code}] {self.detail}"


SLANG = ["亲爱的", "宝子", "家人们", "姐妹们", "绝绝子", "yyds", "种草", "宠粉", "老板", "冲鸭", "集美"]
SLANG_RE = re.compile(r"(^|[，。！？\s])亲[~～，！]")  # v2: "亲，" as an address only, not "灯火可亲，"
PRESSURE = ["限时", "抢购", "最后机会", "赶紧", "错过就", "仅剩", "手慢无", "先到先得", "马上下单", "名额有限"]
INVEST = ["保值", "升值", "投资", "理财", "增值"]
# Advertising-law absolutes. 最 is matched only before evaluative words so 最近/最后一次 are allowed.
ABSOLUTE_RE = re.compile(r"最(好|佳|美|优|强|高级|顶|贵|具|值得|完美|经典|受欢迎|适合)|第一|顶级|唯一|极致|绝对|100%|全网|国家级")
DISCOUNT_OFFER_RE = re.compile(
    r"(给您|帮您|为您|可以|能)[^。！？\n]{0,8}(打折|折扣|优惠|便宜|减免|降价|员工价|内部价|返现|申请.{0,4}价)"
    r"|[0-9一二三四五六七八九]折|满减|立减|返现|员工价|内部价"
)
DISPARAGE = ["假货", "水货", "仿品", "高仿", "来路不明", "不靠谱", "被骗"]
PRIVACY = ["消费了", "累计消费", "您是我们的典藏", "您的等级", "尊享会员", "典藏会员", "VIP客户"]
PLACEHOLDER_RE = re.compile(r"\[.*?\]|【.*?】|XX|xx|\{.*?\}|某某")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
GROUP_MSG = ["全体同仁", "尊敬的客户", "尊敬的会员", "各位"]


def check(message: str, req: Request) -> list[Issue]:
    issues: list[Issue] = []
    m = message.strip()

    # length
    n = len(re.sub(r"\s", "", m))
    if n > 220:
        issues.append(Issue(HARD, "too_long", f"{n}字，超过220字上限"))
    elif n > 160:
        issues.append(Issue(SOFT, "long", f"{n}字，偏长"))
    if n < 15:
        issues.append(Issue(HARD, "too_short", f"仅{n}字"))

    for w in SLANG:
        if w.lower() in m.lower():
            issues.append(Issue(HARD, "slang", f"使用了不符合品牌语气的称呼/流行语「{w}」"))
    if SLANG_RE.search(m):
        issues.append(Issue(HARD, "slang", "使用了“亲”作为称呼"))
    for w in PRESSURE:
        if w in m:
            issues.append(Issue(HARD, "pressure", f"施压用语「{w}」"))
    for w in INVEST:
        if w in m:
            issues.append(Issue(HARD, "investment", f"投资类表述「{w}」"))
    for mt in ABSOLUTE_RE.finditer(m):
        issues.append(Issue(HARD, "absolute", f"广告法极限词「{mt.group(0)}」"))
    for mt in DISCOUNT_OFFER_RE.finditer(m):
        # allow explicit refusals such as "没有折扣" / "不做折扣"
        window = m[max(0, mt.start() - 8): mt.end() + 10]  # v2: negation before OR after
        if not re.search(r"(不|没有|没|无法|不能|并不|给不了)", window):
            issues.append(Issue(HARD, "discount", f"疑似提供折扣/优惠「{mt.group(0)}」"))
    for w in DISPARAGE:
        if w in m:
            issues.append(Issue(HARD, "disparage", f"贬低性表述「{w}」"))
    for w in PRIVACY:
        if w in m:
            issues.append(Issue(HARD, "privacy", f"暴露客户隐私/等级「{w}」"))
    for w in GROUP_MSG:
        if w in m:
            issues.append(Issue(SOFT, "group_tone", f"群发感表述「{w}」"))
    ph = PLACEHOLDER_RE.search(m)
    if ph:
        issues.append(Issue(HARD, "placeholder", f"残留占位符/格式符号「{ph.group(0)}」"))

    # punctuation & emoji
    if m.count("！") + m.count("!") > 1:
        issues.append(Issue(SOFT, "exclaim", "感叹号超过1个"))
    emojis = EMOJI_RE.findall(m)
    formal = "典藏" in req.client.tier
    if len(emojis) > 1 or (formal and emojis):
        issues.append(Issue(SOFT, "emoji", f"emoji 使用不当（{len(emojis)}个{'，典藏客户不使用' if formal else ''}）"))

    # salutation: must use the agreed form, not the wrong surname/gender
    sal = salutation(req)
    c = req.client
    wrong = f"{c.surname}{'先生' if c.gender == 'F' else '女士'}"
    if wrong in m:
        issues.append(Issue(HARD, "wrong_name", f"称呼性别错误「{wrong}」"))
    if c.preferred_name and f"{c.surname}{'女士' if c.gender == 'F' else '先生'}" in m:
        issues.append(Issue(SOFT, "name_pref", f"客户希望被称呼为「{c.preferred_name}」"))
    if sal not in m and c.surname not in m:
        issues.append(Issue(SOFT, "no_name", "未使用称呼，可能显得像群发"))

    # fabrication: prices must be ones given in the input
    given_prices = {p.price for p in req.products if p.price}
    for pm in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d{4,7})\s*元|¥\s*(\d{1,3}(?:,\d{3})+|\d{4,7})|(\d+(?:\.\d+)?)\s*万(\d)?", m):
        if pm.group(3):  # v2: "3万8" = 38000
            val = float(pm.group(3)) * 10000 + (int(pm.group(4)) * 1000 if pm.group(4) else 0)
        else:
            val = float((pm.group(1) or pm.group(2)).replace(",", ""))
        if given_prices and not any(abs(val - gp) / gp < 0.02 for gp in given_prices):
            issues.append(Issue(HARD, "price_fabricated", f"价格「{pm.group(0)}」与输入不符"))
        elif not given_prices:
            issues.append(Issue(HARD, "price_fabricated", f"输入未提供价格却写了「{pm.group(0)}」"))

    # scenario-specific
    if req.scenario == Scenario.GREETING:
        for w in ["新品", "推荐", "上新", "到店选购", "价格"]:
            if w in m:
                issues.append(Issue(HARD, "greeting_sell", f"问候中出现销售内容「{w}」"))
    if req.scenario == Scenario.REACTIVATION:
        for w in ["好久没来", "把我们忘", "怎么不来", "很久没有光顾"]:
            if w in m:
                issues.append(Issue(HARD, "guilt", f"带有指责意味「{w}」"))

    # v2 checks ------------------------------------------------------------
    if req.scenario == Scenario.GREETING:
        for w in ["清洁", "抛光", "保养", "改圈"]:
            if w in m:
                issues.append(Issue(HARD, "greeting_sell", f"问候中提供服务「{w}」"))
                break
    if re.search(r"(——|-{2,}|\n)\s*" + re.escape(req.ca_name) + r"\s*$", m):
        issues.append(Issue(SOFT, "signoff", "结尾署名，微信中显得生硬"))
    if re.search(r"日内瓦(今天|这边|的(秋|冬|春|夏)天|也)", m):
        issues.append(Issue(HARD, "ca_location", "写得像CA身在日内瓦"))
    if "您" in m and re.search(r"你(?!们)", m):
        issues.append(Issue(SOFT, "pronoun_mix", "你/您混用"))
    for w, pat in {"套话:一直记着": r"一直记着|我记下了", "套话:添衣": r"添(件|衣)|多穿一?件|多带一件",
                   "套话:安静的时段": r"安静的?(时段|时间)"}.items():
        if re.search(pat, m):
            issues.append(Issue(SOFT, "cliche", w))

    # client preferences that can be checked mechanically
    prefs = " ".join(c.preferences)
    if "不接受活动邀约" in prefs and req.scenario != Scenario.EVENT and ("活动" in m or "邀请您" in m):
        issues.append(Issue(HARD, "pref_violation", "客户不接受活动邀约"))
    return issues


def hard(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == HARD]


def diversity(messages: list[str]) -> float:
    """Max pairwise similarity between candidates (0 = completely different, 1 = identical)."""
    sims = [SequenceMatcher(None, a, b).ratio() for i, a in enumerate(messages) for b in messages[i + 1:]]
    return max(sims) if sims else 0.0
