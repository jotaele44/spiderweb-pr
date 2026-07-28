# Spiderweb desktop

## Install on macOS — no Terminal

1. Open this repository's **Releases** page and download the latest
   `PRII-SPIDERWEB-macOS.dmg`.
2. Open the disk image and drag **Spiderweb** to **Applications**.
3. Open Spiderweb from Applications.

The release includes its own runtime, local server, standalone dashboard,
vendored browser libraries, and baseline output snapshot. Python, Node.js,
Git, Homebrew, and Terminal are not required.

On first launch, the native **Setup & Repair** screen asks for a writable data
location, copies baseline outputs there without overwriting later work, runs
package diagnostics, and starts the app. **Setup & Diagnostics** remains
available in the lower-right corner for repair.

The dashboard opens even when no local flight database exists. Optional FR24
and contract-finance layers appear when corresponding output files are present
in the selected application-data folder. Heavy geospatial and model workflows
remain optional developer/operator tools, not desktop prerequisites.

## If macOS blocks the first open

Open **System Settings → Privacy & Security**, find the message naming
Spiderweb, and choose **Open Anyway**. No quarantine command is required.
Release CI applies an ad-hoc integrity signature, but public downloads are not
Apple-notarized unless a release is signed with project Developer ID
credentials.

The `PRII-SPIDERWEB.app` committed in a source checkout is a Finder-only
download helper. The self-contained product is the app inside the release
disk image.

## Release contract

The `desktop-build` workflow builds on clean Linux, macOS, and Windows runners,
then tests the fresh-machine setup contract and backend health on the frozen
executable. macOS CI verifies the bundle signature before producing the `.dmg`.

`desktop/launch.py` and `desktop/config.py` are thin adapters over TheHub's
shared `prii_desktop` runtime. Source-checkout setup scripts remain developer
conveniences and are not part of end-user installation.
