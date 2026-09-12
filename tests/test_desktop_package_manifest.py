from pathlib import Path


def test_desktop_bundle_includes_spatial_registries() -> None:
    spec = Path("desktop/pyinstaller.spec").read_text(encoding="utf-8")

    assert '"spatial_boundaries.yaml"' in spec
    assert '"spatial_layer_bindings.yaml"' in spec
