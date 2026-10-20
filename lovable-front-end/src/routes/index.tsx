import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { api, errorMessage } from "@/api";
import { Btn, ErrorText, Shell } from "@/components/kit";
import { pathForStatus, useApplication, useRefresh } from "@/lib/use-application";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Nouvelle candidature" },
      { name: "description", content: "Colle l'URL d'une offre d'emploi et laisse l'agent préparer ta candidature." },
      { property: "og:title", content: "Nouvelle candidature" },
      { property: "og:description", content: "Suivi d'une candidature préparée par ton agent local." },
    ],
  }),
  component: Home,
});

function Home() {
  const { data, isLoading } = useApplication({ follow: false, poll: false });
  const refresh = useRefresh();
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inProgress = data && data.status !== "submitted" && data.status !== "abandoned";

  async function launch(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createApplication(url.trim());
      await refresh();
      navigate({ to: "/suivi" });
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Shell width="max-w-xl">
      <div className="pt-10 sm:pt-20">
        <h1 className="text-3xl font-semibold tracking-tight">Nouvelle candidature</h1>
        <p className="mt-3 text-muted-foreground">
          Colle le lien de l'offre. L'agent s'occupe du reste.
        </p>

        {isLoading ? null : inProgress ? (
          <div className="mt-10 animate-fade-in border-l-2 border-primary pl-4">
            <p className="text-sm font-medium">Candidature en cours</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {data.offer?.job_title ? `${data.offer.job_title} — ${data.offer.company ?? ""}` : data.url}
            </p>
            <Link
              to={pathForStatus(data.status)}
              className="mt-3 inline-block text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              Reprendre →
            </Link>
          </div>
        ) : (
          <form onSubmit={launch} className="mt-10">
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                type="url"
                required
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://…"
                className="h-11 flex-1 rounded-md border border-input bg-card px-3 text-[15px] outline-none transition focus:border-primary focus:ring-2 focus:ring-ring/15"
              />
              <Btn type="submit" loading={busy} className="h-11 px-5">
                Lancer
              </Btn>
            </div>
            <ErrorText>{error}</ErrorText>
          </form>
        )}
      </div>
    </Shell>
  );
}
