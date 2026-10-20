import { createFileRoute, Link } from "@tanstack/react-router";
import { Check, Download, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/api";
import { Btn, ErrorText, Notice, Section, Shell } from "@/components/kit";
import { useAction, useApplication } from "@/lib/use-application";

export const Route = createFileRoute("/recap")({
  head: () => ({
    meta: [
      { title: "Récapitulatif — Candidature" },
      { name: "description", content: "Ton CV, le formulaire rempli et l'offre en bref avant d'envoyer." },
      { property: "og:title", content: "Récapitulatif — Candidature" },
      { property: "og:description", content: "Ton CV, le formulaire rempli et l'offre en bref avant d'envoyer." },
    ],
  }),
  component: Recap,
});

function Modal({ children, onClose, wide }: { children: ReactNode; onClose: () => void; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={`animate-fade-in w-full rounded-lg border bg-card shadow-xl ${wide ? "h-[90vh] max-w-4xl" : "max-w-md p-6"}`}
      >
        {children}
      </div>
    </div>
  );
}

function Confirm({ title, text, cta, danger, onConfirm, onClose, busy, error }: {
  title: string; text: string; cta: string; danger?: boolean; onConfirm: () => void; onClose: () => void;
  busy: boolean; error: string | null;
}) {
  return (
    <Modal onClose={onClose}>
      <p className="font-semibold">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{text}</p>
      <div className="mt-6 flex justify-end gap-2">
        <Btn variant="secondary" onClick={onClose} disabled={busy}>Annuler</Btn>
        <Btn variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={busy}>{error ? "Réessayer" : cta}</Btn>
      </div>
      {error && <p className="mt-3 text-right text-sm text-destructive">{error}</p>}
    </Modal>
  );
}

function List({ items, tone }: { items: string[]; tone?: "success" | "warning" }) {
  const dot = tone === "success" ? "bg-success" : tone === "warning" ? "bg-warning" : "bg-muted-foreground/50";
  return (
    <ul className="space-y-1.5">
      {items.map((i) => (
        <li key={i} className="flex gap-2.5 text-[15px]">
          <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
          {i}
        </li>
      ))}
    </ul>
  );
}

function Recap() {
  const { data } = useApplication();
  const focus = useAction(api.focusChrome);
  const submit = useAction(api.markSubmitted);
  const abandon = useAction(api.abandon);
  const [pdfOpen, setPdfOpen] = useState(false);
  const [confirm, setConfirm] = useState<null | "submit" | "abandon">(null);
  const [cvUrl, setCvUrl] = useState("");

  useEffect(() => setCvUrl(api.cvUrl()), [data?.id]);

  if (!data) return <Shell>{null}</Shell>;
  const o = data.offer;

  if (data.status === "submitted" || data.status === "abandoned") {
    const ok = data.status === "submitted";
    return (
      <Shell width="max-w-xl">
        <div className="animate-fade-in pt-16">
          {ok && (
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-success text-primary-foreground">
              <Check className="h-5 w-5" strokeWidth={3} />
            </span>
          )}
          <h1 className="mt-5 text-2xl font-semibold tracking-tight">
            {ok ? "Candidature enregistrée" : "Offre abandonnée"}
          </h1>
          <p className="mt-1 text-muted-foreground">
            {o?.job_title} — {o?.company}
          </p>
          <Link to="/" className="mt-8 inline-block">
            <Btn>Nouvelle candidature</Btn>
          </Link>
        </div>
      </Shell>
    );
  }

  const meta = [o?.location, o?.contract_type, o?.job_level].filter(Boolean);

  return (
    <Shell width="max-w-3xl">
      <div className="space-y-12">
        <header className="animate-fade-in">
          <p className="text-sm text-muted-foreground">{o?.company}</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">{o?.job_title}</h1>
          {meta.length > 0 && <p className="mt-3 text-sm text-muted-foreground">{meta.join("  ·  ")}</p>}
        </header>

        <Section title="Ton CV">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
            <button
              onClick={() => setPdfOpen(true)}
              className="relative h-[198px] w-[140px] shrink-0 overflow-hidden rounded-md border bg-card shadow-sm transition hover:border-primary"
              aria-label="Ouvrir le CV en grand"
            >
              {cvUrl && (
                <iframe
                  src={`${cvUrl}#toolbar=0&navpanes=0&view=Fit`}
                  title="Aperçu du CV"
                  className="pointer-events-none h-[792px] w-[560px] origin-top-left scale-[0.25]"
                />
              )}
              <span className="absolute inset-0" />
            </button>
            <div className="flex-1 space-y-4">
              <a href={cvUrl} download="CV.pdf" className="inline-block">
                <Btn variant="secondary"><Download className="h-4 w-4" /> Télécharger</Btn>
              </a>
              {data.cv && data.cv.verification_issues.length > 0 && (
                <Notice tone="warning">
                  <p className="mb-1.5 font-medium">À vérifier</p>
                  <List items={data.cv.verification_issues} tone="warning" />
                </Notice>
              )}
            </div>
          </div>
        </Section>

        <Section title="La candidature">
          <Btn variant="secondary" loading={focus.busy} onClick={() => focus.run()}>Ouvrir le formulaire rempli</Btn>
          <ErrorText>{focus.error}</ErrorText>
          {data.answers_filled.length > 0 && (
            <dl className="mt-6 divide-y">
              {data.answers_filled.map((a) => (
                <div key={a.field} className="grid gap-1 py-3 sm:grid-cols-[180px_1fr] sm:gap-6">
                  <dt className="text-sm text-muted-foreground">{a.field}</dt>
                  <dd className="text-[15px] leading-relaxed">{a.value}</dd>
                </div>
              ))}
            </dl>
          )}
          {data.manual.length > 0 && (
            <div className="mt-8">
              <p className="mb-3 text-sm font-medium">À faire par toi</p>
              <div className="space-y-2">
                {data.manual.map((m) => (
                  <Notice key={m.field} tone="warning">
                    <span className="font-medium">{m.field}</span>
                    <span className="text-muted-foreground"> — {m.reason}</span>
                  </Notice>
                ))}
              </div>
            </div>
          )}
        </Section>

        {o && (
          <Section title="L'offre en bref">
            <div className="space-y-8">
              {o.summary && <p className="text-[15px] leading-relaxed">{o.summary}</p>}
              {o.key_points.length > 0 && (
                <div className="space-y-4">
                  {o.key_points.map((k) => (
                    <div key={k.point}>
                      <p className="text-[15px] font-medium">{k.point}</p>
                      <p className="mt-1 text-sm italic text-muted-foreground">« {k.quote} »</p>
                    </div>
                  ))}
                </div>
              )}
              <div className="grid gap-8 sm:grid-cols-2">
                <div>
                  <p className="mb-2 text-sm font-medium">Indispensable</p>
                  <List items={o.must_have} />
                </div>
                <div>
                  <p className="mb-2 text-sm font-medium">En plus</p>
                  <List items={o.nice_to_have} />
                </div>
              </div>
              {o.practical_info.length > 0 && (
                <div>
                  <p className="mb-2 text-sm font-medium">Infos pratiques</p>
                  <List items={o.practical_info} />
                </div>
              )}
            </div>
          </Section>
        )}

        <Section title="Ton profil face à l'offre">
          <div className="grid gap-8 sm:grid-cols-2">
            <div>
              <p className="mb-3 text-sm font-medium text-success">Tes points forts</p>
              <List items={data.strengths} tone="success" />
            </div>
            <div>
              <p className="mb-3 text-sm font-medium text-warning">Ce qui te manque</p>
              <List items={data.gaps} tone="warning" />
            </div>
          </div>
        </Section>

        <div className="flex flex-col items-stretch gap-4 border-t pt-10 sm:flex-row-reverse sm:items-center sm:justify-between">
          <Btn className="h-11 px-6 text-[15px]" onClick={() => setConfirm("submit")}>J'ai envoyé ma candidature</Btn>
          <Btn variant="ghost" className="h-auto self-center text-[13px]" onClick={() => setConfirm("abandon")}>
            Abandonner cette offre
          </Btn>
        </div>
      </div>

      {pdfOpen && (
        <Modal wide onClose={() => setPdfOpen(false)}>
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b px-4 py-2">
              <p className="text-sm font-medium">Ton CV</p>
              <button onClick={() => setPdfOpen(false)} aria-label="Fermer" className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>
            <iframe src={cvUrl} title="CV" className="flex-1 rounded-b-lg" />
          </div>
        </Modal>
      )}
      {confirm === "submit" && (
        <Confirm
          title="Tu as bien envoyé ta candidature ?"
          text="Elle sera enregistrée comme envoyée."
          cta="Oui, c'est envoyé"
          onClose={() => setConfirm(null)}
          busy={submit.busy}
          error={submit.error}
          onConfirm={async () => { if (await submit.run()) setConfirm(null); }}
        />
      )}
      {confirm === "abandon" && (
        <Confirm
          title="Abandonner cette offre ?"
          text="L'agent arrête de travailler dessus. Tu ne pourras pas la reprendre."
          cta="Abandonner"
          danger
          onClose={() => setConfirm(null)}
          busy={abandon.busy}
          error={abandon.error}
          onConfirm={async () => { if (await abandon.run()) setConfirm(null); }}
        />
      )}
    </Shell>
  );
}
