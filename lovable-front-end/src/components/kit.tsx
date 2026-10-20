import { Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { setDemoMode } from "@/api";
import { CURRENT_KEY, useDemoMode, useReachable } from "@/lib/use-application";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "warning" | "danger";
const variants: Record<Variant, string> = {
  primary: "bg-primary text-primary-foreground hover:bg-primary/90",
  secondary: "border border-input bg-card text-foreground hover:bg-accent",
  ghost: "text-muted-foreground underline-offset-4 hover:text-foreground hover:underline px-0",
  warning: "bg-warning text-primary-foreground hover:bg-warning/90",
  danger: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
};

export function Btn({
  variant = "primary",
  className,
  loading,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean }) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={cn(
        "inline-flex h-9 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:pointer-events-none disabled:opacity-50",
        variants[variant],
        className,
      )}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent", className)}
    />
  );
}

export function ErrorText({ children }: { children: ReactNode }) {
  if (!children) return null;
  return <p className="mt-2 animate-fade-in text-sm text-destructive">{children}</p>;
}

export function Section({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn("animate-fade-in border-t pt-8", className)}>
      <h2 className="mb-5 text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">{title}</h2>
      {children}
    </section>
  );
}

export function Notice({ tone, children }: { tone: "warning" | "error" | "info"; children: ReactNode }) {
  const t = {
    warning: "border-warning bg-warning-soft",
    error: "border-destructive bg-destructive-soft",
    info: "border-primary bg-primary-soft",
  }[tone];
  return <div className={cn("rounded-r-md border-l-2 px-4 py-3 text-sm", t)}>{children}</div>;
}

function DemoSwitch() {
  const on = useDemoMode();
  return (
    <button
      onClick={() => setDemoMode(!on)}
      className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground"
      aria-pressed={on}
    >
      <span className={cn("relative block h-4 w-7 rounded-full transition-colors", on ? "bg-primary" : "bg-input")}>
        <span
          className={cn(
            "absolute left-0 top-0.5 block h-3 w-3 rounded-full bg-card transition-transform",
            on ? "translate-x-3.5" : "translate-x-0.5",
          )}
        />
      </span>
      Mode démo
    </button>
  );
}

function OfflineBanner() {
  const reachable = useReachable();
  const demo = useDemoMode();
  const qc = useQueryClient();
  if (reachable || demo) return null;
  return (
    <div className="border-b border-destructive/30 bg-destructive-soft">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-5 py-2.5">
        <p className="text-sm font-medium text-destructive">
          Agent local injoignable — lance le serveur sur ton ordinateur
        </p>
        <Btn variant="danger" className="h-8 px-3" onClick={() => qc.refetchQueries({ queryKey: CURRENT_KEY })}>
          Réessayer
        </Btn>
      </div>
    </div>
  );
}

export function Shell({ children, width = "max-w-2xl" }: { children: ReactNode; width?: string }) {
  const demo = useDemoMode();
  return (
    <div className="min-h-screen">
      <OfflineBanner />
      <header>
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-5">
          <div className="flex items-center gap-3">
            <Link to="/" className="text-sm font-semibold tracking-tight">
              Candidature
            </Link>
            {demo && (
              <span className="rounded bg-warning px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-primary-foreground">
                DÉMO
              </span>
            )}
          </div>
          <DemoSwitch />
        </div>
      </header>
      <main className={cn("mx-auto px-5 pb-16 pt-8 sm:pt-12", width)}>{children}</main>
    </div>
  );
}

export function OfferHeader({ company, title }: { company?: string | null | undefined; title?: string | null | undefined }) {
  if (!company && !title) {
    return <p className="text-sm text-muted-foreground">Lecture de l'offre…</p>;
  }
  return (
    <div className="animate-fade-in">
      <p className="text-sm text-muted-foreground">{company}</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-[28px]">{title}</h1>
    </div>
  );
}
