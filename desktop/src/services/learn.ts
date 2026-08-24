import { apiFetch } from "./api";
import type { LessonResponse } from "./types";

export type CourseStatus = "draft" | "in_progress" | "completed" | "archived";
export type NextActionKind = "continue" | "remediate" | "practice";

export type LessonOutcome = {
  check_correct?: boolean | null;
  practice_correct?: boolean | null;
  struggled?: boolean;
  completed_at?: string;
};

export type CourseLesson = {
  id: string;
  title: string;
  kind: string;
  rationale: string;
  status: string;
  payload?: LessonResponse | null;
  outcome?: LessonOutcome | null;
  has_payload?: boolean;
};

export type Course = {
  id: string;
  title: string;
  subject: string;
  topic: string;
  goal: string;
  confidence: string;
  style: string;
  exam: string;
  objective: string;
  status: CourseStatus;
  current_index: number;
  next_action?: {
    kind: NextActionKind;
    reason?: string;
    lesson_id?: string;
  };
  lessons: CourseLesson[];
  skipped_because?: { title: string; skipped_because: string }[];
  language?: string;
  progress?: {
    total: number;
    completed: number;
    pct: number;
    current_index: number;
    current_title: string;
  };
};

export type LectureSuggestion = {
  kind: string;
  subject: string;
  topic: string;
  title: string;
  reason: string;
  course_id?: string | null;
};

export type AssessItem = {
  id: string;
  topic: string;
  question: string;
  passage?: string | null;
  options: string[];
  year?: string | number | null;
  exam_board?: string;
  images?: { url: string; path?: string; caption?: string }[];
  answer?: string;
  explanation?: string;
};

export function listCourses(status?: string) {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiFetch<{ courses: Course[] }>(`/learn/courses${q}`);
}

export function fetchSuggestions() {
  return apiFetch<{ suggestions: LectureSuggestion[] }>("/learn/suggestions");
}

export function planCourse(body: {
  topic: string;
  subject?: string;
  goal?: string;
  confidence?: string;
  style?: string;
  exam?: string;
}) {
  return apiFetch<Course>("/learn/plan", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchCourse(id: string) {
  return apiFetch<Course>(`/learn/courses/${id}`);
}

export function generateCourseLesson(courseId: string, lessonId: string) {
  return apiFetch<Course>(
    `/learn/courses/${courseId}/lessons/${lessonId}/generate`,
    { method: "POST" },
  );
}

export function completeCourseLesson(
  courseId: string,
  lessonId: string,
  body: {
    check_correct?: boolean | null;
    practice_correct?: boolean | null;
    struggled?: boolean;
  },
) {
  return apiFetch<Course>(
    `/learn/courses/${courseId}/lessons/${lessonId}/complete`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function updateCourseProgress(
  courseId: string,
  body: { current_index?: number; status?: string; lesson_id?: string },
) {
  return apiFetch<Course>(`/learn/courses/${courseId}/progress`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchCourseAssessment(courseId: string, n = 6) {
  return apiFetch<{
    course_id: string;
    subject: string;
    topic: string;
    items: AssessItem[];
  }>(`/learn/courses/${courseId}/assess?n=${n}`, { method: "POST" });
}

export function regenerateCourse(courseId: string) {
  return apiFetch<Course>(`/learn/courses/${courseId}/regenerate`, {
    method: "POST",
  });
}
