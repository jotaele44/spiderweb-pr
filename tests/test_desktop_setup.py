"""First-run setup must finish without asking the user to run anything."""

from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
import tarfile
import tomllib
from pathlib import Path

import pytest

from desktop import setup

REPO_ROOT = Path(__file__).resolve().parents[1]
APP = REPO_ROOT / "PRII-SPIDERWEB.app" / "Contents"
APP_LAUNCHER = APP / "MacOS" / "PRII-SPIDERWEB"
APP_SETUP = APP / "Resources" / "first-run-setup.command"
SHELL_LAUNCHERS = [
    APP_LAUNCHER,
    APP_SETUP,
    REPO_ROOT / "PRII-SPIDERWEB.command",
    REPO_ROOT / "PRII-SPIDERWEB.sh",
]


def test_min_python_matches_project_floor():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]
    floor = re.search(r">=\s*(\d+)\.(\d+)", project["requires-python"])
    assert setup.MIN_PYTHON == (int(floor.group(1)), int(floor.group(2)))


@pytest.mark.parametrize("script", SHELL_LAUNCHERS, ids=lambda p: p.name)
def test_shell_launchers_parse_and_are_executable(script):
    shell = "sh" if script.suffix == ".sh" else "bash"
    assert subprocess.run([shell, "-n", str(script)]).returncode == 0
    assert os.access(script, os.X_OK)


def test_app_launcher_runs_setup_itself():
    text = APP_LAUNCHER.read_text()
    # It must hand over to the setup window, never tell the user to run setup.
    assert 'open -a Terminal "$SETUP"' in text
    assert "python3 desktop/setup.py" not in text
    assert "Open Terminal" not in text
    assert "desktop/setup.py" in APP_SETUP.read_text()


@pytest.mark.parametrize("script", SHELL_LAUNCHERS[1:], ids=lambda p: p.name)
def test_launchers_pick_a_python_that_meets_the_floor(script):
    text = script.read_text()
    major, minor = setup.MIN_PYTHON
    assert f"sys.version_info < ({major}, {minor})" in text


def test_git_requirement_becomes_archive_url():
    rewritten = setup.without_git(setup.REQUIREMENTS.read_text())
    assert "git+" not in rewritten
    line = next(ln for ln in rewritten.splitlines() if ln.startswith("prii-desktop"))
    assert re.fullmatch(
        r"prii-desktop @ https://github\.com/jotaele44/thehub-pr/archive/"
        r"[0-9a-f]{40}\.zip#subdirectory=packages/prii_desktop",
        line,
    )
    # Everything else is left exactly as written.
    original = setup.REQUIREMENTS.read_text().splitlines()
    assert [a for a, b in zip(original, rewritten.splitlines()) if a != b] == [
        ln for ln in original if ln.startswith("prii-desktop")
    ]


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Darwin", "arm64", "node-v22.1.0-darwin-arm64.tar.gz"),
        ("Darwin", "x86_64", "node-v22.1.0-darwin-x64.tar.gz"),
        ("Linux", "aarch64", "node-v22.1.0-linux-arm64.tar.gz"),
        ("Windows", "AMD64", "node-v22.1.0-win-x64.zip"),
    ],
)
def test_node_archive_name(system, machine, expected):
    assert setup.node_archive_name("v22.1.0", system, machine) == expected


def test_node_archive_name_rejects_unknown_platform():
    with pytest.raises(SystemExit):
        setup.node_archive_name("v22.1.0", "SunOS", "sparc")


def _fake_node(tmp_path: Path, name: str = "npm") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    for exe in (name, "node"):
        path = tmp_path / exe
        path.write_text("#!/bin/sh\n")
        path.chmod(0o755)
    return tmp_path


