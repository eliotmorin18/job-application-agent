import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "@tanstack/react-router";
import { useEffect, useState, useSyncExternalStore } from "react";
import { api, errorMessage, isDemoMode, isReachable, subscribeDemoMode, type AppStatus } from "@/api";

export const CURRENT_KEY = ["application", "current"];

export function useDemoMode() {
  return useSyncExternalStore(subscribeDemoMode, isDemoMode, () => false);
}
export function useReachable() {
  return useSyncExternalStore(subscribeDemoMode, isReachable, () => true);
}

/** Écran correspondant à chaque statut — seule source de vérité des redirections. */
export function pathForStatus(status: AppStatus): "/suivi" | "/questions" | "/recap" {
  switch (status) {
    case "questions":
      return "/questions";
    case "ready":
    case "submitted":
    case "abandoned":
      return "/recap";
    default:
      return "/suivi";
  }
}

/**
 * Candidature en cours, interrogée toutes les 2 secondes.
 * Avec `follow`, la page redirige automatiquement selon le statut.
 */
export function useApplication({ follow = true, poll = true } = {}) {
  const demo = useDemoMode();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  useEffect(() => {
    qc.resetQueries({ queryKey: CURRENT_KEY });
  }, [demo, qc]);

  const query = useQuery({
    queryKey: CURRENT_KEY,
    queryFn: () => api.getCurrent(),
    refetchInterval: poll ? 2000 : false,
    retry: false,
  });

  const status = query.data?.status;
  useEffect(() => {
    if (!follow || !status) return;
    const target = pathForStatus(status);
    if (target !== pathname) navigate({ to: target, replace: true });
  }, [follow, status, pathname, navigate]);

  return query;
}

export function useRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: CURRENT_KEY });
}

/** Bouton d'action : chargement, erreur courte, puis rafraîchissement si succès. */
export function useAction<A extends unknown[]>(fn: (...args: A) => Promise<unknown>) {
  const refresh = useRefresh();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(...args: A): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await fn(...args);
      await refresh();
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { run, busy, error };
}
