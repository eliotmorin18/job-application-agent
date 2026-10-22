import { queryOptions, useQuery } from "@tanstack/react-query";

import { ApiError, cvApi } from "@/services/api/cvApi";

export const cvListQuery = queryOptions({
  queryKey: ["cvs"],
  queryFn: () => cvApi.listCvs(),
});

/** Never retried on 409 (CV created before cv.json) or 404: those are answers, not failures. */
const retryUnlessClientError = (count: number, error: Error) =>
  !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2;

export const cvDetailQuery = (id: string) =>
  queryOptions({
    queryKey: ["cvs", id, "detail"],
    queryFn: () => cvApi.getCv(id),
    retry: retryUnlessClientError,
  });

export const cvAnalysisQuery = (id: string) =>
  queryOptions({
    queryKey: ["cvs", id, "analysis"],
    queryFn: () => cvApi.getAnalysis(id),
    retry: retryUnlessClientError,
  });

/** Zones of one compiled version of the PDF (`version` = updated_at of the CV): refetched with each new PDF. */
export const cvLayoutQuery = (id: string, version: number) =>
  queryOptions({
    queryKey: ["cvs", id, "layout", version],
    queryFn: () => cvApi.getLayout(id),
    retry: retryUnlessClientError,
    staleTime: Infinity,
  });

export function useCvList() {
  return useQuery(cvListQuery);
}

/** Polls a generation/analysis task while it is pending or running. */
export function useCvTask(taskId: string | null) {
  return useQuery({
    queryKey: ["cv-task", taskId],
    queryFn: () => cvApi.getTask(taskId!),
    enabled: taskId !== null,
    retry: retryUnlessClientError,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" || query.state.error ? false : 1000;
    },
  });
}

/** Message to show for an API error, with the backend "problems" when there are some. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.title && error.status !== 0)
    return `${error.title} : ${error.message}`;
  return error instanceof Error ? error.message : "Une erreur est survenue.";
}
