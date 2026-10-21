import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, CalendarDays, Flag, Github, MapPin, Pencil, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { candidateApi, getItemKey, type ItemSection, type Priority } from "@/services/api/candidateApi";
import { ConfirmDialog, TagList } from "../components/common";
import { ItemFormDialog } from "../forms/ItemFormDialog";
import { formatRange, PRIORITY_LABELS } from "../format";
import { useCandidateAction, useProfile } from "../hooks";
import { sectionConfig } from "../sectionConfig";

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t py-6 first:border-t-0 first:pt-0">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</h2>
      {children}
    </section>
  );
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2">
      {items.map((l, i) => (
        <li key={i} className="flex gap-3 text-sm leading-relaxed">
          <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/60" />
          {l}
        </li>
      ))}
    </ul>
  );
}

const priorityVariant: Record<Priority, string> = {
  high: "bg-priority-high text-priority-high-foreground",
  medium: "bg-priority-medium text-priority-medium-foreground",
  low: "bg-muted text-muted-foreground",
};

export function ItemDetailPage({ section, id }: { section: ItemSection; id: string }) {
  const navigate = useNavigate();
  const run = useCandidateAction();
  const { data: profile, isLoading } = useProfile();
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const config = sectionConfig[section];

  const back = (
    <Button asChild variant="ghost" size="sm" className="-ml-2 text-muted-foreground">
      <Link to="/candidat" search={{ tab: section }}>
        <ArrowLeft className="size-4" />
        {config.backLabel}
      </Link>
    </Button>
  );

  if (isLoading || !profile)
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-8">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-6 h-64 w-full rounded-xl" />
      </div>
    );

  const items = profile[section] as unknown as Record<string, unknown>[];
  const index = items.findIndex((it, i) => getItemKey(it, i) === id);
  const item = items[index];

  if (!item)
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-8">
        {back}
        <p className="mt-10 text-center text-sm text-muted-foreground">Cet élément n'existe pas ou a été supprimé.</p>
      </div>
    );

  const s = config.summary(item as never);
  const str = (k: string) => item[k] as string | undefined;
  const arr = (k: string) => (item[k] as string[] | undefined) ?? [];
  const priority = str("priority") as Priority | undefined;
  const range = formatRange(str("start_date"), str("end_date"), section === "experiences" ? "Présent" : "En cours");

  const remove = async () => {
    const ok = await run(() => candidateApi.deleteItem(section, id), config.deletedMessage);
    if (ok) navigate({ to: "/candidat", search: { tab: section } });
  };

  return (
    <div className="mx-auto w-full max-w-3xl animate-fade-up px-4 py-8 sm:px-8 sm:py-10">
      {back}

      <header className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{s.title}</h1>
          {s.subtitle && <p className="mt-1 text-base text-muted-foreground">{s.subtitle}</p>}
          {section === "education" && str("specialization") && (
            <p className="mt-1 text-sm text-muted-foreground">{str("specialization")}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
            {str("location") && (
              <span className="inline-flex items-center gap-1.5">
                <MapPin className="size-3.5" />
                {str("location")}
              </span>
            )}
            {range && (
              <span className="inline-flex items-center gap-1.5">
                <CalendarDays className="size-3.5" />
                {range}
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          {str("github_url") && (
            <Button asChild variant="outline" size="sm">
              <a href={str("github_url")} target="_blank" rel="noreferrer">
                <Github className="size-4" />
                GitHub
              </a>
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
            <Pencil className="size-3.5" />
            Modifier
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={() => setDeleteOpen(true)}
          >
            <Trash2 className="size-3.5" />
            Supprimer
          </Button>
        </div>
      </header>

      <div className="mt-8 rounded-xl border bg-card p-6 shadow-soft">
        {str("context") && (
          <Block title="Contexte">
            <p className="text-sm leading-relaxed">{str("context")}</p>
          </Block>
        )}
        {str("description") && (
          <Block title="Description">
            <p className="text-sm leading-relaxed">{str("description")}</p>
          </Block>
        )}
        {arr("responsibilities").length > 0 && (
          <Block title="Missions">
            <Bullets items={arr("responsibilities")} />
          </Block>
        )}
        {arr("achievements").length > 0 && (
          <Block title="Réalisations">
            <Bullets items={arr("achievements")} />
          </Block>
        )}
        {arr("details").length > 0 && (
          <Block title="Détails">
            <Bullets items={arr("details")} />
          </Block>
        )}
        {arr("skills").length > 0 && (
          <Block title="Compétences utilisées">
            <TagList tags={arr("skills")} />
          </Block>
        )}
        {(arr("tags").length > 0 || priority) && (
          <Block title="Tags et priorité">
            <div className="flex flex-wrap items-center gap-3">
              {priority && (
                <Badge className={`gap-1 border-transparent font-medium ${priorityVariant[priority]}`}>
                  <Flag className="size-3" />
                  Priorité {PRIORITY_LABELS[priority].toLowerCase()}
                </Badge>
              )}
              <TagList tags={arr("tags").map((t) => `#${t}`)} variant="outline" />
            </div>
          </Block>
        )}
        {!str("context") &&
          !str("description") &&
          !arr("responsibilities").length &&
          !arr("achievements").length &&
          !arr("details").length &&
          !arr("skills").length && (
            <p className="text-center text-sm text-muted-foreground">
              Aucun détail pour le moment.{" "}
              <button className="text-primary hover:underline" onClick={() => setEditOpen(true)}>
                Compléter cette {config.singular === "projet" ? "fiche" : config.singular}
              </button>
            </p>
          )}
      </div>

      <ItemFormDialog
        section={section}
        open={editOpen}
        onOpenChange={setEditOpen}
        item={item as never}
        onSubmit={async (data) => {
          // A legacy education entry ("index-N") receives an id when edited: follow it
          let savedId: string | undefined;
          const ok = await run(async () => {
            savedId = (await candidateApi.updateItem(section, id, data)).id;
          }, config.updatedMessage);
          if (ok && savedId && savedId !== id)
            navigate({ to: "/candidat/$section/$id", params: { section, id: savedId }, replace: true });
          return ok;
        }}
      />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={`Supprimer cette ${config.singular === "projet" ? "fiche projet" : config.singular} ?`}
        description={`« ${s.title} » sera définitivement retiré(e) de votre profil.`}
        onConfirm={remove}
      />
    </div>
  );
}
