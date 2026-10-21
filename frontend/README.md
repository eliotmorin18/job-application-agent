# Job Application Agent — frontend

React interface (generated with [Lovable](https://lovable.dev), TanStack Start) for the candidate profile and CV import.
It talks only to the local FastAPI backend (`api/main.py`) through `src/services/api/`.

```sh
bun install --frozen-lockfile   # dependencies (lockfile: bun.lock)
npm run dev                     # http://localhost:8080 — /api is proxied to http://127.0.0.1:8000
```

The backend must be running from the project root: `uvicorn api.main:app --reload`.
`VITE_API_MODE=mock` (in `.env.local`) runs the interface on fictional in-memory data instead.

See the main [README](../README.md) for the full setup, tests and privacy notes.
