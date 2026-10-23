# Roadmap

State on branch `refactor/mvp-cv`. How the implemented parts work: [architecture.md](architecture.md).

## Implemented

- **Candidate profile**: local YAML profile, edited from the « Candidat » pages.
- **CV import**: PDF → extraction by Claude → comparison with the profile → user decisions applied.
- **CV pipeline**: offer URL → offer reading and analysis → tailored CV (`cv.json`) checked against the
  profile → LaTeX PDF with clickable zones; from the CLI or the web interface.
- **« Mes candidatures »** (formerly « Mes CV », routes `/cvs`): list of applications (job title,
  company, date), preparation from an offer URL with progress, application page with three tabs
  (« Offre et adéquation », « Préparation à l'entretien », « CV » with the editor and PDF
  recompilation), CV download, deletion, real creation dates for new applications. Interface only:
  one application is still one CV folder.
- **Fit analysis**: offer explained, requirements rated with verified evidence, strengths and
  weaknesses (score computed but not shown). Interview content comes only from the deep preparation.
- **One-page CV**: real page count of the PDF; a longer CV is shortened by removing its least
  relevant content (no Claude call), otherwise the generation fails; editor changes that would
  create a second page are refused.
- **Deep interview preparation** (on demand, saved once in `preparation.json`): company understood
  from the offer and sourced web research, priorities, likely questions (existing ones reused),
  knowledge to deepen, real experiences to prepare, points of vigilance. At most two Claude calls,
  with the claude.ai subscription only.

## Validated decisions

- **Application-centred product.** The app moves from a CV-centred tool to an application-centred
  one: an application (« candidature ») is a potential job opportunity that may hold an offer, a
  tailored CV, a cover letter, a status, notes and other information.
- **Reuse the CV pipeline.** The existing pipeline (offer reading, CV generation, verification,
  compilation, analysis) is kept and reused as much as possible.
- **Still to design**: the application data model and the migration of the existing
  `cv/applications/` folders. None of them exists yet; the interface already speaks of
  applications (first step, no backend change).
- **Manual submission.** Initial tracking relies on the user submitting each application
  themselves. Automating submission is only a possibility, not decided.
- **One offer at a time**, chosen by the user; never bulk applications.
- **Profile as the only source of facts**; the fit score is not displayed.
- **Claude Code subscription only** for the V0: no API key, no API billing, never `--bare`. New AI
  features go through `llm/structured.py` so that other providers can be added later.

## Next steps

1. Design the transition to applications: data model, link with the existing CV folders,
   migration, API and screens. To be validated before any implementation.
2. Build application tracking (statuses, board) in « Mes candidatures ».

## Known issues

- CV quality: dates of an ongoing experience in the gaps (Claude does not know today's date),
  wording sometimes stronger than the profile not caught by the verification, degree status
  (« Étudiant » vs studies completed).
- Running tasks are lost when the server restarts.
- One application is one CV folder: preparing an application twice for the same offer gives two
  applications.
- Old Prettier errors in Lovable/shadcn files (`npm run lint`).

## Possible evolutions (not decided)

- Cover letters generated from the profile and the offer.
- Profile enrichment from GitHub or LinkedIn.
- Interview preparation beyond the deep preparation (regeneration, simulation, audio).
- Explaining why each experience or project was selected; AI-assisted CV editing.
- A « Paramètres » section.
- Filling or submitting applications automatically (an older prototype exists on `main`).
