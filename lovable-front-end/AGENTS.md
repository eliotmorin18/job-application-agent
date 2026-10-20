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

- All backend calls and types live in src/api.ts (incl. demo simulation) — single file to plug into the local Python agent.
- Client-only rendering (defaultSsr: false in src/start.ts) — local single-user app.
- Status-based redirects live only in useApplication (src/lib/use-application.ts).
