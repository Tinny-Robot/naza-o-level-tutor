import { apiFetch } from "./api";

export type PracticeImage = {
  url: string;
  path?: string;
  caption?: string;
};

export type PracticeQuestion = {
  id: string;
  subject: string;
  topic: string;
  exam_board: string;
  jamb_style?: boolean;
  year?: string | number;
  question: string;
  options: string[];
  answer: string;
  explanation: string;
  images?: PracticeImage[];
};

export function fetchPracticeTopics(subject: string) {
  return apiFetch<{ subject: string; topics: string[] }>(
    `/practice/topics?subject=${encodeURIComponent(subject)}`,
  );
}

export function fetchNextPractice(body: {
  subject: string;
  topic?: string | null;
  exam?: string;
  n?: number;
}) {
  return apiFetch<{ items: PracticeQuestion[] }>("/practice/next", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function submitPracticeAnswer(body: {
  subject: string;
  topic: string;
  question_id: string;
  question: string;
  options: string[];
  answer: string;
  student_answer: string;
  explanation: string;
}) {
  return apiFetch<{
    correct: boolean;
    expected: string;
    explanation: string;
    feedback: string;
    encouragement: string;
    confused?: string | null;
  }>("/practice/answer", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
