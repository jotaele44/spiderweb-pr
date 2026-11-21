"""Shared drawing conventions: evidence styles, legend, FAIL watermark."""

from __future__ import annotations

from typing import Any

from .svg import Svg

# evidence class -> (stroke colour, dash pattern or None, drawn?)
LINK_STYLE: dict[str, tuple[str, str | None, bool]] = {
    "observed": ("#0b5cad", None, True),
    "modeled": ("#7b3fb0", "8 3", True),
    "inferred": ("#c77700", "3 4", True),
    "unknown": ("#888888", None, False),
}
LEGEND = (
    ("observed: solid (requires observation_ref)", "#0b5cad", None),
    ("modeled: long dash (requires model_id)", "#7b3fb0", "8 3"),
    ("inferred: dotted (hypothesis, not evidence)", "#c77700", "3 4"),
    ("unknown: never drawn as a link", "#888888", None),
)


def footer(
    svg: Svg,
    y: float,
    render_id: str,
    status: str,
    issues: list[dict[str, Any]],
    title: str,
) -> None:
    svg.text(10, y, title, 12, "#111", 'font-weight="bold"')
    for i, (label, colour, dash) in enumerate(LEGEND):
        yy = y + 16 + 14 * i
        svg.polyline([(10, yy - 4), (44, yy - 4)], colour, 2, dash)
        svg.text(52, yy, label, 10)
    svg.text(
        10,
        y + 16 + 14 * len(LEGEND) + 4,
        f"render_id {render_id[:16]}  validation {status}",
        10,
        "#444",
    )
    svg.text(
        10,
        y + 16 + 14 * len(LEGEND) + 18,
        "Picture only: a drawn line is not evidence of a connection.",
        10,
        "#444",
    )


def watermark(svg: Svg, issues: list[dict[str, Any]]) -> None:
    svg.text(
        20,
        svg.height / 2,
        "VALIDATION FAILED - NOT FOR PUBLICATION",
        26,
        "#cc0000",
        'font-weight="bold" opacity="0.8"',
    )
    codes = sorted({i["code"] for i in issues if i["severity"] == "error"})
    svg.text(20, svg.height / 2 + 22, "issues: " + ", ".join(codes), 12, "#cc0000")
