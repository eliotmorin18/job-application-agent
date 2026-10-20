import { createFileRoute } from "@tanstack/react-router";
import { Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/api";
import { Btn, OfferHeader, Shell } from "@/components/kit";
import { useApplication, useRefresh } from "@/lib/use-application";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/questions")({
  head: () => ({
    meta: [
      { title: "Tes réponses — Candidature" },
      { name: "description", content: "Réponds aux questions que l'agent n'a pas pu remplir seul." },
      { property: "og:title", content: "Tes réponses — Candidature" },
      { property: "og:description", content: "Réponds aux questions que l'agent n'a pas pu remplir seul." },
    ],
  }),
  component: Questions,
});

function Questions() {
  const { data } = useApplication();
  const refresh = useRefresh();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [waitingFrom, setWaitingFrom] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const chatLen = data?.chat.length ?? 0;
  const lastRole = data?.chat[chatLen - 1]?.role;

  // L'agent a répondu : fin de l'attente.
  useEffect(() => {
    if (waitingFrom !== null && chatLen > waitingFrom && lastRole === "agent") setWaitingFrom(null);
  }, [chatLen, lastRole, waitingFrom]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatLen, waitingFrom]);

  const busy = sending || waitingFrom !== null;

  async function send() {
    const t = text.trim();
    if (!t || busy) return;
    setSending(true);
    setError(null);
    try {
      await api.sendAnswers(t);
      setText(""); // vidé seulement après un envoi réussi
      setWaitingFrom(chatLen + 1);
      await refresh();
    } catch (e) {
      setError(`Envoi impossible : ${errorMessage(e)} Ton texte est conservé, tu peux renvoyer.`);
    } finally {
      setSending(false);
    }
  }

  if (!data) return <Shell>{null}</Shell>;
  const remaining = data.questions.filter((q) => !q.answered).length;

  return (
    <Shell>
      <div className="pb-64">
        <OfferHeader company={data.offer?.company} title={data.offer?.job_title} />

        <h2 className="mt-12 text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
          {remaining === 0 ? "Toutes les questions ont une réponse" : `Il me manque ${remaining} réponse${remaining > 1 ? "s" : ""}`}
        </h2>
        <ul className="mt-4 divide-y border-y">
          {data.questions.map((q) => (
            <li key={q.number} className={cn("py-4 transition-opacity", q.answered && "opacity-50")}>
              <div className="flex items-start justify-between gap-3">
                <p className="text-[15px] font-medium">
                  <span className="mr-2 tabular-nums text-muted-foreground">{q.number}</span>
                  {q.field}
                </p>
                {q.answered && (
                  <span className="flex shrink-0 items-center gap-1 text-xs text-success">
                    <Check className="h-3.5 w-3.5" /> Répondu
                  </span>
                )}
              </div>
              <p className="mt-1 pl-5 text-sm text-muted-foreground">{q.reason}</p>
              {q.options.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5 pl-5">
                  {q.options.map((o) => (
                    <span key={o} className="rounded bg-secondary px-2 py-0.5 text-xs">
                      {o}
                    </span>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>

        <div className="mt-12 flex flex-col gap-5">
          {data.chat.map((m, i) => (
            <div key={i} className={cn("flex animate-fade-in flex-col", m.role === "user" ? "items-end" : "items-start")}>
              <div
                className={cn(
                  "max-w-[85%] whitespace-pre-wrap text-[15px] leading-relaxed",
                  m.role === "user" ? "rounded-lg bg-primary px-4 py-2.5 text-primary-foreground" : "text-foreground",
                )}
              >
                {m.text}
              </div>
              <span className="mt-1.5 text-[11px] text-muted-foreground">
                {m.role === "agent" ? "Agent" : "Toi"} · {m.time}
              </span>
            </div>
          ))}
          {waitingFrom !== null && (
            <p className="animate-fade-in text-sm text-muted-foreground">L'agent lit tes réponses…</p>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="fixed inset-x-0 bottom-0 border-t bg-background">
        <div className="mx-auto max-w-2xl px-5 py-4">
          {error && <p className="mb-2 animate-fade-in text-sm text-destructive">{error}</p>}
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                send();
              }
            }}
            rows={4}
            placeholder="Réponds à tout d'un coup, en vrac : « dispo début février, vu sur LinkedIn, … »"
            className="w-full resize-none rounded-md border border-input bg-card px-3 py-2.5 text-[15px] outline-none transition focus:border-primary focus:ring-2 focus:ring-ring/15"
          />
          <div className="mt-2 flex items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">⌘ + Entrée pour envoyer</span>
            <Btn onClick={send} loading={sending} disabled={!text.trim() || waitingFrom !== null}>
              {error ? "Renvoyer" : "Envoyer"}
            </Btn>
          </div>
        </div>
      </div>
    </Shell>
  );
}
