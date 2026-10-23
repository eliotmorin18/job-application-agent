# job-application-agent

## Overview

`job-application-agent` generates a tailored, one-page CV from the URL of a job offer.

You describe your background once in a local candidate profile. For each offer, the tool reads the job posting, picks the experiences and projects that matter for it, writes a CV adapted to the offer, checks that everything in it comes from your profile, and exports it to PDF with LaTeX.

The goal is a CV that fits the offer **and stays faithful to what you have actually done**. It runs locally: from the terminal, or from a local web interface (React + FastAPI) to manage the candidate profile, import a CV and prepare applications: offer analysis, interview preparation and a tailored CV to edit and download (« Mes candidatures »). No account, no database, no hosted server.

## Features

What works today:

- **Read a job offer from its URL** (company career sites, Workday, Lever, LinkedIn job pages…). LinkedIn search links are converted to the direct job page.
- **Analyze the offer with Claude**: missions, required vs. nice-to-have skills, keywords and key points, each key point backed by a quote checked against the page.
- **Select the relevant experiences and projects** from your profile (up to the limits you set).
- **Write a tailored CV** in the language of the offer, following a LaTeX template.
- **Fact-check the CV against your profile**: a second Claude call flags anything not supported by your profile, and the CV is rewritten (up to 2 times) until it is clean. Remaining issues are printed in the terminal.
- **Export to PDF** with LaTeX, and warn if the CV is longer than one page.
- **List the requirements of the offer that your profile does not cover**, so you know your gaps.
- **Manage the candidate profile from a local web interface**: view, add, edit and delete experiences, education, projects, skills, languages, interests, contact details, career status and preferences.
- **Import an existing CV (PDF)**: Claude extracts a proposal, which is compared with the profile (duplicates, uncertain fields); you choose what to add, update or skip, and can correct any extracted value, before anything is saved.
- **« Mes candidatures » in the web interface**: prepare an application from an offer URL and follow its steps, list the applications (job title, company, date), and on each application read the offer/profile match analysis, prepare the interview (advice, possible questions, and on demand a deep preparation: company with sourced facts, priorities, likely questions, knowledge to deepen, experiences to tell, points of vigilance), edit the CV (content, order, entries added from the profile) with PDF recompilation and clickable zones, download it, or delete the application. For now an application is one generated CV folder.

## How it works

```
Job offer URL
  → read the page                    jobs/read_job.py      (Playwright)
  → analyze the offer                jobs/analyze_job.py   (Claude)
  → pick and write the CV content    cv/generate.py        (Claude → structured JSON, facts added from your profile)
  → fact-check against your profile  cv/verify.py          (Claude, up to 2 rewrites)
  → convert to LaTeX                 cv/render.py          (Python, with the LaTeX template)
  → save and compile the PDF         cv/build_cv.py        (cv.json + latexmk)
  → analyse the match with the offer cv/analysis.py        (Claude; score computed in Python: cv/fit_score.py)
```

Claude never writes LaTeX: it returns the CV content as JSON (`cv/document.py`). Dates, places, contact details and links are taken from your profile, and Python turns the content into the LaTeX sections of the template. Each generated CV keeps its content in `cv.json`, which the CV editor of « Mes candidatures » modifies before recompiling the PDF.

`cv/cli.py` runs the whole pipeline. Claude is called through the Claude Code CLI (`llm/claude_cli.py`, `claude -p`), with a JSON schema that forces structured answers.

Your candidate profile is the single source of truth: verifiable facts (skills, tools, results, dates, degrees) and commitments (availability, salary…) must come from it. A few short motivation statements are allowed in the CV summary.

## Installation

### Prerequisites

- **Python 3.10+**
- **Claude Code CLI** (`claude` command), installed and logged in, in a recent version that supports `--json-schema`. The pipeline uses your Claude Code usage (subscription or API, depending on how you are logged in).
- **A LaTeX distribution with `latexmk`** and the packages used by the template (`titlesec`, `enumitem`, `fontawesome5`, `tabularx`, `hyperref`…), for example MacTeX or TeX Live.
- **Chromium for Playwright**, installed in the steps below.

The project has been developed and tested on macOS.

### Setup

```bash
git clone https://github.com/eliotmorin18/job-application-agent.git
cd job-application-agent

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

### Create your candidate profile

```bash
mkdir -p profile/private
cp profile/candidate.example.yaml profile/private/candidate.yaml
```

Then fill `profile/private/candidate.yaml` with your own information: personal details, education, experiences, projects, skills, languages, interests.

- Every experience and project needs a unique `id`: the generator selects items by id.
- `application_rules.max_cv_experiences` and `max_cv_projects` set how many items can appear on the CV.
- Put your interests in order of priority: the first ones are used first.
- Be specific: the CV can only contain what is written in the profile.

Optionally, put previous CVs written with the same LaTeX template (`.tex` files) in `cv/reference/`. They are used as **style** references only, never as a source of facts.

### Run

```bash
python -m cv.cli "<URL of the job offer>"
```

The former command `python main.py "<URL>"` still works: it delegates to `cv/cli.py`.

A browser window opens to read the page, then the pipeline takes a few minutes (several Claude calls). The terminal shows each step, the selected experiences and projects, your gaps, any remaining verification issue, and the path of the PDF:

```
cv/applications/<company>-<role>/build/<FirstName>_<LastName>_Candidature_<Company>_<Role>.pdf
```

Always read the CV before sending it.

### Web interface (candidate profile, CV import, « Mes candidatures »)

Additional prerequisites: **Node.js 22** and **[Bun](https://bun.sh)** (the frontend lockfile is `frontend/bun.lock`).

Install the frontend dependencies once:

```bash
cd frontend
bun install --frozen-lockfile
```

Then start the two parts, each in its own terminal:

```bash
# Terminal 1 — backend (from the project root, with the virtual environment activated)
source .venv/bin/activate
uvicorn api.main:app --reload
```

```bash
# Terminal 2 — frontend
cd frontend
npm run dev
```

Open **http://localhost:8080/candidat** (profile) or **http://localhost:8080/cvs** (« Mes candidatures »). The frontend calls `/api/...`; Vite forwards these calls to the backend on `http://127.0.0.1:8000`.