@pytest.mark.skipif(os.name == "nt", reason="POSIX executables")
def test_resolve_npm_prefers_path_then_version_managers(tmp_path, monkeypatch):
    on_path = _fake_node(tmp_path / "onpath")
    home = tmp_path / "home"
    old = _fake_node(home / ".nvm" / "versions" / "node" / "v9.11.0" / "bin")
    new = _fake_node(home / ".nvm" / "versions" / "node" / "v22.3.0" / "bin")
    dirs = [d for d in setup.candidate_node_dirs(home) if home in d.parents]
    assert dirs[:2] == [new, old]  # newest version first, not lexical order

    monkeypatch.setattr(setup, "candidate_node_dirs", lambda: dirs)
    monkeypatch.setattr(
        setup, "install_private_node", lambda: pytest.fail("downloaded")
    )

    monkeypatch.setenv("PATH", str(on_path))
    assert setup.resolve_npm() == (str(on_path / "npm"), None)

    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert setup.resolve_npm() == (str(new / "npm"), new)


@pytest.mark.skipif(os.name == "nt", reason="POSIX executables")
def test_resolve_npm_downloads_when_nothing_is_installed(tmp_path, monkeypatch):
    private = tmp_path / ".node" / "bin"
    monkeypatch.setattr(setup, "NODE_DIR", tmp_path / ".node")
    monkeypatch.setattr(setup, "candidate_node_dirs", lambda: [])
    monkeypatch.setattr(setup, "install_private_node", lambda: _fake_node(private))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert setup.resolve_npm() == (str(private / "npm"), private)


def _node_tarball(version: str) -> tuple[str, bytes]:
    name = setup.node_archive_name(version, "Linux", "x86_64")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for member in ("bin/node", "bin/npm"):
            info = tarfile.TarInfo(f"{name.removesuffix('.tar.gz')}/{member}")
            info.mode = 0o755
            data = b"#!/bin/sh\n"
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return name, buffer.getvalue()


@pytest.mark.skipif(os.name == "nt", reason="POSIX layout")
@pytest.mark.parametrize("tampered", [False, True])
def test_private_node_is_checksum_verified(tmp_path, monkeypatch, tampered):
    name, payload = _node_tarball("v22.9.9")
    digest = hashlib.sha256(payload).hexdigest()
    served = payload + b"x" if tampered else payload

    def fake_download(url: str, dest: Path) -> None:
        if url.endswith("SHASUMS256.txt"):
            dest.write_text(f"{digest}  {name}\n")
        else:
            assert url.endswith(name)
            dest.write_bytes(served)

    monkeypatch.setattr(setup, "_download", fake_download)
    monkeypatch.setattr(setup, "NODE_DIR", tmp_path / ".node")
    monkeypatch.setattr(setup, "node_archive_name", lambda version: name)

    if tampered:
        with pytest.raises(SystemExit, match="checksum"):
            setup.install_private_node()
        assert not (tmp_path / ".node").exists()
    else:
        assert setup.install_private_node() == tmp_path / ".node" / "bin"
        assert (tmp_path / ".node" / "bin" / "npm").is_file()


def test_desktop_constraints_agree_with_the_lockfile():
    """A pin that drifts from uv.lock can make first-run `pip install` unsolvable.

    That happened: pydantic-core was pinned to a version the pinned pydantic
    rejects, so setup failed on every machine.
    """
    versions: dict[str, set[str]] = {}
    for package in tomllib.loads((REPO_ROOT / "uv.lock").read_text())["package"]:
        if "version" in package:
            name = package["name"].lower().replace("_", "-")
            versions.setdefault(name, set()).add(package["version"])
    drifted = []
    for line in setup.CONSTRAINTS_DESKTOP.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==")
        locked = versions.get(name.lower().replace("_", "-"))
        if locked and version not in locked:
            drifted.append(f"{line} (uv.lock: {', '.join(sorted(locked))})")
    assert not drifted, "constraints-desktop.txt disagrees with uv.lock:\n" + "\n".join(
        drifted
    )


@pytest.mark.parametrize(
    ("name", "linkname"),
    [("../escape", None), ("/abs/escape", None), ("pkg/link", "../../outside")],
)
def test_tar_extraction_refuses_entries_outside_the_target(tmp_path, name, linkname):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo(name)
        if linkname:
            info.type = tarfile.SYMTYPE
            info.linkname = linkname
            tf.addfile(info)
        else:
            info.size = 1
            tf.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(SystemExit, match="unsafe"):
        setup._extract_tar(archive, tmp_path / "out")
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "outside").exists()
