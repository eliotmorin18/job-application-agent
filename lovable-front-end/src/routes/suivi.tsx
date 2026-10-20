import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Check } from "lucide-react";
import { useState } from "react";
import { api, errorMessage, type Step } from "@/api";
import { Btn, ErrorText, Notice, OfferHeader, Shell } from "@/components/kit";
import { CURRENT_KEY, useAction, useApplication, useReachable } from "@/lib/use-application";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/suivi")({
  head: () => ({
    meta: [
      { title: "Suivi en direct — Candidature" },
      { name: "description", content: "Les étapes de préparation de ta candidature, en direct." },
      { property: "og:title", content: "Suivi en direct — Candidature" },
      { property: "og:description", content: "Les étapes de préparation de ta candidature, en direct." },
    ],
  }),
  component: Suivi,
});

function Suivi() {
  const { data, isLoading } = useApplication();
  const reachable = useReachable();

  if (isLoading || (!data && !reachable)) return <Shell>{null}</Shell>;
  if (!data)
    return (
      <Shell>
        <p className="text-muted-foreground">Aucune candidature en cours.</p>
        <Link to="/" className="mt-4 inline-block text-sm text-primary underline-offset-4 hover:underline">
          Lancer une candidature
        </Link>
      </Shell>
    );

  return (
    <Shell>
      <OfferHeader company={data.offer?.company} title={data.offer?.job_title} />
      {data.status === "error" && data.message && (
        <div className="mt-6">
          <Notice tone="error">{data.message}</Notice>
        </div>
      )}
      <ol className="mt-12">
        {data.steps.map((s, i) => (
          <StepRow key={s.key} step={s} last={i === data.steps.length - 1} />
        ))}
      </ol>
      <div className="mt-12 border-t pt-6">
        <AbandonButton />
      </div>
    </Shell>
  );
}

function StepRow({ step, last }: { step: Step; last: boolean }) {
  const cont = useAction(api.continue);
  const retry = useAction(api.retry);
  const active = step.status === "running" || step.status === "action_required" || step.status === "error";

  return (
    <li className={cn("relative flex gap-5", last ? "" : active ? "pb-10" : "pb-6")}>
      {!last && (
        <span
          className={cn("absolute left-[7px] top-6 bottom-1 w-px", step.status === "done" ? "bg-success/30" : "bg-border")}
        />
      )}
      <span className="relative z-10 mt-1 flex h-[15px] w-[15px] shrink-0 items-center justify-center">
        {step.status === "done" && (
          <span className="flex h-[15px] w-[15px] items-center justify-center rounded-full bg-success text-primary-foreground">
            <Check className="h-2.5 w-2.5" strokeWidth={3.5} />
          </span>
        )}
        {step.status === "pending" && <span className="h-[7px] w-[7px] rounded-full bg-border" />}
        {step.status === "running" && <span className="h-[15px] w-[15px] animate-spin rounded-full border-2 border-primary border-r-transparent [animation-duration:1.2s]" />}
        {step.status === "action_required" && <span className="h-[11px] w-[11px] rounded-full bg-warning" />}
        {step.status === "error" && <span className="h-[11px] w-[11px] rounded-full bg-destructive" />}
      </span>

      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "transition-colors",
            step.status === "pending" && "text-[15px] text-muted-foreground/60",
            step.status === "done" && "text-[15px] text-muted-foreground",
            active && "text-[17px] font-semibold text-foreground",
          )}
        >
          {step.label}
        </p>
        {step.status === "running" && (
          <p className="mt-1 text-sm text-primary">{step.detail ?? "En cours…"}</p>
        )}
        {step.status === "done" && step.detail && (
          <p className="mt-0.5 text-[13px] text-muted-foreground/80">{step.detail}</p>
        )}
        {step.status === "action_required" && (
          <div className="mt-3 animate-fade-in">
            <p className="text-[15px] leading-relaxed">{step.detail ?? "Une action de ta part est nécessaire."}</p>
            <Btn variant="warning" className="mt-4" loading={cont.busy} onClick={() => cont.run()}>
              C'est fait
            </Btn>
            <ErrorText>{cont.error}</ErrorText>
          </div>
        )}
        {step.status === "error" && (
          <div className="mt-3 animate-fade-in">
            <p className="text-[15px] leading-relaxed text-destructive">{step.detail ?? "Quelque chose s'est mal passé."}</p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Btn variant="danger" loading={retry.busy} onClick={() => retry.run()}>
                Réessayer
              </Btn>
              <AbandonButton prominent />
            </div>
            <ErrorText>{retry.error}</ErrorText>
          </div>
        )}
      </div>
    </li>
  );
}

/** Abandonne la candidature en cours (le serveur arrête l'agent) et revient à l'accueil. */
function AbandonButton({ prominent = false }: { prominent?: boolean }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function abandon() {
    if (!window.confirm("Abandonner cette candidature et revenir à l'accueil ?")) return;
    setBusy(true);
    setError(null);
    try {
      await api.abandon();
      // On oublie l'ancien état avant de partir, pour que l'accueil affiche le champ URL
      qc.removeQueries({ queryKey: CURRENT_KEY });
      navigate({ to: "/" });
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <>
      <Btn variant={prominent ? "secondary" : "ghost"} loading={busy} onClick={abandon}>
        {prominent ? "Abandonner et revenir à l'accueil" : "Abandonner cette candidature"}
      </Btn>
      <ErrorText>{error}</ErrorText>
    </>
  );
}
