# Architecture

What is implemented today (branch `refactor/mvp-cv`). Planned changes are in [roadmap.md](roadmap.md);
setup and usage in the [README](../README.md); LaTeX details in [cv/README.md](../cv/README.md).

## Overview

```
Browser (React, frontend/) ──/api──▶ Vite proxy ──▶ FastAPI (api/) ──▶ candidate/, jobs/, cv/
                                                                          │
                     local files: profile/private/, cv/applications/ ◀────┤
                     external tools: Claude Code CLI (llm/), Playwright, latexmk
```

- Single user, local only: no account, no authentication, no database. The state is files.
- Claude is only reached through `llm/claude_cli.run_claude` (`claude -p` with a JSON schema):
  Claude returns structured data, Python validates it, writes files and never lets Claude write
  LaTeX or choose ids that do not exist in the profile.
- The CLI (`python -m cv.cli "<URL>"`) and the API share the same pipeline (`cv/pipeline.py`).

## Data

| Location | Content | Written by |
|---|---|---|
| `profile/private/candidate.yaml` | the candidate profile, single source of truth | `candidate/manager.py` (ruamel.yaml, keeps comments and order) |
| `profile/private/imports/`, `extracted/` | imported CV PDFs and their extraction proposals | `candidate/import_cv.py` |
| `cv/applications/<cv_id>/` | one folder per generated CV (see below) | `cv/build_cv.py`, `api/cvs.py` |

A CV folder holds `offer.json` (analysed offer), `cv.json` (content, schema_version 1),
`selection.json` (Claude's choices, verification issues), `sections/*.tex` (computed from cv.json),
`build/` (PDF, `layout.json`), `analysis.json` (fit analysis, schema_version 1) and `metadata.json`
(creation/update dates, UTC). Older folders may lack some of these files: without `cv.json` a CV is
read-only, without `layout.json` it has no clickable zones, without `metadata.json` its creation date
comes from `offer.json` (macOS) or is unknown.

## Main flows

**Profile.** The « Candidat » pages call `/api/profile`, `/api/skills`, `/api/languages`… which edit
`candidate.yaml` through `candidate/manager.py`. Education entries without `id` are addressed by
position (`index-N`).

**CV import.** `POST /api/imports` (PDF) → `import_cv.py` extracts text and asks Claude for a proposal
→ `review_import.py` compares it with the profile (new, duplicate, probable duplicate) → the user
decides per item → `POST /api/imports/{id}/apply` → `apply_import.py` applies all decisions or none.

**CV generation.** `POST /api/cvs/generate {url}` checks the URL, creates a task and returns 202.
The task runs `cv/pipeline.py`: `read_offer` (Playwright, `jobs/read_job.py`) → `analyze_offer`
(Claude, `jobs/analyze_job.py`) → `write_cv` (Claude, `cv/generate.py`; Python adds dates, places,
contacts and links from the profile) → `verify_cv` (Claude, `cv/verify.py`, up to 2 rewrites) →
`compile` (`render.py` + latexmk, `layout.json` from invisible `\cvanchor` markers) → `analyze_fit`.
The frontend polls `GET /api/cvs/tasks/{id}`. A failed analysis is saved as `status: failed` and
never loses the CV.

**CV editing.** The editor sends the whole `cv.json` with `PUT /api/cvs/{cv_id}`: validation, new
`source_id`s must exist in the profile, then sections are rewritten and the PDF recompiled. If
compilation fails, the previous cv.json, sections, PDF and layout are restored (422). On success
`metadata.json.updated_at` changes; the frontend reloads the PDF and the zones for that version.

**Fit analysis.** `cv/analysis.py`, one Claude call: Python fixes the list of requirements from
`offer.json`; Claude rates each one (`met`, `partial`, `not_documented`, `missing`), writes the
overview, strengths, recommendations and interview questions; Python drops evidence that does not
exist in the profile, computes the score (`cv/fit_score.py`) and saves `analysis.json`. Reading an
analysis never calls Claude; `POST /api/cvs/{cv_id}/analysis` (re)runs it, also for older CVs.
The score is stored but not displayed.

**Deletion.** `DELETE /api/cvs/{cv_id}`: the folder is renamed to a hidden name, then removed;
409 while a generation, analysis or edit of that CV is running.

## « Mes CV » API (`api/cvs.py`)

| Route | Purpose |
|---|---|
| `POST /api/cvs/generate` | start a generation → `{task_id, status}` (202); 422 for a refused URL |
| `GET /api/cvs/tasks/{task_id}` | `status` (pending, running, completed, failed), `step`, `step_label`, `error`, `cv_id`, `result` |
| `GET /api/cvs` | saved CVs with metadata (newest creation first, unknown dates last) |
| `GET /api/cvs/{cv_id}` | `{cv, document, verification_issues}`; 409 for a CV without cv.json |
| `GET /api/cvs/{cv_id}/pdf`, `/layout` | the PDF (no cache) and its clickable zones |
| `PUT /api/cvs/{cv_id}` | save an edited cv.json and recompile (422 invalid or compile error, 409 locked) |
| `DELETE /api/cvs/{cv_id}` | delete the CV folder → 204 (404, 409) |
| `GET`/`POST /api/cvs/{cv_id}/analysis` | read the saved analysis (404 if none) / run it → 202 |

Errors always have the shape `{"detail": {"message", "problems"}}`, without server paths.

## Safety

- Offer URLs must be public pages: `jobs/url_check.py` refuses localhost, private, loopback,
  link-local and reserved addresses before navigation, and `read_job.py` re-checks every request
  and redirect inside the browser (no WebSocket/WebRTC, no images or media).
- A `cv_id` must match `^[a-z0-9][a-z0-9-]{0,150}$`, be a real folder directly in `cv/applications/`
  and not a symbolic link.
- A per-CV lock prevents two edits at once and edits during a generation; deletion is also refused
  while a generation, analysis or edit of that CV is running.

## Frontend

TanStack Start (file routes in `src/routes/`), TanStack Query, shadcn/ui. Features live in
`src/features/{candidate,import,cvs}`; all HTTP goes through `src/services/api/` (`httpClient.ts`).
`cvTypes.ts` mirrors the backend; UI-only shapes (zones, selection, steps, entries built from the
profile) are derived in `features/cvs/adapters.ts`. The PDF is rendered with pdfjs-dist; its URL and
the layout query are keyed by `updated_at`, so the preview and its zones always match.

## Limits

- Tasks are kept in memory and run one at a time (generations and analyses share one worker): a
  server restart forgets running tasks (saved CVs are kept).
- CVs created before `cv.json` cannot be edited; before the markers they have no zones; before
  `metadata.json` their creation date may be unknown.
- Claude's free text (CV wording, answer guidance of interview questions) is guided by the prompts
  and checked by `verify.py` for the CV, but cannot be fully proven against the profile.
- Generation depends on the Claude Code CLI and latexmk; tested on macOS only.
- `npm run lint` still reports old Prettier errors in files generated by Lovable/shadcn.
