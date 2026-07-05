"""Theme 12 — docs & structure checks (T12-93/94/96/97/98/99/100)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"


def test_docs_index_exists_and_links_resolve():
    index = DOCS / "README.md"
    assert index.exists(), "docs/README.md index is missing (T12-93)"
    text = index.read_text()
    # Every relative .md link in the index must resolve on disk.
    broken = []
    for m in re.finditer(r"\]\(([^)]+\.md)\)", text):
        target = m.group(1)
        if target.startswith("http"):
            continue
        if not (DOCS / target).resolve().exists() and not (index.parent / target).resolve().exists():
            broken.append(target)
    assert not broken, f"docs/README.md has broken links: {broken}"


@pytest.mark.parametrize("pkg", ["gebco", "earthgpt", "llm"])
def test_subsystem_readmes_exist(pkg):
    assert (REPO / pkg / "README.md").exists(), f"{pkg}/README.md missing (T12-96)"


def test_new_docs_present():
    # FR24_GUIDE.md migrated to skywatcher-pr with the FR24/RLSM pipeline.
    for name in ("MONOREPO_SPLIT_EVALUATION.md", "API_REFERENCE.md"):
        assert (DOCS / name).exists(), f"docs/{name} missing"


def test_ledger_records_roadmap_completion():
    ledger = (DOCS / "ROI_TASK_LEDGER.md").read_text()
    assert "Themes 2–12" in ledger or "Themes 2-12" in ledger
    assert "Docs & structure" in ledger


def test_readme_links_docs_index():
    readme = (REPO / "README.md").read_text()
    assert "docs/README.md" in readme


def test_architecture_refresh_mentions_federation_and_rlsm():
    arch = (DOCS / "ARCHITECTURE.md").read_text()
    assert "Status refresh" in arch
    assert "Federation" in arch and "RLSM" in arch
