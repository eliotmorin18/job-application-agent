import { createFileRoute } from "@tanstack/react-router";

import {
  CANDIDATE_TABS,
  CandidateProfilePage,
  type CandidateTab,
} from "@/features/candidate/pages/CandidateProfilePage";

export const Route = createFileRoute("/candidat/")({
  validateSearch: (search: Record<string, unknown>): { tab: CandidateTab } => ({
    tab: CANDIDATE_TABS.includes(search["tab"] as CandidateTab) ? (search["tab"] as CandidateTab) : "experiences",
  }),
  head: () => ({
    meta: [
      { title: "Mon profil candidat — Job Application Agent" },
      { name: "description", content: "Centralisez expériences, formations et compétences pour des CV sur mesure." },
      { property: "og:title", content: "Mon profil candidat — Job Application Agent" },
      { property: "og:description", content: "Centralisez expériences, formations et compétences pour des CV sur mesure." },
    ],
  }),
  component: CandidatePage,
});

function CandidatePage() {
  const { tab } = Route.useSearch();
  return <CandidateProfilePage tab={tab} />;
}
