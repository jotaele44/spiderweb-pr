"""One-time setup for the spiderweb-pr desktop wrapper (stdlib only).

Creates a private .venv with the small server dependencies and builds the Vite
single-page app under server/frontend, which the wrapper then serves from the
same origin as the backend. The build needs Node/npm: an installed copy is used
when one can be found, otherwise a private copy is downloaded into .node/.

Usage:
  python desktop/setup.py            run setup (skips when already complete)
  python desktop/setup.py --ensure   quiet fast-path used by the launchers
  python desktop/setup.py --force    redo setup from scratch
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import venv
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.config import (  # noqa: E402
    DIST_DIR,
    EXTRA_BUILD_ENV,
    FRONTEND_DIR,
    REPO_ROOT,
)

VENV_DIR = REPO_ROOT / ".venv"
MARKER = Path(__file__).resolve().parent / ".setup-complete"
MIN_PYTHON = (3, 11)

REQUIREMENTS = REPO_ROOT / "requirements-desktop.txt"
CONSTRAINTS_DESKTOP = REPO_ROOT / "constraints-desktop.txt"

# Private Node.js, used only when no installed npm can be found.
NODE_DIR = REPO_ROOT / ".node"
NODE_DIST = "https://nodejs.org/dist/latest-v22.x"

_GIT_REQUIREMENT = re.compile(
    r"git\+(https://github\.com/[^/\s]+/[^/\s@]+?)(?:\.git)?@([0-9a-f]{40})(?=#|\s|$)"
)


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    what: str | None = None,
) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    try:
        subprocess.run(cmd, cwd=cwd, check=True, env=env)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Setup stopped: {what or cmd[0]} failed (exit {exc.returncode}). "
            "The lines above show why; an internet connection is needed the first time."
        ) from None


def is_complete() -> bool:
    return (
        MARKER.exists()
        and venv_python().exists()
        and (DIST_DIR / "index.html").is_file()
    )


# ── Python environment ───────────────────────────────────────────────────────


def venv_is_usable() -> bool:
    """True when .venv has an interpreter that runs and is new enough."""
    if not venv_python().exists():
        return False
    check = (
        f"import sys; raise SystemExit(0 if sys.version_info >= {MIN_PYTHON!r} else 1)"
    )
    try:
        return (
            subprocess.run(
                [str(venv_python()), "-c", check], capture_output=True, timeout=60
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def git_is_usable() -> bool:
    if not shutil.which("git"):
        return False
    if sys.platform == "darwin":
        # /usr/bin/git is a stub that pops an "install developer tools" dialog
        # until the Xcode command line tools are installed.
        try:
            return (
                subprocess.run(
                    ["xcode-select", "-p"], capture_output=True, timeout=30
                ).returncode
                == 0
            )
        except (OSError, subprocess.SubprocessError):
            return False
    return True


def without_git(requirements_text: str) -> str:
    """Rewrite pinned GitHub git requirements to the same commit's archive URL."""
    return _GIT_REQUIREMENT.sub(r"\1/archive/\2.zip", requirements_text)


