import {
  ArrowDown,
  ArrowUp,
  Briefcase,
  FolderGit2,
  GraduationCap,
  Heart,
  Languages,
  Plus,
  Sparkles,
  Trash2,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ListEditor, TagInput } from "@/features/candidate/components/common";
import type {
  ContactType,
  CvDocument,
  CvEducation,
  CvExperience,
  CvProject,
} from "@/services/api/cvTypes";
import type { CandidateProfile } from "@/services/api/types";
import { profileEntries, type CvSectionKey, type CvSelection, type ItemSection } from "../adapters";

const SECTIONS: { key: CvSectionKey; label: string; icon: LucideIcon }[] = [
  { key: "profile", label: "Profil", icon: UserRound },
  { key: "experiences", label: "Expériences", icon: Briefcase },
  { key: "education", label: "Formation", icon: GraduationCap },
  { key: "projects", label: "Projets", icon: FolderGit2 },
  { key: "skills", label: "Compétences", icon: Sparkles },
  { key: "languages", label: "Langues", icon: Languages },
  { key: "interests", label: "Intérêts", icon: Heart },
];

const CONTACT_LABELS: Record<ContactType, string> = {
  email: "Email",
  phone: "Téléphone",
  linkedin: "LinkedIn",
  github: "GitHub",
};

type Entry = CvExperience | CvEducation | CvProject;

/** Labeled form field wrapper. */
function Field({
  label,
  labelAction,
  children,
}: {
  label: string;
  labelAction?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {labelAction}
      </div>
      {children}
    </div>
  );
}

function entryTitle(section: ItemSection, entry: Entry): { title: string; subtitle: string } {
  if (section === "experiences") {
    const e = entry as CvExperience;
    return { title: e.title, subtitle: [e.organization, e.dates].filter(Boolean).join(" · ") };
  }
  if (section === "education") {
    const e = entry as CvEducation;
    return { title: e.institution, subtitle: [e.location, e.dates].filter(Boolean).join(" · ") };
  }
  const p = entry as CvProject;
  return { title: p.name, subtitle: p.link?.url ?? "" };
}

