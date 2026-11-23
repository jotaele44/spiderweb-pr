"""Minimal deterministic SVG writer (fixed float precision, stable ordering)."""

from __future__ import annotations

from xml.sax.saxutils import escape


def n(value: float) -> str:
    text = f"{value:.2f}"
    return "0.00" if text == "-0.00" else text


class Svg:
    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.parts: list[str] = []
        self.footer_y: float = float(height) - 130.0
        self.title: str = ""

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    def rect(
        self, x: float, y: float, w: float, h: float, fill: str, extra: str = ""
    ) -> None:
        self.add(
            f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" fill="{fill}" {extra}/>'
        )

    def polyline(
        self,
        pts: list[tuple[float, float]],
        stroke: str,
        width: float = 1.5,
        dash: str | None = None,
        extra: str = "",
    ) -> None:
        d = " ".join(f"{n(x)},{n(y)}" for x, y in pts)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<polyline points="{d}" fill="none" stroke="{stroke}" stroke-width="{n(width)}"{da} {extra}/>'
        )

    def polygon(
        self, pts: list[tuple[float, float]], fill: str, stroke: str, extra: str = ""
    ) -> None:
        d = " ".join(f"{n(x)},{n(y)}" for x, y in pts)
        self.add(f'<polygon points="{d}" fill="{fill}" stroke="{stroke}" {extra}/>')

    def circle(
        self, x: float, y: float, r: float, fill: str, stroke: str, extra: str = ""
    ) -> None:
        self.add(
            f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r)}" fill="{fill}" stroke="{stroke}" {extra}/>'
        )

    def text(
        self,
        x: float,
        y: float,
        content: str,
        size: int = 11,
        fill: str = "#222",
        extra: str = "",
    ) -> None:
        self.add(
            f'<text x="{n(x)}" y="{n(y)}" font-family="monospace" font-size="{size}" fill="{fill}" {extra}>{escape(content)}</text>'
        )

    def render(self, metadata: str) -> str:
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}">\n<metadata>{escape(metadata)}</metadata>\n'
            f'<rect width="{self.width}" height="{self.height}" fill="#ffffff"/>\n'
        )
        return head + "\n".join(self.parts) + "\n</svg>\n"
