import { API_BASE, ApiError, OFFLINE_ENGINE_MESSAGE, apiFetch } from "./api";
import type {
  ChatMessage,
  Citation,
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

export type StreamEvent =
  | {
      type: "meta";
      mode?: "study" | "general";
      citations?: Citation[];
      confidence?: number;
      refused?: boolean;
    }
  | { type: "token"; token: string };

/**
 * Stream a chat response as SSE token events.
 *
 * Yields StreamEvent objects as they arrive from the backend `/chat/stream` endpoint.
 * Supports cancellation via AbortSignal and detects empty/partial failure conditions.
 */
export async function* sendChatStream(
  message: string,
  history: ChatMessage[] = [],
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent, void, unknown> {
  const url = `${API_BASE.replace(/\/$/, "")}/chat/stream`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ message, history }),
      signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return;
    }
    throw new ApiError(OFFLINE_ENGINE_MESSAGE, { offline: true, status: 0 });
  }

  if (!res.ok) {
    throw new ApiError(`Stream request failed (${res.status}).`, {
      status: res.status,
      offline: res.status >= 500 || res.status === 0,
    });
  }

  const reader = res.body?.getReader();
  if (!reader) throw new ApiError("Streaming not supported.", { offline: true });

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (payload === "[DONE]") return;
        try {
          const parsed = JSON.parse(payload) as {
            type?: string;
            token?: string;
            error?: string;
            mode?: "study" | "general";
            citations?: Citation[];
            confidence?: number;
            refused?: boolean;
          };
          if (parsed.error) throw new ApiError(parsed.error);
          if (parsed.type === "meta") {
            yield {
              type: "meta",
              mode: parsed.mode,
              citations: parsed.citations,
              confidence: parsed.confidence,
              refused: parsed.refused,
            };
          } else if (parsed.type === "token" && parsed.token) {
            yield { type: "token", token: parsed.token };
          } else if (parsed.token) {
            yield { type: "token", token: parsed.token };
          }
        } catch (e) {
          if (e instanceof ApiError) throw e;
          // Ignore malformed SSE lines
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
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
