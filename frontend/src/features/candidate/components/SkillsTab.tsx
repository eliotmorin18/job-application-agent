import { Plus, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { candidateApi } from "@/services/api/candidateApi";
import { formatCategory } from "../format";
import { useCandidateAction } from "../hooks";
import { EditableTag, EmptyState, InlineAdd } from "./common";

export function SkillsTab({ skills, addSignal }: { skills: Record<string, string[]>; addSignal: number }) {
  const run = useCandidateAction();
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState("");
  const [skill, setSkill] = useState("");

  useEffect(() => {
    if (addSignal) setOpen(true);
  }, [addSignal]);

  const categories = Object.entries(skills);

  const createCategory = async () => {
    const ok = await run(() => candidateApi.addSkill(category, skill, true), "Compétence ajoutée");
    if (ok) {
      setOpen(false);
      setCategory("");
      setSkill("");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Cliquez sur une compétence pour la renommer ou la supprimer.
        </p>
        <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
          <Plus className="size-4" />
          Nouvelle catégorie
        </Button>
      </div>

      {categories.length === 0 ? (
        <EmptyState
          icon={Sparkles}
          title="Aucune compétence pour le moment"
          text="Regroupez vos compétences par catégorie : langages, outils, domaines…"
          action={
            <Button size="sm" onClick={() => setOpen(true)}>
              <Plus className="size-4" />
              Ajouter une compétence
            </Button>
          }
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {categories.map(([cat, list]) => (
            <section key={cat} className="animate-fade-up rounded-xl border bg-card p-5 shadow-soft">
              <div className="mb-3 flex items-baseline justify-between">
                <h3 className="text-sm font-semibold">{formatCategory(cat)}</h3>
                <span className="text-xs text-muted-foreground">{list.length}</span>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {list.map((s) => (
                  <EditableTag
                    key={s}
                    value={s}
                    onRename={(n) => run(() => candidateApi.renameSkill(cat, s, n), "Compétence renommée")}
                    onDelete={() => run(() => candidateApi.deleteSkill(cat, s), "Compétence supprimée")}
                  />
                ))}
                <InlineAdd
                  label="Ajouter"
                  placeholder="Nouvelle compétence"
                  onAdd={(v) => run(() => candidateApi.addSkill(cat, v), "Compétence ajoutée")}
                />
              </div>
            </section>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Ajouter une compétence</DialogTitle>
            <DialogDescription>
              Choisissez une catégorie existante ou saisissez-en une nouvelle.
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              createCategory();
            }}
          >
            <div>
              <Label htmlFor="skill-category" className="mb-1.5 block text-xs text-muted-foreground">
                Catégorie
              </Label>
              <Input
                id="skill-category"
                list="skill-categories"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Ex. Computer Vision"
              />
              <datalist id="skill-categories">
                {categories.map(([c]) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </div>
            <div>
              <Label htmlFor="skill-name" className="mb-1.5 block text-xs text-muted-foreground">
                Compétence
              </Label>
              <Input id="skill-name" value={skill} onChange={(e) => setSkill(e.target.value)} placeholder="Ex. OpenCV" />
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                Annuler
              </Button>
              <Button type="submit">Enregistrer</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
