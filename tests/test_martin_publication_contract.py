from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.build_martin_config import compile_config
from scripts.check_martin_promotion import check
from server.backend.martin_ingress import UPSTREAM_BASE_URL, create_router, published_source_ids

ROOT = Path(__file__).resolve().parent.parent


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_committed_martin_config_contains_zero_sources_and_no_autodiscovery():
    config = _yaml(ROOT / "martin" / "config.yaml")
    assert config["geojson"]["sources"] == {}
    assert "paths" not in config["geojson"]


def test_validated_is_certifiable_but_not_production_published():
    certification, cert_manifest = compile_config("certification")
    production, prod_manifest = compile_config("production")
    cert = yaml.safe_load(certification)
    prod = yaml.safe_load(production)
    assert set(cert["geojson"]["sources"]) == {"municipios"}
    assert prod["geojson"]["sources"] == {}
    assert cert_manifest["admitted_sources"] == ["municipios"]
    assert prod_manifest["admitted_sources"] == []


def test_config_generation_is_deterministic():
    a, ma = compile_config("production")
    b, mb = compile_config("production")
    assert a == b
    assert ma["config_sha256"] == mb["config_sha256"]
    assert ma["input_sha256"] == mb["input_sha256"]


def test_canary_and_certification_never_use_directory_discovery():
    for env in ("canary", "certification", "production"):
        rendered, _ = compile_config(env)
        geojson = yaml.safe_load(rendered)["geojson"]
        assert "paths" not in geojson


def test_registry_property_policy_is_exact_and_fail_closed():
    source = _yaml(ROOT / "configs" / "martin_delivery.yaml")["sources"]["municipios"]
    assert source["publication_state"] == "validated"
    assert source["delivery_properties"] == {
        "include": ["GEOID", "NAME"],
        "exclude_by_default": True,
    }


def test_promotion_checker_is_non_mutating_and_only_reports_eligibility():
    before = (ROOT / "configs" / "martin_delivery.yaml").read_bytes()
    receipt = check("municipios", "published")
    after = (ROOT / "configs" / "martin_delivery.yaml").read_bytes()
    assert before == after
    assert receipt["current_state"] == "validated"
    assert receipt["target_state"] == "published"
    assert receipt["mutation_performed"] is False


def test_invalid_transition_rejected():
    with pytest.raises(ValueError, match="invalid transition"):
        check("municipios", "deprecated")


def test_production_ingress_authorizes_no_sources_today():
    assert published_source_ids() == set()


def test_arbitrary_martin_proxy_target_is_rejected():
    with pytest.raises(ValueError, match="arbitrary proxy targets"):
        create_router(upstream_base_url="https://example.com")
    create_router(upstream_base_url=UPSTREAM_BASE_URL)


def test_quarantine_removes_source_from_ingress(tmp_path: Path):
    registry = _yaml(ROOT / "configs" / "martin_delivery.yaml")
    registry["sources"]["municipios"]["publication_state"] = "published"
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    assert published_source_ids(path) == {"municipios"}
    registry["sources"]["municipios"]["publication_state"] = "quarantined"
    path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    assert published_source_ids(path) == set()


def test_registry_does_not_contain_forbidden_expansion_sources():
    sources = set(_yaml(ROOT / "configs" / "martin_delivery.yaml")["sources"])
    assert sources == {"municipios"}
    assert not {"tracts", "places", "barrios"} & sources


def test_no_postgis_introduced_in_current_source():
    source = _yaml(ROOT / "configs" / "martin_delivery.yaml")["sources"]["municipios"]
    assert source["source_type"] == "geojson"
