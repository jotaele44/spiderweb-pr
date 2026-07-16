from __future__ import annotations

def audit_collision(candidate_files: set[str], open_pr_files: dict[int, set[str]]) -> dict:
    collisions = []
    for number, paths in sorted(open_pr_files.items()):
        overlap = sorted(candidate_files & paths)
        if overlap:
            collisions.append({"pr": number, "files": overlap})
    return {"passed": not collisions, "collisions": collisions}
