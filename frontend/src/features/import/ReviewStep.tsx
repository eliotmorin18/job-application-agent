import { AlertTriangle, Info } from "lucide-react";
import type { ReactNode } from "react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ImportReview, ItemProposal } from "@/services/api/types";
import { formatCategory } from "../candidate/format";
import { sectionConfig } from "../candidate/sectionConfig";
import { CorrectableName, CorrectableValue, fieldType, StatusMayChange } from "./corrections";
import {
  correctedMatchFields,
  correctedNameMatches,
  defaultUpdateFields,
  skillInProfile,
  unavailableActions,
  ITEM_SECTION_KEYS,
  type CorrectedValue,
  type Choices,
  type InterestChoice,
  type ItemChoice,
  type ItemSectionKey,
  type LanguageChoice,
  type SkillChoice,
} from "./decisions";
import type { CandidateProfile } from "@/services/api/types";
import {
  ActionToggle,
  CheckLine,
  fieldLabel,
  ProblemList,
  StatusBadge,
  STATUS_LABELS,
  Uncertain,
  UnavailableNote,
  Value,
} from "./parts";

type Update = (fn: (c: Choices) => Choices) => void;

const toggle = (list: string[], value: string, on: boolean) =>
  on ? (list.includes(value) ? list : [...list, value]) : list.filter((v) => v !== value);

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: ReactNode;
}) {
  if (!count) return null;
  return (
    <section className="space-y-3">
      <h2 className="flex items-baseline gap-2 text-sm font-semibold">
        {title}
        <span className="text-xs font-normal text-muted-foreground">{count}</span>
      </h2>
      {children}
    </section>
  );
}

function itemTitle(section: ItemSectionKey, data: Record<string, unknown>) {
  const s = (k: string) => (typeof data[k] === "string" ? (data[k] as string) : "");
  if (section === "experiences")
    return [s("title"), s("company")].filter(Boolean).join(" — ") || "Expérience";
  if (section === "education")
    return [s("degree"), s("school")].filter(Boolean).join(" — ") || "Formation";
  return s("name") || "Projet";
}

// ---------- Expériences, formations, projets ----------

