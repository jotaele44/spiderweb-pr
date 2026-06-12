#!/usr/bin/env python3
"""
Spanish-language text-extraction helpers for PR missing-persons harvesters.

Every Spanish-text source we ingest (PRPB Alertas plans, PRPB Desaparecidos
gallery, Observatorio EEG quarterly PDFs, journalism trackers, FB tip-stream)
needs the same primitives:

  * Date normalization (ISO / DD/MM/YYYY / "15 de marzo de 2024" → ISO)
  * Age extraction ("Edad: 28" / "28 años")
  * Sex extraction ("Sexo: Masculino" → "M")
  * Status extraction ("ACTIVO" / "RESUELTO" / "ENCONTRADA" → canonical)
  * Municipio resolution (substring match against the 78-municipio list)
  * Address extraction ("Dirección: …")

This module centralizes them so a future template-cue change is a one-line
PR in one file, not five. The functions are pure (no I/O, no state) and
stdlib-only.

The 78-municipio list is a literal — splitting on whitespace breaks multi-
word names ("Aguas Buenas" → ["Aguas", "Buenas"]) and produces false-positive
matches against common Spanish words. We hit that exact bug in phase 2c.1 and
the test for it lives in tests/test_prpb_alertas.py.
"""

from __future__ import annotations

import re
from typing import List


# ---------------------------------------------------------------- dates

DATE_PATTERNS = [
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
    re.compile(
        r"\b(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|"
        r"agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})\b",
        re.IGNORECASE,
    ),
]

SPANISH_MONTHS = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
}


def extract_date(value: str) -> str:
    """Normalize a date-bearing string to ISO YYYY-MM-DD. Returns "" if none
    of our patterns match. Slash format is DD/MM/YYYY (PR convention).

    Works as both a cue-anchored extractor (the caller passes the text after
    'Fecha:') AND a free-text scanner (the caller passes the whole caption).
    The gallery harvester relies on the free-text mode because PRPB captions
    rarely use a clean 'Fecha de la alerta:' label — they say things like
    'Reportado desaparecido en Carolina el 2024-08-15'."""
    if not value:
        return ""
    for p in DATE_PATTERNS:
        m = p.search(value)
        if not m:
            continue
        if len(m.groups()) == 3:
            a, b, c = m.groups()
            if a.isdigit() and len(a) == 4:
                return f"{a}-{int(b):02d}-{int(c):02d}"
            if c.isdigit() and len(c) == 4 and b.isdigit():
                return f"{c}-{int(b):02d}-{int(a):02d}"
            if c.isdigit() and len(c) == 4:
                mm = SPANISH_MONTHS.get(b.lower(), "")
                if mm:
                    return f"{c}-{mm}-{int(a):02d}"
    return ""


# ---------------------------------------------------------------- field cues

# Field-label markers. Right-hand-side regex captures the value to the next
# newline. Cues are matched case-insensitively, then the value can still be
# post-processed (e.g., extract_date(_match_after_cue(text, FIELD_CUES["report_date"])))
FIELD_CUES = {
    "report_date": [
        r"fecha\s+de\s+(?:la\s+)?alerta\s*:?\s*",
        r"fecha\s+de\s+publicaci[óo]n\s*:?\s*",
        r"emitido\s+el\s*:?\s*",
        r"reportado(?:\s+el)?\s*:?\s*",
    ],
    "last_seen_date": [
        r"[úu]ltima\s+vez\s+visto\s+el\s*:?\s*",
        r"fecha\s+de\s+desaparici[óo]n\s*:?\s*",
        r"desaparecid[oa]\s+desde(?:\s+el)?\s*:?\s*",
    ],
    "address": [
        r"direcci[óo]n\s*:?\s*",
        r"[úu]ltima\s+vez\s+visto\s+en\s*:?\s*",
        r"lugar\s+de\s+(?:la\s+)?desaparici[óo]n\s*:?\s*",
    ],
    "age": [
        r"edad\s*:?\s*",
        r"(\d{1,3})\s*a[ñn]os",
    ],
    "sex": [
        r"sexo\s*:?\s*",
        r"g[ée]nero\s*:?\s*",
    ],
    "status_keyword": [
        r"\b(activ[oa]|resuelto|resuelta|encontrad[oa]|localizad[oa]|hallad[oa])\b",
    ],
}