/** Adds an entry built from the candidate profile (same content as cv/document.entry_from_profile). */
function AddFromProfileDialog({
  section,
  profile,
  profileError,
  existingSourceIds,
  onAdd,
  open,
  onOpenChange,
}: {
  section: ItemSection;
  profile: CandidateProfile | undefined;
  profileError: string | null;
  existingSourceIds: Set<string>;
  onAdd: (entry: Entry) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const candidates = profile ? profileEntries(section, profile) : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Ajouter depuis le profil</DialogTitle>
          <DialogDescription>
            Choisissez un élément de votre profil candidat à ajouter à ce CV.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-80 space-y-2 overflow-y-auto">
          {profileError ? (
            <p className="py-6 text-center text-sm text-destructive">{profileError}</p>
          ) : !profile ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Chargement du profil…</p>
          ) : candidates.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Aucun élément disponible dans votre profil.
            </p>
          ) : null}
          {candidates.map((c) => {
            const already = existingSourceIds.has(c.entry.source_id);
            return (
              <div
                key={c.entry.source_id}
                className="flex items-center justify-between gap-3 rounded-lg border p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{c.label}</p>
                  {c.detail && <p className="truncate text-xs text-muted-foreground">{c.detail}</p>}
                </div>
                <Button
                  size="sm"
                  variant={already ? "ghost" : "outline"}
                  disabled={already}
                  onClick={() => {
                    onAdd(structuredClone(c.entry));
                    onOpenChange(false);
                  }}
                >
                  {already ? "Déjà ajouté" : "Ajouter"}
                </Button>
              </div>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function CvEditorPanel({
  draft,
  onChange,
  selection,
  onSelect,
  profile,
  profileError,
}: {
  draft: CvDocument;
  onChange: (next: CvDocument) => void;
  selection: CvSelection;
  onSelect: (s: CvSelection) => void;
  profile: CandidateProfile | undefined;
  profileError: string | null;
}) {
  const [addOpen, setAddOpen] = useState(false);
  const section = selection.section;
  const isItemSection =
    section === "experiences" || section === "education" || section === "projects";

  const patch = (p: Partial<CvDocument>) => onChange({ ...draft, ...p });
  const patchHeader = (p: Partial<CvDocument["header"]>) =>
    patch({ header: { ...draft.header, ...p } });

  const items: Entry[] = isItemSection ? draft[section] : [];
  const selectedIndex = isItemSection ? selection.index : undefined;
  const selectedItem = selectedIndex !== undefined ? items[selectedIndex] : undefined;

  const setItems = (next: Entry[]) => patch({ [section]: next } as Partial<CvDocument>);
  const patchItem = (index: number, p: Record<string, unknown>) =>
    setItems(items.map((it, i) => (i === index ? ({ ...it, ...p } as Entry) : it)));

  const moveItem = (index: number, dir: -1 | 1) => {
    const target = index + dir;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target]!, next[index]!];
    setItems(next);
    if (selectedIndex === index) onSelect({ section, index: target });
    else if (selectedIndex === target) onSelect({ section, index });
  };

  const removeItem = (index: number) => {
    setItems(items.filter((_, i) => i !== index));
    onSelect({ section });
  };

  const moveGroup = (index: number, dir: -1 | 1) => {
    const target = index + dir;
    if (target < 0 || target >= draft.skills.length) return;
    const next = [...draft.skills];
    [next[index], next[target]] = [next[target]!, next[index]!];
    patch({ skills: next });
  };

  const missingContactTypes = (Object.keys(CONTACT_LABELS) as ContactType[]).filter(
    (type) => !draft.header.contacts.some((c) => c.type === type),
  );

  return (
    <div className="flex h-full flex-col rounded-xl border bg-card shadow-soft">
      {/* Section nav */}
      <div className="flex flex-wrap gap-1 border-b p-2">
        {SECTIONS.map((s) => {
          const active = s.key === section;
          const count = s.key === "profile" ? undefined : draft[s.key].length;
          return (
            <button
              key={s.key}
              type="button"
              onClick={() => onSelect({ section: s.key })}
              className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <s.icon className="size-3.5" />
              {s.label}
              {count !== undefined && (
                <span className={active ? "opacity-80" : "opacity-60"}>({count})</span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {section === "profile" && (
          <>
            <Field label="Nom">
              <Input
                value={draft.header.name}
                onChange={(e) => patchHeader({ name: e.target.value })}
              />
            </Field>
            <Field label="Résumé">
              <Textarea
                value={draft.header.summary}
                onChange={(e) => patchHeader({ summary: e.target.value })}
                rows={5}
                className="resize-y"
              />
            </Field>
            <Field label="Coordonnées">
              <div className="space-y-2">
                {draft.header.contacts.map((contact, i) => (
                  <div key={contact.type} className="space-y-1">
                    <span className="text-[11px] text-muted-foreground">
                      {CONTACT_LABELS[contact.type]}
                    </span>
                    <div className="flex items-center gap-2">
                      <Input
                        value={contact.value}
                        aria-label={CONTACT_LABELS[contact.type]}
                        onChange={(e) =>
                          patchHeader({
                            contacts: draft.header.contacts.map((c, j) =>
                              j === i ? { ...c, value: e.target.value } : c,
                            ),
                          })
                        }
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-9 shrink-0 text-muted-foreground hover:text-destructive"
                        aria-label={`Retirer ${CONTACT_LABELS[contact.type]}`}
                        onClick={() =>
                          patchHeader({ contacts: draft.header.contacts.filter((_, j) => j !== i) })
                        }
                      >
                        <X className="size-4" />
                      </Button>
                    </div>
                  </div>
                ))}
                {missingContactTypes.length > 0 && (
                  <Select
                    value=""
                    onValueChange={(type) =>
                      patchHeader({
                        contacts: [
                          ...draft.header.contacts,
                          { type: type as ContactType, value: "" },
                        ],
                      })
                    }
                  >
                    <SelectTrigger className="h-8 w-auto gap-1.5 border-dashed text-xs text-primary">
                      <Plus className="size-3.5" />
                      <SelectValue placeholder="Ajouter une coordonnée" />
                    </SelectTrigger>
                    <SelectContent>
                      {missingContactTypes.map((type) => (
                        <SelectItem key={type} value={type}>
                          {CONTACT_LABELS[type]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </Field>
          </>
        )}

        {isItemSection && (
          <>
            {/* Item list */}
            <div className="space-y-1.5">
              {items.length === 0 && (
                <p className="py-2 text-center text-sm text-muted-foreground">
                  Aucun élément dans cette section.
                </p>
              )}
              {items.map((it, idx) => {
                const { title, subtitle } = entryTitle(section, it);
                const active = idx === selectedIndex;
                return (
                  <div
                    key={it.source_id}
                    className={`flex items-center gap-1 rounded-lg border p-2 transition-colors ${
                      active ? "border-primary/50 bg-accent/40" : "bg-background"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => onSelect({ section, index: idx })}
                      className="min-w-0 flex-1 text-left"
                    >
                      <p className="truncate text-sm font-medium">{title || "Sans titre"}</p>
                      {subtitle && (
                        <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
                      )}
                    </button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7 shrink-0"
                      aria-label="Monter"
                      disabled={idx === 0}
                      onClick={() => moveItem(idx, -1)}
                    >
                      <ArrowUp className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7 shrink-0"
                      aria-label="Descendre"
                      disabled={idx === items.length - 1}
                      onClick={() => moveItem(idx, 1)}
                    >
                      <ArrowDown className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7 shrink-0 text-muted-foreground hover:text-destructive"
                      aria-label="Retirer du CV"
                      onClick={() => removeItem(idx)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                );
              })}
            </div>
            <Button variant="outline" size="sm" className="w-full" onClick={() => setAddOpen(true)}>
              <Plus className="size-4" />
              Ajouter depuis le profil
            </Button>

            {/* Selected item fields */}
            {selectedItem && selectedIndex !== undefined && section === "experiences" && (
              <div className="space-y-4 border-t pt-4">
                {(() => {
                  const it = selectedItem as CvExperience;
                  const set = (p: Partial<CvExperience>) => patchItem(selectedIndex, p);
                  return (
                    <>
                      <Field label="Intitulé du poste">
                        <Input value={it.title} onChange={(e) => set({ title: e.target.value })} />
                      </Field>
                      <Field label="Entreprise">
                        <Input
                          value={it.organization}
                          onChange={(e) => set({ organization: e.target.value })}
                        />
                      </Field>
                      <Field label="Contexte (facultatif)">
                        <Input
                          value={it.context ?? ""}
                          onChange={(e) => set({ context: e.target.value || null })}
                        />
                      </Field>
                      <div className="grid grid-cols-2 gap-3">
                        <Field label="Dates">
                          <Input
                            placeholder="2024–2025"
                            value={it.dates}
                            onChange={(e) => set({ dates: e.target.value })}
                          />
                        </Field>
                        <Field label="Lieu">
                          <Input
                            value={it.location}
                            onChange={(e) => set({ location: e.target.value })}
                          />
                        </Field>
                      </div>
                      <Field label="Points clés">
                        <ListEditor
                          value={it.bullets}
                          onChange={(bullets) => set({ bullets })}
                          addLabel="Ajouter un point"
                          placeholder="Décrivez une réalisation…"
                        />
                      </Field>
                    </>
                  );
                })()}
              </div>
            )}

            {selectedItem && selectedIndex !== undefined && section === "education" && (
              <div className="space-y-4 border-t pt-4">
                {(() => {
                  const it = selectedItem as CvEducation;
                  const set = (p: Partial<CvEducation>) => patchItem(selectedIndex, p);
                  return (
                    <>
                      <Field label="Établissement">
                        <Input
                          value={it.institution}
                          onChange={(e) => set({ institution: e.target.value })}
                        />
                      </Field>
                      <div className="grid grid-cols-2 gap-3">
                        <Field label="Dates">
                          <Input
                            placeholder="2024–2025"
                            value={it.dates}
                            onChange={(e) => set({ dates: e.target.value })}
                          />
                        </Field>
                        <Field label="Lieu">
                          <Input
                            value={it.location}
                            onChange={(e) => set({ location: e.target.value })}
                          />
                        </Field>
                      </div>
                      <Field label="Détails">
                        <ListEditor
                          value={it.bullets}
                          onChange={(bullets) => set({ bullets })}
                          addLabel="Ajouter un détail"
                          placeholder="Diplôme, spécialité, cours…"
                        />
                      </Field>
                    </>
                  );
                })()}
              </div>
            )}

            {selectedItem && selectedIndex !== undefined && section === "projects" && (
              <div className="space-y-4 border-t pt-4">
                {(() => {
                  const it = selectedItem as CvProject;
                  const set = (p: Partial<CvProject>) => patchItem(selectedIndex, p);
                  return (
                    <>
                      <Field label="Nom du projet">
                        <Input value={it.name} onChange={(e) => set({ name: e.target.value })} />
                      </Field>
                      <Field label="Lien (facultatif)">
                        <Input
                          placeholder="https://github.com/…"
                          value={it.link?.url ?? ""}
                          onChange={(e) =>
                            set({
                              link: e.target.value
                                ? { url: e.target.value, label: it.link?.label || "GitHub" }
                                : null,
                            })
                          }
                        />
                      </Field>
                      <Field label="Points clés">
                        <ListEditor
                          value={it.bullets}
                          onChange={(bullets) => set({ bullets })}
                          addLabel="Ajouter un point"
                          placeholder="Décrivez une réalisation…"
                        />
                      </Field>
                    </>
                  );
                })()}
              </div>
            )}
          </>
        )}

        {section === "skills" && (
          <div className="space-y-4">
            {draft.skills.map((group, i) => (
              <div key={i} className="space-y-1.5 rounded-lg border bg-background p-2.5">
                <div className="flex items-center gap-1">
                  <Input
                    value={group.label}
                    placeholder="Nom du groupe"
                    aria-label="Nom du groupe"
                    className="h-8 text-sm font-medium"
                    onChange={(e) =>
                      patch({
                        skills: draft.skills.map((g, j) =>
                          j === i ? { ...g, label: e.target.value } : g,
                        ),
                      })
                    }
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7 shrink-0"
                    aria-label="Monter"
                    disabled={i === 0}
                    onClick={() => moveGroup(i, -1)}
                  >
                    <ArrowUp className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7 shrink-0"
                    aria-label="Descendre"
                    disabled={i === draft.skills.length - 1}
                    onClick={() => moveGroup(i, 1)}
                  >
                    <ArrowDown className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7 shrink-0 text-muted-foreground hover:text-destructive"
                    aria-label={`Retirer le groupe ${group.label}`}
                    onClick={() => patch({ skills: draft.skills.filter((_, j) => j !== i) })}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
                <TagInput
                  value={group.items}
                  onChange={(items) =>
                    patch({ skills: draft.skills.map((g, j) => (j === i ? { ...g, items } : g)) })
                  }
                  placeholder="Ajouter une compétence…"
                />
              </div>
            ))}
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => patch({ skills: [...draft.skills, { label: "", items: [] }] })}
            >
              <Plus className="size-4" />
              Ajouter un groupe
            </Button>
          </div>
        )}

        {section === "languages" && (
          <div className="space-y-2">
            {draft.languages.map((lang, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input
                  value={lang.name}
                  placeholder="Langue"
                  aria-label="Langue"
                  onChange={(e) =>
                    patch({
                      languages: draft.languages.map((l, j) =>
                        j === i ? { ...l, name: e.target.value } : l,
                      ),
                    })
                  }
                />
                <Input
                  value={lang.level}
                  placeholder="Niveau"
                  aria-label="Niveau"
                  onChange={(e) =>
                    patch({
                      languages: draft.languages.map((l, j) =>
                        j === i ? { ...l, level: e.target.value } : l,
                      ),
                    })
                  }
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-9 shrink-0 text-muted-foreground hover:text-destructive"
                  aria-label="Retirer cette langue"
                  onClick={() => patch({ languages: draft.languages.filter((_, j) => j !== i) })}
                >
                  <X className="size-4" />
                </Button>
              </div>
            ))}
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => patch({ languages: [...draft.languages, { name: "", level: "" }] })}
            >
              <Plus className="size-4" />
              Ajouter une langue
            </Button>
          </div>
        )}

        {section === "interests" && (
          <Field label="Centres d'intérêt">
            <TagInput
              value={draft.interests}
              onChange={(interests) => patch({ interests })}
              placeholder="Ajouter un centre d'intérêt…"
            />
          </Field>
        )}
      </div>

      {isItemSection && (
        <AddFromProfileDialog
          section={section}
          profile={profile}
          profileError={profileError}
          existingSourceIds={new Set(items.map((it) => it.source_id))}
          onAdd={(entry) => {
            setItems([...items, entry]);
            onSelect({ section, index: items.length });
          }}
          open={addOpen}
          onOpenChange={setAddOpen}
        />
      )}
    </div>
  );
}
