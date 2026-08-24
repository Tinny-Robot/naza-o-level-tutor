import { apiFetch } from "./api";
import type { QuizPayload } from "./types";

export async function getQuiz(): Promise<QuizPayload> {
  return apiFetch<QuizPayload>("/quiz");
}
