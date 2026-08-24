import { apiFetch } from "./api";

export type ExamImage = {
  path?: string;
  url: string;
  caption?: string;
};

export type ExamItem = {
  id: string;
  topic: string;
  question: string;
  passage?: string | null;
  options: string[];
  year?: string | number | null;
  exam_board: string;
  paper_type?: string;
  jamb_style?: boolean;
  images?: ExamImage[];
};

export function fetchExamMeta() {
  return apiFetch<{
    exams: string[];
    subjects: string[];
    sizes: number[];
    bank?: Record<
      string,
      { total: number; by_board: Record<string, number>; with_images: number }
    >;
  }>("/exams/meta");
}

export function startExam(body: {
  exam: string;
  subject: string;
  n: number;
  minutes: number;
}) {
  return apiFetch<{
    session_id: string;
    exam: string;
    subject: string;
    duration_s: number;
    requested: number;
    delivered: number;
    items: ExamItem[];
  }>("/exams/start", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function submitExam(body: {
  session_id: string;
  answers: Record<string, string>;
  flagged: string[];
}) {
  return apiFetch<{
    score_pct: number;
    correct: number;
    total: number;
    breakdown: {
      topic: string;
      correct: number;
      total: number;
      accuracy: number;
    }[];
    weak_topics: string[];
    incorrect: {
      topic: string;
      question?: string;
      expected?: string;
      explanation?: string;
    }[];
  }>("/exams/submit", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function resolveExamImageUrl(url: string, path?: string): string {
  if (url.startsWith("http")) return url;
  if (url.startsWith("/api/")) return url;
  if (url.startsWith("/media")) return `/api${url}`;
  if (path) return `/api/media?path=${encodeURIComponent(path)}`;
  return url;
}
