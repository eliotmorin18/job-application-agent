import { queryOptions, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { toast } from "sonner";

import { candidateApi } from "@/services/api/candidateApi";

export const profileQuery = queryOptions({
  queryKey: ["candidate-profile"],
  queryFn: () => candidateApi.getProfile(),
});

export function useProfile() {
  return useQuery(profileQuery);
}

/** Runs an API action, refreshes the profile and shows a success/error toast. */
export function useCandidateAction() {
  const qc = useQueryClient();
  return useCallback(
    async (fn: () => Promise<unknown>, successMessage?: string): Promise<boolean> => {
      try {
        await fn();
        await qc.invalidateQueries({ queryKey: profileQuery.queryKey });
        if (successMessage) toast.success(successMessage);
        return true;
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Une erreur est survenue.");
        return false;
      }
    },
    [qc],
  );
}
