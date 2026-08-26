from __future__ import annotations

from pipeline.marine_archive_sources import fetch_archive_listing, product_candidates
from pipeline.marine_sources import FrozenHttpResponse


def _transport(url: str) -> FrozenHttpResponse:
    body = b'''<a href="a.gsf">a</a><a href="sub/">sub</a><a href="../escape.gsf">escape</a><a href="https://evil.test/x.gsf">evil</a>'''
    return FrozenHttpResponse(
        request_url=url,
        status=200,
        retrieved_utc="2026-08-16T00:00:00+00:00",
        response_sha256="0" * 64,
        response_size=len(body),
        headers={},
        body=body,
    )


def test_archive_listing_is_host_and_prefix_bounded() -> None:
    result = fetch_archive_listing("https://data.example.test/root/", transport=_transport)
    assert result.links == (
        "https://data.example.test/root/a.gsf",
        "https://data.example.test/root/sub/",
    )
    assert product_candidates(result.links) == ("https://data.example.test/root/a.gsf",)
