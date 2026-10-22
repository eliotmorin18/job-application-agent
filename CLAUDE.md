# CLAUDE.md — job-application-agent

Personal application to prepare and track job applications, one offer at a time chosen by the
user (never bulk). Implemented today: from a job offer URL, generate a tailored CV (LaTeX → PDF),
explain the offer and analyse the fit with the candidate profile.

## Current scope (branch `refactor/mvp-cv`)
- Implemented: candidate profile + CV import (« Candidat »); « Mes candidatures » (routes `/cvs`,
  formerly « Mes CV »): preparing an application from a URL (offer analysis + tailored CV), list,
  application page with three tabs (« Offre et adéquation », « Préparation à l'entretien », « CV »:
  editing of `cv.json` with PDF recompilation and clickable zones), deletion. One application = one
  CV folder for now: the interface uses the application vocabulary, the code and API keep `cv`.
- Not implemented: application tracking (statuses, board), cover letters, « Paramètres » (disabled
  "Bientôt" entry in the sidebar), submitting applications. `main` still holds an older prototype
  (server.py, workflows/): do not reuse it unless asked.

## Product direction (decided, partly implemented)
- The app will become centred on the application (« candidature ») instead of the CV: an
  application is a potential job opportunity that may hold an offer, a tailored CV, a cover
  letter, a status, notes and other information. First step done (interface only): « Mes CV »
  became « Mes candidatures », without any backend, API or storage change.
- The existing CV pipeline is kept and reused as much as possible.
- The target data model and migrations are still to be designed: none of them exists yet. Next
  step: design this transition, then build application tracking in « Mes candidatures ».

## Architecture
Backend: Python 3.12 (`.venv`), FastAPI, organised by feature.
- `api/` — `main.py` (profile, import routes), `cvs.py` (« Mes candidatures » routes, background
  tasks, locks), `common.py` (error format `{"detail": {"message", "problems"}}`, `profile_path`).
- `candidate/` — `profile.py` (load/validate), `manager.py` (edits), `import_cv.py`,
  `extract_profile.py`, `review_import.py`, `apply_import.py` (CV import flow).
- `jobs/` — `url_check.py` (refuses local/internal URLs), `read_job.py` (Playwright),
  `analyze_job.py` (offer → JSON, Claude).
- `cv/` — `pipeline.py` (read → analyse offer → `generate.py` → `verify.py` → build → analysis),
  `document.py` (cv.json schema), `render.py` (cv.json → LaTeX), `build_cv.py` (folder + latexmk),
  `layout.py` (layout.json zones), `analysis.py` + `fit_score.py` (analysis.json), `metadata.py`
  (creation/update dates), `cli.py` (`python -m cv.cli "<URL>"`), `template/`.
- `llm/claude_cli.py` — the only call to Claude (`run_claude`: `claude -p` + JSON schema).
- A CV lives in `cv/applications/<cv_id>/`: cv.json, offer.json, selection.json, analysis.json,
  metadata.json, sections/, build/ (PDF, layout.json). CVs without cv.json are read-only (409).

Frontend: `frontend/` (Lovable, TanStack Start/Router, React 19, TanStack Query, shadcn/ui,
Vitest). Rules in `frontend/AGENTS.md`.
- `src/routes/` file routes (`routeTree.gen.ts` is generated), `src/features/{candidate,import,cvs}`.
- `src/services/api/` — `httpClient.ts` (ApiError), `cvApi.ts` + `cvTypes.ts` (mirror the backend,
  never bent to fit the UI; UI shapes go in `features/cvs/adapters.ts`), candidate API.
- Vite proxies `/api` to `http://127.0.0.1:8000` (`API_PROXY_TARGET` to change it).

## Invariants
- `profile/private/candidate.yaml` is the only source of truth about the candidate: never invent
  experience, skill, figure or achievement; every evidence id must exist in the profile.
- Personal data stays local and out of Git: `profile/private/`, `cv/applications/`,
  `cv/reference/`, `browser/session/`, `.env`. Never write them outside an explicit user action.
- `cv.json`, `analysis.json`, `layout.json` schemas (schema_version 1) and the Claude prompts change
  only with the user's agreement; new fields must stay compatible with saved files.
- The fit score is computed and stored but never displayed in the interface.
- "Missing" and "not documented" requirements stay distinct.
- No demo data or mock fallback in « Mes candidatures »: show backend errors as they are.

## Tests (always fictional data)
- Never call Claude for real (patch `run_claude`), never read or write the real profile or real
  CVs: use `profile/candidate.example.yaml`, temporary folders and `app.dependency_overrides`.
- Backend: `.venv/bin/python -m unittest discover tests`
  (browser test, optional: `RUN_BROWSER_TESTS=1 .venv/bin/python -m unittest tests.test_read_job_browser`)
- Frontend (`cd frontend`): `npx tsc --noEmit`, `npm test`, `npm run build`.
- Lint: `npm run lint` fails on ~96 pre-existing Prettier errors (Lovable/shadcn files). Lint the
  files you touched instead: `npx eslint <files>`; do not reformat unrelated files.
- Dependencies: `bun.lock` is the lockfile (`bun install --frozen-lockfile`); never create a
  `package-lock.json`.

## Run
- Backend: `uvicorn api.main:app --reload` (from the root, `.venv` active) — port 8000.
- Frontend: `cd frontend && npm run dev` — http://localhost:8080.
- The user's own servers often run on 8000/8080: use other ports for test servers.

## Collaboration
- Read the existing code before changing it; prefer the simplest solution; no new dependency,
  database, queue or Docker without agreement.
- Explain significant backend changes (routes, schemas, pipeline, prompts) before implementing them.
- Never switch branches, merge, rebase, commit, or push without the user's explicit agreement.
  Preserve existing work. Commits: conventional, in English (`feat(cv): …`), one unit of work each.
- Follow the local conventions of each file (comment language, style).

## Docs
- `docs/architecture.md` — implemented architecture, flows, limits; `docs/roadmap.md` — implemented,
  decided, next steps, possible evolutions.
- `README.md` — setup, features, privacy; `cv/README.md` — LaTeX template and build;
  `frontend/README.md` and `frontend/AGENTS.md` — frontend setup and rules.
