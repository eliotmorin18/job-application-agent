import { Languages, Plus, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { candidateApi, type Language } from "@/services/api/candidateApi";
import { useCandidateAction } from "../hooks";
import { ConfirmDialog, EmptyState } from "./common";

export const LANGUAGE_LEVELS = ["Native", "C2", "C1", "B2", "B1", "A2", "A1"];

function LevelSelect({ value, onChange, className }: { value: string; onChange: (v: string) => void; className?: string | undefined }) {
  const levels = LANGUAGE_LEVELS.includes(value) ? LANGUAGE_LEVELS : [value, ...LANGUAGE_LEVELS];
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={className} aria-label="Niveau">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {levels.map((l) => (
          <SelectItem key={l} value={l}>
            {l === "Native" ? "Natif (Native)" : l}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function LanguagesTab({ languages, addSignal }: { languages: Language[]; addSignal: number }) {
  const run = useCandidateAction();
  const [name, setName] = useState("");
  const [level, setLevel] = useState("B2");
  const [toDelete, setToDelete] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (addSignal) inputRef.current?.focus();
  }, [addSignal]);

  const add = async () => {
    const ok = await run(() => candidateApi.addLanguage(name, level), "Langue ajoutée");
    if (ok) setName("");
  };

  return (
    <div className="space-y-4">
      {languages.length === 0 ? (
        <EmptyState icon={Languages} title="Aucune langue pour le moment" text="Ajoutez les langues que vous parlez et votre niveau." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-soft">
          <div className="grid grid-cols-[1fr_10rem_2.5rem] items-center border-b bg-muted/50 px-5 py-2 text-xs font-medium text-muted-foreground">
            <span>Langue</span>
            <span>Niveau</span>
            <span />
          </div>
          {languages.map((l) => (
            <div key={l.language} className="grid grid-cols-[1fr_10rem_2.5rem] items-center border-b px-5 py-2 last:border-b-0">
              <span className="text-sm font-medium">{l.language}</span>
              <LevelSelect
                value={l.level}
                className="h-8 w-36"
                onChange={(v) => run(() => candidateApi.updateLanguageLevel(l.language, v), "Niveau mis à jour")}
              />
              <Button
                size="icon"
                variant="ghost"
                className="size-8 text-muted-foreground hover:text-destructive"
                aria-label={`Supprimer ${l.language}`}
                onClick={() => setToDelete(l.language)}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
        </div>
      )}

      <form
        className="flex flex-col gap-2 rounded-xl border border-dashed bg-card p-3 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
      >
        <Input ref={inputRef} value={name} onChange={(e) => setName(e.target.value)} placeholder="Nouvelle langue, ex. Italien" className="sm:flex-1" />
        <LevelSelect value={level} onChange={setLevel} className="sm:w-40" />
        <Button type="submit" variant="outline">
          <Plus className="size-4" />
          Ajouter
        </Button>
      </form>

      <ConfirmDialog
        open={toDelete !== null}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Supprimer cette langue ?"
        description={`« ${toDelete ?? ""} » sera retirée de votre profil.`}
        onConfirm={() => toDelete && run(() => candidateApi.deleteLanguage(toDelete), "Langue supprimée")}
      />
    </div>
  );
}
