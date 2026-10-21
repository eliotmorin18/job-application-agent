import { Pencil, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  candidateApi,
  type Career,
  type Personal,
  type PreferenceCategory,
  type Preferences,
} from "@/services/api/candidateApi";
import { formatDate } from "../format";
import { useCandidateAction } from "../hooks";
import { EditableTag, InlineAdd, SectionCard } from "./common";

const PERSONAL_FIELDS: { key: keyof Personal; label: string; placeholder?: string | undefined }[] = [
  { key: "first_name", label: "Prénom" },
  { key: "last_name", label: "Nom" },
  { key: "email", label: "E-mail" },
  { key: "phone", label: "Téléphone" },
  { key: "address", label: "Adresse" },
  { key: "postal_code", label: "Code postal" },
  { key: "city", label: "Ville" },
  { key: "country", label: "Pays" },
  { key: "linkedin", label: "LinkedIn", placeholder: "https://linkedin.com/in/…" },
  { key: "github", label: "GitHub", placeholder: "https://github.com/…" },
  { key: "birth_date", label: "Date de naissance", placeholder: "AAAA-MM-JJ" },
  { key: "nationality", label: "Nationalité" },
  { key: "gender", label: "Genre" },
];

// Values expected by the backend (candidate/manager.py, SECTION_SPECS["career"]), with French labels
type StatusOption = { value: string; label: string };
const ACADEMIC_STATUSES: StatusOption[] = [
  { value: "student", label: "Étudiant(e)" },
  { value: "graduated", label: "Diplômé(e)" },
];
const EMPLOYMENT_STATUSES: StatusOption[] = [
  { value: "employed", label: "En poste" },
  { value: "job_seeking", label: "En recherche d'emploi" },
  { value: "internship", label: "En stage" },
  { value: "freelance", label: "Indépendant(e)" },
  { value: "other", label: "Autre" },
];

