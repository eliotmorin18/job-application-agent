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
- Claude is only reached through `llm/claude_cli.py` (`claude -p` with a JSON schema):
  Claude returns structured data, Python validates it, writes files and never lets Claude write
  LaTeX or choose ids that do not exist in the profile.
- Every call uses the claude.ai subscription of the connected Claude Code account, never an API
  key: the variables that would switch to API billing (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
  `ANTHROPIC_BASE_URL`, Bedrock, Vertex) are removed from the environment, and `claude auth status`
  is checked BEFORE each call (cached 5 minutes): nothing runs unless the method is `claude.ai`.
  `--bare` is never used (it skips the macOS keychain, hence the claude.ai login).
- `run_claude` serves the existing calls unchanged. `run_claude_task` serves light calls (interview
  preparation): one attempt, temporary working directory, short system prompt, no MCP, no skills,
  optional WebSearch/WebFetch, `--max-budget-usd` cap, consulted pages read from `stream-json`.
  New business modules go through the facade `llm/structured.py` (`generate_structured`): they
  describe what they need (schema, web research, model tier) without knowing the provider.
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
`compile` (`render.py` + latexmk, `layout.json` from invisible `\cvanchor` markers; one page at
most, see below) → `analyze_fit`. The interview preparation is never started here.
The frontend polls `GET /api/cvs/tasks/{id}`. A failed analysis is saved as `status: failed` and
never loses the CV.

**One page at most.** The page count is read from the PDF itself (pypdf; unknown counts as a
failure). `build_cv.fit_one_page` brings a longer CV back to one page without calling Claude:
it removes secondary content from the end of each list (Claude orders lists by relevance), one
reduction per compilation (at most 6): secondary bullets of projects and education, last project,
education beyond two entries, experience bullets beyond two, interests beyond three, last
experience. Nothing is rewritten. The adjustments are saved in `selection.json`
(`page_adjustments`) and shown after the generation. If one page cannot be reached, the full CV is
restored, the generation fails (`CvTooLongError`, no analysis) and the folder stays available to be
shortened in the editor. A generation with more than one page is never reported as a success.

**CV editing.** The editor sends the whole `cv.json` with `PUT /api/cvs/{cv_id}`: validation, new
`source_id`s must exist in the profile, then sections are rewritten and the PDF recompiled. If
compilation fails or the PDF has more than one page, the previous cv.json, sections, PDF and
layout are restored (422). On success
`metadata.json.updated_at` changes; the frontend reloads the PDF and the zones for that version.

