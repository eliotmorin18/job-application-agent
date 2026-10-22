# Job Application Agent — frontend

React interface (generated with [Lovable](https://lovable.dev), TanStack Start) for the candidate profile, CV import and « Mes candidatures ».
It talks only to the local FastAPI backend (`api/main.py`) through `src/services/api/`.

```sh
bun install --frozen-lockfile   # dependencies (lockfile: bun.lock)
npm run dev                     # http://localhost:8080 — /api is proxied to http://127.0.0.1:8000
```

The backend must be running from the project root: `uvicorn api.main:app --reload`.
`VITE_API_MODE=mock` (in `.env.local`) runs the profile pages on fictional in-memory data instead; CV import and « Mes candidatures » always need the backend.

See the main [README](../README.md) for the full setup, tests and privacy notes.
