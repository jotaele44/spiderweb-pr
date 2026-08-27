# Spiderweb for macOS

Use the standalone macOS `.dmg` from a desktop release:

1. Open the downloaded `.dmg`.
2. Drag **Spiderweb** to **Applications**.
3. Open Spiderweb from Finder or Launchpad.
4. In **Setup & Diagnostics**, choose a workspace and select **Save & Open App**.

The release app is self-contained. End-user setup needs no Terminal and no
separate Python, Node.js, Git, package-manager, or source checkout.

First launch creates a writable workspace and prepares `server/priis.db` for the
live backend. It seeds the diagnostic dataset only when the database is absent;
existing user state is left untouched.

Use the always-available gear button in the app to reopen **Setup & Diagnostics**.
It can choose the workspace, run local checks, or repair generated configuration.
Repair is idempotent and does not delete user data.

## If macOS blocks the first open

Open **System Settings → Privacy & Security**, find the message naming
Spiderweb, and select **Open Anyway**. This is the complete UI-only recovery
path for an unnotarized development release.

## If the app reports that first-run setup could not finish

Opening `PRII-SPIDERWEB.app` straight out of an unzipped download makes macOS
run it from a throwaway read-only copy under
`/private/var/folders/…/AppTranslocation/…`, where the rest of the checkout is
not present and no `.venv` can be written. Move the folder somewhere else (your
home folder is fine), double-click `Fix-Gatekeeper.command` once, then open the
app again. Running `PRII-SPIDERWEB.command` instead also avoids it — only `.app`
bundles are translocated.

Genuine setup failures write their output to
`$TMPDIR/prii-spiderweb-pr-setup.log`, and the failure message names that file.

## Architecture

`desktop/config.py` and `desktop/app_server.py` are the thin Spiderweb adapters
for its Vite/FastAPI diagnostic app. Native setup, repair, diagnostics, the per-user
lock, and the pywebview lifecycle live in
`thehub-pr/packages/prii_desktop`. Release CI builds and smokes the frozen app
on macOS, Windows, and Linux and packages the macOS `.dmg`.

`desktop/setup.py` and command-line launcher flags remain developer conveniences;
they are not part of end-user installation.
