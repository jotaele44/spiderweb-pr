#!/usr/bin/env python3
"""
PRPB ``Personas Desaparecidas`` gallery harvester (phase 2c.2).

WHY THIS IS DIFFERENT FROM PRPB ALERTAS
---------------------------------------
The PRPB ``policia.pr.gov/desaparecidos`` page is a *gallery* — one HTML
page contains MANY person cards, each with a photo, a name, and a thin
caption. The page exposes no public case ID, no last-seen lat/lon, no
explicit date or status field. Per the deep-research workflow finding:

    "Photo gallery — names visible; case_id/coords/dates/status NOT
     surfaced. Thin canonical rows; geocoding required from caption text."

This harvester therefore:

  1. Reads the operator-saved HTML pages (one or more pages per snapshot
     — the gallery is paginated).
  2. Detects per-person *cards* by their repeating CONTAINER element (see
     ``_GalleryCardExtractor``), not by the ``<img>`` — so wrapper/thumb divs
     don't truncate the caption and page logos/share-icons don't become rows.
  3. **Drops the visible name string entirely** — names are never copied
     into ``circumstances_subcategory``, never into ``status_reason``,
     never anywhere.
  4. Derives a stable ``case_id_hash`` from the photo URL (the image
     filename is the closest thing to a stable PRPB-side identifier).
  5. Extracts whatever signal *is* in the caption: municipio (matched
     against the 78-municipio list), age if mentioned, last-seen date if
     mentioned. Most cards yield only municipio.
  6. Defaults ``incident_class = missing_adult_other``. If the extracted
     age is under 18, the class flips to ``missing_juvenile``.
  7. Sets ``federation_eligible = false`` — but note this flag is only
     DECLARED in ``configs/missing_persons_sources.yaml``; no runtime path in
     this harvester enforces it. Enforcement (refusing to emit this source's
     case-level rows into a federation export) is the responsibility of the
     phase-2b consolidator/export layer, which is not yet built. Until then
     the boundary is documentation + an advisory audit WARN, not a code gate.

The harvester is *file-driven*. The operator pulls gallery pages manually
(or via a one-off pacing script) and drops them as ``.html`` files under::

    data/sources/prpb_desaparecidos/<YYYY-MM-DD>/page_<n>.html

Stdlib only.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts._harvest_base import (  # noqa: E402
    HarvestBase,
    bucket_age,
    bucket_ethnicity,
    empty_canonical,
    hash_id,
    normalize_sex,
    validate_incident_class,
)
from scripts._text_extract_es import (  # noqa: E402
    extract_age,
    extract_date,
    extract_municipio,
    extract_sex,
    extract_status,
    FIELD_CUES,
    match_after_cue,
)


# ---------------------------------------------------------------- card extractor

class _GalleryCardExtractor(HTMLParser):
    """Walk the gallery DOM and accumulate one structured record per *card*.

    A *card* is a repeating container element, NOT an ``<img>``. Keying off
    ``<img>`` (the old approach) breaks on the extremely common thumbnail-frame
    markup ``<div class=card><div class=thumb><img></div><p>caption</p></div>``:
    the inner ``</div>`` (closing the thumb wrapper) would fire a premature
    card-close before the caption ``<p>`` was ever read, dropping the entire
    caption. It also turned every page logo and per-card share/social icon into
    a phantom row.

    Instead we open a card when we ENTER a card container and close it when
    that SAME container (matched by element depth) closes:

      * Card containers are ``<li>`` / ``<article>`` always (semantic list/card
        tags), plus ``<div>``/``<a>``/``<figure>``/``<section>`` ONLY when their
        class attribute matches a card-ish token (card|item|persona|
        desaparecid|missing|result|gallery-item).
      * All text and all ``<img>`` srcs inside the container accumulate into the
        one card. At close we pick the best person-photo src (prefer a src whose
        path looks like a person photo; else the first img) and emit ONLY if the
        caption text is non-empty — so logo/icon-only containers never emit.

    Cards do not nest in real galleries; if a second container opens while one
    is active it is treated as interior structure, and the active card closes
    when we return to its open depth.

    Name strings inside the caption survive in ``text`` — but the harvester's
    ``normalize_row`` NEVER reads them into the canonical. ``text`` is forensic
    input to the Spanish-text scanners, not output.
    """

    CONTAINER_TAGS = {"li", "article"}
    AMBIGUOUS_CONTAINER_TAGS = {"div", "a", "figure", "section"}
    CARD_CLASS_RE = re.compile(
        r"card|item|persona|desaparecid|missing|result|gallery-item|thumb-card",
        re.IGNORECASE,
    )
    # ``src`` paths that look like a per-person photo (preferred for case_id).
    PHOTO_SRC_RE = re.compile(
        r"photo|foto|desaparecid|/people/|/persons?/|/missing/|/casos?/",
        re.IGNORECASE,
    )
    BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br",
                  "figure", "section", "article", "td", "tr"}
    SKIP_TAGS = {"script", "style", "noscript", "head"}
    # Void elements never carry a matching end tag — they must not change depth.
    VOID_TAGS = {"img", "br", "hr", "input", "meta", "link", "source", "area",
                 "base", "col", "embed", "param", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._cards: List[Dict[str, str]] = []
        self._depth = 0
        self._skip_depth = 0
        # Exactly one active card at a time (the innermost open container).
        self._active: Optional[Dict[str, object]] = None

    @property
    def cards(self) -> List[Dict[str, str]]:
        return self._cards

    def _is_container(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> bool:
        if tag in self.CONTAINER_TAGS:
            return True
        if tag in self.AMBIGUOUS_CONTAINER_TAGS:
            cls = ""
            for k, v in attrs:
                if k.lower() == "class":
                    cls = v or ""
                    break
            return bool(self.CARD_CLASS_RE.search(cls))
        return False

    def _add_img(self, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if self._active is None:
            return
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        src = attr_map.get("src", "").strip()
        if src:
            self._active["imgs"].append(src)  # type: ignore[union-attr]

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag not in self.VOID_TAGS:
            self._depth += 1
        if self._active is None and self._is_container(tag, attrs):
            self._active = {"open_depth": self._depth, "imgs": [], "text_chunks": []}
        if tag == "img":
            self._add_img(attrs)
        elif tag == "br" and self._active is not None:
            self._active["text_chunks"].append("\n")  # type: ignore[union-attr]

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        """``<img/>`` self-closing form (XHTML-shaped pages)."""
        if self._skip_depth:
            return
        if tag.lower() == "img":
            self._add_img(attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in self.BLOCK_TAGS and self._active is not None:
            self._active["text_chunks"].append("\n")  # type: ignore[union-attr]
        if tag in self.VOID_TAGS:
            return
        # Closing the element that opened the active card → emit and reset.
        if self._active is not None and self._depth == self._active["open_depth"]:
            self._finish_active()
        if self._depth > 0:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._active is None:
            return
        self._active["text_chunks"].append(data)  # type: ignore[union-attr]

    def close(self) -> None:  # type: ignore[override]
        super().close()
        if self._active is not None:
            self._finish_active()

    def _finish_active(self) -> None:
        card = self._active
        self._active = None
        if card is None:
            return
        text = "".join(card["text_chunks"])  # type: ignore[arg-type]
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text).strip()
        # Require a caption — logo/icon-only containers (no text) never emit.
        if not text:
            return
        imgs = card["imgs"]  # type: ignore[assignment]
        photo_src = ""
        for src in imgs:  # type: ignore[union-attr]
            if self.PHOTO_SRC_RE.search(src):
                photo_src = src
                break
        if not photo_src and imgs:
            photo_src = imgs[0]  # type: ignore[index]
        self._cards.append({"photo_src": photo_src, "text": text})


# ---------------------------------------------------------------- harvester

class PrpbDesaparecidosHarvest(HarvestBase):
    SOURCE_ID = "prpb_desaparecidos"
    SOURCE_STRATUM = "A"
    SOURCE_DIR_NAME = "prpb_desaparecidos"
    RAW_ALIASES: Dict[str, List[str]] = {}

    def harvest(self, snapshot_dir: Path) -> Tuple[Path, int, int]:
        html_paths = sorted(snapshot_dir.glob("*.html"))
        if not html_paths:
            raise FileNotFoundError(f"No *.html files in {snapshot_dir}")
        snapshot_date = snapshot_dir.name
        canonical: List[Dict[str, str]] = []
        dropped = 0
        for html_path in html_paths:
            page_html = html_path.read_text(encoding="utf-8", errors="replace")
            extractor = _GalleryCardExtractor()
            extractor.feed(page_html)
            extractor.close()
            for card in extractor.cards:
                row = self.normalize_row({**card, "_page_filename": html_path.name},
                                         snapshot_date)
                if row is None:
                    dropped += 1
                    continue
                canonical.append(row)
        out_path = snapshot_dir / self.canonical_filename()
        self.write_canonical(canonical, out_path)
        return out_path, len(canonical), dropped

    def normalize_row(self, raw: Dict[str, str], snapshot_date: str) -> Optional[Dict[str, str]]:
        photo_src = raw.get("photo_src", "")
        text = raw.get("text", "")
        # Require a caption. A card with no text is a logo/icon container that
        # slipped through, not a person — drop it. (The extractor already
        # enforces this; the guard is defense-in-depth for direct callers.)
        if not text:
            return None

        canonical = empty_canonical(snapshot_date, self.SOURCE_ID)

        # Stable per-card ID = hash of the photo URL filename stem (the only
        # PRPB-side identifier on the page). If the photo filename is empty,
        # fall back to a hash of the card position + page filename — less
        # stable across snapshots but at least lets the row exist.
        stem = ""
        if photo_src:
            stem = photo_src.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if not stem:
            stem = f"{raw.get('_page_filename', 'unknown')}::{hash_id(text)[:8]}"
        canonical["case_id_hash"] = hash_id(stem)
        canonical["source_record_url_hash"] = hash_id(photo_src or stem)

        # Caption scanning — every field is optional. Names in the caption
        # are NOT extracted into the canonical — they sit unused in ``text``.
        # Date extraction has a cue-first / free-text-fallback shape: the
        # gallery captions rarely use a 'Fecha:' label, so when the cue fails
        # we scan the whole caption for any date pattern.
        canonical["report_date"] = extract_date(match_after_cue(text, FIELD_CUES["report_date"]))
        canonical["last_seen_date"] = (
            extract_date(match_after_cue(text, FIELD_CUES["last_seen_date"]))
            or extract_date(text)
        )

        age = extract_age(text)
        canonical["age_band"] = bucket_age(age)
        canonical["age_exact_known"] = "true" if age else ""

        canonical["sex"] = normalize_sex(extract_sex(text))
        canonical["ethnicity_band"] = bucket_ethnicity("")

        canonical["last_seen_municipio"] = extract_municipio(text)
        canonical["last_seen_geocode_method"] = "pending" if canonical["last_seen_municipio"] else ""

        # Default: missing_adult_other. Flip to missing_juvenile if the age
        # extractor surfaced a value < 18.
        incident_class = "missing_adult_other"
        if age:
            try:
                if int(age) < 18:
                    incident_class = "missing_juvenile"
            except ValueError:
                pass
        canonical["incident_class"] = validate_incident_class(incident_class)

        # Default status: appearing on the page → active. The page does not
        # publish resolution events; closed cases are removed from the page.
        canonical["status"] = extract_status(text)

        return canonical


if __name__ == "__main__":
    raise SystemExit(PrpbDesaparecidosHarvest().main())
