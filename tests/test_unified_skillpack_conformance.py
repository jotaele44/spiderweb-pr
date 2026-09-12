from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_unified_skillpacks", ROOT / "tools" / "validate_unified_skillpacks.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class UnifiedSkillpackConformanceTests(unittest.TestCase):
    def test_full_conformance(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "success", result["errors"])

    def test_change_scope_can_use_current_integration_base(self) -> None:
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        result = MODULE.validate(ROOT, enforce_change_scope=True, change_base=head)
        self.assertEqual(result["status"], "success", result["errors"])
        self.assertIn("change_base_ancestry", result["checks"])

    def test_change_scope_rejects_forbidden_path(self) -> None:
        def fake_run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
            stdout = ""
            if args == ("rev-parse", "--is-shallow-repository"):
                stdout = "false\n"
            elif args[:2] == ("diff", "--name-only"):
                stdout = "src/outside_scope.py\n"
            return subprocess.CompletedProcess(args, 0, stdout, "")

        with patch.object(MODULE, "run_git", side_effect=fake_run_git):
            result = MODULE.validate(
                ROOT,
                enforce_change_scope=True,
                change_base="0" * 40,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            result["errors"],
            ["out-of-scope change: src/outside_scope.py"],
        )

    def test_dispatch_metadata_is_complete(self) -> None:
        manifest = json.loads((ROOT / ".claude/skillpacks/MANIFEST.json").read_text())
        for capability in manifest["capabilities"]:
            self.assertTrue(capability.get("status"), capability["id"])
            self.assertTrue(
                capability.get("preserved_responsibility"), capability["id"]
            )
            self.assertTrue(capability.get("anchor"), capability["id"])

    def test_compatibility_targets_resolve(self) -> None:
        ledger = json.loads(
            (ROOT / ".claude/skillpacks/LEGACY_COMPATIBILITY.json").read_text()
        )
        skill = (ROOT / ".claude/skillpacks/SKILL.md").read_text()
        for entry in ledger["entries"]:
            target = entry["unified_target"].split("#", 1)[1]
            self.assertIn(f'<a id="{target}"></a>', skill, entry["capability_id"])

    def test_spatial_architecture_allowlist_is_exact(self) -> None:
        manifest = json.loads((ROOT / ".claude/skillpacks/MANIFEST.json").read_text())
        allowed = manifest["allowed_change_paths"]
        intended = {
            ".github/workflows/federation-spatial-reference-freeze.yml",
            "docs/FEDERATION_SPATIAL_ARCHITECTURE_V1.md",
            "federation/spatial_service_v1_1.py",
            "registry/spatial/federation_spatial_identity_v1_1.json",
            "registry/spatial/reference_source_candidates_v1_1.json",
            "schemas/federation_spatial_identity_v1_1.schema.json",
            "schemas/federation_spatial_migration_receipt_v1_1.schema.json",
            "scripts/freeze_federation_reference_v1_1.py",
            "scripts/validate_federation_spatial_identity_v1_1.py",
            "scripts/validate_federation_spatial_migration_receipt_v1_1.py",
            "tests/test_federation_spatial_identity_v1_1.py",
            "tests/test_federation_spatial_migration_receipt_v1_1.py",
            "tests/test_federation_spatial_service_v1_1.py",
            "tests/test_freeze_federation_reference_v1_1.py",
        }
        self.assertTrue(intended.issubset(allowed))
        for near_miss in (
            ".github/workflows/federation-spatial-reference-freeze.yml.bak",
            "docs/FEDERATION_SPATIAL_ARCHITECTURE_V1.md/extra",
            "federation/spatial_service_v1_1.pyc",
            "registry/spatial/federation_spatial_identity_v1_1.json.bak",
            "schemas/federation_spatial_identity_v1_1.schema.json/extra",
            "scripts/freeze_federation_reference_v1_1.pyc",
            "tests/test_freeze_federation_reference_v1_1.py.bak",
        ):
            self.assertFalse(MODULE.is_allowed_path(near_miss, allowed), near_miss)


if __name__ == "__main__":
    unittest.main()
