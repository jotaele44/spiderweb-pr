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


_META_CHARSET_RE = re.compile(rb"""charset=["']?\s*([\w-]+)""", re.IGNORECASE)


def _read_html(path: Path) -> str:
    """Decode an operator-saved HTML page robustly. Older PR-gov pages are often
    Latin-1/CP1252, not UTF-8; reading those as UTF-8 mangles every accented
    field (Bayamón, años, …) and silently loses municipios/ages. Try the
    declared ``<meta charset>`` first, then UTF-8, then CP1252, and only
    last-resort replace."""
    raw = path.read_bytes()
    candidates: List[str] = []
    m = _META_CHARSET_RE.search(raw[:2048])
    if m:
        try:
            candidates.append(m.group(1).decode("ascii").lower())
        except UnicodeDecodeError:
            pass
    for enc in [*candidates, "utf-8", "cp1252"]:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


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
      * We keep a STACK of open containers and emit only a LEAF container — one
        whose nested containers did NOT themselves emit cards. So a card-ish
        WRAPPER (``<section class=missing-persons>`` / ``<div class=results>``
        around many cards) is discarded rather than swallowing every inner card
        into a single phantom row, while a real card that merely holds a sub-list
        is still emitted. Unclosed sibling ``<li>``s (which ``html.parser`` does
        not auto-close) are recovered via an implied end tag.
      * All text and ``<img>`` srcs accumulate into the innermost open card. At
        close we pick the best person-photo src (prefer a path that looks like a
        person photo; else the first img) and emit ONLY if the card has BOTH
        caption text AND a photo — so a logo, a nav/footer/pagination ``<li>``,
        or a share-icon container never becomes a row.

    Name strings inside the caption survive in ``text`` — but the harvester's
    ``normalize_row`` NEVER reads them into the canonical. ``text`` is forensic
    input to the Spanish-text scanners, not output.
    """

    CONTAINER_TAGS = {"li", "article"}
    AMBIGUOUS_CONTAINER_TAGS = {"div", "a", "figure", "section"}
    # <li> has an OPTIONAL end tag and html.parser does NOT auto-close it, so a
    # real page's unclosed sibling <li>s would otherwise nest and get discarded
    # as wrappers (dropping every card but the last). We implement the implied
    # </li>. LIST_TAGS track genuine nesting: a new <li> is a sibling to close
    # ONLY when no list is currently open inside the active card.
    AUTO_CLOSE_TAGS = {"li"}
    LIST_TAGS = {"ul", "ol", "menu", "dl"}
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
        # Stack of open card containers (innermost last). A container is emitted
        # only when it closes as a LEAF (no nested card container opened inside
        # it), so a card-ish wrapper around many cards is discarded, not merged.
        self._stack: List[Dict[str, object]] = []

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
        if not self._stack:
            return
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        src = attr_map.get("src", "").strip()
        if src:
            self._stack[-1]["imgs"].append(src)  # type: ignore[union-attr]

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag not in self.VOID_TAGS:
            self._depth += 1
        if tag in self.LIST_TAGS and self._stack:
            self._stack[-1]["open_lists"] = self._stack[-1].get("open_lists", 0) + 1  # type: ignore[operator]
        if self._is_container(tag, attrs):
            # Implied </li>: an unclosed sibling <li> closes the previous one.
            # A genuinely nested <li> sits inside an open list (open_lists > 0)
            # and is left alone — so flat unclosed siblings are recovered without
            # collapsing real sub-lists.
            while (tag in self.AUTO_CLOSE_TAGS and self._stack
                   and self._stack[-1].get("open_tag") == tag
                   and self._stack[-1].get("open_lists", 0) == 0):
                self._close_top()
            self._stack.append(
                {"open_depth": self._depth, "open_tag": tag, "open_lists": 0,
                 "imgs": [], "text_chunks": [], "had_emitted_child": False}
            )
        if tag == "img":
            self._add_img(attrs)
        elif tag == "br" and self._stack:
            self._stack[-1]["text_chunks"].append("\n")  # type: ignore[union-attr]

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
        if tag in self.BLOCK_TAGS and self._stack:
            self._stack[-1]["text_chunks"].append("\n")  # type: ignore[union-attr]
        if tag in self.LIST_TAGS and self._stack:
            self._stack[-1]["open_lists"] = max(0, self._stack[-1].get("open_lists", 0) - 1)  # type: ignore[operator]
        if tag in self.VOID_TAGS:
            return
        # Closing the element that opened the innermost card → resolve it.
        if self._stack and self._depth == self._stack[-1]["open_depth"]:
            self._close_top()
        if self._depth > 0:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not self._stack:
            return
        self._stack[-1]["text_chunks"].append(data)  # type: ignore[union-attr]

    def close(self) -> None:  # type: ignore[override]
        super().close()
        while self._stack:
            self._close_top()

    def _close_top(self) -> None:
        card = self._stack.pop()
        text = "".join(card["text_chunks"])  # type: ignore[arg-type]
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text).strip()
        imgs = card["imgs"]  # type: ignore[assignment]
        # A real person card has BOTH a caption and a photo (this is a photo
        # gallery), AND is a leaf — a container whose children already emitted
        # cards is a wrapper, not a card, so it is discarded (its leaves were the
        # real rows). Requiring an <img> also drops nav/footer/pagination <li>s
        # and caption/photo-less logo containers. Note: a card that merely holds
        # a nested sub-list (whose items emit nothing) keeps had_emitted_child
        # False and is still emitted.
        if not text or not imgs or card.get("had_emitted_child"):
            return
        photo_src = ""
        for src in imgs:  # type: ignore[union-attr]
            if self.PHOTO_SRC_RE.search(src):
                photo_src = src
                break
        if not photo_src:
            photo_src = imgs[0]  # type: ignore[index]
        self._cards.append({"photo_src": photo_src, "text": text})
        if self._stack:
            # The enclosing container produced a real card child → it is a
            # wrapper, and must not also emit itself as a row.
            self._stack[-1]["had_emitted_child"] = True


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
        seen_ids: set[str] = set()
        for html_path in html_paths:
            page_html = _read_html(html_path)
            extractor = _GalleryCardExtractor()
            extractor.feed(page_html)
            extractor.close()
            for card in extractor.cards:
                row = self.normalize_row({**card, "_page_filename": html_path.name},
                                         snapshot_date)
                if row is None:
                    dropped += 1
                    continue
                # Cross-page dedup: paginated pulls overlap, and the same person
                # can appear on two saved pages. case_id_hash is the photo-stem
                # identity, so a re-pull of one person collapses to one row.
                case_id = row.get("case_id_hash", "")
                if case_id and case_id in seen_ids:
                    dropped += 1
                    continue
                seen_ids.add(case_id)
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
        report_date = extract_date(match_after_cue(text, FIELD_CUES["report_date"]))
        canonical["report_date"] = report_date
        last_seen_cued = extract_date(match_after_cue(text, FIELD_CUES["last_seen_date"]))
        if last_seen_cued:
            canonical["last_seen_date"] = last_seen_cued
        else:
            # Free-text fallback (captions rarely label the date), but don't just
            # re-read the report date into last_seen — that double-assigns one
            # date to two fields with different meanings.
            free = extract_date(text)
            canonical["last_seen_date"] = free if free and free != report_date else ""

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
