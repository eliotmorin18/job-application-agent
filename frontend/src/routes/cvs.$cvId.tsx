import { createFileRoute } from "@tanstack/react-router";

import { CV_DETAIL_TABS, CvDetailPage, type CvDetailTab } from "@/features/cvs/pages/CvDetailPage";

export const Route = createFileRoute("/cvs/$cvId")({
  validateSearch: (search: Record<string, unknown>): { tab: CvDetailTab } => ({
    tab: CV_DETAIL_TABS.includes(search["tab"] as CvDetailTab)
      ? (search["tab"] as CvDetailTab)
      : "analyse",
  }),
  head: () => ({
    meta: [
      { title: "Candidature — Job Application Agent" },
      {
        name: "description",
        content: "Comprenez l'offre, préparez l'entretien et retouchez le CV de cette candidature.",
      },
      { property: "og:title", content: "Candidature — Job Application Agent" },
      {
        property: "og:description",
        content: "Comprenez l'offre, préparez l'entretien et retouchez le CV de cette candidature.",
      },
    ],
  }),
  component: CvDetailRoute,
});

function CvDetailRoute() {
  const { cvId } = Route.useParams();
  const { tab } = Route.useSearch();
  return <CvDetailPage cvId={cvId} tab={tab} />;
}
