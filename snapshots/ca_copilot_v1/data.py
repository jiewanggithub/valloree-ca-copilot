"""Load brand catalogue, CRM clients and test cases into Request objects."""
from __future__ import annotations

from pathlib import Path

import yaml

from .schema import Client, Product, Request

ROOT = Path(__file__).resolve().parent.parent


def load_products() -> dict[str, Product]:
    rows = yaml.safe_load((ROOT / "brand/products.yaml").read_text(encoding="utf-8"))
    return {r["sku"]: Product(**r) for r in rows}


def load_clients() -> dict[str, Client]:
    rows = yaml.safe_load((ROOT / "data/clients.yaml").read_text(encoding="utf-8"))
    return {cid: Client(client_id=cid, **r) for cid, r in rows.items()}


def load_cases() -> list[tuple[Request, dict]]:
    """Returns (request, meta) pairs. meta holds test-design fields not shown to the generator."""
    products, clients = load_products(), load_clients()
    rows = yaml.safe_load((ROOT / "data/cases.yaml").read_text(encoding="utf-8"))
    out = []
    for r in rows:
        req = Request(
            case_id=r["id"], scenario=r["scenario"], today=r["today"], client=clients[r["client"]],
            history=r.get("history", []), products=[products[s] for s in r.get("products", [])],
            context=(r.get("context") or "").strip() or None,
        )
        out.append((req, {"type": r.get("type", "core"), "focus": r.get("focus", "")}))
    return out
