"""Input / output data contracts for the CA message tool."""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Scenario(str, Enum):
    GREETING = "greeting"            # 1 Birthday & festive greetings
    RECOMMENDATION = "recommendation"  # 2 Product recommendation
    AFTERCARE = "aftercare"          # 3 Post-purchase care
    REACTIVATION = "reactivation"    # 4 Reactivation
    EVENT = "event"                  # 5 Event invitation
    PRICE_OBJECTION = "price_objection"  # 6 Price objection


SCENARIO_LABELS = {
    Scenario.GREETING: "1 生日与节日问候 Birthday & festive greeting",
    Scenario.RECOMMENDATION: "2 产品推荐 Product recommendation",
    Scenario.AFTERCARE: "3 售后关怀 Post-purchase care",
    Scenario.REACTIVATION: "4 沉睡唤醒 Reactivation",
    Scenario.EVENT: "5 活动邀约 Event invitation",
    Scenario.PRICE_OBJECTION: "6 价格异议 Price objection",
}


class Purchase(BaseModel):
    date: str
    item: str
    note: Optional[str] = None  # e.g. "gift for wife", "self-purchase, promotion"


class Client(BaseModel):
    client_id: str
    surname: str
    gender: Literal["F", "M"]
    preferred_name: Optional[str] = None   # how the client asked to be called, e.g. "Vivian"
    age_band: Optional[str] = None
    city: Optional[str] = None
    tier: str = "会员 Member"
    birthday: Optional[str] = None         # MM-DD
    occupation: Optional[str] = None
    interests: list[str] = Field(default_factory=list)
    style_notes: Optional[str] = None      # taste, sizes, metals
    purchases: list[Purchase] = Field(default_factory=list)
    last_visit: Optional[str] = None
    preferences: list[str] = Field(default_factory=list)  # contact rules, sensitivities
    family: Optional[str] = None
    ca_notes: Optional[str] = None


class Turn(BaseModel):
    speaker: Literal["CA", "client"]
    time: str
    text: str


class Product(BaseModel):
    sku: str
    name: str
    collection: Optional[str] = None
    category: Optional[str] = None
    material: Optional[str] = None
    price: Optional[int] = None
    story: Optional[str] = None
    care: Optional[str] = None


class Request(BaseModel):
    case_id: Optional[str] = None
    scenario: Scenario
    today: str                         # YYYY-MM-DD, needed for timing
    ca_name: str = "Lina"
    client: Client
    history: list[Turn] = Field(default_factory=list)
    products: list[Product] = Field(default_factory=list)
    context: Optional[str] = None      # occasion, event details, CA intent


class Candidate(BaseModel):
    angle: str
    message: str
    rationale: str = ""
    facts_used: list[str] = Field(default_factory=list)      # v3: fact-sheet IDs the generator says it used
    critic_removed: list[str] = Field(default_factory=list)  # v3: unsupported fragments the critic removed
    issues: list[str] = Field(default_factory=list)   # guardrail findings after final pass
    repaired: bool = False


class Result(BaseModel):
    case_id: Optional[str] = None
    version: str
    analysis: dict = Field(default_factory=dict)
    candidates: list[Candidate]
    model: str
    latency_s: float = 0.0