**Fit analysis.** `cv/analysis.py`, one Claude call: Python fixes the list of requirements from
`offer.json`; Claude rates each one (`met`, `partial`, `not_documented`, `missing`), writes the
overview and the strengths (no interview content: `recommendations` is kept empty, and the
`recommendations`/`interview_questions` of older analyses are read as they are, never shown in
« Vue d'ensemble », and reused by the interview preparation); Python drops evidence that does not
exist in the profile (experiences, projects, education, skills, languages and, since this version,
interests), marks a requirement or part whose words repeat an earlier one as `duplicate_of`, copies
`company_activity` from the offer extraction into `offer`, computes the score (`cv/fit_score.py`) and saves `analysis.json`. Reading an
analysis never calls Claude; `POST /api/cvs/{cv_id}/analysis` (re)runs it, also for older CVs.
The score is stored but not displayed.

**Interview preparation.** `interview/`, on demand only (never during generation), at most two
calls. `POST /api/cvs/{cv_id}/preparation` requires `offer.json` and a completed analysis, and is
refused once `preparation.json` exists (no regeneration).
1. `research.py`: company research (tier `light` = Sonnet, WebSearch/WebFetch, 150 s, budget cap).
   It receives only the company, job title, location, offer summary, offer domain and today's date,
   never the profile. Python keeps a fact only if its URL was really returned by a tool during the
   call, its numbers appear in what the tool returned for that page, and a news item is dated and
   less than 18 months old; otherwise the fact is dropped. Saved in `company_research.json` (also
   `ambiguous`/`not_found`) and reused on the next attempt; a failed research is not saved and the
   preparation continues with the offer only.
2. `preparation.py`: personalised preparation (default model, no tools, 300 s, budget cap) from a
   compact input: offer, requirements with their analysis status, strengths, recommendations,
   existing interview questions (by id, without their guidance), company facts (without URLs),
   profile filtered (cited elements in detail, others on one line, no contact or personal data),
   CV summary. Existing questions are kept as they are; Claude only writes the missing ones (5 to 8
   in total). Python checks every id, evidence and limit, computes the kind of each point of
   vigilance from the analysis statuses, and writes `preparation.json` atomically. On failure
   nothing is written (no "failed" file). Reading a preparation never calls Claude.

**Deletion.** `DELETE /api/cvs/{cv_id}`: the folder is renamed to a hidden name, then removed;
409 while a generation, analysis or edit of that CV is running.

## « Mes candidatures » API (`api/cvs.py`)

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
| `GET`/`POST /api/cvs/{cv_id}/preparation` | read the saved interview preparation (404 if none) / generate it once → 202 (409 if it exists, is running, or lacks offer or completed analysis) |

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

« Mes candidatures » (routes `/cvs` and `/cvs/$cvId`, formerly « Mes CV ») presents each CV folder as
an application: the title is the job title of the offer (else the role of the CV, else the folder
name). The application page has a compact header (title, company, location and contract from the
analysis, « Télécharger le CV », « Voir l'offre », a discreet « Supprimer » with confirmation) and three tabs in `?tab=`:
`analyse` (« Vue d'ensemble »), `edition` (« CV ») and `preparation` (« Entretien »); unknown values
fall back to `analyse`. `OverviewTab` presents the saved analysis in two columns (page width up to 88rem; the
« Entretien » tab keeps 72rem for readable lines). « Le poste et l'entreprise »: « L'entreprise » (first sentence of
`offer.company_activity`, else of an activity the deep preparation kept from the offer; hidden when
unknown or when it only repeats the job), « Le poste en bref » (two summary sentences), up to four missions (a mission that repeats an earlier one in other words is skipped; « Voir
toutes les missions » shows the full list), two example tasks that do not repeat a shown mission, up to six
technical keywords (no personal qualities, sentences or general terms covered by a more precise one;
« PyTorch ou TensorFlow » when the offer gives alternatives; essential requirements first). « Mon profil
pour ce poste »: three strengths (title + first sentence, evidence kept in the data and in the
requirements), at most two attention points among required requirements (not met, then essential
partial, then essential not documented, each with its own wording). « Exigences détaillées » is folded
below, in three groups: « Obligatoires » (conditions — education, experience, languages — and required
skills of normal importance), « Essentielles » (required skills the offer stresses), « Souhaitées ».
`requirementLines` gives one line per requirement of the offer, its split parts gathered under it
(`parent_id`); the overall status is shown only when reliable (same status for all parts; the best
one when the offer writes the parts as alternatives with « ou »/« or »; « non remplie » when they are
joined by « et »/« and » and one is not met), otherwise the statuses of the parts are counted. A click
opens the criteria, their own status, justification and profile references under the line, one at a
time. Equivalent requirements are shown once (`duplicate_of`, or the same words in the same order). Selection is done in `features/cvs/adapters.ts` and never rewrites a text; `warnings`
(technical diagnostics) and the score are not shown; `PreparationTab` shows the saved deep preparation
in six folded sections, or only a short presentation and the « Générer ma préparation » button. Only the interface changed: the API, files and code names keep `cv`.

## Limits

- Tasks are kept in memory and run one at a time (generations, analyses and preparations share one worker): a
  server restart forgets running tasks (saved CVs are kept).
- CVs created before `cv.json` cannot be edited; before the markers they have no zones; before
  `metadata.json` their creation date may be unknown.
- Claude's free text (CV wording, answer guidance of interview questions) is guided by the prompts
  and checked by `verify.py` for the CV, but cannot be fully proven against the profile.
- Company research can only check that a source was returned by a tool and that its numbers
  appear in it, not that it supports every word of a fact; the interface asks to verify sources.
- Interview preparation consumes the Claude Code subscription quota (two calls at most); the
  budget caps are estimates in API-equivalent dollars used as quota limits.
- Generation depends on the Claude Code CLI and latexmk; tested on macOS only.
- `npm run lint` still reports old Prettier errors in files generated by Lovable/shadcn.
