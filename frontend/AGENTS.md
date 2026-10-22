<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Architecture rules
- UI components read/write candidate data only through `src/services/api/candidateApi.ts` (implements `CandidateApi`): the FastAPI HTTP client by default, the in-memory mock only with `VITE_API_MODE=mock`.
- Candidate data keys stay snake_case to match the Python backend contract in `src/services/api/types.ts`.
- Items without an `id` (legacy education) are addressed as `index-N` via `getItemKey`, so ids stay backend-owned.
- Routing uses TanStack Router (fixed by the platform), not React Router; candidate tabs live in the `?tab=` search param.
- "Mes candidatures" (routes `/cvs`, feature folder `features/cvs`, formerly "Mes CV") data flows only through `src/services/api/cvApi.ts` (HTTP client of FastAPI `api/cvs.py`, implements `CvApi` in `cvTypes.ts`); types mirror the backend exactly (`cv.json`, `analysis.json`, `layout.json`), there is no demo data and no mock fallback: errors (backend down, 404, 409, 422) are shown as they are.
- UI-only shapes (clickable zones, selection, generation steps, entries added from the profile) are derived in `src/features/cvs/adapters.ts`; never change `cvTypes.ts` to fit the UI.
- PDFs are compiled by the backend (LaTeX) and rendered with pdfjs-dist; the PDF URL and the `layout.json` query are keyed by the CV `updated_at`, so preview and zones always belong to the same compiled version.
- The fit score of `analysis.json` is never displayed (product choice).
- Long-running work (CV generation, offer analysis) runs as backend tasks polled through `GET /api/cvs/tasks/{id}` (`CvTask`), never as fake instant success.
