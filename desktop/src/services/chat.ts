import { apiFetch } from "./api";
import type {
  ChatMessage,
  HealthResponse,
  LessonFeedbackRequest,
  LessonFeedbackResponse,
  TutorResponse,
} from "./types";

/** Client-side mirror of backend lesson-intent cues (routing still server-side). */
export function looksLikeLessonIntent(text: string): boolean {
  const q = text.trim();
  if (!q) return false;
  if (/\bi\s+(?:just\s+)?learned\b/i.test(q)) return false;
  return /\b(?:teach\s+me|help\s+me\s+(?:to\s+)?(?:learn|understand)|i\s+want\s+to\s+learn|learn(?:\s+about)?|lesson\s+on|explain\s+the\s+topic|give\s+me\s+a\s+lesson|walk\s+me\s+through|can\s+you\s+teach)\b/i.test(
    q,
  );
}

export async function sendChat(
  message: string,
  history: ChatMessage[] = [],
): Promise<TutorResponse> {
  return apiFetch<TutorResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ message, history }),
  });
}

export async function sendLessonFeedback(
  body: LessonFeedbackRequest,
): Promise<LessonFeedbackResponse> {
  return apiFetch<LessonFeedbackResponse>("/lesson/feedback", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}
