// « Assistant IA » mode of the CV tab: a conversation about this CV (api/assistant.py). Opening it only
// reads assistant.json; each message is one Claude call. Changes to the CV are decided, checked and
// saved by the backend (same path as the editor): this panel shows what really happened.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowUp, Check, Loader2, Undo2 } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  cvApi,
  type AssistantChange,
  type AssistantMessage,
  type AssistantResult,
  type CvSummary,
  type CvUpdateResult,
} from "@/services/api/cvApi";
import { cvAssistantQuery, errorMessage } from "../hooks";

const CHANGE_TITLES: Record<AssistantChange["status"], string> = {
  applied: "CV enregistré, PDF recompilé",
  not_applied: "Modification non appliquée",
  failed: "Échec de l'enregistrement : le CV précédent est conservé",
  undone: "Modification annulée",
};

function ChangeNote({ change }: { change: AssistantChange }) {
  const ok = change.status === "applied" || change.status === "undone";
  const lines = ok ? change.summary : change.problems;
  return (
    <div
      className={cn(
        "mt-1.5 rounded-md border px-2.5 py-1.5 text-xs",
        ok ? "bg-muted/40" : "border-priority-medium bg-priority-medium/40",
      )}
    >
      <p className="flex items-center gap-1.5 font-medium">
        {ok ? <Check className="size-3.5" /> : <AlertTriangle className="size-3.5" />}
        {CHANGE_TITLES[change.status]}
      </p>
      {lines.length > 0 && (
        <ul className="mt-0.5 space-y-0.5 text-muted-foreground">
          {lines.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Message({ message }: { message: AssistantMessage }) {
  if (message.role === "user")
    return (
      <li className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-muted px-3 py-2 text-sm">
          {message.text}
        </p>
      </li>
    );
  return (
    <li className="max-w-[92%]">
      {message.text && (
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.text}</p>
      )}
      {message.change && <ChangeNote change={message.change} />}
    </li>
  );
}

export function CvAssistantPanel({
  cv,
  dirty,
  onSaved,
}: {
  cv: CvSummary;
  /** Unsaved changes in « Modifier »: the assistant may discuss, not change the CV. */
  dirty: boolean;
  /** The CV was saved by the assistant (or an undo): same result as PUT /api/cvs/{id}. */
  onSaved: (result: CvUpdateResult) => void;
}) {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery(cvAssistantQuery(cv.id));
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [undoing, setUndoing] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const busy = pending !== null || undoing;
  const guard = { allow_changes: !dirty, base_updated_at: cv.updated_at };

  // The latest message stays in view
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [data?.messages.length, pending]);

  const received = (result: AssistantResult) => {
    qc.setQueryData(cvAssistantQuery(cv.id).queryKey, {
      messages: result.messages,
      can_undo: result.can_undo,
    });
    if (result.saved) onSaved(result.saved);
  };

  const send = async () => {
    const message = text.trim();
    if (!message || busy) return;
    setPending(message);
    setFailure(null);
    setText("");
    try {
      received(await cvApi.sendAssistantMessage(cv.id, message, guard));
    } catch (e) {
      setText(message); // nothing was recorded: the message can be sent again
      setFailure(errorMessage(e));
    } finally {
      setPending(null);
    }
  };

  const undo = async () => {
    setUndoing(true);
    setFailure(null);
    try {
      received(await cvApi.undoAssistant(cv.id, guard));
    } catch (e) {
      setFailure(errorMessage(e));
    } finally {
      setUndoing(false);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send();
    }
  };

  const messages = data?.messages ?? [];
  return (
    <section
      aria-label="Assistant IA"
      className="flex h-full flex-col rounded-xl border bg-card shadow-soft"
    >
      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-3/4" />
            <Skeleton className="ml-auto h-8 w-1/2" />
          </div>
        ) : error ? (
          <p className="flex items-start gap-2 text-sm text-muted-foreground">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
            {errorMessage(error)}
          </p>
        ) : messages.length === 0 && pending === null ? (
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>
              Discute de ton CV avec l'assistant : avis sur une formulation, autres versions, puces
              plus courtes… Colle un passage du CV pour en parler.
            </p>
            <p>
              Il ne modifie le CV que si tu le demandes clairement (« mets cette version », «
              supprime Docker des outils »), puis l'enregistre et recompile le PDF.
            </p>
          </div>
        ) : (
          <ol aria-label="Conversation" className="space-y-4">
            {messages.map((m) => (
              <Message key={m.id} message={m} />
            ))}
            {pending !== null && (
              <>
                <Message message={{ id: "pending", role: "user", text: pending, created_at: "" }} />
                <li role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  L'assistant rédige sa réponse…
                </li>
              </>
            )}
          </ol>
        )}
      </div>

      <div className="space-y-2 border-t p-3">
        {failure && (
          <p role="alert" className="flex items-start gap-1.5 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            {failure}
          </p>
        )}
        {dirty && (
          <p className="text-xs text-muted-foreground">
            Modifications non enregistrées dans « Modifier » : l'assistant peut en discuter, mais ne
            modifiera pas le CV avant que tu les enregistres ou les annules.
          </p>
        )}
        <div className="flex items-end gap-2">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            maxLength={8000}
            aria-label="Message à l'assistant"
            placeholder="Écris à l'assistant… (Entrée pour envoyer, Maj + Entrée pour aller à la ligne)"
            className="max-h-40 min-h-[2.75rem] resize-none text-sm"
          />
          <Button
            size="icon"
            className="size-9 shrink-0"
            aria-label="Envoyer"
            disabled={!text.trim() || busy}
            onClick={() => void send()}
          >
            {pending !== null ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <ArrowUp className="size-4" />
            )}
          </Button>
        </div>
        {data?.can_undo && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-muted-foreground"
            disabled={busy || dirty}
            title={dirty ? "Enregistre ou annule d'abord tes modifications manuelles" : undefined}
            onClick={() => void undo()}
          >
            {undoing ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Undo2 className="size-3.5" />
            )}
            Annuler la dernière modification de l'assistant
          </Button>
        )}
      </div>
    </section>
  );
}
