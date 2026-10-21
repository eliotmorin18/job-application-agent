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
- UI components read/write candidate data only through `src/services/api/candidateApi.ts` (implements `CandidateApi`); swap the mock for an HTTP client to connect FastAPI without touching the UI.
- Candidate data keys stay snake_case to match the Python backend contract in `src/services/api/types.ts`.
- Items without an `id` (legacy education) are addressed as `index-N` via `getItemKey`, so ids stay backend-owned.
- Routing uses TanStack Router (fixed by the platform), not React Router; candidate tabs live in the `?tab=` search param.
