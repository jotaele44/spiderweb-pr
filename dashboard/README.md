# dashboard/ — generated branding derivatives only

This directory no longer holds a UI. The standalone `dashboard.html` viewer was
retired: it shipped Aircraft Catalog / Flight Log / **FR24 Review Queue** tabs,
which belong to [`skywatcher-pr`](https://github.com/jotaele44/skywatcher-pr)
(see `docs/REPO_BOUNDARY.md`). Spiderweb's single interface is the Vite SPA under
`server/frontend`, served by `desktop/`.

The two PNGs here are **generated**, not source. `thehub-pr`'s
`tools/build_program_icons.py` carries a spiderweb-specific `STANDALONE` entry:

```python
STANDALONE = {"spiderweb-pr": ("dashboard", ("icon-64.png", "icon-180.png"))}
```

so `--check` reports drift unless those files exist. They are kept solely to
satisfy that gate.

**Follow-up (in `thehub-pr`, not here):** drop the `STANDALONE` entry now that the
no-build dashboard is gone, then delete this directory. Regenerate with
`python ../thehub-pr/tools/build_program_icons.py --repo .` — never edit the PNGs
by hand; they derive from `assets/branding/icon.png`.

Do not add a new UI here.
