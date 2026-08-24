import { apiFetch } from "./api";
import type { ProgressPayload } from "./types";

export async function getProgress(): Promise<ProgressPayload> {
  return apiFetch<ProgressPayload>("/progress");
}
