import { Link } from "@tanstack/react-router";
import { CalendarDays, ChevronRight, MapPin, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getItemKey, type ItemSection, type SectionItem } from "@/services/api/types";
import { sectionConfig } from "../sectionConfig";
import { EmptyState, TagList } from "./common";

export function ItemsTab({
  section,
  items,
  onAdd,
}: {
  section: ItemSection;
  items: SectionItem[];
  onAdd: () => void;
}) {
  const config = sectionConfig[section];
  const Icon = config.icon;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {items.length} {items.length > 1 ? config.label.toLowerCase() : config.singular}
        </p>
        <Button size="sm" variant="outline" onClick={onAdd}>
          <Plus className="size-4" />
          {config.addLabel}
        </Button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon={Icon}
          title={config.emptyTitle}
          text={config.emptyText}
          action={
            <Button size="sm" onClick={onAdd}>
              <Plus className="size-4" />
              {config.addLabel}
            </Button>
          }
        />
      ) : (
        <div className="grid gap-3">
          {items.map((item, i) => {
            const s = config.summary(item);
            const [location, dates] = s.meta.length === 2 ? s.meta : [undefined, s.meta[0]];
            return (
              <Link
                key={getItemKey(item, i)}
                to="/candidat/$section/$id"
                params={{ section, id: getItemKey(item, i) }}
                className="group flex animate-fade-up items-start gap-4 rounded-xl border bg-card p-5 shadow-soft transition-all hover:border-primary/30 hover:shadow-lift"
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                  <Icon className="size-[18px]" />
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="font-medium leading-snug">{s.title}</h3>
                  {s.subtitle && <p className="text-sm text-muted-foreground">{s.subtitle}</p>}
                  {s.description && <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{s.description}</p>}
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {location && (
                      <span className="inline-flex items-center gap-1">
                        <MapPin className="size-3" />
                        {location}
                      </span>
                    )}
                    {dates && (
                      <span className="inline-flex items-center gap-1">
                        <CalendarDays className="size-3" />
                        {dates}
                      </span>
                    )}
                  </div>
                  {s.tags.length > 0 && (
                    <div className="mt-3">
                      <TagList tags={s.tags} max={5} />
                    </div>
                  )}
                </div>
                <ChevronRight className="mt-2 size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
