// Interview questions of the analysis (analysis.json, interview_questions), shown in « Préparer l'entretien ».
// Display only: possible questions to prepare, never presented as the questions the recruiter will ask.

import { ChevronDown } from "lucide-react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import { TagList } from "@/features/candidate/components/common";
import type { InterviewQuestion, InterviewQuestionKind, Requirement } from "@/services/api/cvTypes";
import { STATUS_CLASSES, STATUS_LABELS } from "../analysisLabels";
import { EvidenceBadges, MetaBadge } from "./AnalysisParts";

const KIND_LABELS: Record<InterviewQuestionKind, string> = {
  technical: "Technique",
  experience: "Expérience",
  gap: "Point à clarifier",
  motivation: "Motivation",
};

function Detail({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h5 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h5>
      {children}
    </div>
  );
}

function QuestionItem({
  item,
  requirements,
}: {
  item: InterviewQuestion;
  requirements: Requirement[];
}) {
  // Linked requirements with their status: keeps « Non remplie » and « Non documentée » distinct
  const linked = item.requirement_ids
    .flatMap((id) => {
      const exact = requirements.find((r) => r.id === id);
      return exact ? [exact] : requirements.filter((r) => r.parent_id === id);
    })
    .filter((r, i, all) => all.findIndex((x) => x.id === r.id) === i);

  return (
    <Collapsible className="group/question rounded-lg bg-muted/40">
      <CollapsibleTrigger className="flex w-full items-start gap-3 rounded-lg px-4 py-3 text-left transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
        <span className="min-w-0 flex-1 text-sm font-medium leading-relaxed">{item.question}</span>
        <span className="hidden shrink-0 pt-0.5 text-[11px] text-muted-foreground sm:inline">
          {KIND_LABELS[item.kind] ?? item.kind}
        </span>
        <ChevronDown className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-data-[state=open]/question:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3.5 px-4 pb-4">
        {item.purpose && (
          <Detail title="Ce que le recruteur cherche à évaluer">
            <p className="text-sm leading-relaxed text-muted-foreground">{item.purpose}</p>
          </Detail>
        )}
        {item.answer_guidance.length > 0 && (
          <Detail title="Pistes de réponse">
            <ul className="space-y-1.5">
              {item.answer_guidance.map((tip, i) => (
                <li key={i} className="flex gap-3 text-sm leading-relaxed">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/60" />
                  {tip}
                </li>
              ))}
            </ul>
          </Detail>
        )}
        {item.evidence.length > 0 && (
          <Detail title="Expériences utiles">
            <div className="flex flex-wrap gap-1.5">
              <EvidenceBadges evidence={item.evidence} />
            </div>
          </Detail>
        )}
        {item.topics_to_review.length > 0 && (
          <Detail title="Notions à réviser">
            <TagList tags={item.topics_to_review} />
          </Detail>
        )}
        {linked.length > 0 && (
          <Detail title="Exigence liée">
            <ul className="space-y-1.5">
              {linked.map((r) => (
                <li
                  key={r.id}
                  className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground"
                >
                  {r.text}
                  <Badge className={`border-transparent font-normal ${STATUS_CLASSES[r.status]}`}>
                    {STATUS_LABELS[r.status]}
                  </Badge>
                </li>
              ))}
            </ul>
          </Detail>
        )}
        <div className="sm:hidden">
          <MetaBadge>{KIND_LABELS[item.kind] ?? item.kind}</MetaBadge>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function InterviewQuestions({
  questions,
  requirements,
}: {
  questions: InterviewQuestion[];
  requirements: Requirement[];
}) {
  if (questions.length === 0) return null;
  return (
    <div className="space-y-2.5">
      <div>
        <h4 className="text-sm font-medium">Questions possibles</h4>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Des questions plausibles pour cette offre, à préparer : le recruteur ne les posera pas
          forcément.
        </p>
      </div>
      <div className="space-y-2">
        {questions.map((item, i) => (
          <QuestionItem key={i} item={item} requirements={requirements} />
        ))}
      </div>
    </div>
  );
}
