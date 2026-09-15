"""Keep the local and hosted curated lint/type denominators identical."""

from pathlib import Path
import re


def _makefile_paths() -> list[str]:
    text = Path("Makefile").read_text()

    match = re.search(
        r"LINT_PATHS := (.*?)(?:\n\n|\n[a-zA-Z_-]+:)",
        text,
        re.S,
    )
    assert match is not None, "Makefile LINT_PATHS not found"

    return (
        match.group(1)
        .replace("\\\n", " ")
        .replace("\t", " ")
        .split()
    )


def _ci_paths() -> list[str]:
    text = Path(".github/workflows/ci.yml").read_text()
    matches = re.findall(r'LINT_PATHS="([^"]+)"', text)

    assert len(matches) == 1, (
        "Expected exactly one CI LINT_PATHS declaration; "
        f"found {len(matches)}"
    )

    return matches[0].split()


def test_makefile_and_ci_lint_denominators_are_identical():
    make = _makefile_paths()
    ci = _ci_paths()

    assert len(make) == len(set(make)), "Duplicate Makefile LINT_PATHS"
    assert len(ci) == len(set(ci)), "Duplicate CI LINT_PATHS"

    assert make == ci, {
        "makefile_only": sorted(set(make) - set(ci)),
        "ci_only": sorted(set(ci) - set(make)),
        "makefile": make,
        "ci": ci,
    }
