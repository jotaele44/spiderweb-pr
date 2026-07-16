from __future__ import annotations
from pathlib import PurePosixPath

PRODUCT_PREFIXES = ("pipeline/", "integration/", "readiness/", "federation/", "fr24/", "server/", "earthgpt/", "gebco/", "llm/", "imagery/")

def analyze(paths: list[str], allowed_prefix: str = "skills/spiderweb-pr-self-auditing-implementer/") -> dict:
    normalized = [str(PurePosixPath(p)) for p in paths]
    outside = [p for p in normalized if not p.startswith(allowed_prefix)]
    product = [p for p in normalized if p.startswith(PRODUCT_PREFIXES)]
    return {"passed": not outside and not product, "outside_scope": outside, "product_code": product}
