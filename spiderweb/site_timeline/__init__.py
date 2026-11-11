"""Site imagery timeline: dated satellite scenes for sites another producer registers.

Offline build. Nothing here fetches imagery: acquisition sits behind the single seam
in :mod:`spiderweb.site_timeline.adapters`, whose live implementation is a
fail-closed stub until credentials exist. The contract is
``docs/contracts/SITE_IMAGERY_TIMELINE.md``.

Importing this package pulls in no HTTP client, no imaging library and no provider.
"""
