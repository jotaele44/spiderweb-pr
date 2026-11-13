"""The `source_monitors` export stream (thehub-pr ADR 0013).

One row per source in manifests/pr_hydrography/source_registry.csv and
configs/missing_persons_sources.yaml, never one the registry marks
`federation_eligible: false`. Declared fields reproduce thehub-pr's registry reader
(src/hub/source_monitor.py). When a source last succeeded comes only from a run
receipt in data/source_run_state.json (RUN_RECEIPT); no fetcher writes one yet, so
on committed data every source is NOT_RECORDED with a null time.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import federation_export as fe  # noqa: E402
import prii_export_utils  # noqa: E402

NOW = "2026-11-13T18:00:00Z"
HYDROGRAPHY = REPO / "manifests/pr_hydrography/source_registry.csv"
MISSING_PERSONS = REPO / "configs/missing_persons_sources.yaml"
SCHEMA = REPO / "schemas/federation_source_monitor.schema.json"
# sha256 of thehub-pr schemas/federation_source_monitor.schema.json (1.0.0, added in
# 7b9759f, unchanged at 0f62e4b): the vendored copy must stay byte-identical.
HUB_SCHEMA_SHA256 = "3cae40aacc4dff008cb0c97b4e5ab531648f6c262bc882627545fc32fb6c8e46"


def _hydrography() -> list[dict[str, str]]:
    with HYDROGRAPHY.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _missing_persons() -> dict[str, dict]:
    return yaml.safe_load(MISSING_PERSONS.read_text(encoding="utf-8"))["sources"]


def _never_federated() -> set[str]:
    return {
        k for k, v in _missing_persons().items() if v["federation_eligible"] is False
    }


def _committed(tmp_path: Path) -> list[dict]:
    # A local data/source_run_state.json is git-ignored; keep tests off it.
    return fe.build_source_monitors(NOW, run_state_path=tmp_path / "absent.json")


def _by_ref(rows: list[dict]) -> dict[str, dict]:
    return {r["source_ref"]: r for r in rows}


def test_one_row_per_registered_source(tmp_path):
    rows = _committed(tmp_path)
    expected = [r["source_id"] for r in _hydrography()]
    expected += [k for k in _missing_persons() if k not in _never_federated()]
    assert [r["source_ref"] for r in rows] == sorted(expected)
    for row in rows:
        digest = hashlib.sha256(
            f"spiderweb-pr|{row['source_ref']}".encode()
        ).hexdigest()
        assert row["monitor_id"] == "mon_" + digest[:32]
        assert row["monitor_id"] == prii_export_utils.monitor_id(
            fe.PRODUCER, row["source_ref"]
        )
    assert len({r["monitor_id"] for r in rows}) == len(rows)
    registry = {r["source_ref"]: r["registry_path"] for r in rows}
    assert {registry[r["source_id"]] for r in _hydrography()} == {
        "manifests/pr_hydrography/source_registry.csv"
    }
    assert registry["namus"] == "configs/missing_persons_sources.yaml"


def test_never_federated_sources_are_not_emitted(tmp_path):
    excluded = _never_federated()
    assert excluded, "the registry marks some sources never-federated"
    assert not excluded & {r["source_ref"] for r in _committed(tmp_path)}


def test_rows_validate_against_the_vendored_hub_schema(tmp_path):
    assert hashlib.sha256(SCHEMA.read_bytes()).hexdigest() == HUB_SCHEMA_SHA256
    validator = jsonschema.Draft7Validator(
        json.loads(SCHEMA.read_text()), format_checker=jsonschema.FormatChecker()
    )
    for row in _committed(tmp_path):
        errors = [e.message for e in validator.iter_errors(row)]
        assert not errors, (row["source_ref"], errors)


def test_without_receipts_nothing_is_recorded(tmp_path):
    # No fetcher writes run receipts yet and no committed output carries a
    # per-source retrieval time: every source is NOT_RECORDED, with null times.
    for row in _committed(tmp_path):
        assert row["last_success_basis"] == "NOT_RECORDED"
        assert row["last_success_at"] is None
        assert row["last_attempt_at"] is None and row["last_attempt_status"] is None
        assert row["synthetic"] is False


def test_run_receipts_give_the_last_success(tmp_path):
    state = tmp_path / "source_run_state.json"
    prii_export_utils.record_run(
        state, "TIGER_PR_BOUNDARY", "success", "2026-11-10T10:00:00Z"
    )
    prii_export_utils.record_run(state, "namus", "success", "2026-11-09T08:00:00Z")
    prii_export_utils.record_run(state, "namus", "failure", "2026-11-12T08:00:00Z")
    prii_export_utils.record_run(
        state, "prpb_alertas_amber", "failure", "2026-11-12T09:00:00Z"
    )
    # Receipts for a never-federated or an unregistered source add no rows.
    prii_export_utils.record_run(
        state, "prpb_desaparecidos", "success", "2026-11-12T09:00:00Z"
    )
    prii_export_utils.record_run(state, "NOT_A_REGISTERED_SOURCE", "success")
    rows = _by_ref(fe.build_source_monitors(NOW, run_state_path=state))
    assert "prpb_desaparecidos" not in rows and "NOT_A_REGISTERED_SOURCE" not in rows

    tiger = rows["TIGER_PR_BOUNDARY"]
    assert (tiger["last_success_at"], tiger["last_success_basis"]) == (
        "2026-11-10T10:00:00Z",
        "RUN_RECEIPT",
    )
    assert (tiger["last_attempt_at"], tiger["last_attempt_status"]) == (
        "2026-11-10T10:00:00Z",
        "success",
    )
    # A failed latest attempt keeps the last success.
    namus = rows["namus"]
    assert (namus["last_success_at"], namus["last_success_basis"]) == (
        "2026-11-09T08:00:00Z",
        "RUN_RECEIPT",
    )
    assert (namus["last_attempt_at"], namus["last_attempt_status"]) == (
        "2026-11-12T08:00:00Z",
        "failure",
    )
    # Attempts that never succeeded record no success time.
    amber = rows["prpb_alertas_amber"]
    assert (amber["last_success_at"], amber["last_success_basis"]) == (
        None,
        "NOT_RECORDED",
    )
    assert amber["last_attempt_status"] == "failure"
    assert rows["USGS_NHD_WATERBODY"]["last_success_basis"] == "NOT_RECORDED"


@pytest.mark.parametrize(
    ("ref", "name", "family", "tier", "cadence", "window", "status"),
    [
        (
            "TIGER_PR_BOUNDARY",
            "U.S. Census Bureau: JURISDICTION_BOUNDARY",
            "JURISDICTION_BOUNDARY",
            "T1",
            "static",
            None,
            "unknown",
        ),
        (
            "USGS_NHD_WATERBODY",
            "U.S. Geological Survey: NHD_WATERBODY_FEATURE",
            "NHD_WATERBODY_FEATURE",
            "T1",
            "event",
            None,
            "unknown",
        ),
        (
            "USGS_INLAND_BATHY_V4",
            "U.S. Geological Survey: USGS_BATHY_SURVEY_FOOTPRINT",
            "USGS_BATHY_SURVEY_FOOTPRINT",
            "T1",
            "event",
            None,
            "unknown",
        ),
        (
            "namus",
            "NIJ — National Institute of Justice / DOJ Office of Justice Programs",
            "missing_persons",
            None,
            "quarterly",
            7776000,
            "active",
        ),
        (
            "namus_unclaimed",
            "NIJ",
            "missing_persons",
            None,
            "quarterly",
            15552000,
            "not_active",
        ),
        (
            "prpb_alertas_amber",
            "Negociado de la Policía de PR (Plan AMBER)",
            "missing_persons",
            None,
            "daily",
            86400,
            "active",
        ),
        (
            "cpi_genero",
            "Centro de Periodismo Investigativo",
            "missing_persons",
            None,
            "monthly",
            2592000,
            "not_active",
        ),
        (
            "ncic_aggregate",
            "FBI Criminal Justice Information Services Division",
            "missing_persons",
            None,
            "yearly",
            31536000,
            "partial",
        ),
        (
            "uscg_d7_sar",
            "US Coast Guard District 7 (PR/USVI)",
            "missing_persons",
            None,
            "yearly",
            31536000,
            "manual",
        ),
        (
            "nmead_disaster",
            "Negociado de Manejo de Emergencias y Administración de Desastres",
            "missing_persons",
            None,
            "static",
            None,
            "not_active",
        ),
    ],
)
def test_declared_fields_match_the_hub_registry_reader(
    tmp_path, ref, name, family, tier, cadence, window, status
):
    # Values as thehub-pr's ADR 0012 reader yields them at 0f62e4b, so the Hub
    # shows the same labels when it reads this producer from the stream instead.
    row = _by_ref(_committed(tmp_path))[ref]
    assert (row["name"], row["producer_family"], row["evidence_tier"]) == (
        name,
        family,
        tier,
    )
    assert (row["cadence"], row["cadence_window_seconds"], row["declared_status"]) == (
        cadence,
        window,
        status,
    )


def test_every_committed_registry_value_is_mapped():
    policies = {r["refresh_policy"].strip().lower() for r in _hydrography()}
    assert policies <= set(fe._REFRESH_POLICY_CADENCE), policies - set(
        fe._REFRESH_POLICY_CADENCE
    )
    statuses = {str(s["status"]).strip().lower() for s in _missing_persons().values()}
    assert statuses <= set(fe._MISSING_PERSONS_STATUS), statuses - set(
        fe._MISSING_PERSONS_STATUS
    )
    tiers = {r["evidence_tier"] for r in _hydrography()}
    assert tiers <= set(fe._MONITOR_TIERS), tiers


def test_vocabulary_mapping():
    assert fe._named("PIN_BY_VINTAGE", fe._REFRESH_POLICY_CADENCE) == "static"
    assert fe._named(None, fe._REFRESH_POLICY_CADENCE) == "unknown"
    assert fe._named("weekly_snapshot", fe._REFRESH_POLICY_CADENCE) == "unknown"
    assert fe._cadence_from_seconds(86400) == "daily"
    assert fe._cadence_from_seconds(90 * 86400) == "quarterly"
    assert fe._cadence_from_seconds(900) == "realtime"
    assert fe._cadence_from_seconds(None) == "unknown"
    assert fe._cadence_from_seconds(0) == "unknown"
    assert fe._monitor_window("daily", "not a number") == 86400
    assert fe._monitor_window("event") is None
    assert fe._monitor_tier(" t2 ") == "T2" and fe._monitor_tier("A") is None


_CSV_HEADER = "source_id,authority,universe,endpoint,refresh_policy,evidence_tier\n"


def _registries(tmp_path: Path, csv_rows: str, yaml_sources: str) -> Path:
    root = tmp_path / "repo"
    (root / "manifests/pr_hydrography").mkdir(parents=True)
    (root / "configs").mkdir()
    (root / fe.SOURCE_MONITOR_REGISTRIES["hydrography"]).write_text(
        _CSV_HEADER + csv_rows
    )
    (root / fe.SOURCE_MONITOR_REGISTRIES["missing_persons"]).write_text(
        "sources:\n" + yaml_sources
    )
    return root


def test_duplicate_ids_across_registries_fail(tmp_path):
    root = _registries(
        tmp_path,
        "namus,Authority,UNIVERSE,https://example.test,PIN_BY_VINTAGE,T1\n",
        "  namus:\n    operator: NIJ\n    federation_eligible: aggregate_only\n",
    )
    with pytest.raises(ValueError, match="duplicate source id 'namus'"):
        fe.build_source_monitors(NOW, repo_root=root)


def test_an_undocumented_federation_eligible_value_fails(tmp_path):
    root = _registries(
        tmp_path, "", "  x:\n    operator: X\n    federation_eligible: maybe\n"
    )
    with pytest.raises(ValueError, match="federation_eligible='maybe'"):
        fe.build_source_monitors(NOW, repo_root=root)


def test_a_registry_without_a_required_column_fails(tmp_path):
    root = _registries(
        tmp_path, "", "  x:\n    operator: X\n    federation_eligible: true\n"
    )
    path = root / fe.SOURCE_MONITOR_REGISTRIES["hydrography"]
    path.write_text("source_id,authority\nA,B\n")
    with pytest.raises(ValueError, match="missing column"):
        fe.build_source_monitors(NOW, repo_root=root)


def test_package_lists_the_stream_and_its_manifest_validates(tmp_path):
    from integration.schema_validation import SchemaValidator

    rows = _committed(tmp_path)
    manifest_path = fe.write_package(
        {"source_monitors": rows}, tmp_path / "pkg", "test", NOW
    )
    manifest = json.loads(manifest_path.read_text())
    [entry] = manifest["files"]
    assert (entry["stream"], entry["filename"]) == (
        "source_monitors",
        "source_monitors.jsonl",
    )
    assert entry["schema_id"] == "federation_source_monitor.schema.json"
    assert entry["record_count"] == len(rows)
    written = tmp_path / "pkg" / entry["filename"]
    assert hashlib.sha256(written.read_bytes()).hexdigest() == entry["sha256"]
    schema = json.loads(
        (REPO / "schemas/federation_export_manifest.schema.json").read_text()
    )
    jsonschema.validate(manifest, schema)
    assert (
        entry["schema_id"].replace(".schema.json", "")
        in SchemaValidator().available_schemas()
    )


def test_the_exporter_writes_the_stream(tmp_path):
    import subprocess

    out = tmp_path / "fed"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/federation_export.py"),
            "--package",
            str(REPO / "exports/samples"),
            "--out",
            str(out),
            "--no-ppp-geometry",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((out / "manifest.json").read_text())
    counts = {f["stream"]: f["record_count"] for f in manifest["files"]}
    assert counts["source_monitors"] == len(_committed(tmp_path))


SHIM = REPO / "scripts" / "prii_export_utils.py"


def _run_with_scripts_first(lines: list[str], *, path: list[str], no_site=False):
    """Run ``lines`` in a fresh interpreter whose sys.path starts with ``path``.

    A fresh interpreter, because which ``prii_export_utils`` this process already
    holds in sys.modules depends on test order (the shim, or the pinned package
    when ``scripts.federation_export`` was imported without scripts/ on sys.path).
    """
    import subprocess

    code = "\n".join(
        [
            "import sys",
            "from pathlib import Path",
            f"sys.path[:0] = {path!r}",
            "import prii_export_utils as shim",
            "here = Path(shim.__file__).resolve()",
            f"assert here == Path({str(SHIM)!r}), here",
            *lines,
        ]
    )
    # -S: no site-packages, so only ``path`` can provide the pinned package.
    argv = [sys.executable, *(["-S"] if no_site else []), "-c", code]
    return subprocess.run(argv, capture_output=True, text=True)


def test_local_helpers_keep_their_ids_and_reach_the_pinned_package():
    # scripts/prii_export_utils.py shadows the pinned package (the exporter runs
    # with scripts/ first on sys.path); its own helpers stay as they were (ids
    # depend on them) and other names come from the package.
    result = _run_with_scripts_first(
        [
            "import hashlib",
            "expected = 'ent_' + hashlib.sha256(b'a|').hexdigest()[:32]",
            "assert shim.fid('ent', 'a', None) == expected",
            "assert shim.norm('Río Grande') == 'rio_grande'",
            "assert callable(shim.source_monitor_row)",
            "assert callable(shim.resolve_last_success)",
            "assert callable(shim.SourceRunState.load)",
            "try:",
            "    shim.no_such_helper",
            "except AttributeError:",
            "    pass",
            "else:",
            "    raise AssertionError('no_such_helper resolved')",
        ],
        path=[str(REPO / "scripts")],
    )
    assert result.returncode == 0, result.stderr


def test_pinned_package_loads_from_an_archive(tmp_path):
    # A frozen build can bundle the pinned package in an archive, where it has no
    # source file on disk, so the shim must import it with the loader its finder
    # returns. A zip on sys.path is the same case: an archive-backed loader.
    import importlib.machinery
    import zipfile

    search = [p for p in sys.path if Path(p or ".").resolve() != SHIM.parent]
    spec = importlib.machinery.PathFinder.find_spec("prii_export_utils", search)
    assert spec is not None and spec.origin, "the pinned package is not installed"
    package = Path(spec.origin).parent
    archive = tmp_path / "pinned.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in sorted(package.glob("*.py")):
            zf.write(path, f"prii_export_utils/{path.name}")
    result = _run_with_scripts_first(
        [
            "assert shim.norm('Río Grande') == 'rio_grande'",
            "row = shim.source_monitor_row",
            "module = row.__module__",
            "assert module == 'prii_export_utils.source_monitor', module",
            "assert sys.modules['prii_export_utils'] is shim",
        ],
        path=[str(REPO / "scripts"), str(archive)],
        no_site=True,
    )
    assert result.returncode == 0, result.stderr