# Status detection is split into three keyword classes, checked in priority
# order: DECEASED wins over any alive/resolution verb (so "encontrado
# fallecido" → deceased, NOT alive). RESOLVED_ALIVE covers the resolution
# verbs including "hallar" (which the old extractor missed → it returned the
# bare 'active' default for "fue hallada sana y salva"). Anything else falls
# through to 'active' — appearing on a missing-persons page implies an open
# case unless an explicit resolution/death keyword is present.
DECEASED_RE = re.compile(
    r"\b(fallecid[oa]s?|muert[oa]s?|cad[áa]ver(?:es)?|sin\s+vida|deceso|occis[oa]|"
    r"restos\s+(?:humanos|mortales)|hallad[oa]s?\s+(?:sin\s+vida|muert[oa]))\b",
    re.IGNORECASE,
)
RESOLVED_ALIVE_RE = re.compile(
    r"\b(resuelt[oa]s?|encontrad[oa]s?|localizad[oa]s?|hallad[oa]s?|aparecid[oa]s?|"
    r"sana?\s+y\s+salv[oa]|con\s+vida|en\s+buenas?\s+condiciones)\b",
    re.IGNORECASE,
)


def first_match(text: str, patterns: List[re.Pattern]) -> str:
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(0)
    return ""


def match_after_cue(text: str, cues: List[str]) -> str:
    """Find the first cue, return the text from end-of-cue to newline."""
    for cue in cues:
        m = re.search(cue, text, re.IGNORECASE)
        if m:
            tail = text[m.end():]
            line = tail.split("\n", 1)[0].strip()
            if line:
                return line
    return ""


# Relative-time phrases use "años" for elapsed time, not age:
# "desapareció hace 5 años", "lleva 3 años desaparecida". The age fallback
# must NOT read these as an age (a bogus small number would wrongly flip an
# adult case to missing_juvenile). We detect a relative-time cue immediately
# before the "NN años" span and skip it.
_RELATIVE_TIME_PREFIX_RE = re.compile(r"\b(hace|lleva|desde|por)\s*$", re.IGNORECASE)


