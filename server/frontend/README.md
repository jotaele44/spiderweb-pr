# spiderweb-pr frontend

> **Diagnostic-only surface (ADR 0001, Phase 2).** This repo's frontend is a
> development and diagnostic tool for this producer only. The supported product
> surface for the PRII federation is the hub app
> (`thehub-pr/server/frontend`), which renders this producer's data alongside
> the other engines. See `thehub-pr/docs/adr/0001-federated-engines-single-hub.md`.

This is the local diagnostic UI for the `spiderweb-pr` spatial / operational
producer. It is useful for inspecting this engine's own exports in isolation
during development; it is not the federation's product surface and is not
required for the producer's `federation.json` + export-package contract with the
Hub.
