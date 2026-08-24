import { useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";
import { GraduationCap, Lightbulb, Send } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Naza } from "../../components/naza/Naza";
import { Badge } from "../../components/ui/Badge";
import { Button, ButtonLink } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { MarkdownMessage } from "../../components/ui/MarkdownMessage";
import { stripChunkCitations } from "../../utils/stripChunkCitations";
import { TextArea } from "../../components/ui/Input";
import { ApiError } from "../../services/api";
import { looksLikeLessonIntent, sendChat } from "../../services/chat";
import { planCourse } from "../../services/learn";
import type {
  ChatMessage,
  ChatResponse,
  LessonResponse,
  TutorResponse,
} from "../../services/types";
import { isLessonResponse } from "../../services/types";
import { useLanguage } from "../../i18n/LanguageProvider";
import type { MessageKey } from "../../i18n/en";
import styles from "../pages.module.css";
import { LessonView } from "./LessonView";

type Msg = {
  role: "user" | "assistant";
  text: string;
  full?: string;
  meta?: ChatResponse;
  typing?: boolean;
};

const TYPE_MS = 12;
const STARTERS: MessageKey[] = [
  "tutor.starter1",
  "tutor.starter2",
  "tutor.starter3",
  "tutor.starter4",
];

export function TutorPage() {
  const { t } = useLanguage();
  const reduceMotion = Boolean(useReducedMotion());
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [savingCourse, setSavingCourse] = useState(false);
  const bootTopicRef = useRef<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [last, setLast] = useState<TutorResponse | null>(null);
  const [activeLesson, setActiveLesson] = useState<LessonResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryPayload, setRetryPayload] = useState<{
    message: string;
    history: ChatMessage[];
  } | null>(null);
  const [composerFocusToken, setComposerFocusToken] = useState(0);
  const [buildingLesson, setBuildingLesson] = useState(false);
  const typingTimer = useRef<number | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  const citations = last?.citations ?? [];
  const isEmpty = messages.length === 0 && !busy && !error && !buildingLesson;

  const modeBadge = useMemo(() => {
    if (!last) return null;
    if (isLessonResponse(last)) {
      return <Badge tone="study">{t("tutor.lessonMode")}</Badge>;
    }
    return last.mode === "study" ? (
      <Badge tone="study">{t("tutor.studyMode")}</Badge>
    ) : (
      <Badge tone="general">{t("tutor.generalMode")}</Badge>
    );
  }, [last, t]);

  useEffect(() => {
    setMessages((m) => {
      if (m.length === 0) return [];
      if (m.length === 1 && m[0].role === "assistant" && !m[0].meta) return [];
      return m;
    });
  }, [t]);

  useEffect(() => {
    return () => {
      if (typingTimer.current != null) window.clearInterval(typingTimer.current);
    };
  }, []);

  useEffect(() => {
    if (composerFocusToken > 0) {
      composerRef.current?.focus();
    }
  }, [composerFocusToken]);

  useEffect(() => {
    const q = searchParams.get("q")?.trim();
    const topic = searchParams.get("topic")?.trim();
    const boot = q || (topic ? `Teach me ${topic}` : "");
    if (!boot || bootTopicRef.current === boot) return;
    bootTopicRef.current = boot;
    setSearchParams({}, { replace: true });
    void send(boot);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- boot once per topic param
  }, [searchParams]);

  function finishTyping() {
    if (typingTimer.current != null) {
      window.clearInterval(typingTimer.current);
      typingTimer.current = null;
    }
    setMessages((m) => {
      const copy = [...m];
      const idx = copy.length - 1;
      if (idx >= 0 && copy[idx].typing) {
        copy[idx] = {
          ...copy[idx],
          text: copy[idx].full || copy[idx].text,
          typing: false,
        };
      }
      return copy;
    });
  }

  function revealAnswer(full: string, meta: ChatResponse) {
    const cleaned = stripChunkCitations(full);
    if (reduceMotion) {
      setMessages((m) => [...m, { role: "assistant", text: cleaned, full: cleaned, meta }]);
      return;
    }
    const placeholder: Msg = {
      role: "assistant",
      text: "",
      full: cleaned,
      meta,
      typing: true,
    };
    setMessages((m) => [...m, placeholder]);
    let i = 0;
    if (typingTimer.current != null) window.clearInterval(typingTimer.current);
    typingTimer.current = window.setInterval(() => {
      i += 1;
      const slice = cleaned.slice(0, i);
      setMessages((m) => {
        const copy = [...m];
        const idx = copy.length - 1;
        if (idx >= 0 && copy[idx].typing) {
          copy[idx] = {
            ...copy[idx],
            text: slice,
            typing: i < cleaned.length,
          };
        }
        return copy;
      });
      if (i >= cleaned.length && typingTimer.current != null) {
        window.clearInterval(typingTimer.current);
        typingTimer.current = null;
      }
    }, TYPE_MS);
  }

  async function send(text?: string) {
    const q = (text ?? input).trim();
    if (!q || busy) return;

    const history: ChatMessage[] = messages
      .filter((m) => m.role === "user" || (m.role === "assistant" && Boolean(m.meta)))
      .map((m) => ({
        role: m.role,
        content: m.meta?.answer ?? m.text,
      }));

    if (activeLesson) {
      history.push({
        role: "assistant",
        content: activeLesson.answer || t("tutor.lessonReady", { title: activeLesson.title }),
      });
    }

    const lessonIntent = looksLikeLessonIntent(q);
    setInput("");
    setBusy(true);
    setBuildingLesson(lessonIntent);
    setError(null);
    setRetryPayload({ message: q, history });
    setMessages((m) => [...m, { role: "user", text: q }]);
    setActiveLesson(null);

    try {
      const res = await sendChat(q, history);
      setLast(res);
      setRetryPayload(null);
      setBuildingLesson(false);
      if (isLessonResponse(res)) {
        setActiveLesson(res);
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            text: t("tutor.opening", { title: res.title }),
            meta: {
              type: "chat",
              mode: "study",
              answer: res.answer || t("tutor.lessonReady", { title: res.title }),
              citations: res.citations,
              confidence: res.confidence,
              retrieved_chunks: [],
              refused: res.refused,
              latency_ms: res.latency_ms ?? 0,
            },
          },
        ]);
      } else {
        revealAnswer(res.answer, res);
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t("offline");
      setError(msg);
      setMessages((m) => m.slice(0, -1));
      if (!lessonIntent) setBuildingLesson(false);
    } finally {
      setBusy(false);
    }
  }

  async function retry() {
    if (!retryPayload || busy) return;
    const { message, history } = retryPayload;
    const lessonIntent = looksLikeLessonIntent(message);
    setBusy(true);
    setBuildingLesson(lessonIntent);
    setError(null);
    setMessages((m) => [...m, { role: "user", text: message }]);
    try {
      const res = await sendChat(message, history);
      setLast(res);
      setRetryPayload(null);
      setBuildingLesson(false);
      if (isLessonResponse(res)) {
        setActiveLesson(res);
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            text: t("tutor.opening", { title: res.title }),
            meta: {
              type: "chat",
              mode: "study",
              answer: res.answer || t("tutor.lessonReady", { title: res.title }),
              citations: res.citations,
              confidence: res.confidence,
              retrieved_chunks: [],
              refused: res.refused,
              latency_ms: res.latency_ms ?? 0,
            },
          },
        ]);
      } else {
        revealAnswer(res.answer, res);
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t("offline");
      setError(msg);
      setMessages((m) => m.slice(0, -1));
      if (!lessonIntent) setBuildingLesson(false);
    } finally {
      setBusy(false);
    }
  }

  function askFollowUp() {
    setActiveLesson(null);
    setComposerFocusToken((n) => n + 1);
  }

  function continueLearning(topicHint?: string) {
    const next = topicHint
      ? t("tutor.continueMore", { topic: topicHint })
      : t("tutor.continueNext");
    void send(next);
  }

  async function saveAsCourse() {
    if (!activeLesson || savingCourse) return;
    setSavingCourse(true);
    setError(null);
    try {
      const course = await planCourse({ topic: activeLesson.title });
      navigate(`/learn/${course.id}`);
    } catch {
      setError(t("tutor.saveError"));
    } finally {
      setSavingCourse(false);
    }
  }

  const statusCopy = buildingLesson
    ? t("tutor.findingLesson")
    : busy
      ? t("tutor.preparing")
      : null;

  return (
    <div className={`${styles.page} ${styles.pageFill}`}>
      <div className={styles.tutorLayout}>
        <div className={styles.chatPane}>
          <div className={styles.chatHeader}>
            <div className={styles.pillRow}>
              {modeBadge ?? <Badge tone="offline">{t("tutor.auto")}</Badge>}
              {last ? (
                <span className={styles.muted}>
                  {t("tutor.confidence", { pct: (last.confidence * 100).toFixed(0) })}
                </span>
              ) : null}
            </div>
            <span className={styles.muted}>{t("tutor.modes")}</span>
          </div>
          {last?.refused ? (
            <p className={styles.tutorStatus} role="status">
              {t("tutor.refused")}
            </p>
          ) : last && last.confidence < 0.45 ? (
            <p className={styles.tutorStatus} role="status">
              {t("tutor.confidenceLow")}
            </p>
          ) : null}

          {activeLesson ? (
            <>
              <div className={styles.banner}>
                {t("tutor.keepLecture")}
                <div className={`${styles.pillRow} ${styles.metaFoot}`}>
                  <ButtonLink
                    to={`/learn?topic=${encodeURIComponent(activeLesson.title)}`}
                    variant="ghost"
                  >
                    <GraduationCap size={14} /> {t("tutor.openLearn")}
                  </ButtonLink>
                  <Button
                    variant="ghost"
                    onClick={() => void saveAsCourse()}
                    disabled={savingCourse || busy}
                    loading={savingCourse}
                  >
                    {savingCourse ? t("tutor.saving") : t("tutor.saveCourse")}
                  </Button>
                </div>
              </div>
              <LessonView
                lesson={activeLesson}
                onAskFollowUp={askFollowUp}
                onContinueLearning={continueLearning}
              />
            </>
          ) : buildingLesson ? (
            <div className={styles.lessonBuilding} role="status" aria-live="polite">
              <Card lift={false} className={styles.lessonBuildingCard}>
                {!error ? <div className={styles.lessonBuildingPulse} aria-hidden /> : null}
                <p className={styles.eyebrow}>{t("tutor.lessonMode")}</p>
                <h2 className={styles.sectionTitle}>
                  {error ? t("tutor.buildFail") : t("tutor.building")}
                </h2>
                <p className={`${styles.muted} ${styles.lessonLead}`}>
                  {error ? error : t("tutor.buildingLead")}
                </p>
                <div className={`${styles.pillRow} ${styles.sectionBodyGap}`}>
                  {error ? (
                    <Button onClick={() => void retry()} disabled={busy || !retryPayload} loading={busy}>
                      {t("tutor.retry")}
                    </Button>
                  ) : null}
                  {error ? (
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setBuildingLesson(false);
                        setError(null);
                      }}
                    >
                      {t("tutor.backChat")}
                    </Button>
                  ) : null}
                </div>
              </Card>
            </div>
          ) : (
            <>
              <div className={styles.messages}>
                {isEmpty ? (
                  <div className={styles.tutorEmpty}>
                    <Naza pose="look" size={80} speech={t("tutor.emptyLead")} />
                    <p className={styles.muted}>{t("tutor.hello")}</p>
                    <div className={styles.pillRow}>
                      {STARTERS.map((key) => (
                        <Button
                          key={key}
                          variant="ghost"
                          onClick={() => void send(t(key))}
                          disabled={busy}
                        >
                          {t(key)}
                        </Button>
                      ))}
                    </div>
                  </div>
                ) : (
                  messages.map((m, i) => (
                    <div
                      key={i}
                      className={m.role === "user" ? styles.bubbleUser : styles.bubbleAi}
                      aria-busy={m.typing || undefined}
                      onClick={m.typing ? finishTyping : undefined}
                    >
                      {m.role === "assistant" && !m.typing ? (
                        <MarkdownMessage>{m.text}</MarkdownMessage>
                      ) : (
                        <>
                          {m.text}
                          {m.typing ? "▍" : null}
                        </>
                      )}
                      {m.role === "assistant" &&
                        m.meta?.mode === "study" &&
                        !m.typing && (
                          <div className={`${styles.pillRow} ${styles.sectionBodyGap}`}>
                            <Button
                              variant="ghost"
                              onClick={() => void send(t("tutor.promptSimpler"))}
                              disabled={busy}
                            >
                              {t("tutor.simpler")}
                            </Button>
                            <Button
                              variant="ghost"
                              onClick={() => void send(t("tutor.promptExample"))}
                              disabled={busy}
                            >
                              <Lightbulb size={14} /> {t("tutor.example")}
                            </Button>
                            <Button
                              variant="secondary"
                              onClick={() => void send(t("tutor.promptQuiz"))}
                              disabled={busy}
                            >
                              {t("tutor.quiz")}
                            </Button>
                          </div>
                        )}
                    </div>
                  ))
                )}
                {statusCopy && !buildingLesson ? (
                  <p className={styles.tutorStatus} role="status" aria-live="polite">
                    {statusCopy}
                  </p>
                ) : null}
                {error ? (
                  <Card lift={false} className={styles.empty}>
                    <Naza pose="look" size={48} />
                    <p className={styles.fieldSpaced}>{error}</p>
                    <Button onClick={() => void retry()} disabled={busy || !retryPayload} loading={busy}>
                      {t("tutor.retry")}
                    </Button>
                  </Card>
                ) : null}
              </div>

              <div className={styles.composer}>
                <TextArea
                  ref={composerRef}
                  rows={1}
                  placeholder={t("tutor.placeholder")}
                  value={input}
                  disabled={busy}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                />
                <Button onClick={() => void send()} disabled={busy} loading={busy} aria-label={t("tutor.send")}>
                  <Send size={16} />
                </Button>
              </div>
            </>
          )}

          {activeLesson ? (
            <div className={styles.composer}>
              <TextArea
                ref={composerRef}
                rows={1}
                placeholder={t("tutor.followPh")}
                value={input}
                disabled={busy}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
              />
              <Button onClick={() => void send()} disabled={busy} loading={busy}>
                <Send size={16} />
              </Button>
            </div>
          ) : null}
        </div>

        <aside className={styles.sourcesPane}>
          <h2 className={styles.sectionTitle}>{t("tutor.sources")}</h2>
          <p className={styles.muted}>
            {last && (isLessonResponse(last) || last.mode === "study")
              ? t("tutor.grounded")
              : t("tutor.noRetrieval")}
          </p>
          {citations.length === 0 ? (
            <Card lift={false} className={styles.empty}>
              {t("tutor.citeEmpty")}
            </Card>
          ) : (
            citations.map((c) => (
              <Card key={c.chunk_id} className={styles.citeCard}>
                <strong className={styles.citeTopic}>{c.topic}</strong>
              </Card>
            ))
          )}
        </aside>
      </div>
    </div>
  );
}
