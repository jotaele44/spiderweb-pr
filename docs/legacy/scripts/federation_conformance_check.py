#!/usr/bin/env python3
"""Live cross-repo conformance check for the moneysweep-pr financial handoff.

When the moneysweep-pr repo is available locally, this builds a real export
package with *its* producer (``scripts/build_export_package.py``) and ingests it
through *this* repo's consumer (adapter + production gate + contract-finance
layer). A green run proves the producer and consumer agree on the v1.2.0 on-wire
contract — the guarantee that the committed conformance fixtures encode.

In separate-repo CI (where moneysweep-pr is not checked out) it skips
gracefully with exit code 0; the committed ``tests/fixtures/moneysweep_v1_2``
fixture + ``tests/test_moneysweep_conformance.py`` cover the consumer side.

Usage::

    python scripts/federation_conformance_check.py [--moneysweep-pr PATH]
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from federation.hub.adapters.moneysweep import (  # noqa: E402
    EXPECTED_VERSION,
    export_moneysweep_features,
)
from readiness.contract_finance_layer import build_contract_finance_layer  # noqa: E402
from readiness.moneysweep_package_gate import assess_moneysweep_package  # noqa: E402

DEFAULT_CS_PATHS = (
    REPO_ROOT.parent / "moneysweep-pr",
    REPO_ROOT.parent / "moneysweep-pr",
)


def _find_moneysweep(explicit: str | None) -> Path | None:
    candidates = [Path(explicit)] if explicit else list(DEFAULT_CS_PATHS)
    for cand in candidates:
        if (cand / "scripts" / "build_export_package.py").is_file():
            return cand
    return None


def _load_producer_builder(cs_root: Path):
    spec = importlib.util.spec_from_file_location(
        "_cs_build_export_package", cs_root / "scripts" / "build_export_package.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--moneysweep-pr", default=None, help="path to the moneysweep-pr repo")
    args = parser.parse_args(argv)

    cs_root = _find_moneysweep(args.moneysweep)
    if cs_root is None:
        print("[SKIP] moneysweep-pr repo not found locally; "
              "consumer-side conformance is covered by tests/test_moneysweep_conformance.py")
        return 0

    builder = _load_producer_builder(cs_root)
    if builder.EXPORT_CONTRACT_VERSION != EXPECTED_VERSION:
        print(f"[FAIL] producer EXPORT_CONTRACT_VERSION={builder.EXPORT_CONTRACT_VERSION!r} "
              f"!= consumer EXPECTED_VERSION={EXPECTED_VERSION!r}")
        return 1

    # Prefer the producer's non-synthetic conformance package so the production
    # gate is exercised; fall back to the synthetic samples in test mode.
    conformance_src = cs_root / "exports" / "conformance" / "v1_2"
    if conformance_src.is_dir():
        build_input, build_mode = conformance_src, "production"
    else:
        build_input, build_mode = cs_root / "exports" / "samples", "test"

    with tempfile.TemporaryDirectory(prefix="fed_conformance_") as tmp:
        pkg = Path(tmp) / "package"
        adapter_out = Path(tmp) / "adapter"
        layer_out = Path(tmp) / "layer"
        # Build a real package with the producer's own build script.
        builder.build_package(input_dir=build_input, output_dir=pkg, mode=build_mode)

        export_moneysweep_features(pkg, adapter_out, mode=build_mode)
        layer = build_contract_finance_layer(adapter_out, layer_out)
        gate = assess_moneysweep_package(pkg) if build_mode == "production" else None

    if (gate is not None and gate["status"] == "NOT_READY") or layer["status"] != "READY":
        gate_status = gate["status"] if gate else "skipped(test-mode)"
        blockers = gate.get("blockers") if gate else None
        print(f"[FAIL] gate={gate_status} layer={layer['status']} blockers={blockers}")
        return 1

    gate_status = gate["status"] if gate else "skipped(test-mode)"
    print(f"[OK] live round-trip green: producer={cs_root.name} version={EXPECTED_VERSION} "
          f"mode={build_mode} gate={gate_status} layer={layer['status']} "
          f"records={layer['record_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
