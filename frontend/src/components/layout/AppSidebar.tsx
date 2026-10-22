import { Link, useRouterState } from "@tanstack/react-router";
import { Briefcase, Settings, UserRound, type LucideIcon } from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { initials } from "@/features/candidate/format";
import { useProfile } from "@/features/candidate/hooks";

const SOON: { label: string; icon: LucideIcon }[] = [{ label: "Paramètres", icon: Settings }];

export function AppSidebar() {
  const { data } = useProfile();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const p = data?.personal;
  const name = [p?.first_name, p?.last_name].filter(Boolean).join(" ") || "Candidat";

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-1 py-1.5 group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:px-0">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-sm font-semibold text-primary-foreground">
            J
          </div>
          <span className="flex-1 truncate text-sm font-semibold group-data-[collapsible=icon]:hidden">
            Job Application Agent
          </span>
          <SidebarTrigger className="text-muted-foreground" aria-label="Réduire ou agrandir la barre latérale" />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  tooltip="Candidat"
                  isActive={pathname.startsWith("/candidat")}
                >
                  <Link to="/candidat" search={{ tab: "experiences" }}>
                    <UserRound />
                    <span>Candidat</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  tooltip="Mes candidatures"
                  isActive={pathname.startsWith("/cvs")}
                >
                  <Link to="/cvs">
                    <Briefcase />
                    <span>Mes candidatures</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              {SOON.map((item) => (
                <SidebarMenuItem key={item.label}>
                  <SidebarMenuButton disabled tooltip={`${item.label} — bientôt`} className="cursor-not-allowed">
                    <item.icon />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                  <SidebarMenuBadge className="rounded-full bg-muted px-1.5 text-[10px] font-medium text-muted-foreground">
                    Bientôt
                  </SidebarMenuBadge>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <div className="flex items-center gap-2.5 rounded-lg p-1.5 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-0">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
            {initials(p?.first_name, p?.last_name)}
          </div>
          <div className="min-w-0 group-data-[collapsible=icon]:hidden">
            <p className="truncate text-sm font-medium">{name}</p>
            <p className="truncate text-xs text-muted-foreground">{p?.email ?? "Mode démonstration"}</p>
          </div>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
