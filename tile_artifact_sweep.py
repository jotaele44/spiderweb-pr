"""
TILE ARTIFACT SWEEP
Detects basemap image-quality artifacts in FR24/Apple Maps screenshots.

This module is intentionally conservative. It flags evidence-quality problems
such as directional stretching, texture smear, blur patches, and candidate
structure-edge warp. It does not classify those artifacts as hidden objects or
confirmed anomalies. Downstream consumers should use these outputs to reduce
visual/georeference confidence and to route frames for cross-basemap review.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ARTIFACT_DIRECTIONAL_STRETCH = "DIRECTIONAL_STRETCH_ARTIFACT"
ARTIFACT_TEXTURE_SMEAR = "TEXTURE_SMEAR"
ARTIFACT_BLUR_PATCH = "BLUR_PATCH"
ARTIFACT_STRUCTURE_EDGE_WARP = "STRUCTURE_EDGE_WARP_CANDIDATE"
ARTIFACT_OVERLAY_CONTAMINATION = "OVERLAY_CONTAMINATION_RISK"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_MEDIUM_HIGH = "medium_high"
SEVERITY_HIGH = "high"


@dataclass
class TileArtifactRegion:
    """One image region with artifact-like texture behavior."""

    bbox_px: Tuple[int, int, int, int]
    artifact_types: List[str] = field(default_factory=list)
    confidence: float = 0.0
    severity: str = SEVERITY_LOW
    direction: str = "unknown"  # vertical | horizontal | mixed | unknown
    description: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "bbox_px": list(self.bbox_px),
            "artifact_types": list(self.artifact_types),
            "confidence": round(float(self.confidence), 4),
            "severity": self.severity,
            "direction": self.direction,
            "description": self.description,
            "metrics": {k: round(float(v), 6) for k, v in self.metrics.items()},
        }


@dataclass
class TileArtifactReport:
    """Frame-level artifact summary for export/review routing."""

    image_path: str
    basemap_source: str = "FR24/Apple Maps"
    artifact_present: bool = False
    artifact_types: List[str] = field(default_factory=list)
    artifact_confidence: float = 0.0
    artifact_severity: str = SEVERITY_LOW
    regions: List[TileArtifactRegion] = field(default_factory=list)
    requires_cross_basemap_review: bool = False
    analysis_effect: str = "none"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "image_path": self.image_path,
            "basemap_source": self.basemap_source,
            "tile_artifact_present": self.artifact_present,
            "tile_artifact_types": list(self.artifact_types),
            "artifact_confidence": round(float(self.artifact_confidence), 4),
            "artifact_severity": self.artifact_severity,
            "requires_cross_basemap_review": self.requires_cross_basemap_review,
            "analysis_effect": self.analysis_effect,
            "notes": self.notes,
            "affected_regions": [r.to_dict() for r in self.regions],
        }


class TileArtifactSweeper:
    """
    Conservative smudge/stretch detector for FR24 screenshot basemap regions.

    The detector uses local texture statistics over the map viewport:
      - directional gradient imbalance for stretch artifacts
      - low local sharpness/contrast for blur patches
      - anisotropic high-gradient edges for structure-edge warp candidates

    If numpy/Pillow are unavailable, analyze() returns a no-artifact report
    instead of raising so the screenshot pipeline remains fail-soft.
    """

    def __init__(self,
                 segmenter=None,
                 cell_size: int = 96,
                 stride: int = 64,
                 min_confidence: float = 0.58,
                 basemap_source: str = "FR24/Apple Maps"):
        self.segmenter = segmenter
        self.cell_size = int(max(cell_size, 32))
        self.stride = int(max(stride, 16))
        self.min_confidence = float(min_confidence)
        self.basemap_source = basemap_source

    # ------------------------------------------------------------------ public

    def analyze(self, image_path: str) -> TileArtifactReport:
        """Analyze a screenshot file and return a frame-level report."""
        try:
            import numpy as np
            from PIL import Image

            with Image.open(image_path) as img:
                arr = np.array(img.convert("RGB"), dtype=np.uint8)
            return self.analyze_array(arr, image_path=image_path)
        except Exception as exc:
            return TileArtifactReport(
                image_path=image_path,
                basemap_source=self.basemap_source,
                artifact_present=False,
                notes=f"artifact sweep unavailable: {exc.__class__.__name__}",
            )

    def analyze_array(self, arr, image_path: str = "") -> TileArtifactReport:
        """Analyze an RGB array. Useful for synthetic tests."""
        try:
            import numpy as np
        except Exception:
            return TileArtifactReport(image_path=image_path, basemap_source=self.basemap_source)

        if arr is None or len(arr.shape) < 2:
            return TileArtifactReport(image_path=image_path, basemap_source=self.basemap_source)

        rgb = arr[:, :, :3].astype("float32") if len(arr.shape) == 3 else arr.astype("float32")
        grey = rgb.mean(axis=2) if len(rgb.shape) == 3 else rgb

        map_grey, x_off, y_off = self._extract_map_region(grey, image_path)
        if map_grey.size == 0:
            return TileArtifactReport(image_path=image_path, basemap_source=self.basemap_source)

        global_metrics = self._global_metrics(map_grey)
        regions: List[TileArtifactRegion] = []

        h, w = map_grey.shape
        if h < self.cell_size or w < self.cell_size:
            # Single-cell fallback for close-cropped screenshots.
            region = self._score_cell(map_grey, 0, 0, w, h, global_metrics, x_off, y_off)
            if region and region.confidence >= self.min_confidence:
                regions.append(region)
        else:
            for y in range(0, h - self.cell_size + 1, self.stride):
                for x in range(0, w - self.cell_size + 1, self.stride):
                    cell = map_grey[y:y + self.cell_size, x:x + self.cell_size]
                    region = self._score_cell(
                        cell, x, y, self.cell_size, self.cell_size,
                        global_metrics, x_off, y_off,
                    )
                    if region and region.confidence >= self.min_confidence:
                        regions.append(region)

        # Keep highest-confidence regions first and avoid excessive exports.
        regions.sort(key=lambda r: r.confidence, reverse=True)
        regions = self._dedupe_regions(regions)[:12]

        artifact_types = sorted({t for r in regions for t in r.artifact_types})
        max_conf = max((r.confidence for r in regions), default=0.0)
        severity = _severity_from_confidence(max_conf)
        present = bool(regions)

        notes = ""
        if present:
            notes = (
                "Basemap artifact candidates detected. Treat as image-quality "
                "and georeference-confidence reduction until confirmed across "
                "independent basemaps."
            )

        return TileArtifactReport(
            image_path=image_path,
            basemap_source=self.basemap_source,
            artifact_present=present,
            artifact_types=artifact_types,
            artifact_confidence=max_conf,
            artifact_severity=severity,
            regions=regions,
            requires_cross_basemap_review=present,
            analysis_effect="reduce_visual_georef_confidence" if present else "none",
            notes=notes,
        )

    # ----------------------------------------------------------------- scoring

    def _score_cell(self, cell, x: int, y: int, w: int, h: int,
                    global_metrics: Dict[str, float], x_off: int, y_off: int) -> Optional[TileArtifactRegion]:
        try:
            import numpy as np
        except Exception:
            return None

        if cell.size == 0:
            return None

        gx = np.abs(cell[:, 1:] - cell[:, :-1]).mean() if cell.shape[1] > 1 else 0.0
        gy = np.abs(cell[1:, :] - cell[:-1, :]).mean() if cell.shape[0] > 1 else 0.0
        contrast = float(cell.std())
        sharpness = float(_laplacian_variance(cell))
        edge_density = float((gx + gy) / 2.0)

        denom = max(gx + gy, 1e-6)
        anisotropy = abs(gx - gy) / denom
        vertical_stretch = gx / max(gy, 1e-6)
        horizontal_stretch = gy / max(gx, 1e-6)

        g_contrast = max(global_metrics.get("contrast", 1.0), 1e-6)
        g_sharpness = max(global_metrics.get("sharpness", 1.0), 1e-6)
        contrast_ratio = contrast / g_contrast
        sharpness_ratio = sharpness / g_sharpness

        types: List[str] = []
        direction = "unknown"
        scores: List[float] = []

        # Directional texture pull.  Vertical visual streaks usually produce
        # stronger left/right gradients than up/down gradients.
        if vertical_stretch >= 1.65 and anisotropy >= 0.24:
            types.extend([ARTIFACT_DIRECTIONAL_STRETCH, ARTIFACT_TEXTURE_SMEAR])
            direction = "vertical"
            scores.append(min(0.95, 0.45 + (vertical_stretch - 1.0) / 2.5 + anisotropy * 0.35))
        elif horizontal_stretch >= 1.65 and anisotropy >= 0.24:
            types.extend([ARTIFACT_DIRECTIONAL_STRETCH, ARTIFACT_TEXTURE_SMEAR])
            direction = "horizontal"
            scores.append(min(0.95, 0.45 + (horizontal_stretch - 1.0) / 2.5 + anisotropy * 0.35))

        # Blurred/smeared patch: weak local detail compared to surrounding map.
        if sharpness_ratio <= 0.52 and contrast_ratio <= 0.92:
            types.append(ARTIFACT_BLUR_PATCH)
            scores.append(min(0.90, 0.50 + (0.52 - sharpness_ratio) * 0.75))

        # Candidate structure edge warp: anisotropic texture plus enough edges to
        # plausibly affect roofs/roads/clearings rather than just uniform blur.
        if anisotropy >= 0.30 and edge_density >= max(global_metrics.get("edge_density", 0.0) * 0.70, 2.0):
            types.append(ARTIFACT_STRUCTURE_EDGE_WARP)
            scores.append(min(0.88, 0.48 + anisotropy * 0.80))

        if not types:
            return None

        # Deduplicate types while keeping order.
        ordered_types: List[str] = []
        for t in types:
            if t not in ordered_types:
                ordered_types.append(t)

        confidence = max(scores) if scores else 0.0
        if ARTIFACT_BLUR_PATCH in ordered_types and ARTIFACT_DIRECTIONAL_STRETCH in ordered_types:
            confidence = min(0.98, confidence + 0.06)
        if ARTIFACT_STRUCTURE_EDGE_WARP in ordered_types and ARTIFACT_TEXTURE_SMEAR in ordered_types:
            confidence = min(0.98, confidence + 0.04)

        desc = _describe_region(ordered_types, direction)
        return TileArtifactRegion(
            bbox_px=(int(x + x_off), int(y + y_off), int(w), int(h)),
            artifact_types=ordered_types,
            confidence=confidence,
            severity=_severity_from_confidence(confidence),
            direction=direction,
            description=desc,
            metrics={
                "gx": float(gx),
                "gy": float(gy),
                "anisotropy": float(anisotropy),
                "vertical_stretch": float(vertical_stretch),
                "horizontal_stretch": float(horizontal_stretch),
                "contrast": float(contrast),
                "sharpness": float(sharpness),
                "contrast_ratio": float(contrast_ratio),
                "sharpness_ratio": float(sharpness_ratio),
                "edge_density": float(edge_density),
            },
        )

    # ----------------------------------------------------------------- helpers

    def _extract_map_region(self, grey, image_path: str):
        """Return map-region greyscale array and full-image offsets."""
        if self.segmenter is None:
            return grey, 0, 0
        try:
            if image_path:
                segs = self.segmenter.segment(image_path)
            else:
                h, w = grey.shape
                segs = self.segmenter.segment_from_size(w, h)
            bb = segs.map_bbox
            return grey[bb.y:bb.y + bb.h, bb.x:bb.x + bb.w], bb.x, bb.y
        except Exception:
            return grey, 0, 0

    def _global_metrics(self, grey) -> Dict[str, float]:
        try:
            import numpy as np
            gx = np.abs(grey[:, 1:] - grey[:, :-1]).mean() if grey.shape[1] > 1 else 0.0
            gy = np.abs(grey[1:, :] - grey[:-1, :]).mean() if grey.shape[0] > 1 else 0.0
            return {
                "contrast": float(grey.std()),
                "sharpness": float(_laplacian_variance(grey)),
                "edge_density": float((gx + gy) / 2.0),
            }
        except Exception:
            return {"contrast": 1.0, "sharpness": 1.0, "edge_density": 0.0}

    def _dedupe_regions(self, regions: List[TileArtifactRegion]) -> List[TileArtifactRegion]:
        kept: List[TileArtifactRegion] = []
        for region in regions:
            if all(_iou(region.bbox_px, other.bbox_px) < 0.45 for other in kept):
                kept.append(region)
        return kept


def _laplacian_variance(cell) -> float:
    """Small dependency-free Laplacian variance using numpy slicing."""
    try:
        import numpy as np
        if cell.shape[0] < 3 or cell.shape[1] < 3:
            return 0.0
        c = cell[1:-1, 1:-1]
        lap = (
            -4.0 * c
            + cell[:-2, 1:-1]
            + cell[2:, 1:-1]
            + cell[1:-1, :-2]
            + cell[1:-1, 2:]
        )
        return float(np.var(lap))
    except Exception:
        return 0.0


def _severity_from_confidence(confidence: float) -> str:
    if confidence >= 0.86:
        return SEVERITY_HIGH
    if confidence >= 0.74:
        return SEVERITY_MEDIUM_HIGH
    if confidence >= 0.58:
        return SEVERITY_MEDIUM
    return SEVERITY_LOW


def _describe_region(types: List[str], direction: str) -> str:
    if ARTIFACT_DIRECTIONAL_STRETCH in types and ARTIFACT_BLUR_PATCH in types:
        return f"Directional {direction} texture stretch with local blur/smear."
    if ARTIFACT_STRUCTURE_EDGE_WARP in types:
        return f"Candidate {direction} edge/texture warp affecting mapped feature reliability."
    if ARTIFACT_DIRECTIONAL_STRETCH in types:
        return f"Directional {direction} texture stretch/smear."
    if ARTIFACT_BLUR_PATCH in types:
        return "Localized low-detail blur patch."
    return "Basemap artifact candidate."


def _iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, aw) * max(0, ah)
    area_b = max(0, bw) * max(0, bh)
    denom = area_a + area_b - inter
    return inter / denom if denom else 0.0


def sweep_image(image_path: str, segmenter=None) -> dict:
    """Convenience wrapper returning a serializable dict."""
    return TileArtifactSweeper(segmenter=segmenter).analyze(image_path).to_dict()
