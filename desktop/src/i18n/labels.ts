import type { MessageKey } from "./en";
import type { MessageVars } from "./types";

type Translate = (key: MessageKey, vars?: MessageVars) => string;

const SUBJECTS: Record<string, MessageKey> = {
  english: "learn.subjects.english",
  mathematics: "learn.subjects.mathematics",
  physics: "learn.subjects.physics",
  chemistry: "learn.subjects.chemistry",
};

const PLAN_KINDS: Record<string, MessageKey> = {
  learn: "home.kind.learn",
  lesson: "home.kind.learn",
  lecture: "home.kind.learn",
  practice: "home.kind.practice",
  exam: "home.kind.exam",
  session: "home.kind.session",
};

const LEARN_STATUS: Record<string, MessageKey> = {
  ready: "learn.status.ready",
  in_progress: "learn.status.in_progress",
  complete: "learn.status.complete",
  planned: "learn.status.planned",
  archived: "learn.status.archived",
};

const LEARN_KIND: Record<string, MessageKey> = {
  lesson: "learn.kind.lesson",
  assessment: "learn.kind.assessment",
  practice: "learn.kind.practice",
  exam: "learn.kind.exam",
  lecture: "learn.kind.lecture",
};

export function labelSubject(subject: string, t: Translate) {
  const key = SUBJECTS[subject.toLowerCase()];
  return key ? t(key) : subject;
}

export function labelPlanKind(kind: string, t: Translate) {
  const key = PLAN_KINDS[kind.toLowerCase()];
  return key ? t(key) : kind;
}

export function labelLearnStatus(status: string, t: Translate) {
  const key = LEARN_STATUS[status];
  return key ? t(key) : status.replaceAll("_", " ");
}

export function labelLearnKind(kind: string, t: Translate) {
  const key = LEARN_KIND[kind];
  return key ? t(key) : kind;
}

export function formatActivityAt(at?: string) {
  if (!at) return "";
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return at.slice(0, 16);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function learnHref(topic?: string, subject?: string) {
  if (!topic) return "/learn";
  const q = new URLSearchParams({ topic });
  if (subject) q.set("subject", subject);
  return `/learn?${q.toString()}`;
}
