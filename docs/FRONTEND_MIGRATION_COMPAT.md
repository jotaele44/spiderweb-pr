# Spiderweb migrated frontend compatibility layer

This bundle adds a read-only adapter for testing the migrated Vite frontend without replacing the current `server/frontend` workbench.

## Run mode

```bash
python3 -m uvicorn server.backend.compat_app:app --reload --port 8000
```

## Local validation performed

```bash
cd server_frontend_migrated_patched
npm run lint
npm run build
python3 -m py_compile ../server/backend/compat_shim.py ../server/backend/compat_app.py
```

## Swap gate

Do not replace `server/frontend` until the migrated candidate passes browser smoke tests against `server.backend.compat_app:app`.
