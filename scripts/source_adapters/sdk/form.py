"""Common HTML form parsing helpers for source adapters."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin


@dataclass(frozen=True)
class InputOption:
    """A parsed HTML input element."""

    input_type: str
    name: str
    value: str
    label: str = ""
    input_id: str = ""


@dataclass(frozen=True)
class ParsedForm:
    """A parsed HTML form with reproducible submission metadata."""

    source_url: str
    action_url: str
    method: str
    inputs: tuple[InputOption, ...]

    @property
    def hidden_fields(self) -> tuple[tuple[str, str], ...]:
        return tuple((item.name, item.value) for item in self.inputs if item.input_type == "hidden" and item.name)

    @property
    def checkboxes(self) -> tuple[InputOption, ...]:
        return tuple(item for item in self.inputs if item.input_type == "checkbox")


class BasicFormParser(HTMLParser):
    """Dependency-free parser for legacy government HTML forms."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_form = False
        self.form_action = ""
        self.form_method = "get"
        self.inputs: list[InputOption] = []
        self._pending_input: InputOption | None = None
        self._pending_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()
        if tag == "form":
            self.in_form = True
            self.form_action = attr.get("action", "")
            self.form_method = attr.get("method", "get").lower() or "get"
            return
        if not self.in_form or tag != "input":
            return
        input_type = attr.get("type", "text").lower()
        option = InputOption(
            input_type=input_type,
            name=attr.get("name", ""),
            value=attr.get("value", ""),
            input_id=attr.get("id", ""),
        )
        if input_type in {"checkbox", "radio"}:
            self._flush_pending()
            self._pending_input = option
            self._pending_text = []
        else:
            self.inputs.append(option)

    def handle_data(self, data: str) -> None:
        if self._pending_input is not None and data.strip():
            self._pending_text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"label", "li", "tr", "p", "br"}:
            self._flush_pending()
        if tag == "form":
            self._flush_pending()
            self.in_form = False

    def close(self) -> None:
        self._flush_pending()
        super().close()

    def _flush_pending(self) -> None:
        if self._pending_input is None:
            return
        self.inputs.append(
            InputOption(
                input_type=self._pending_input.input_type,
                name=self._pending_input.name,
                value=self._pending_input.value,
                input_id=self._pending_input.input_id,
                label=" ".join(self._pending_text).strip(),
            )
        )
        self._pending_input = None
        self._pending_text = []


def parse_first_form(html: str, source_url: str) -> ParsedForm:
    """Parse the first form in an HTML document."""

    parser = BasicFormParser()
    parser.feed(html)
    parser.close()
    method = parser.form_method if parser.form_method in {"get", "post"} else "get"
    return ParsedForm(
        source_url=source_url,
        action_url=urljoin(source_url, parser.form_action or source_url),
        method=method,
        inputs=tuple(parser.inputs),
    )