def setup_python() -> None:
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(
            f"Setup stopped: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required, "
            f"found {sys.version.split()[0]}."
        )
    if not venv_is_usable():
        print(f"Creating virtual environment at {VENV_DIR} …", flush=True)
        venv.EnvBuilder(with_pip=True, clear=True).create(VENV_DIR)
    run(
        [str(venv_python()), "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
        what="upgrading pip",
    )
    constraints = (
        ["-c", str(CONSTRAINTS_DESKTOP)] if CONSTRAINTS_DESKTOP.is_file() else []
    )
    requirements = REQUIREMENTS
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if not git_is_usable():
        print("git is not available; installing from the pinned source archive.")
        temp_dir = tempfile.TemporaryDirectory(prefix="prii-desktop-req-")
        requirements = Path(temp_dir.name) / REQUIREMENTS.name
        requirements.write_text(
            without_git(REQUIREMENTS.read_text(encoding="utf-8")), encoding="utf-8"
        )
    try:
        run(
            [
                str(venv_python()),
                "-m",
                "pip",
                "install",
                "--quiet",
                "-r",
                str(requirements),
            ]
            + constraints,
            what="installing the Python dependencies",
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


# ── Node.js ──────────────────────────────────────────────────────────────────


def npm_command() -> str:
    """npm is a .cmd shim on Windows, which subprocess needs spelled out."""
    return "npm.cmd" if os.name == "nt" else "npm"


def _version_key(name: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", name))


def candidate_node_dirs(home: Path | None = None) -> list[Path]:
    """Places Node version managers and installers put npm, best first.

    Apps started from Finder get a minimal PATH, so an npm that works in the
    user's shell is often not on PATH here.
    """
    home = home or Path.home()
    dirs: list[Path] = []
    for root, pattern in (
        (home / ".nvm" / "versions" / "node", "*/bin"),
        (home / ".local" / "share" / "fnm" / "node-versions", "*/installation/bin"),
        (
            home / "Library" / "Application Support" / "fnm" / "node-versions",
            "*/installation/bin",
        ),
        (home / ".asdf" / "installs" / "nodejs", "*/bin"),
    ):
        if root.is_dir():
            # Newest installed version first.
            dirs.extend(
                sorted(
                    root.glob(pattern),
                    key=lambda p, root=root: _version_key(p.relative_to(root).parts[0]),
                    reverse=True,
                )
            )
    dirs += [
        home / ".volta" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ]
    return dirs


def private_node_bin() -> Path:
    return NODE_DIR if os.name == "nt" else NODE_DIR / "bin"


def node_archive_name(
    version: str, system: str | None = None, machine: str | None = None
) -> str:
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        machine
    )
    os_name = {"darwin": "darwin", "linux": "linux", "windows": "win"}.get(system)
    if not arch or not os_name:
        raise SystemExit(
            f"Setup stopped: no Node.js download is available for {system}/{machine}. "
            "Install Node 22+ and open the app again."
        )
    ext = "zip" if os_name == "win" else "tar.gz"
    return f"node-{version}-{os_name}-{arch}.{ext}"


def _download(url: str, dest: Path) -> None:
    """Fetch url to dest. Falls back to curl when Python has no CA certificates
    (a stock python.org install on macOS until its certificate step is run)."""
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            with dest.open("wb") as out:
                shutil.copyfileobj(response, out)
        return
    except (urllib.error.URLError, ssl.SSLError, OSError) as exc:
        curl = shutil.which("curl")
        if not curl:
            raise SystemExit(
                f"Setup stopped: could not download {url} ({exc}). "
                "Check the internet connection."
            ) from None
    result = subprocess.run(
        [curl, "--fail", "--location", "--silent", "--show-error", "-o", str(dest), url]
    )
    if result.returncode != 0:
        raise SystemExit(
            f"Setup stopped: could not download {url}. Check the internet connection."
        )


def install_private_node() -> Path:
    """Download the current Node 22 release into .node/ and return its bin dir."""
    print(
        "Node.js was not found; downloading a private copy (about 50 MB) …", flush=True
    )
    with tempfile.TemporaryDirectory(prefix="prii-node-") as tmp:
        tmp_dir = Path(tmp)
        sums = tmp_dir / "SHASUMS256.txt"
        _download(f"{NODE_DIST}/SHASUMS256.txt", sums)
        checksums = {
            name: digest
            for digest, name in (
                line.split() for line in sums.read_text().splitlines() if line.strip()
            )
        }
        version = next(
            (m.group(1) for n in checksums if (m := re.match(r"node-(v[\d.]+)-", n))),
            None,
        )
        if version is None:
            raise SystemExit("Setup stopped: the Node.js release list was unreadable.")
        name = node_archive_name(version)
        if name not in checksums:
            raise SystemExit(f"Setup stopped: Node.js release {name} was not listed.")
        archive = tmp_dir / name
        _download(f"{NODE_DIST}/{name}", archive)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != checksums[name]:
            raise SystemExit(
                f"Setup stopped: the Node.js download {name} failed its checksum."
            )
        unpacked = tmp_dir / "unpacked"
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(unpacked)
        else:
            with tarfile.open(archive) as tf:
                # The archive's checksum was verified above. `filter` exists
                # from Python 3.11.4; earlier 3.11 releases take no argument.
                if hasattr(tarfile, "tar_filter"):
                    tf.extractall(unpacked, filter="tar")
                else:
                    tf.extractall(unpacked)
        shutil.rmtree(NODE_DIR, ignore_errors=True)
        shutil.move(str(next(unpacked.iterdir())), str(NODE_DIR))
    return private_node_bin()


def resolve_npm() -> tuple[str, Path | None]:
    """Return (npm executable, directory to prepend to PATH or None)."""
    npm = npm_command()
    found = shutil.which(npm)
    if found:
        return found, None
    for directory in [*candidate_node_dirs(), private_node_bin()]:
        found = shutil.which(npm, path=str(directory))
        if found and shutil.which("node", path=str(directory)):
            return found, directory
    bin_dir = install_private_node()
    found = shutil.which(npm, path=str(bin_dir))
    if not found:
        raise SystemExit("Setup stopped: the downloaded Node.js has no npm.")
    return found, bin_dir


def build_frontend() -> None:
    """Install and build the SPA that the wrapper serves."""
    npm, bin_dir = resolve_npm()
    env = dict(os.environ)
    if bin_dir is not None:
        # npm is a `#!/usr/bin/env node` script, so node must be on PATH too.
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    lock = FRONTEND_DIR / "package-lock.json"
    run(
        [npm, "ci" if lock.exists() else "install", "--no-audit", "--no-fund"],
        cwd=FRONTEND_DIR,
        env=env,
        what="installing the dashboard's packages",
    )
    # Blank the API base so the bundle talks to whichever port the wrapper binds.
    run(
        [npm, "run", "build"],
        cwd=FRONTEND_DIR,
        env={**env, **EXTRA_BUILD_ENV},
        what="building the dashboard",
    )


def main() -> None:
    args = set(sys.argv[1:])
    if "--force" in args:
        MARKER.unlink(missing_ok=True)
    if is_complete():
        if "--ensure" not in args:
            print("Setup already complete (use --force to redo).")
        return
    setup_python()
    build_frontend()
    MARKER.write_text("ok\n", encoding="utf-8")
    print("Desktop setup complete.")


if __name__ == "__main__":
    main()
