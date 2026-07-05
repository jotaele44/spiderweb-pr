# Spiderweb frontend migration compatibility bundle

Contents:

- `server_frontend_migrated_patched/` — migrated frontend from upload, patched for lint and API base handling.
- `server/backend/compat_shim.py` — FastAPI compatibility shim for migrated frontend endpoints.
- `server/backend/compat_app.py` — ASGI entrypoint that installs the shim without modifying `server/backend/main.py`.
- `docs/FRONTEND_MIGRATION_COMPAT.md` — run notes and swap-readiness matrix.

Suggested repo placement:

```text
server/frontend-migrated/        <= copy server_frontend_migrated_patched/* here
server/backend/compat_shim.py
server/backend/compat_app.py
docs/FRONTEND_MIGRATION_COMPAT.md
```

Run backend compatibility mode:

```bash
python3 -m uvicorn server.backend.compat_app:app --reload --port 8000
```

Run migrated frontend candidate:

```bash
cd server/frontend-migrated
npm install
VITE_SPIDERWEB_API_BASE_URL=http://localhost:8000/api npm run dev
```
