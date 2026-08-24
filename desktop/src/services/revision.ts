import { apiFetch } from "./api";
import type { RevisionPayload } from "./types";

export async function getRevision(): Promise<RevisionPayload> {
  return apiFetch<RevisionPayload>("/revision");
}