def extract_age(text: str) -> str:
    """Find a numeric age. Prefer a labeled 'Edad: NN'; otherwise fall back to
    the first 'NN años' that is NOT part of a relative-time phrase
    ('hace 5 años' → skipped). Returns the bare number string, or ''."""
    label_match = re.search(r"edad\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    if label_match:
        return label_match.group(1)
    for m in re.finditer(r"(\d{1,3})\s*a[ñn]os", text, re.IGNORECASE):
        # Inspect up to 15 chars before the number for a relative-time cue.
        window = text[max(0, m.start() - 15):m.start()]
        if _RELATIVE_TIME_PREFIX_RE.search(window):
            continue
        return m.group(1)
    return ""


def extract_status(text: str) -> str:
    """Spanish-language status → canonical status, checked in PRIORITY order:

      1. DECEASED keywords ('fallecido', 'encontrado muerto', 'sin vida') →
         ``resolved_deceased``. Deceased wins over any alive/resolution verb,
         so 'encontrado fallecido' is correctly deceased, not alive.
      2. RESOLVED-ALIVE keywords ('encontrado', 'localizado', 'hallada',
         'sana y salva', 'con vida') → ``resolved_alive``.
      3. Otherwise → ``active``. Appearing on a missing-persons page implies an
         open case unless an explicit resolution/death keyword is present.

    This is a shared primitive: PRPB Alertas, PRPB Desaparecidos, and the
    journalism/NGO sources all route status through here, so the canonical
    ``resolved_deceased`` value (used everywhere else in the pipeline) must be
    reachable from Spanish text — the old extractor could never produce it."""
    if not text:
        return "active"
    if DECEASED_RE.search(text):
        return "resolved_deceased"
    if RESOLVED_ALIVE_RE.search(text):
        return "resolved_alive"
    return "active"


def extract_sex(text: str) -> str:
    return match_after_cue(text, FIELD_CUES["sex"])


def extract_address(text: str) -> str:
    return match_after_cue(text, FIELD_CUES["address"])


# ---------------------------------------------------------------- municipios

# All 78 PR municipios as a literal list. Multi-word names MUST stay intact —
# splitting on whitespace produces false tokens ("Buenas", "Juan", "Alta")
# that match common Spanish words in alert narratives. Match is case-
# insensitive whole-word; longer names matched first so "San Juan" wins over
# the (non-existent) shorter token "Juan".
MUNICIPIOS = [
    "Adjuntas", "Aguada", "Aguadilla", "Aguas Buenas", "Aibonito", "Añasco",
    "Arecibo", "Arroyo", "Barceloneta", "Barranquitas", "Bayamón",
    "Cabo Rojo", "Caguas", "Camuy", "Canóvanas", "Carolina", "Cataño",
    "Cayey", "Ceiba", "Ciales", "Cidra", "Coamo", "Comerío", "Corozal",
    "Culebra", "Dorado", "Fajardo", "Florida", "Guánica", "Guayama",
    "Guayanilla", "Guaynabo", "Gurabo", "Hatillo", "Hormigueros", "Humacao",
    "Isabela", "Jayuya", "Juana Díaz", "Juncos", "Lajas", "Lares",
    "Las Marías", "Las Piedras", "Loíza", "Luquillo", "Manatí", "Maricao",
    "Maunabo", "Mayagüez", "Moca", "Morovis", "Naguabo", "Naranjito",
    "Orocovis", "Patillas", "Peñuelas", "Ponce", "Quebradillas", "Rincón",
    "Río Grande", "Sabana Grande", "Salinas", "San Germán", "San Juan",
    "San Lorenzo", "San Sebastián", "Santa Isabel", "Toa Alta", "Toa Baja",
    "Trujillo Alto", "Utuado", "Vega Alta", "Vega Baja", "Vieques",
    "Villalba", "Yabucoa", "Yauco",
]

MUNICIPIO_PATTERNS = [
    (m, re.compile(rf"\b{re.escape(m)}\b", re.IGNORECASE))
    for m in sorted(MUNICIPIOS, key=len, reverse=True)
]

# Municipio names that are ALSO common Spanish/English words. A bare token
# match on these produces false positives on in-domain text:
#   "Florida" (US state / flower-adjective), "Salinas" (salt flats — a real
#   non-municipio PR feature near Cabo Rojo), "Dorado" (golden — appearance
#   descriptions like "cabello dorado"), "Arroyo" (stream/brook), "Cataño".
# These match ONLY when anchored to a location cue ("en Dorado"), never bare.
AMBIGUOUS_MUNICIPIOS = {"Florida", "Salinas", "Dorado", "Arroyo", "Cataño"}

# Location-cue-anchored matcher: a preposition/locator immediately followed by
# a municipio name. Longest-first alternation so "San Juan" wins over a bare
# token. Used as the high-confidence first pass.
_LOCATION_CUE = r"(?:en|de|del|municipio\s+de|desde|hacia|para|residente\s+de|procedente\s+de)"
_MUNI_ALTERNATION = "|".join(
    re.escape(m) for m in sorted(MUNICIPIOS, key=len, reverse=True)
)
_CUE_MUNICIPIO_RE = re.compile(
    rf"\b{_LOCATION_CUE}\s+({_MUNI_ALTERNATION})\b", re.IGNORECASE
)
_MUNICIPIO_LOOKUP = {m.lower(): m for m in MUNICIPIOS}


def extract_municipio(text: str) -> str:
    """Resolve a PR municipio from free text.

    Two passes:
      1. High-confidence: a municipio immediately following a location cue
         ('en Carolina', 'municipio de Ponce'). This is the only path by which
         an ambiguous common-word name (Florida, Salinas, Dorado, …) can match.
      2. Fallback: a bare whole-word match for any UNAMBIGUOUS municipio name
         (longest-first so 'San Juan' wins). Ambiguous names are excluded here
         to avoid false positives on appearance/description text.

    Empty string if none."""
    cue_match = _CUE_MUNICIPIO_RE.search(text)
    if cue_match:
        return _MUNICIPIO_LOOKUP.get(cue_match.group(1).lower(), cue_match.group(1))
    for muni, pat in MUNICIPIO_PATTERNS:
        if muni in AMBIGUOUS_MUNICIPIOS:
            continue
        if pat.search(text):
            return muni
    return ""
