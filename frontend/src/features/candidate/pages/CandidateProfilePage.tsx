import { useNavigate } from "@tanstack/react-router";
import {
  Briefcase,
  ChevronDown,
  FileUp,
  FolderGit2,
  GraduationCap,
  Heart,
  Languages,
  Plus,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { candidateApi, type ItemSection, type SectionItemMap } from "@/services/api/candidateApi";
import { ItemsTab } from "../components/ItemsTab";
import { LanguagesTab } from "../components/LanguagesTab";
import { OtherTab } from "../components/OtherTab";
import { SkillsTab } from "../components/SkillsTab";
import { ItemFormDialog } from "../forms/ItemFormDialog";
import { useCandidateAction, useProfile } from "../hooks";
import { sectionConfig } from "../sectionConfig";

export const CANDIDATE_TABS = ["experiences", "education", "projects", "skills", "languages", "other"] as const;
export type CandidateTab = (typeof CANDIDATE_TABS)[number];

const TAB_LABELS: Record<CandidateTab, string> = {
  experiences: "Expériences",
  education: "Formations",
  projects: "Projets",
  skills: "Compétences",
  languages: "Langues",
  other: "Autres",
};

export function PageHeader() {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Mon profil candidat</h1>
      <p className="mt-1 max-w-xl text-sm text-muted-foreground">
        Centralisez vos expériences, formations et compétences pour créer des CV adaptés à chaque candidature.
      </p>
    </div>
  );
}

export function CandidateProfilePage({ tab }: { tab: CandidateTab }) {
  const navigate = useNavigate();
  const { data: profile, isLoading } = useProfile();
  const run = useCandidateAction();
  const [formSection, setFormSection] = useState<ItemSection | null>(null);
  const [signals, setSignals] = useState({ skills: 0, languages: 0, interests: 0 });

  const setTab = (t: string) => navigate({ to: "/candidat", search: { tab: t as CandidateTab }, replace: true });

  const addTo = (target: ItemSection | "skills" | "languages" | "interests") => {
    if (target === "skills" || target === "languages" || target === "interests") {
      setTab(target === "interests" ? "other" : target);
      setSignals((s) => ({ ...s, [target]: s[target] + 1 }));
    } else {
      setTab(target);
      setFormSection(target);
    }
  };

  const create = async (data: Record<string, unknown>) => {
    if (!formSection) return false;
    const section = formSection;
    return run(
      () => candidateApi.addItem(section, data as Omit<SectionItemMap[typeof section], "id">),
      sectionConfig[section].createdMessage,
    );
  };

  const addMenu = [
    { key: "experiences", label: "Une expérience", icon: Briefcase },
    { key: "education", label: "Une formation", icon: GraduationCap },
    { key: "projects", label: "Un projet", icon: FolderGit2 },
    { key: "skills", label: "Une compétence", icon: Sparkles },
    { key: "languages", label: "Une langue", icon: Languages },
    { key: "interests", label: "Un centre d'intérêt", icon: Heart },
  ] as const;

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-8 sm:py-10">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <PageHeader />
        <div className="flex shrink-0 gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                <Plus className="size-4" />
                Ajouter des informations
                <ChevronDown className="size-3.5 opacity-60" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              {addMenu.map((m, i) => (
                <div key={m.key}>
                  {i === 3 && <DropdownMenuSeparator />}
                  <DropdownMenuItem onSelect={() => addTo(m.key)}>
                    <m.icon className="size-4 text-muted-foreground" />
                    {m.label}
                  </DropdownMenuItem>
                </div>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button onClick={() => navigate({ to: "/candidat/import" })}>
            <FileUp className="size-4" />
            Importer un CV
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="mt-8">
        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <TabsList className="h-auto w-full justify-start gap-1 rounded-none border-b bg-transparent p-0">
            {CANDIDATE_TABS.map((t) => (
              <TabsTrigger
                key={t}
                value={t}
                className="relative flex-none rounded-none border-0 bg-transparent px-3 pb-3 pt-1.5 text-muted-foreground shadow-none after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:bg-transparent hover:text-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none data-[state=active]:after:bg-primary"
              >
                {TAB_LABELS[t]}
                {profile && t in sectionConfig && (
                  <span className="ml-1.5 text-xs text-muted-foreground">
                    {profile[t as ItemSection].length}
                  </span>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <div className="mt-6">
          {isLoading || !profile ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-28 w-full rounded-xl" />
              ))}
            </div>
          ) : (
            <>
              {(["experiences", "education", "projects"] as const).map((s) => (
                <TabsContent key={s} value={s}>
                  <ItemsTab section={s} items={profile[s]} onAdd={() => setFormSection(s)} />
                </TabsContent>
              ))}
              <TabsContent value="skills">
                <SkillsTab skills={profile.skills} addSignal={signals.skills} />
              </TabsContent>
              <TabsContent value="languages">
                <LanguagesTab languages={profile.languages} addSignal={signals.languages} />
              </TabsContent>
              <TabsContent value="other">
                <OtherTab
                  personal={profile.personal}
                  career={profile.career}
                  interests={profile.interests}
                  preferences={profile.preferences}
                  interestSignal={signals.interests}
                />
              </TabsContent>
            </>
          )}
        </div>
      </Tabs>

      {formSection && (
        <ItemFormDialog
          section={formSection}
          open={formSection !== null}
          onOpenChange={(o) => !o && setFormSection(null)}
          onSubmit={create}
        />
      )}

    </div>
  );
}
