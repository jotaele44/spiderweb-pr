from __future__ import annotations
POSITIVE = ("finish spiderweb-pr", "implement spiderweb", "audit spiderweb-pr", "complete repository backlog")
NEGATIVE = ("skywatcher-pr", "thehub-pr correlation", "general code review", "deploy production")

def decide(text: str) -> dict:
    t = text.lower()
    if any(x in t for x in NEGATIVE):
        return {"activate": False, "mode": "route_or_refuse"}
    if any(x in t for x in POSITIVE):
        return {"activate": True, "mode": "analysis_then_branch"}
    return {"activate": "analysis_only", "mode": "ambiguous"}