function ItemCard({
  section,
  proposal,
  choice,
  setChoice,
  problems,
  profile,
}: {
  section: ItemSectionKey;
  proposal: ItemProposal;
  choice: ItemChoice;
  setChoice: (c: ItemChoice) => void;
  problems?: string[] | undefined;
  profile?: CandidateProfile | undefined;
}) {
  const match = proposal.matches[choice.target];
  const sameName = correctedNameMatches(section, choice, proposal, profile);
  const uncertain = (f: string) => proposal.uncertain_fields.includes(f);
  const fields = Object.keys(proposal.data);
  const changedMatch =
    choice.action === "skip" ? [] : correctedMatchFields(section, choice, proposal);

  // A correction is kept in the page state only; the corrected field is taken automatically
  const correct = (f: string, value: CorrectedValue) => {
    const key = choice.action === "update" ? "updateFields" : "addFields";
    setChoice({
      ...choice,
      corrections: { ...choice.corrections, [f]: value },
      [key]: toggle(choice[key], f, true),
    });
  };
  const reset = (f: string) => {
    const { [f]: _removed, ...rest } = choice.corrections;
    setChoice({ ...choice, corrections: rest });
  };

  return (
    <article
      id={`proposal-${proposal.proposal_id}`}
      className="rounded-xl border bg-card p-5 shadow-soft"
    >
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">
              {itemTitle(section, { ...proposal.data, ...choice.corrections })}
            </h3>
            <StatusBadge status={proposal.status} />
          </div>
          {proposal.matches.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              Ressemble à :{" "}
              {proposal.matches
                .map(
                  (m) =>
                    `${itemTitle(section, m.existing)} (${m.reasons.join(", ") || STATUS_LABELS[m.level].toLowerCase()})`,
                )
                .join(" · ")}
            </p>
          )}
        </div>
        <ActionToggle
          value={choice.action}
          onChange={(action) => setChoice({ ...choice, action })}
          options={[
            { value: "add", label: "Ajouter" },
            { value: "update", label: "Mettre à jour", disabled: proposal.matches.length === 0 },
            { value: "skip", label: "Ignorer" },
          ]}
        />
      </header>
      {sameName.length > 0 ? (
        <p className="mt-2 flex items-start gap-2 rounded-lg border border-amber-300/60 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-100">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <span>
            Après correction, ce nom correspond à « {sameName.join(" », « ")} » déjà dans ton
            profil. Coche « Ce n'est pas un doublon » pour l'ajouter quand même, sinon l'ajout sera
            refusé.
          </span>
        </p>
      ) : (
        changedMatch.length > 0 && (
          <StatusMayChange what={changedMatch.map(fieldLabel).join(", ").toLowerCase()} />
        )
      )}

      {choice.action === "add" && (
        <div className="mt-4 space-y-3">
          <div className="divide-y rounded-lg border">
            {fields.map((f) => (
              <div key={f} className="grid gap-2 px-3 py-2.5 sm:grid-cols-[11rem_1fr]">
                <CheckLine
                  checked={choice.addFields.includes(f)}
                  onChange={(on) =>
                    setChoice({ ...choice, addFields: toggle(choice.addFields, f, on) })
                  }
                >
                  <span className="text-xs font-medium text-muted-foreground">{fieldLabel(f)}</span>{" "}
                  {uncertain(f) && <Uncertain />}
                </CheckLine>
                <div className="text-sm">
                  <CorrectableValue
                    type={fieldType(section, f)}
                    extracted={proposal.data[f]}
                    correction={choice.corrections[f]}
                    onChange={(v) => correct(f, v)}
                    onReset={() => reset(f)}
                  />
                </div>
              </div>
            ))}
          </div>
          {(proposal.status !== "new" || changedMatch.length > 0) && (
            <CheckLine
              checked={choice.allowDuplicate}
              onChange={(on) => setChoice({ ...choice, allowDuplicate: on })}
            >
              Ce n'est pas un doublon : l'ajouter quand même
            </CheckLine>
          )}
        </div>
      )}

      {choice.action === "update" && match && (
        <div className="mt-4 space-y-3">
          {proposal.matches.length > 1 && (
            <Select
              value={String(choice.target)}
              onValueChange={(v) => {
                const target = Number(v);
                setChoice({
                  ...choice,
                  target,
                  updateFields: defaultUpdateFields(proposal, proposal.matches[target]),
                });
              }}
            >
              <SelectTrigger className="h-8 sm:w-96" aria-label="Élément à mettre à jour">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {proposal.matches.map((m, i) => (
                  <SelectItem key={i} value={String(i)}>
                    {itemTitle(section, m.existing)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <p className="text-xs text-muted-foreground">
            Mise à jour de « {itemTitle(section, match.existing)} ». Les listes sont complétées
            (rien n'est retiré), les textes sont remplacés.
          </p>
          {Object.keys(match.differences).length === 0 ? (
            <p className="rounded-lg border border-dashed px-3 py-4 text-center text-sm text-muted-foreground">
              Aucune différence avec l'élément existant.
            </p>
          ) : (
            <div className="divide-y rounded-lg border">
              <div className="hidden grid-cols-[11rem_1fr_1fr] gap-3 bg-muted/50 px-3 py-2 text-xs font-medium text-muted-foreground sm:grid">
                <span>Reprendre ?</span>
                <span>Dans ton profil</span>
                <span>Extrait du CV</span>
              </div>
              {Object.entries(match.differences).map(([f, diff]) => (
                <div
                  key={f}
                  className="grid gap-2 px-3 py-2.5 text-sm sm:grid-cols-[11rem_1fr_1fr] sm:gap-3"
                >
                  <CheckLine
                    checked={choice.updateFields.includes(f)}
                    onChange={(on) =>
                      setChoice({ ...choice, updateFields: toggle(choice.updateFields, f, on) })
                    }
                  >
                    <span className="text-xs font-medium text-muted-foreground">
                      {fieldLabel(f)}
                    </span>{" "}
                    {uncertain(f) && <Uncertain />}
                  </CheckLine>
                  <Value value={diff.current} muted />
                  <CorrectableValue
                    type={fieldType(section, f)}
                    extracted={diff.extracted}
                    correction={choice.corrections[f]}
                    onChange={(v) => correct(f, v)}
                    onReset={() => reset(f)}
                    display={
                      diff.change === "new_values" ? (
                        <>
                          <p className="mb-1 text-xs text-muted-foreground">À ajouter :</p>
                          <Value value={diff.new_values} />
                        </>
                      ) : undefined
                    }
                  />
                </div>
              ))}
            </div>
          )}
          <CheckLine
            checked={choice.allowLessPrecise}
            onChange={(on) => setChoice({ ...choice, allowLessPrecise: on })}
          >
            Autoriser une valeur moins précise (ex. « 2026 » à la place de « 2026-02 »)
          </CheckLine>
        </div>
      )}

      {choice.action === "skip" && (
        <p className="mt-3 text-xs text-muted-foreground">Cette proposition sera ignorée.</p>
      )}
      <ProblemList problems={problems} />
    </article>
  );
}

// ---------- Compétences, langues, centres d'intérêt ----------

function Row({
  id,
  children,
  problems,
}: {
  id: string;
  children: ReactNode;
  problems?: string[] | undefined;
}) {
  return (
    <div id={`proposal-${id}`} className="px-4 py-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        {children}
      </div>
      <ProblemList problems={problems} />
    </div>
  );
}

const NEW_CATEGORY = "__new__:";

const isCorrected = (correction: string | null, extracted: string) =>
  correction !== null && correction.trim() !== "" && correction.trim() !== extracted;

export function ReviewStep({
  review,
  choices,
  update,
  problems,
  categories,
  profile,
}: {
  review: ImportReview;
  choices: Choices;
  update: Update;
  problems: Record<string, string[]>;
  categories: string[];
  profile?: CandidateProfile | undefined;
}) {
  // Recomputed on every change (correction, category, other proposals of the same import)
  const unavailable = unavailableActions(review, choices, profile);
  const setItem = (id: string, c: ItemChoice) =>
    update((all) => ({ ...all, items: { ...all.items, [id]: c } }));
  const setSkill = (id: string, c: SkillChoice) =>
    update((all) => ({ ...all, skills: { ...all.skills, [id]: c } }));
  const setLanguage = (id: string, c: LanguageChoice) =>
    update((all) => ({ ...all, languages: { ...all.languages, [id]: c } }));
  const setInterest = (id: string, c: InterestChoice) =>
    update((all) => ({ ...all, interests: { ...all.interests, [id]: c } }));

  return (
    <div className="space-y-8">
      {review.warnings.length > 0 && (
        <div className="rounded-xl border border-amber-300/60 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-100">
          <p className="mb-2 flex items-center gap-2 font-medium">
            <AlertTriangle className="size-4" />
            Points à vérifier signalés par l'extraction
          </p>
          <ul className="list-disc space-y-1 pl-5">
            {review.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="flex items-start gap-2 text-xs text-muted-foreground">
        <Info className="mt-0.5 size-3.5 shrink-0" />
        Une valeur extraite est fausse ? Clique sur le crayon pour la corriger. Les corrections ne
        sont enregistrées qu'au moment où tu appliques l'import.
      </p>

      <ProblemList problems={problems["_general"]} />

      {review.personal.length > 0 && (
        <section id="proposal-personal" className="space-y-3">
          <h2 className="text-sm font-semibold">Coordonnées</h2>
          <div className="divide-y rounded-xl border bg-card shadow-soft">
            {review.personal.map((p) => (
              <div
                key={p.field}
                className="grid gap-2 px-4 py-2.5 text-sm sm:grid-cols-[12rem_1fr_1fr] sm:gap-3"
              >
                <CheckLine
                  checked={choices.personal.fields.includes(p.field)}
                  disabled={p.status === "same"}
                  onChange={(on) =>
                    update((all) => ({
                      ...all,
                      personal: {
                        ...all.personal,
                        fields: toggle(all.personal.fields, p.field, on),
                      },
                    }))
                  }
                >
                  <span className="text-xs font-medium text-muted-foreground">
                    {fieldLabel(p.field)}
                  </span>{" "}
                  {p.uncertain && <Uncertain />}
                </CheckLine>
                <Value value={p.current} muted />
                {p.status === "same" ? (
                  <span>
                    <Value value={p.extracted} />
                    <span className="ml-2 text-xs text-muted-foreground">(identique)</span>
                  </span>
                ) : (
                  <CorrectableValue
                    type="text"
                    extracted={p.extracted}
                    correction={choices.personal.corrections[p.field]}
                    onChange={(v) =>
                      update((all) => ({
                        ...all,
                        personal: {
                          ...all.personal,
                          corrections: { ...all.personal.corrections, [p.field]: String(v) },
                          fields: toggle(all.personal.fields, p.field, true),
                        },
                      }))
                    }
                    onReset={() =>
                      update((all) => {
                        const { [p.field]: _removed, ...rest } = all.personal.corrections;
                        return { ...all, personal: { ...all.personal, corrections: rest } };
                      })
                    }
                  />
                )}
              </div>
            ))}
            <div className="px-4 py-2.5">
              <CheckLine
                checked={choices.personal.allowLessPrecise}
                onChange={(on) =>
                  update((all) => ({ ...all, personal: { ...all.personal, allowLessPrecise: on } }))
                }
              >
                Autoriser une valeur moins précise (ex. « Paris » à la place de « Paris, France »)
              </CheckLine>
            </div>
          </div>
          <ProblemList problems={problems["personal"]} />
        </section>
      )}

      {ITEM_SECTION_KEYS.map((section) => (
        <Section key={section} title={sectionConfig[section].label} count={review[section].length}>
          {review[section].map((p) => {
            const c = choices.items[p.proposal_id];
            return c ? (
              <ItemCard
                key={p.proposal_id}
                section={section}
                proposal={p}
                choice={c}
                setChoice={(next) => setItem(p.proposal_id, next)}
                problems={problems[p.proposal_id]}
                profile={profile}
              />
            ) : null;
          })}
        </Section>
      ))}

      <Section title="Compétences" count={review.skills.length}>
        <div className="divide-y rounded-xl border bg-card shadow-soft">
          {review.skills.map((s) => {
            const c = choices.skills[s.proposal_id];
            if (!c) return null;
            const newCategory = s.category_in_profile === null ? s.category : null;
            const blocked = unavailable[s.proposal_id]?.add;
            const skill = c.correction?.trim() || s.skill;
            return (
              <Row key={s.proposal_id} id={s.proposal_id} problems={problems[s.proposal_id]}>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <CorrectableName
                      extracted={s.skill}
                      correction={c.correction}
                      onChange={(v) => setSkill(s.proposal_id, { ...c, correction: v })}
                      onReset={() => setSkill(s.proposal_id, { ...c, correction: null })}
                    />
                    <StatusBadge status={s.status} />
                  </div>
                  {isCorrected(c.correction, s.skill) && <StatusMayChange what="nom" />}
                  {(s.note || s.matches.length > 0) && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {s.note ?? `Déjà dans « ${formatCategory(s.matches[0]?.category ?? "")} »`}
                    </p>
                  )}
                  <UnavailableNote reason={blocked} selected={c.action === "add"} action="Ajout" />
                  {c.action === "add" && !blocked && skillInProfile(profile, skill) && (
                    <div className="mt-1.5">
                      <CheckLine
                        checked={c.allowDuplicate}
                        onChange={(on) => setSkill(s.proposal_id, { ...c, allowDuplicate: on })}
                      >
                        L'ajouter aussi dans la catégorie choisie
                      </CheckLine>
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <Select
                    value={c.createCategory ? NEW_CATEGORY + c.category : c.category}
                    disabled={c.action === "skip" && !blocked} // blocked: another category may make it possible
                    onValueChange={(v) =>
                      setSkill(
                        s.proposal_id,
                        v.startsWith(NEW_CATEGORY)
                          ? { ...c, category: v.slice(NEW_CATEGORY.length), createCategory: true }
                          : { ...c, category: v, createCategory: false },
                      )
                    }
                  >
                    <SelectTrigger className="h-8 w-52" aria-label="Catégorie">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {categories.map((cat) => (
                        <SelectItem key={cat} value={cat}>
                          {formatCategory(cat)}
                        </SelectItem>
                      ))}
                      {newCategory && (
                        <SelectItem value={NEW_CATEGORY + newCategory}>
                          Nouvelle catégorie : {formatCategory(newCategory)}
                        </SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                  <ActionToggle
                    value={c.action}
                    onChange={(action) => setSkill(s.proposal_id, { ...c, action })}
                    options={[
                      {
                        value: "add",
                        label: "Ajouter",
                        disabled: Boolean(blocked) && c.action !== "add",
                        title: blocked,
                      },
                      { value: "skip", label: "Ignorer" },
                    ]}
                  />
                </div>
              </Row>
            );
          })}
        </div>
      </Section>

      <Section title="Langues" count={review.languages.length}>
        <div className="divide-y rounded-xl border bg-card shadow-soft">
          {review.languages.map((l) => {
            const c = choices.languages[l.proposal_id];
            if (!c) return null;
            const existing = l.matches[0];
            const blocked = unavailable[l.proposal_id]?.add;
            return (
              <Row key={l.proposal_id} id={l.proposal_id} problems={problems[l.proposal_id]}>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    {c.action === "add" ? (
                      <CorrectableName
                        extracted={l.language}
                        correction={c.correction}
                        onChange={(v) => setLanguage(l.proposal_id, { ...c, correction: v })}
                        onReset={() => setLanguage(l.proposal_id, { ...c, correction: null })}
                      />
                    ) : (
                      <span className="text-sm font-medium">{l.language}</span>
                    )}
                    <StatusBadge status={l.status} />
                  </div>
                  {c.action === "add" && isCorrected(c.correction, l.language) && (
                    <StatusMayChange what="nom" />
                  )}
                  {existing && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Dans ton profil : {existing.language} — {existing.level}
                      {l.level_differs && " · niveau différent"}
                    </p>
                  )}
                  <UnavailableNote reason={blocked} selected={c.action === "add"} action="Ajout" />
                  {c.action === "add" && !blocked && l.status === "duplicate" && (
                    <div className="mt-1.5">
                      <CheckLine
                        checked={c.allowDuplicate}
                        onChange={(on) => setLanguage(l.proposal_id, { ...c, allowDuplicate: on })}
                      >
                        L'ajouter quand même comme une autre langue
                      </CheckLine>
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <Input
                    value={c.level}
                    disabled={c.action === "skip"}
                    onChange={(e) => setLanguage(l.proposal_id, { ...c, level: e.target.value })}
                    placeholder="Niveau"
                    aria-label="Niveau"
                    className="h-8 w-36"
                  />
                  <ActionToggle
                    value={c.action}
                    onChange={(action) => setLanguage(l.proposal_id, { ...c, action })}
                    options={[
                      {
                        value: "add",
                        label: "Ajouter",
                        disabled: Boolean(blocked) && c.action !== "add",
                        title: blocked,
                      },
                      { value: "update", label: "Mettre à jour le niveau", disabled: !existing },
                      { value: "skip", label: "Ignorer" },
                    ]}
                  />
                </div>
              </Row>
            );
          })}
        </div>
      </Section>

      <Section title="Centres d'intérêt" count={review.interests.length}>
        <div className="divide-y rounded-xl border bg-card shadow-soft">
          {review.interests.map((i) => {
            const c = choices.interests[i.proposal_id];
            if (!c) return null;
            const blocked = unavailable[i.proposal_id];
            return (
              <Row key={i.proposal_id} id={i.proposal_id} problems={problems[i.proposal_id]}>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <CorrectableName
                      extracted={i.interest}
                      correction={c.correction}
                      onChange={(v) => setInterest(i.proposal_id, { ...c, correction: v })}
                      onReset={() => setInterest(i.proposal_id, { ...c, correction: null })}
                    />
                    <StatusBadge status={i.status} />
                  </div>
                  {isCorrected(c.correction, i.interest) && <StatusMayChange what="nom" />}
                  {i.matches.length > 0 && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Proche de : {i.matches.join(", ")}
                    </p>
                  )}
                  <UnavailableNote
                    reason={blocked?.add}
                    selected={c.action === "add"}
                    action="Ajout"
                  />
                  <UnavailableNote
                    reason={blocked?.update}
                    selected={c.action === "update"}
                    action="Remplacement"
                  />
                  {c.action === "add" && !blocked?.add && i.status !== "new" && (
                    <div className="mt-1.5">
                      <CheckLine
                        checked={c.allowDuplicate}
                        onChange={(on) => setInterest(i.proposal_id, { ...c, allowDuplicate: on })}
                      >
                        Ce n'est pas un doublon : l'ajouter quand même
                      </CheckLine>
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {c.action === "update" && i.matches.length > 1 && (
                    <Select
                      value={c.target}
                      onValueChange={(target) => setInterest(i.proposal_id, { ...c, target })}
                    >
                      <SelectTrigger className="h-8 w-40" aria-label="Centre d'intérêt à remplacer">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {i.matches.map((m) => (
                          <SelectItem key={m} value={m}>
                            {m}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                  <ActionToggle
                    value={c.action}
                    onChange={(action) => setInterest(i.proposal_id, { ...c, action })}
                    options={[
                      {
                        value: "add",
                        label: "Ajouter",
                        disabled: Boolean(blocked?.add) && c.action !== "add",
                        title: blocked?.add,
                      },
                      {
                        value: "update",
                        label:
                          i.matches.length === 1 ? `Remplacer « ${i.matches[0]} »` : "Remplacer",
                        disabled:
                          !i.matches.length || (Boolean(blocked?.update) && c.action !== "update"),
                        title: blocked?.update,
                      },
                      { value: "skip", label: "Ignorer" },
                    ]}
                  />
                </div>
              </Row>
            );
          })}
        </div>
      </Section>
    </div>
  );
}
