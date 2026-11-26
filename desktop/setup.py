# Rendered from thehub-pr/federation-templates/desktop/setup.py.
# Edit the template there and re-render (tools/render_federation_templates.py);
# do not hand-edit this file — template-drift.yml fails the build if you do.
"""Set up and start this PRII desktop app (stdlib only).

Every launcher (the .app, .command, .sh and .bat) finds a Python and runs this
file; everything else lives here so it is written, tested and fixed once.

What it does:
  * creates a private .venv and installs the app's Python requirements;
  * finds Node.js, or downloads a private copy into .node/, and builds the
    dashboard;
  * starts the app, and reinstalls once if a set-up app fails to start;
  * notices when the requirements changed since the last setup and redoes it.

Per-app values come from desktop/config.py. Per-user choices come from a
launcher.json preferences file (see `--help` for its location).

Usage:
  python desktop/setup.py              set up if needed (does not start the app)
  python desktop/setup.py --launch     set up if needed, then start the app
  python desktop/setup.py --help       every option
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
import venv
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop import config  # noqa: E402

TEMPLATE_VERSION = 2

REPO_ROOT: Path = config.REPO_ROOT
VENV_DIR = REPO_ROOT / ".venv"
NODE_DIR = REPO_ROOT / ".node"
MARKER = Path(__file__).resolve().parent / ".setup-complete"
CONSTRAINTS = REPO_ROOT / "constraints-desktop.txt"

# Exit status that tells a windowless launcher (the macOS .app) "this needs a
# person to watch it": setup is required, or the app failed to start.
EXIT_NEEDS_TERMINAL = 75
# A start that survives this long was a working start, not an install problem.
STARTED_AFTER_SECONDS = 120

LANGUAGES = ("en", "es")
PREFERENCE_KEYS = ("language", "window", "data_home", "check_on_start")


# ── Per-app settings (desktop/config.py; every one optional) ─────────────────


def setting(name: str, default):
    return getattr(config, name, default)


APP_TITLE: str = setting("APP_TITLE", REPO_ROOT.name)
APP_KEY: str = re.sub(r"[^a-z0-9]+", "-", str(setting("APP_ID", REPO_ROOT.name)).lower())
MIN_PYTHON: tuple[int, int] = tuple(setting("MIN_PYTHON", (3, 10)))[:2]
NODE_MAJOR: int = int(setting("NODE_MAJOR", 22))
BUILD_FRONTEND: bool = bool(setting("BUILD_FRONTEND", True))
FRONTEND_DIR: Path | None = setting("FRONTEND_DIR", None)
DIST_DIR: Path | None = setting("DIST_DIR", None)
SETUP_VERSION = setting("SETUP_VERSION", 1)


def requirement_files() -> list[Path]:
    files = setting("REQUIREMENT_FILES", None)
    if files is None:
        files = [REPO_ROOT / "requirements-desktop.txt"]
    return [Path(f) for f in files]


# ── Messages ─────────────────────────────────────────────────────────────────

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "title": "{app} — setup",
        "intro": "This needs an internet connection and takes a few minutes.",
        "repairing": "{app} did not start. Reinstalling its components.",
        "last_report": "What the failed start reported:",
        "step": "Step {n} of {total} — {name}",
        "step.python": "Preparing the Python environment",
        "step.components": "Installing components",
        "step.node": "Getting Node.js",
        "step.dashboard": "Building the dashboard",
        "step.finish": "Finishing",
        "ok": "done",
        "failed": "failed",
        "setup_done": "Setup finished.",
        "starting": "Starting {app}…",
        "keep_open": "Keep this window open while you use {app}.",
        "opening": "Opening {app}…",
        "already": "Setup is already complete.",
        "still_failing": "{app} still did not start. The lines above are the error it reported.",
        "log_at": "A full record is saved at: {path}",
        "retry": "Press Return to try again (or close this window to stop)… ",
        "cause": "Cause: {text}",
        "details": "Last lines of the output:",
        "need_python": "Python {need}+ is required; this is Python {have}.",
        "open_python": "Opening the Python download page — run the installer it offers, then start the app again.",
        "node_download": "Node.js {major}+ was not found; downloading a private copy (about 50 MB).",
        "no_git": "git is not available; installing from the pinned source archive.",
        "offline_incomplete": "Offline mode: setup is not complete and needs the internet once. Start again without offline mode.",
        "offline_stale": "Offline mode: the components are out of date but will be used as they are.",
        "prefs_bad": "Ignoring the preferences file (it is not valid JSON): {path}",
        "prefs_value": "Ignoring preference {key!r}: {value!r} is not allowed.",
        "reset": "Removing the installed components.",
        "err.step": "{what} did not complete (exit {code}). An internet connection is needed the first time.",
        "err.download": "Could not download {url}. Check the internet connection.",
        "err.checksum": "The Node.js download {name} failed its integrity check.",
        "err.platform": "No Node.js download exists for {system}/{machine}. Install Node {major}+ and start the app again.",
        "err.node_list": "The Node.js release list could not be read.",
        "err.archive": "The Node.js archive contains an unexpected entry: {name}",
        "err.no_dist": "The dashboard build did not produce {path}.",
        "err.no_frontend": "This app's configuration names no dashboard folder (FRONTEND_DIR / DIST_DIR).",
        "help.description": "Set up and start {app}.",
        "help.launch": "start the app after making sure it is set up",
        "help.ensure": "set up only if needed, quietly (default without --launch)",
        "help.reinstall": "reinstall the components and rebuild the dashboard",
        "help.reset": "delete the installed components first, then set up again",
        "help.browser": "open in the default browser instead of the app window",
        "help.no_window": "run the server only; print its address",
        "help.verbose": "show the full output of every step",
        "help.offline": "never use the network; start with what is installed",
        "help.lang": "language of these messages",
        "help.version": "print version information and exit",
        "help.epilog": "Preferences file: {prefs}\nKeys: language (en|es), window (native|browser), data_home (folder), check_on_start (true|false).\nEnvironment: PRII_LANG, PRII_OFFLINE=1.\nAny other option is passed on to the app.",
    },
    "es": {
        "title": "{app} — instalación",
        "intro": "Requiere conexión a internet y tarda unos minutos.",
        "repairing": "{app} no pudo iniciar. Reinstalando sus componentes.",
        "last_report": "Lo que informó el inicio fallido:",
        "step": "Paso {n} de {total} — {name}",
        "step.python": "Preparando el entorno de Python",
        "step.components": "Instalando componentes",
        "step.node": "Obteniendo Node.js",
        "step.dashboard": "Construyendo el panel",
        "step.finish": "Finalizando",
        "ok": "listo",
        "failed": "falló",
        "setup_done": "Instalación terminada.",
        "starting": "Iniciando {app}…",
        "keep_open": "Mantenga esta ventana abierta mientras usa {app}.",
        "opening": "Abriendo {app}…",
        "already": "La instalación ya está completa.",
        "still_failing": "{app} sigue sin iniciar. Las líneas anteriores son el error que informó.",
        "log_at": "El registro completo está en: {path}",
        "retry": "Presione Retorno para intentar de nuevo (o cierre esta ventana para detener)… ",
        "cause": "Causa: {text}",
        "details": "Últimas líneas de la salida:",
        "need_python": "Se requiere Python {need}+; este es Python {have}.",
        "open_python": "Abriendo la página de descarga de Python — ejecute el instalador que ofrece y vuelva a iniciar la aplicación.",
        "node_download": "No se encontró Node.js {major}+; descargando una copia privada (unos 50 MB).",
        "no_git": "git no está disponible; instalando desde el archivo de código fijado.",
        "offline_incomplete": "Modo sin conexión: la instalación no está completa y necesita internet una vez. Inicie de nuevo sin el modo sin conexión.",
        "offline_stale": "Modo sin conexión: los componentes están desactualizados pero se usarán tal como están.",
        "prefs_bad": "Se ignora el archivo de preferencias (no es JSON válido): {path}",
        "prefs_value": "Se ignora la preferencia {key!r}: {value!r} no está permitido.",
        "reset": "Eliminando los componentes instalados.",
        "err.step": "{what} no se completó (código {code}). La primera vez se necesita conexión a internet.",
        "err.download": "No se pudo descargar {url}. Revise la conexión a internet.",
        "err.checksum": "La descarga de Node.js {name} no pasó la verificación de integridad.",
        "err.platform": "No existe descarga de Node.js para {system}/{machine}. Instale Node {major}+ y vuelva a iniciar la aplicación.",
        "err.node_list": "No se pudo leer la lista de versiones de Node.js.",
        "err.archive": "El archivo de Node.js contiene una entrada inesperada: {name}",
        "err.no_dist": "La construcción del panel no produjo {path}.",
        "err.no_frontend": "La configuración de esta aplicación no indica la carpeta del panel (FRONTEND_DIR / DIST_DIR).",
        "help.description": "Instala e inicia {app}.",
        "help.launch": "inicia la aplicación tras comprobar que está instalada",
        "help.ensure": "instala solo si hace falta, sin mensajes (predeterminado sin --launch)",
        "help.reinstall": "reinstala los componentes y reconstruye el panel",
        "help.reset": "elimina primero los componentes instalados y vuelve a instalar",
        "help.browser": "abre en el navegador predeterminado en vez de la ventana de la aplicación",
        "help.no_window": "ejecuta solo el servidor; muestra su dirección",
        "help.verbose": "muestra la salida completa de cada paso",
        "help.offline": "nunca usa la red; inicia con lo que está instalado",
        "help.lang": "idioma de estos mensajes",
        "help.version": "muestra la versión y termina",
        "help.epilog": "Archivo de preferencias: {prefs}\nClaves: language (en|es), window (native|browser), data_home (carpeta), check_on_start (true|false).\nEntorno: PRII_LANG, PRII_OFFLINE=1.\nCualquier otra opción se pasa a la aplicación.",
    },
}

_lang = "en"


def t(key: str, /, **values) -> str:
    text = MESSAGES[_lang].get(key) or MESSAGES["en"][key]
    return text.format(app=APP_TITLE, **values)


class SetupError(Exception):
    """A step failed; str() is the sentence to show the person."""


class PythonTooOld(SetupError):
    """Retrying cannot help: a newer Python has to be installed first."""


# ── Places on disk ───────────────────────────────────────────────────────────


def log_dir() -> Path:
    override = os.environ.get("PRII_LOG_DIR", "").strip()
    if override:
        base = Path(override)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Logs" / "PRII" / APP_KEY
    elif os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        base = Path(local) / "PRII" / APP_KEY / "Logs"
    else:
        state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
        base = Path(state) / "prii" / APP_KEY
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        base = Path(tempfile.gettempdir())
    return base


def prefs_path() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "PRII" / APP_KEY
    elif os.name == "nt":
        roaming = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        base = Path(roaming) / "PRII" / APP_KEY
    else:
        cfg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        base = Path(cfg) / "prii" / APP_KEY
    return base / "launcher.json"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


# ── Preferences and language ─────────────────────────────────────────────────


def load_preferences(warn=print) -> dict:
    """Read launcher.json. Unknown keys are ignored; bad values are reported
    and dropped, so a typo never stops the app from starting."""
    path = prefs_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        warn(t("prefs_bad", path=path))
        return {}
    if not isinstance(raw, dict):
        warn(t("prefs_bad", path=path))
        return {}
    allowed = {
        "language": lambda v: v in LANGUAGES,
        "window": lambda v: v in ("native", "browser"),
        "data_home": lambda v: isinstance(v, str) and bool(v.strip()),
        "check_on_start": lambda v: isinstance(v, bool),
    }
    prefs = {}
    for key in PREFERENCE_KEYS:
        if key not in raw:
            continue
        if allowed[key](raw[key]):
            prefs[key] = raw[key]
        else:
            warn(t("prefs_value", key=key, value=raw[key]))
    return prefs


def system_language() -> str | None:
    candidates = [os.environ.get(v, "") for v in ("LC_ALL", "LC_MESSAGES", "LANG")]
    if sys.platform == "darwin":
        # Apps started from Finder have no LANG; ask the system setting.
        try:
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleLocale"],
                capture_output=True, text=True, timeout=5,
            )
            candidates.append(out.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    elif os.name == "nt":
        try:
            import ctypes
            import locale

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            candidates.append(locale.windows_locale.get(lang_id, ""))
        except Exception:  # noqa: BLE001 - language detection is best-effort
            pass
    for value in candidates:
        code = value.strip().lower()[:2]
        if code in LANGUAGES:
            return code
    return None


def choose_language(option: str | None, prefs: dict) -> str:
    """Option, then environment, then preferences, then the system, then the app."""
    for value in (
        option,
        os.environ.get("PRII_LANG", "").strip().lower()[:2],
        prefs.get("language"),
        system_language(),
        setting("DEFAULT_LANGUAGE", None),
    ):
        if value in LANGUAGES:
            return value
    return "en"


# ── Output: quiet steps, full log ────────────────────────────────────────────


class Console:
    """Numbered steps on screen; every tool's output in the log."""

    def __init__(self, log_file: Path, *, verbose: bool, quiet: bool) -> None:
        self.log_file = log_file
        self.verbose = verbose
        self.quiet = quiet
        self.total = 0
        self.number = 0
        try:
            log_file.write_text("", encoding="utf-8")
        except OSError:
            pass

    def say(self, text: str = "") -> None:
        self.log(text)
        if not self.quiet:
            print(text, flush=True)

    def log(self, text: str) -> None:
        try:
            with self.log_file.open("a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except OSError:
            pass

    def tail(self, lines: int = 15) -> list[str]:
        try:
            content = self.log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        return content.splitlines()[-lines:]

    def step(self, name_key: str) -> None:
        self.number += 1
        self.say(t("step", n=self.number, total=self.total, name=t(name_key)))

    def run(self, cmd: list[str], *, what: str, cwd: Path | None = None,
            env: dict[str, str] | None = None) -> None:
        self.log("$ " + " ".join(str(c) for c in cmd))
        if self.verbose and not self.quiet:
            code = subprocess.run(cmd, cwd=cwd, env=env).returncode
        else:
            code = self._run_logged(cmd, cwd, env)
        if code != 0:
            raise SetupError(t("err.step", what=what, code=code))

    def _run_logged(self, cmd, cwd, env) -> int:
        stop = threading.Event()
        show_progress = not self.quiet and sys.stdout.isatty()

        def dots() -> None:
            while not stop.wait(5):
                print(".", end="", flush=True)

        ticker = threading.Thread(target=dots, daemon=True)
        if show_progress:
            ticker.start()
        try:
            with self.log_file.open("a", encoding="utf-8") as fh:
                return subprocess.run(
                    cmd, cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT
                ).returncode
        except OSError as exc:
            self.log(f"could not run: {exc}")
            return 127
        finally:
            stop.set()
            if show_progress:
                ticker.join(timeout=1)
                print(flush=True)


# ── Is setup complete, and is it current? ────────────────────────────────────


def fingerprint() -> str:
    """Changes when the things setup installs from change, so an update that
    alters the requirements is noticed before it becomes a failed start."""
    digest = hashlib.sha256()
    digest.update(f"{TEMPLATE_VERSION}|{SETUP_VERSION}".encode())
    sources = [*requirement_files(), CONSTRAINTS]
    if BUILD_FRONTEND and FRONTEND_DIR is not None:
        sources += [FRONTEND_DIR / "package.json", FRONTEND_DIR / "package-lock.json"]
    for path in sources:
        digest.update(str(path.name).encode())
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<absent>")
    for spec in setting("EXTRA_PIP_SPECS", []):
        digest.update(str(spec).replace(str(REPO_ROOT), "").encode())
    return digest.hexdigest()


def is_complete() -> bool:
    if not (MARKER.exists() and venv_python().exists()):
        return False
    if BUILD_FRONTEND and DIST_DIR is not None:
        return (DIST_DIR / "index.html").is_file()
    return True


def is_current() -> bool:
    """A marker written before fingerprints existed counts as out of date."""
    try:
        return json.loads(MARKER.read_text(encoding="utf-8")).get("fingerprint") == fingerprint()
    except (OSError, ValueError, AttributeError):
        return False


def write_marker() -> None:
    MARKER.write_text(
        json.dumps({"fingerprint": fingerprint(), "template": TEMPLATE_VERSION}) + "\n",
        encoding="utf-8",
    )


# ── Python environment ───────────────────────────────────────────────────────

_GIT_REQUIREMENT = re.compile(
    r"git\+(https://github\.com/[^/\s]+/[^/\s@]+?)(?:\.git)?@([0-9a-f]{40})(?=#|\s|$)"
)


def without_git(requirements_text: str) -> str:
    """Rewrite pinned GitHub git requirements to the same commit's archive URL."""
    return _GIT_REQUIREMENT.sub(r"\1/archive/\2.zip", requirements_text)


def venv_is_usable() -> bool:
    """True when .venv has an interpreter that runs and is new enough."""
    if not venv_python().exists():
        return False
    check = f"import sys; raise SystemExit(0 if sys.version_info >= {MIN_PYTHON!r} else 1)"
    try:
        return subprocess.run(
            [str(venv_python()), "-c", check], capture_output=True, timeout=60
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def git_is_usable() -> bool:
    if not shutil.which("git"):
        return False
    if sys.platform == "darwin":
        # /usr/bin/git is a stub that pops an "install developer tools" dialog
        # until the Xcode command line tools are installed.
        try:
            return subprocess.run(
                ["xcode-select", "-p"], capture_output=True, timeout=30
            ).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    return True


def setup_python(console: Console) -> None:
    console.step("step.python")
    if not venv_is_usable():
        venv.EnvBuilder(with_pip=True, clear=True).create(VENV_DIR)
    py = str(venv_python())
    console.run([py, "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
                what=t("step.python"))

    console.step("step.components")
    constraints = ["-c", str(CONSTRAINTS)] if CONSTRAINTS.is_file() else []
    files = [f for f in requirement_files() if f.is_file()]
    with tempfile.TemporaryDirectory(prefix="prii-req-") as tmp:
        if not git_is_usable():
            rewritten, announced = [], False
            for index, source in enumerate(files):
                text = source.read_text(encoding="utf-8")
                # A copy lives in a temp folder, so a file with relative
                # "-r"/"-e"/"-c" lines is left as it is rather than broken.
                relative = re.search(r"^\s*-(r|e|c)\s", text, flags=re.MULTILINE)
                if "git+" not in text or relative:
                    rewritten.append(source)
                    continue
                if not announced:
                    console.say("  " + t("no_git"))
                    announced = True
                copy = Path(tmp) / f"{index}-{source.name}"
                copy.write_text(without_git(text), encoding="utf-8")
                rewritten.append(copy)
            files = rewritten
        install = [py, "-m", "pip", "install", "--quiet", *constraints]
        for req in files:
            install += ["-r", str(req)]
        if files:
            console.run(install, what=t("step.components"))
        extra = [str(s) for s in setting("EXTRA_PIP_SPECS", [])]
        if extra:
            console.run([py, "-m", "pip", "install", "--quiet", *constraints, *extra],
                        what=t("step.components"))


# ── Node.js ──────────────────────────────────────────────────────────────────

NODE_DIST = f"https://nodejs.org/dist/latest-v{NODE_MAJOR}.x"


def npm_command() -> str:
    """npm is a .cmd shim on Windows, which subprocess needs spelled out."""
    return "npm.cmd" if os.name == "nt" else "npm"


def _version_key(name: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", name))


def candidate_node_dirs(home: Path | None = None) -> list[Path]:
    """Places Node version managers and installers put npm, newest first.

    Apps started from Finder get a minimal PATH, so an npm that works in the
    person's shell is often not on PATH here.
    """
    home = home or Path.home()
    dirs: list[Path] = []
    for root, pattern in (
        (home / ".nvm" / "versions" / "node", "*/bin"),
        (home / ".local" / "share" / "fnm" / "node-versions", "*/installation/bin"),
        (home / "Library" / "Application Support" / "fnm" / "node-versions",
         "*/installation/bin"),
        (home / ".asdf" / "installs" / "nodejs", "*/bin"),
    ):
        if root.is_dir():
            dirs.extend(sorted(
                root.glob(pattern),
                key=lambda p, root=root: _version_key(p.relative_to(root).parts[0]),
                reverse=True,
            ))
    dirs += [home / ".volta" / "bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
    return dirs


def private_node_bin() -> Path:
    return NODE_DIR if os.name == "nt" else NODE_DIR / "bin"


def node_is_new_enough(node: str) -> bool:
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    version = _version_key(out.stdout)
    return bool(version) and version[0] >= NODE_MAJOR


def node_archive_name(version: str, system: str | None = None,
                      machine: str | None = None) -> str:
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    os_name = {"darwin": "darwin", "linux": "linux", "windows": "win"}.get(system)
    if not arch or not os_name:
        raise SetupError(t("err.platform", system=system, machine=machine, major=NODE_MAJOR))
    return f"node-{version}-{os_name}-{arch}.{'zip' if os_name == 'win' else 'tar.gz'}"


def _download(url: str, dest: Path) -> None:
    """Fetch url to dest. Falls back to curl when Python has no CA certificates
    (a stock python.org install on macOS until its certificate step is run)."""
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            with dest.open("wb") as out:
                shutil.copyfileobj(response, out)
        return
    except (urllib.error.URLError, ssl.SSLError, OSError):
        curl = shutil.which("curl")
        if not curl:
            raise SetupError(t("err.download", url=url)) from None
    result = subprocess.run(
        [curl, "--fail", "--location", "--silent", "--show-error", "-o", str(dest), url],
        capture_output=True,
    )
    if result.returncode != 0:
        raise SetupError(t("err.download", url=url))


def _inside(root: Path, target: Path) -> bool:
    return os.path.commonpath([root, os.path.abspath(target)]) == str(root)


def _extract_tar(archive: Path, dest: Path) -> None:
    """Unpack a tarball, refusing any entry that would land outside dest.

    The checksum only proves the download matches the release list, which
    comes from the same server, so the member paths are checked here too:
    plain files, directories and symlinks only, all resolving under dest.
    Entries are written by hand rather than with tarfile.extract(), so nothing
    is created at a path that was not checked.
    """
    root = Path(os.path.abspath(dest))
    root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        for member in tf:
            target = root / member.name
            if not (member.isfile() or member.isdir() or member.issym()):
                raise SetupError(t("err.archive", name=member.name))
            if not _inside(root, target):
                raise SetupError(t("err.archive", name=member.name))
            if member.issym() and not _inside(root, target.parent / member.linkname):
                raise SetupError(t("err.archive", name=member.name))
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.issym():
                os.symlink(member.linkname, target)
                continue
            source = tf.extractfile(member)
            if source is None:
                raise SetupError(t("err.archive", name=member.name))
            with source, target.open("wb") as out:
                shutil.copyfileobj(source, out)
            target.chmod(member.mode & 0o755)


def _extract_zip(archive: Path, dest: Path) -> None:
    root = Path(os.path.abspath(dest))
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            if not _inside(root, root / name):
                raise SetupError(t("err.archive", name=name))
        zf.extractall(root)


def install_private_node() -> Path:
    """Download the current Node release into .node/ and return its bin dir."""
    with tempfile.TemporaryDirectory(prefix="prii-node-") as tmp:
        tmp_dir = Path(tmp)
        sums = tmp_dir / "SHASUMS256.txt"
        _download(f"{NODE_DIST}/SHASUMS256.txt", sums)
        checksums = {}
        for line in sums.read_text().splitlines():
            parts = line.split()
            if len(parts) == 2:
                checksums[parts[1]] = parts[0]
        version = next(
            (m.group(1) for n in checksums if (m := re.match(r"node-(v[\d.]+)-", n))), None
        )
        if version is None:
            raise SetupError(t("err.node_list"))
        name = node_archive_name(version)
        if name not in checksums:
            raise SetupError(t("err.node_list"))
        archive = tmp_dir / name
        _download(f"{NODE_DIST}/{name}", archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != checksums[name]:
            raise SetupError(t("err.checksum", name=name))
        unpacked = tmp_dir / "unpacked"
        if name.endswith(".zip"):
            _extract_zip(archive, unpacked)
        else:
            _extract_tar(archive, unpacked)
        shutil.rmtree(NODE_DIR, ignore_errors=True)
        shutil.move(str(next(unpacked.iterdir())), str(NODE_DIR))
    return private_node_bin()


def resolve_npm(console: Console | None = None) -> tuple[str, Path | None]:
    """Return (npm executable, directory to prepend to PATH or None)."""
    npm = npm_command()
    found, node = shutil.which(npm), shutil.which("node")
    if found and node and node_is_new_enough(node):
        return found, None
    for directory in [*candidate_node_dirs(), private_node_bin()]:
        found = shutil.which(npm, path=str(directory))
        node = shutil.which("node", path=str(directory))
        if found and node and node_is_new_enough(node):
            return found, directory
    if console is not None:
        console.say("  " + t("node_download", major=NODE_MAJOR))
    bin_dir = install_private_node()
    found = shutil.which(npm, path=str(bin_dir))
    if not found:
        raise SetupError(t("err.node_list"))
    return found, bin_dir


def build_frontend(console: Console) -> None:
    if FRONTEND_DIR is None or DIST_DIR is None:
        raise SetupError(t("err.no_frontend"))
    console.step("step.node")
    npm, bin_dir = resolve_npm(console)
    env = dict(os.environ)
    if bin_dir is not None:
        # npm is a `#!/usr/bin/env node` script, so node must be on PATH too.
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    # An empty base makes the dashboard call its API on the origin it was
    # served from. Process env beats a developer .env.local at build time;
    # apps with differently named variables add them via EXTRA_BUILD_ENV.
    env["VITE_API_BASE"] = ""
    env.update({str(k): str(v) for k, v in setting("EXTRA_BUILD_ENV", {}).items()})

    console.step("step.dashboard")
    lock = FRONTEND_DIR / "package-lock.json"
    console.run([npm, "ci" if lock.exists() else "install", "--no-audit", "--no-fund"],
                cwd=FRONTEND_DIR, env=env, what=t("step.dashboard"))
    console.run([npm, "run", "build"], cwd=FRONTEND_DIR, env=env, what=t("step.dashboard"))
    if not (DIST_DIR / "index.html").is_file():
        raise SetupError(t("err.no_dist", path=DIST_DIR / "index.html"))


# ── App hooks ────────────────────────────────────────────────────────────────


def run_hook(console: Console, name: str) -> None:
    """Run an app's "module:function" hook (POST_SETUP, BEFORE_LAUNCH) with the
    private Python, so it can import what setup installed."""
    target = setting(name, None)
    if not target:
        return
    module, _, function = str(target).partition(":")
    code = f"import importlib; getattr(importlib.import_module({module!r}), {function!r})()"
    console.run([str(venv_python()), "-c", code], cwd=REPO_ROOT, what=f"{name} ({target})")


# ── Setup ────────────────────────────────────────────────────────────────────


def run_setup(console: Console) -> None:
    if sys.version_info < MIN_PYTHON:
        need = ".".join(str(n) for n in MIN_PYTHON)
        raise PythonTooOld(t("need_python", need=need, have=platform.python_version()))
    console.total = 3 + (2 if BUILD_FRONTEND else 0)
    console.number = 0
    MARKER.unlink(missing_ok=True)
    setup_python(console)
    if BUILD_FRONTEND:
        build_frontend(console)
    console.step("step.finish")
    run_hook(console, "POST_SETUP")
    write_marker()


def explain_failure(console: Console, error: SetupError) -> None:
    console.say()
    console.say(t("cause", text=error))
    tail = [line for line in console.tail() if line.strip()]
    if tail and not console.verbose:
        console.say(t("details"))
        for line in tail:
            console.say("  " + line)
    console.say(t("log_at", path=console.log_file))


def interactive() -> bool:
    return sys.stdin is not None and sys.stdin.isatty() and sys.stdout.isatty()


def wait_for_retry() -> bool:
    """True when the person asked to try again; False when nobody can answer."""
    if not interactive():
        return False
    try:
        input(t("retry"))
    except (EOFError, KeyboardInterrupt):
        return False
    print()
    return True


def setup_with_retries(console: Console, *, heading: str) -> bool:
    console.say(heading)
    console.say(t("intro"))
    console.say()
    while True:
        try:
            run_setup(console)
        except SetupError as error:
            explain_failure(console, error)
            if isinstance(error, PythonTooOld):
                open_url("https://www.python.org/downloads/")
                console.say(t("open_python"))
                return False
            if not wait_for_retry():
                return False
            continue
        console.say()
        console.say(t("setup_done"))
        return True


def open_url(url: str) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", url], capture_output=True, timeout=30)
        elif os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]  # noqa: S606
        else:
            subprocess.run(["xdg-open", url], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def reset() -> None:
    MARKER.unlink(missing_ok=True)
    for path in (VENV_DIR, NODE_DIR):
        shutil.rmtree(path, ignore_errors=True)


# ── Starting the app ─────────────────────────────────────────────────────────


def launch_once(app_args: list[str], launch_log: Path, *, show: bool) -> tuple[int, float]:
    """Start the app and wait for it. Returns (exit status, seconds it ran)."""
    cmd = [str(venv_python()), str(REPO_ROOT / "desktop" / "launch.py"), *app_args]
    started = time.monotonic()
    try:
        if show:
            with launch_log.open("w", encoding="utf-8") as fh:
                proc = subprocess.Popen(
                    cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, errors="replace",
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    fh.write(line)
                code = proc.wait()
        else:
            with launch_log.open("w", encoding="utf-8") as fh:
                code = subprocess.run(
                    cmd, cwd=REPO_ROOT, stdout=fh, stderr=subprocess.STDOUT
                ).returncode
    except KeyboardInterrupt:
        code = 0
    except OSError as exc:
        launch_log.write_text(f"could not start: {exc}\n", encoding="utf-8")
        code = 127
    return code, time.monotonic() - started


def start_failed(code: int, seconds: float) -> bool:
    """A clean exit, being killed by a signal (force quit, logout), or stopping
    after it had been running for a while is not a failed start."""
    if code == 0 or seconds >= STARTED_AFTER_SECONDS:
        return False
    return not (code < 0 or code > 128)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="desktop/setup.py",
        description=t("help.description"),
        epilog=t("help.epilog", prefs=prefs_path()),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("--launch", action="store_true", help=t("help.launch"))
    parser.add_argument("--ensure", action="store_true", help=t("help.ensure"))
    parser.add_argument("--reinstall", "--force", dest="reinstall", action="store_true",
                        help=t("help.reinstall"))
    parser.add_argument("--reset", action="store_true", help=t("help.reset"))
    parser.add_argument("--browser", action="store_true", help=t("help.browser"))
    parser.add_argument("--no-window", action="store_true", help=t("help.no_window"))
    parser.add_argument("--verbose", action="store_true", help=t("help.verbose"))
    parser.add_argument("--offline", action="store_true", help=t("help.offline"))
    parser.add_argument("--lang", choices=LANGUAGES, help=t("help.lang"))
    parser.add_argument("--version", action="store_true", help=t("help.version"))
    # Used by the macOS launchers; not for people.
    parser.add_argument("--no-prompt", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--handoff", metavar="APP", help=argparse.SUPPRESS)
    return parser


def peek_language(argv: list[str]) -> str | None:
    """--lang has to be known before the parser's own help text is built."""
    for index, arg in enumerate(argv):
        if arg == "--lang" and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


def main(argv: list[str] | None = None) -> int:
    global _lang
    argv = list(sys.argv[1:] if argv is None else argv)
    # A Windows console or a pipe may not be able to encode "—" or "é"; a
    # message with a replaced character is better than a crash.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    warnings: list[str] = []
    prefs = load_preferences(warn=warnings.append)
    _lang = choose_language(peek_language(argv), prefs)
    if warnings:  # collected before the language was known; read again to say them in it
        warnings.clear()
        prefs = load_preferences(warn=warnings.append)

    args, app_args = build_parser().parse_known_args(argv)
    if args.version:
        print(f"{APP_TITLE} — launcher {TEMPLATE_VERSION}, Python {platform.python_version()}")
        return 0

    offline = args.offline or os.environ.get("PRII_OFFLINE", "").strip() not in ("", "0")
    logs = log_dir()
    failed_flag = logs / "launch-failed"
    launch_log = logs / "launch.log"
    console = Console(logs / "setup.log", verbose=args.verbose,
                      quiet=args.ensure and not args.launch)
    for warning in warnings:
        console.say(warning)

    if args.reset:
        console.say(t("reset"))
        reset()

    check = prefs.get("check_on_start", True)
    repairing = failed_flag.exists()
    needs_setup = (
        args.reinstall or args.reset or repairing
        or not is_complete() or (check and not is_current())
    )

    if needs_setup and offline:
        if not is_complete():
            console.quiet = False
            console.say(t("offline_incomplete"))
            return 1
        console.say(t("offline_stale"))
        needs_setup = False

    if needs_setup:
        if args.no_prompt:
            return EXIT_NEEDS_TERMINAL
        console.quiet = False
        if repairing and launch_log.is_file():
            report = [ln for ln in launch_log.read_text(errors="replace").splitlines()[-15:]
                      if ln.strip()]
            if report:
                console.say(t("last_report"))
                for line in report:
                    console.say("  " + line)
                console.say()
        if not setup_with_retries(
            console, heading=t("repairing") if repairing else t("title")
        ):
            return 1
    elif not args.launch and not args.ensure:
        console.say(t("already"))

    if not args.launch:
        failed_flag.unlink(missing_ok=True)
        return 0

    # ── start ────────────────────────────────────────────────────────────────
    if args.handoff and not repairing:
        # Setup ran in a Terminal window opened by the .app; hand back to it so
        # this window can close. After a failed start we stay here instead, so
        # a second failure is readable rather than bouncing between the two.
        console.say(t("opening"))
        open_url(args.handoff)
        return 0

    if (args.browser or prefs.get("window") == "browser") and "--browser" not in app_args:
        app_args.append("--browser")
    if args.no_window and "--no-window" not in app_args:
        app_args.append("--no-window")
    data_home = prefs.get("data_home")
    data_var = setting("DATA_ENV_VAR", None)
    if data_home and data_var and not os.environ.get(data_var):
        os.environ[data_var] = str(Path(data_home).expanduser())

    show = not args.no_prompt
    attempts = 0
    while True:
        attempts += 1
        failed_flag.unlink(missing_ok=True)
        try:
            run_hook(console, "BEFORE_LAUNCH")
        except SetupError as error:
            explain_failure(console, error)
        if show and needs_setup:
            console.say(t("starting"))
            console.say(t("keep_open"))
            console.say()
        code, seconds = launch_once(app_args, launch_log, show=show)
        if not start_failed(code, seconds):
            return 0

        failed_flag.write_text(f"{code}\n", encoding="utf-8")
        if args.no_prompt:
            return EXIT_NEEDS_TERMINAL
        if offline:
            console.say(t("log_at", path=launch_log))
            return code
        if attempts == 1 and not needs_setup:
            # A set-up app that will not start usually has stale components.
            console.quiet = False
            console.say()
            if not setup_with_retries(console, heading=t("repairing")):
                return 1
            needs_setup = True
            continue
        console.say()
        console.say(t("still_failing"))
        console.say(t("log_at", path=launch_log))
        if not wait_for_retry():
            return code
        if not setup_with_retries(console, heading=t("repairing")):
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
