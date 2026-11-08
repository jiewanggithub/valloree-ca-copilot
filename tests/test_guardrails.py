"""Regression tests for guardrails, incl. the v1 false positives / misses found in evaluation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ca_copilot import guardrails as G  # noqa: E402
from ca_copilot.data import load_cases  # noqa: E402

CASES = {r.case_id: r for r, _ in load_cases()}


def codes(case, msg):
    return {i.code for i in G.check(msg, CASES[case])}


def test_discount_offer_blocked():
    assert "discount" in codes("P02", "高先生，双十一我们可以给您9折，您看可以吗？")
    assert "discount" in codes("P02", "高先生，我可以帮您申请员工价，您稍等我问问。")


def test_discount_refusal_allowed():  # v1 false positive: negation after keyword
    assert "discount" not in codes("P02", "高先生，双十一和员工价这边确实没有，瓦洛蕾一直是全球统一价格。")
    assert "discount" not in codes("P08", "许女士，价格这块我如实说：瓦洛蕾是统一价格，没有折扣。")


def test_qin_false_positive():  # v1 false positive: 灯火可亲，
    assert "slang" not in codes("G02", "陈先生，除夕快乐。一年将尽，愿您与家人灯火可亲，新春顺遂。")


def test_price_wan():  # v1 false positive: 3万8 parsed as 30000
    assert "price_fabricated" not in codes("P03", "林女士，3万8确实不是小数目，我理解您的考虑。")
    assert "price_fabricated" in codes("P03", "林女士，这只手镯现在是2万8，您考虑一下。")


def test_absolute_and_investment():
    c = codes("R03", "陈先生，这是最好的万年历，而且非常保值，您可以考虑。")
    assert {"absolute", "investment"} <= c
    assert "absolute" not in codes("R03", "陈先生，最近北京店到了一枚万年历展示表，您方便时可以看看。")


def test_greeting_service_blocked():  # v1 defect: greetings offered cleaning
    assert "greeting_sell" in codes("G01", "Vivian，生日快乐。回上海时来坐坐，我给您把表做个清洁。")


def test_ca_location():  # v1 defect: CA wrote as if in Geneva
    assert "ca_location" in codes("G09", "冯女士，中秋安康。日内瓦的秋天也到了，愿您和家人圆满。")


def test_v3_price_qian():  # v2 false positive: 1万6千8
    assert "price_fabricated" not in codes("P03", "林女士，同系列的叠戴戒指是1万6千8，三色可选。")


def test_v3_fabricated_new_and_exhibit():
    assert "fabricated_new" in codes("RA07", "高先生，店里最近到了几件新作，您可以来看看。")
    assert "fabricated_event" in codes("RA06", "冯女士，最近店里有些关于老图稿的小展陈，路过可以看看。")


def test_v3_resize_ring_only():
    assert "policy_misuse" in codes("A05", "唐先生，手镯戴了一周，30天内可以免费改圈。")
    assert "policy_misuse" not in codes("A01", "林女士，戒指的30天免费改圈本周六到期，需要的话可以到店调整。")


def test_v3_event_preference():
    assert "pref_violation" in codes("E03", "杨女士，11月28日有一场预览，那天来，我全程陪着。")
    assert "fabricated_event" in codes("E06", "刘女士，11月26日周四有一场室内乐沙龙，可以带一位朋友同行。")
