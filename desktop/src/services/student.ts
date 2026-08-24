import { apiFetch } from "./api";

export type PlanItem = {
  kind: string;
  label: string;
  subject: string;
  topic: string;
};

export type StudentSummary = {
  display_name: string;
  streak_days: number;
  goal_today: string;
  goal_weekly: string;
  target_exam: string;
  lessons_completed: number;
  practice_answered: number;
  practice_accuracy: number | null;
  exams_taken: number;
  learning_plan: {
    title: string;
    items: PlanItem[];
    updated_at: string;
  };
  weak_topics: { subject: string; topic: string; score: number }[];
  subjects: { subject: string; mastery: number; topics: number }[];
  recommendation: string;
  recommend_topic: string;
  recommend_subject: string;
  continue_learning: {
    subject: string;
    topic: string;
    label: string;
    course_id?: string;
  };
  recent_activity: { kind?: string; at?: string; label?: string }[];
  preferences: {
    language: string;
    explanation_style: string;
    show_citations: boolean;
    onboarded?: boolean;
  };
  focus_areas: string[];
};

export function fetchStudentSummary() {
  return apiFetch<StudentSummary>("/student/summary");
}

export function patchPreferences(body: {
  language?: string;
  explanation_style?: string;
  show_citations?: boolean;
  display_name?: string;
  goal_today?: string;
  onboarded?: boolean;
}) {
  return apiFetch<{ ok: boolean; summary: StudentSummary }>("/student/preferences", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
