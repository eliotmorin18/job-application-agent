# job-application-agent

## Overview

`job-application-agent` generates a tailored, one-page CV from the URL of a job offer.

You describe your background once in a local candidate profile. For each offer, the tool reads the job posting, picks the experiences and projects that matter for it, writes a CV adapted to the offer, checks that everything in it comes from your profile, and exports it to PDF with LaTeX.

The goal is a CV that fits the offer **and stays faithful to what you have actually done**. It runs locally from the terminal: no account, no server, no web interface.

## Features

What works today:

- **Read a job offer from its URL** (company career sites, Workday, Lever, LinkedIn job pages…). LinkedIn search links are converted to the direct job page.
- **Analyze the offer with Claude**: missions, required vs. nice-to-have skills, keywords and key points, each key point backed by a quote checked against the page.
- **Select the relevant experiences and projects** from your profile (up to the limits you set).
- **Write a tailored CV** in the language of the offer, following a LaTeX template.
- **Fact-check the CV against your profile**: a second Claude call flags anything not supported by your profile, and the CV is rewritten (up to 2 times) until it is clean. Remaining issues are printed in the terminal.
- **Export to PDF** with LaTeX, and warn if the CV is longer than one page.
- **List the requirements of the offer that your profile does not cover**, so you know your gaps.

## How it works

```
Job offer URL
  → read the page                    browser/read_job.py   (Playwright)
  → analyze the offer                llm/analyze_job.py    (Claude)
  → pick and write the CV content    llm/generate_cv.py    (Claude + your profile + LaTeX template)
  → fact-check against your profile  llm/verify_cv.py      (Claude, up to 2 rewrites)
  → build and compile the PDF        cv/build_cv.py        (latexmk)
```

`main.py` runs the whole pipeline. Claude is called through the Claude Code CLI (`claude -p`), with a JSON schema that forces structured answers.

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
python main.py "<URL of the job offer>"
```

A browser window opens to read the page, then the pipeline takes a few minutes (several Claude calls). The terminal shows each step, the selected experiences and projects, your gaps, any remaining verification issue, and the path of the PDF:

```
cv/applications/<company>-<role>/build/<FirstName>_<LastName>_Candidature_<Company>_<Role>.pdf
```

Always read the CV before sending it.

### Tests

```bash
python -m unittest discover tests
```

## Project structure

```
job-application-agent/
├── main.py                     # command-line entry point: URL → CV PDF
├── requirements.txt
├── candidate/
│   ├── profile.py              # reads and validates the candidate profile
│   └── manager.py              # edits the profile (adding an experience for now)
├── browser/
│   └── read_job.py             # reads a job offer page (Playwright)
├── llm/
│   ├── claude_cli.py           # calls `claude -p` with a JSON schema
│   ├── analyze_job.py          # job offer → structured JSON
│   ├── generate_cv.py          # selects profile items and writes the CV sections
│   └── verify_cv.py            # checks the CV against the profile
├── cv/
│   ├── build_cv.py             # writes the LaTeX files and compiles the PDF
│   ├── template/               # LaTeX template (main.tex + sections/)
│   ├── reference/              # optional style references (local, ignored by Git)
│   └── applications/           # generated CVs (local, ignored by Git)
├── profile/
│   ├── candidate.example.yaml  # profile template
│   └── private/                # your real profile (local, ignored by Git)
└── tests/                      # unit tests
```

See [`cv/README.md`](cv/README.md) for details on the LaTeX template and the PDF build.

## Roadmap

Already working: everything listed in [Features](#features).

Planned:

- **Complete, editable candidate profile**: manage experiences, projects, skills and education without editing YAML by hand.
- **Import an existing CV (PDF)** to initialize the profile.
- **More explainable matching**: show why each experience or project was selected for an offer.
- **Graphical interface**.
- **More features**: read the candidate's GitHub projects, edit the CV with the AI, track applications.
- **Possibly later**: automate the applications themselves.

## Privacy

- Your profile (`profile/private/`), your reference CVs (`cv/reference/`) and your generated CVs (`cv/applications/`) are stored **locally** and **ignored by Git**, so they are never committed.
- **Processing is not entirely local**: the job offer, your profile and your reference CVs are sent to Claude through the Claude Code CLI to analyze the offer, write and check the CV. They are processed by Anthropic according to the terms of your Claude account.
- Do not put information in your profile that you do not want to send to the AI provider.