function PersonalSection({ personal }: { personal: Personal }) {
  const run = useCandidateAction();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Personal>(personal);

  useEffect(() => {
    if (!editing) setDraft(personal);
  }, [personal, editing]);

  const save = async () => {
    const changes = Object.fromEntries(
      PERSONAL_FIELDS.map(({ key }) => [key, draft[key]?.trim() || undefined]),
    ) as Partial<Personal>;
    const ok = await run(() => candidateApi.updatePersonal(changes), "Informations personnelles enregistrées");
    if (ok) setEditing(false);
  };

  return (
    <SectionCard
      title="Informations personnelles"
      description="Utilisées en en-tête de vos CV."
      action={
        !editing && (
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
            <Pencil className="size-3.5" />
            Modifier
          </Button>
        )
      }
    >
      {editing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            {PERSONAL_FIELDS.map((f) => (
              <div key={f.key}>
                <Label htmlFor={`p-${f.key}`} className="mb-1.5 block text-xs text-muted-foreground">
                  {f.label}
                </Label>
                <Input
                  id={`p-${f.key}`}
                  value={draft[f.key] ?? ""}
                  placeholder={f.placeholder}
                  onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              Annuler
            </Button>
            <Button type="submit">Enregistrer</Button>
          </div>
        </form>
      ) : (
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          {PERSONAL_FIELDS.map((f) => (
            <div key={f.key} className="min-w-0">
              <dt className="text-xs text-muted-foreground">{f.label}</dt>
              <dd className="truncate text-sm">
                {personal[f.key] ? (
                  f.key === "birth_date" ? formatDate(personal[f.key]) : personal[f.key]
                ) : (
                  <span className="text-muted-foreground/60">Non renseigné</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </SectionCard>
  );
}

function StatusSelect({
  id,
  value,
  options,
  onChange,
}: {
  id: string;
  value?: string | undefined;
  options: StatusOption[];
  onChange: (v: string) => void;
}) {
  const all = value && !options.some((o) => o.value === value) ? [{ value, label: value }, ...options] : options;
  return (
    <Select value={value ?? ""} onValueChange={onChange}>
      <SelectTrigger id={id}>
        <SelectValue placeholder="Sélectionner" />
      </SelectTrigger>
      <SelectContent>
        {all.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function CareerSection({ career }: { career: Career }) {
  const run = useCandidateAction();
  const [grad, setGrad] = useState(career.graduation_date ?? "");
  useEffect(() => setGrad(career.graduation_date ?? ""), [career.graduation_date]);

  const update = (changes: Partial<Career>) => run(() => candidateApi.updateCareer(changes), "Situation mise à jour");

  return (
    <SectionCard title="Situation professionnelle">
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <Label htmlFor="academic_status" className="mb-1.5 block text-xs text-muted-foreground">
            Statut académique
          </Label>
          <StatusSelect id="academic_status" value={career.academic_status} options={ACADEMIC_STATUSES} onChange={(v) => update({ academic_status: v })} />
        </div>
        <div>
          <Label htmlFor="employment_status" className="mb-1.5 block text-xs text-muted-foreground">
            Statut professionnel
          </Label>
          <StatusSelect id="employment_status" value={career.employment_status} options={EMPLOYMENT_STATUSES} onChange={(v) => update({ employment_status: v })} />
        </div>
        <div>
          <Label htmlFor="graduation_date" className="mb-1.5 block text-xs text-muted-foreground">
            Date de diplomation
          </Label>
          <Input
            id="graduation_date"
            value={grad}
            placeholder="AAAA ou AAAA-MM"
            onChange={(e) => setGrad(e.target.value)}
            onBlur={() => grad !== (career.graduation_date ?? "") && update({ graduation_date: grad.trim() || undefined })}
          />
        </div>
      </div>
    </SectionCard>
  );
}

function InterestsSection({ interests, focusSignal }: { interests: string[]; focusSignal: number }) {
  const run = useCandidateAction();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focusSignal) ref.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusSignal]);
  return (
    <div ref={ref}>
      <SectionCard title="Centres d'intérêt" description="Cliquez sur un élément pour le renommer ou le supprimer.">
        <div className="flex flex-wrap items-center gap-1.5">
          {interests.map((i) => (
            <EditableTag
              key={i}
              value={i}
              onRename={(n) => run(() => candidateApi.renameInterest(i, n), "Centre d'intérêt renommé")}
              onDelete={() => run(() => candidateApi.deleteInterest(i), "Centre d'intérêt supprimé")}
            />
          ))}
          <InlineAdd label="Ajouter" placeholder="Ex. Escalade" onAdd={(v) => run(() => candidateApi.addInterest(v), "Centre d'intérêt ajouté")} />
        </div>
      </SectionCard>
    </div>
  );
}

const PREFERENCE_GROUPS: { key: PreferenceCategory; label: string; placeholder: string }[] = [
  { key: "target_roles", label: "Postes recherchés", placeholder: "Ex. ML Engineer" },
  { key: "preferred_locations", label: "Localisations souhaitées", placeholder: "Ex. Lyon" },
  { key: "employment_types", label: "Types de contrats", placeholder: "Ex. CDI" },
];

function PreferencesSection({ preferences }: { preferences: Preferences }) {
  const run = useCandidateAction();
  return (
    <SectionCard title="Préférences professionnelles" description="Servent à évaluer la pertinence des offres.">
      <div className="space-y-4">
        {PREFERENCE_GROUPS.map((g) => {
          const values = preferences[g.key] ?? [];
          return (
            <div key={g.key}>
              <p className="mb-2 text-xs font-medium text-muted-foreground">{g.label}</p>
              <div className="flex flex-wrap items-center gap-1.5">
                {values.map((v) => (
                  <Badge key={v} variant="secondary" className="h-6 gap-1 pr-1 font-normal">
                    {v}
                    <button
                      type="button"
                      aria-label={`Retirer ${v}`}
                      className="rounded-sm opacity-60 hover:opacity-100"
                      onClick={() =>
                        run(() => candidateApi.updatePreferences({ [g.key]: values.filter((x) => x !== v) }), "Préférence retirée")
                      }
                    >
                      <X className="size-3" />
                    </button>
                  </Badge>
                ))}
                <InlineAdd label="Ajouter" placeholder={g.placeholder} onAdd={(v) => run(() => candidateApi.addPreference(g.key, v), "Préférence ajoutée")} />
              </div>
            </div>
          );
        })}
      </div>
    </SectionCard>
  );
}

export function OtherTab({
  personal,
  career,
  interests,
  preferences,
  interestSignal,
}: {
  personal: Personal;
  career: Career;
  interests: string[];
  preferences: Preferences;
  interestSignal: number;
}) {
  return (
    <div className="grid gap-4">
      <PersonalSection personal={personal} />
      <CareerSection career={career} />
      <div className="grid gap-4 lg:grid-cols-2">
        <InterestsSection interests={interests} focusSignal={interestSignal} />
        <PreferencesSection preferences={preferences} />
      </div>
    </div>
  );
}