- Every change is saved directly in `profile/private/candidate.yaml` (comments and formatting are kept), through `candidate/manager.py`.
- CV import calls Claude through the backend only (`candidate/import_cv.py`), which can take 1 to 3 minutes. Extracted proposals are kept in `profile/private/extracted/` and can be reopened from the import page without a new extraction.
- To try the profile pages without the backend, with fictional data: create `frontend/.env.local` with `VITE_API_MODE=mock` (see `frontend/.env.example`). CV import and « Mes candidatures » are not available in this mode.
- If Node.js runs as x64 on an Apple Silicon Mac (Rosetta), install with `bun install --frozen-lockfile --cpu=x64` so that native modules match Node.

« Mes candidatures » runs generations and analyses in the background; their routes, limits and the protection of offer URLs are described in [`docs/architecture.md`](docs/architecture.md).

### Tests

```bash
python -m unittest discover tests      # Python (profile, import, API — temporary profiles, Claude mocked)
RUN_BROWSER_TESTS=1 python -m unittest tests.test_read_job_browser   # optional: real Chromium, local servers only

cd frontend
npx tsc --noEmit                        # TypeScript
npm test                                # frontend unit tests (Vitest)
npm run build                           # production build
npx eslint <files>                      # lint the files you changed (npm run lint still reports old Prettier errors)
```

## Project structure

```
job-application-agent/
├── main.py                     # former entry point, kept for compatibility (→ cv/cli.py)
├── requirements.txt
├── api/
│   ├── main.py                 # local FastAPI backend for the web interface (profile, CV import)
│   ├── cvs.py                  # « Mes candidatures » routes: generation and analysis tasks, list, read, PDF, layout, edit, delete
│   └── common.py               # shared error format and profile path
├── frontend/                   # React web interface (Lovable, TanStack Start)
├── candidate/
│   ├── profile.py              # reads and validates the candidate profile
│   ├── manager.py              # edits the profile (add, update, delete)
│   ├── import_cv.py            # CV PDF → extraction proposal (JSON)
│   ├── extract_profile.py      # CV text → profile proposal (Claude, used by import_cv.py)
│   ├── review_import.py        # compares a proposal with the profile
│   └── apply_import.py         # applies the user's decisions (all or nothing)
├── jobs/
│   ├── url_check.py            # refuses local and internal URLs (before and during the browser navigation)
│   ├── read_job.py             # reads a job offer page (Playwright)
│   └── analyze_job.py          # job offer → structured JSON (Claude)
├── cv/
│   ├── cli.py                  # command-line entry point: URL → CV PDF (python -m cv.cli)
│   ├── pipeline.py             # the generation pipeline, shared by the CLI and the API
│   ├── analysis.py             # offer/profile match analysis (analysis.json, one Claude call)
│   ├── fit_score.py            # deterministic match score (0-100) and its explanation
│   ├── generate.py             # selects profile items and writes the CV content (Claude)
│   ├── verify.py               # checks the CV against the profile (Claude)
│   ├── document.py             # structured CV (cv.json): schema, validation, save/load
│   ├── render.py               # cv.json → LaTeX sections (escaping, **bold**, layout)
│   ├── layout.py               # clickable zones of the PDF (layout.json), from invisible markers
│   ├── build_cv.py             # writes the CV folder and compiles the PDF
│   ├── metadata.py             # creation and update dates of a CV (metadata.json)
│   ├── template/               # LaTeX template (main.tex + sections/)
│   ├── reference/              # optional style references (local, ignored by Git)
│   └── applications/           # generated CVs (local, ignored by Git)
├── interview/                  # deep interview preparation (company research, preparation)
├── llm/                        # shared tools to call Claude
│   ├── claude_cli.py           # calls `claude -p` with a JSON schema (claude.ai subscription only)
│   └── structured.py           # provider-neutral facade for new AI features
├── profile/
│   ├── candidate.example.yaml  # profile template
│   └── private/                # your real profile (local, ignored by Git)
└── tests/                      # unit tests
```

See [`cv/README.md`](cv/README.md) for details on the LaTeX template and the PDF build.

## Roadmap

The application is moving from a CV-centred tool to an application-centred one (« candidature »), reusing the current CV pipeline; this transition is still to be designed. See [`docs/roadmap.md`](docs/roadmap.md) for what is implemented, decided and envisaged.

## Privacy

- Your profile (`profile/private/`), your reference CVs (`cv/reference/`) and your generated CVs (`cv/applications/`) are stored **locally** and **ignored by Git**, so they are never committed.
- **Processing is not entirely local**: the job offer, your profile and your reference CVs are sent to Claude through the Claude Code CLI to analyze the offer, write and check the CV. They are processed by Anthropic according to the terms of your Claude account.
- Do not put information in your profile that you do not want to send to the AI provider.
- Imported CVs are copied to `profile/private/imports/` and their extraction proposals are saved in `profile/private/extracted/` (both ignored by Git). The text of an imported CV is sent to Claude for extraction.
