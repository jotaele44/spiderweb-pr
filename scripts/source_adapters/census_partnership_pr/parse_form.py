"""Parse the Census Partnership Puerto Rico shapefile batch-download form.

The Census page is an HTML form with one checkbox per municipio and a hard
batch limit of five selected municipios. This module is intentionally stdlib-only
so the adapter can run in constrained environments.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin
import re

STATE_CODE_PR = "72"
MUNICIPIO_CODE_RE = re.compile(r"\b72\d{3}\b")
MAX_BATCH_SIZE = 5


@dataclass(frozen=True)
class MunicipioOption:
    """One selectable municipio entry from the Census form."""

    code: str
    name: str
    input_name: str
    input_value: str


@dataclass(frozen=True)
class CensusPartnershipForm:
    """Parsed form metadata required to reproduce a request."""

    source_url: str
    action_url: str
    method: str
    hidden_fields: tuple[tuple[str, str], ...]
    municipios: tuple[MunicipioOption, ...]


class _PartnershipFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_form = False
        self.form_action = ""
        self.form_method = "get"
        self.hidden_fields: list[tuple[str, str]] = []
        self._pending_checkbox: dict[str, str] | None = None
        self._pending_text: list[str] = []
        self.municipios: list[MunicipioOption] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        tag = tag.lower()

        if tag == "form":
            self.in_form = True
            self.form_action = attr.get("action", "")
            self.form_method = attr.get("method", "get").lower() or "get"
            return

        if not self.in_form or tag != "input":
            return

        input_type = attr.get("type", "text").lower()
        name = attr.get("name", "")
        value = attr.get("value", "")

        if input_type == "hidden" and name:
            self.hidden_fields.append((name, value))
            return

        if input_type == "checkbox" and name:
            code = _extract_municipio_code(" ".join([value, name, attr.get("id", "")]))
            if code:
                self._flush_pending_checkbox()
                self._pending_checkbox = {"name": name, "value": value, "code": code}
                self._pending_text = []

    def handle_data(self, data: str) -> None:
        if self._pending_checkbox is not None:
            text = data.strip()
            if text:
                self._pending_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"label", "li", "tr", "p", "br"}:
            self._flush_pending_checkbox()
        if tag == "form":
            self._flush_pending_checkbox()
            self.in_form = False

    def close(self) -> None:
        self._flush_pending_checkbox()
        super().close()

    def _flush_pending_checkbox(self) -> None:
        if self._pending_checkbox is None:
            return
        raw_name = " ".join(self._pending_text).strip()
        code = self._pending_checkbox["code"]
        cleaned_name = _clean_municipio_name(raw_name, code)
        self.municipios.append(
            MunicipioOption(
                code=code,
                name=cleaned_name or code,
                input_name=self._pending_checkbox["name"],
                input_value=self._pending_checkbox["value"],
            )
        )
        self._pending_checkbox = None
        self._pending_text = []


def _extract_municipio_code(value: str) -> str | None:
    match = MUNICIPIO_CODE_RE.search(value or "")
    return match.group(0) if match else None


def _clean_municipio_name(raw: str, code: str) -> str:
    name = re.sub(MUNICIPIO_CODE_RE, "", raw or "")
    name = re.sub(r"^[\s\-–—:;,()]+|[\s\-–—:;,()]+$", "", name)
    return re.sub(r"\s+", " ", name).strip()


def parse_partnership_form(html: str, source_url: str) -> CensusPartnershipForm:
    """Parse the Census form and return reproducible request metadata."""

    parser = _PartnershipFormParser()
    parser.feed(html)
    parser.close()

    deduped: dict[str, MunicipioOption] = {}
    for option in parser.municipios:
        deduped.setdefault(option.code, option)

    municipios = tuple(sorted(deduped.values(), key=lambda item: item.code))
    if not municipios:
        raise ValueError("No Puerto Rico municipio checkbox options were found in the Census form")

    return CensusPartnershipForm(
        source_url=source_url,
        action_url=urljoin(source_url, parser.form_action or source_url),
        method=parser.form_method if parser.form_method in {"get", "post"} else "get",
        hidden_fields=tuple(parser.hidden_fields),
        municipios=municipios,
    )


def make_batches(codes: Iterable[str], batch_size: int = MAX_BATCH_SIZE) -> list[tuple[str, ...]]:
    """Split municipio codes into deterministic batches with the Census limit."""

    if batch_size < 1 or batch_size > MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")

    clean_codes = tuple(dict.fromkeys(str(code).strip() for code in codes if str(code).strip()))
    invalid = [code for code in clean_codes if not MUNICIPIO_CODE_RE.fullmatch(code)]
    if invalid:
        raise ValueError(f"Invalid Puerto Rico municipio code(s): {', '.join(invalid)}")

    return [clean_codes[index : index + batch_size] for index in range(0, len(clean_codes), batch_size)]


def select_municipios(form: CensusPartnershipForm, requested: Iterable[str] | None) -> tuple[MunicipioOption, ...]:
    """Resolve requested codes against the parsed municipio universe."""

    by_code = {municipio.code: municipio for municipio in form.municipios}
    if requested is None:
        return form.municipios

    selected_codes = tuple(dict.fromkeys(code.strip() for code in requested if code.strip()))
    missing = [code for code in selected_codes if code not in by_code]
    if missing:
        raise ValueError(f"Requested municipio code(s) not present in Census form: {', '.join(missing)}")
    return tuple(by_code[code] for code in selected_codes)
