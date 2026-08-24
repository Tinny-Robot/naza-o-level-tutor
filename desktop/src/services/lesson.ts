import { apiFetch } from "./api";
import type { LessonPayload } from "./types";

export async function getLesson(): Promise<LessonPayload> {
  return apiFetch<LessonPayload>("/lesson");
}
