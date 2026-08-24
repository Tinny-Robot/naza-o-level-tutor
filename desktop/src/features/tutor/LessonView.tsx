import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ExamStemNote } from "../../components/layout/ExamStemNote";
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
  Lightbulb,
  MessageCircle,
  Sparkles,
} from "lucide-react";
import { Naza } from "../../components/naza/Naza";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Input, TextArea } from "../../components/ui/Input";
import { MarkdownMessage } from "../../components/ui/MarkdownMessage";
import { sendLessonFeedback } from "../../services/chat";
import { saveRevisionCard } from "../../services/revisionCards";
import { useLanguage } from "../../i18n/LanguageProvider";
import type { MessageKey } from "../../i18n/en";
import type {
  LessonFeedbackResponse,
  LessonResponse,
} from "../../services/types";
import styles from "../pages.module.css";

type NamedStep =
  | "introduction"
  | "objectives"
  | "concepts"
  | "worked"
  | "check"
  | "practice"
  | "feedback"
  | "summary"
  | "revision";

type WizardStep = NamedStep | `section-${number}`;

const STEP_KEYS: Record<NamedStep, MessageKey> = {
  introduction: "lesson.intro",
  objectives: "lesson.objectives",
  concepts: "lesson.concepts",
  worked: "lesson.worked",
  check: "lesson.check",
  practice: "lesson.practice",
  feedback: "lesson.feedback",
  summary: "lesson.summary",
  revision: "lesson.revision",
};

const AFTER_CONCEPTS: NamedStep[] = [
  "worked",
  "check",
  "practice",
  "feedback",
  "summary",
  "revision",
];

type Props = {
  lesson: LessonResponse;
  onAskFollowUp: () => void;
  onContinueLearning: (topicHint?: string) => void;
  onOutcome?: (partial: {
    check_correct?: boolean;
    practice_correct?: boolean;
  }) => void;
  hideDiagrams?: boolean;
  deepSections?: boolean;
};

function parseSectionStep(step: WizardStep): number | null {
  if (!step.startsWith("section-")) return null;
  const n = Number(step.slice("section-".length));
  return Number.isInteger(n) ? n : null;
}

function stepLabel(
  step: WizardStep,
  sectionCount: number,
  t: (key: MessageKey, vars?: Record<string, string | number>) => string,
): string {
  const idx = parseSectionStep(step);
  if (idx != null) {
    return t("lesson.conceptOf", { n: idx + 1, total: Math.max(sectionCount, 1) });
  }
  return t(STEP_KEYS[step as NamedStep]);
}

function sanitizeLessonBody(body: string): string {
  const text = body.trim();
  if (!text) return "";
  const looksJson =
    text.startsWith("```") ||
    (text.startsWith("{") &&
      (text.includes('"heading"') || text.includes('"body"') || text.includes('"sections"')));
  if (!looksJson) {
    return text.replace(/\s*\[Chunk\s+[^\]]+\]/gi, "").trim();
  }
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
  const candidate = fenced?.[1]?.trim() || text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  try {
    const parsed = JSON.parse(candidate) as {
      body?: string;
      content?: string;
      text?: string;
      sections?: { body?: string; content?: string }[];
    };
    const direct = parsed.body || parsed.content || parsed.text;
    if (typeof direct === "string" && direct.trim()) {
      return direct.replace(/\s*\[Chunk\s+[^\]]+\]/gi, "").trim();
    }
    const sectionBody = parsed.sections?.find((s) => s.body || s.content);
    const nested = sectionBody?.body || sectionBody?.content;
    if (typeof nested === "string" && nested.trim()) {
      return nested.replace(/\s*\[Chunk\s+[^\]]+\]/gi, "").trim();
    }
  } catch {
    const match = candidate.match(/"(?:body|content|text)"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (match?.[1]) {
      try {
        return JSON.parse(`"${match[1]}"`) as string;
      } catch {
        return match[1]
          .replace(/\\n/g, "\n")
          .replace(/\\"/g, '"')
          .replace(/\\\\/g, "\\")
          .replace(/\s*\[Chunk\s+[^\]]+\]/gi, "")
          .trim();
      }
    }
  }
  return "";
}

function SectionBody({ body }: { body: string }) {
  const { t } = useLanguage();
  const text = sanitizeLessonBody(body);
  if (!text) {
    return <p className={styles.muted}>{t("lesson.bodySoon")}</p>;
  }
  return <MarkdownMessage className={styles.sectionBody}>{text}</MarkdownMessage>;
}

function EmptyLine({ children }: { children: string }) {
  return <p className={styles.muted}>{children}</p>;
}

function mediaUrl(ref: { url: string; path?: string }) {
  if (ref.url.startsWith("http") || ref.url.startsWith("/api/") || ref.url.startsWith("/media")) {
    return ref.url.startsWith("/media") ? `/api${ref.url}` : ref.url;
  }
  return `/api/media?path=${encodeURIComponent(ref.path || "")}`;
}

function SectionDiagram({
  section,
  fallbackRefs,
  hideDiagrams,
}: {
  section: LessonResponse["sections"][number];
  fallbackRefs?: LessonResponse["image_refs"];
  hideDiagrams?: boolean;
}) {
  const { t } = useLanguage();
  if (hideDiagrams) return null;
  const refs = section.image_refs?.length ? section.image_refs : fallbackRefs;
  if (refs?.length) {
    return (
      <>
        {refs.map((ref) => (
          <figure key={mediaUrl(ref)} className={styles.diagramFrame}>
            <img
              src={mediaUrl(ref)}
              alt={ref.caption || t("lesson.diagram")}
              className={styles.diagramImg}
            />
            <figcaption className={`${styles.muted} ${styles.figCap}`}>
              {ref.caption || t("lesson.diagramCap")}
              {ref.page != null ? ` · p.${ref.page}` : ""}
            </figcaption>
          </figure>
        ))}
      </>
    );
  }
  if (section.diagram_svg) {
    return (
      <div
        className={styles.diagramFrame}
        dangerouslySetInnerHTML={{ __html: section.diagram_svg }}
      />
    );
  }
  return null;
}

export function LessonView({
  lesson,
  onAskFollowUp,
  onContinueLearning,
  onOutcome,
  hideDiagrams,
  deepSections,
}: Props) {
  const { t } = useLanguage();
  const reduceMotion = Boolean(useReducedMotion());
  const stepPanelRef = useRef<HTMLDivElement>(null);
  const steps = useMemo((): WizardStep[] => {
    const before: NamedStep[] = ["introduction", "objectives"];
    if (!deepSections || lesson.sections.length === 0) {
      return [...before, "concepts", ...AFTER_CONCEPTS];
    }
    const sectionSteps = lesson.sections.map(
      (_, i) => `section-${i}` as const,
    );
    return [...before, ...sectionSteps, ...AFTER_CONCEPTS];
  }, [deepSections, lesson.sections.length]);

  const [stepIndex, setStepIndex] = useState(0);
  const [checkAnswer, setCheckAnswer] = useState("");
  const [practiceAnswer, setPracticeAnswer] = useState("");
  const [showHint, setShowHint] = useState(false);
  const [feedback, setFeedback] = useState<LessonFeedbackResponse | null>(null);
  const [grading, setGrading] = useState(false);
  const [gradeError, setGradeError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [flipped, setFlipped] = useState(false);

  const step = steps[stepIndex] ?? "introduction";
  const sectionIdx = parseSectionStep(step);
  const currentSection =
    sectionIdx != null ? lesson.sections[sectionIdx] : undefined;
  const currentLabel = stepLabel(step, lesson.sections.length, t);
  const progress = ((stepIndex + 1) / Math.max(steps.length, 1)) * 100;
  const atStart = stepIndex === 0;
  const atEnd = stepIndex >= steps.length - 1;

  useEffect(() => {
    setStepIndex((i) => Math.min(i, Math.max(0, steps.length - 1)));
  }, [steps.length]);

  useEffect(() => {
    stepPanelRef.current?.focus();
  }, [step]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || target?.isContentEditable) {
        return;
      }
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        if (e.key === "ArrowRight") {
          setStepIndex((i) => Math.min(i + 1, steps.length - 1));
        } else {
          setStepIndex((i) => Math.max(i - 1, 0));
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [steps.length]);

  function goNext() {
    setStepIndex((i) => Math.min(i + 1, steps.length - 1));
  }

  function goPrev() {
    setStepIndex((i) => Math.max(i - 1, 0));
  }

  async function grade(
    kind: "check" | "practice",
    studentAnswer: string,
    expected: string,
    question: string,
    explanation?: string,
  ) {
    const trimmed = studentAnswer.trim();
    if (!trimmed || grading) return;
    setGrading(true);
    setGradeError(null);
    try {
      const res = await sendLessonFeedback({
        question,
        expected_answer: expected,
        student_answer: trimmed,
        explanation: explanation ?? lesson.practice.explanation,
        kind,
        title: lesson.title,
      });
      setFeedback(res);
      if (kind === "check") onOutcome?.({ check_correct: res.correct });
      if (kind === "practice") onOutcome?.({ practice_correct: res.correct });
      const feedbackIdx = steps.indexOf("feedback");
      if (feedbackIdx >= 0) setStepIndex(feedbackIdx);
    } catch {
      // Deterministic local teaching fallback when feedback API is unavailable
      const expectedNorm = expected.trim().toLowerCase();
      const studentNorm = trimmed.toLowerCase();
      const correct =
        studentNorm === expectedNorm ||
        studentNorm.startsWith(expectedNorm) ||
        expectedNorm.startsWith(studentNorm) ||
        (expectedNorm.length === 1 &&
          (studentNorm === expectedNorm ||
            studentNorm.startsWith(`${expectedNorm}.`) ||
            studentNorm.startsWith(`${expectedNorm})`)));
      const explanationText =
        lesson.practice.explanation ||
        (correct
          ? t("lesson.yesTrack", { expected })
          : t("lesson.notQuite", { expected }));
      setFeedback({
        type: "feedback",
        correct,
        feedback: explanationText,
        encouragement: correct ? t("lesson.nice") : t("lesson.mistakes"),
      });
      if (kind === "check") onOutcome?.({ check_correct: correct });
      if (kind === "practice") onOutcome?.({ practice_correct: correct });
      setGradeError(t("lesson.localNote"));
      const feedbackIdx = steps.indexOf("feedback");
      if (feedbackIdx >= 0) setStepIndex(feedbackIdx);
    } finally {
      setGrading(false);
    }
  }

  return (
    <div className={styles.lessonView} role="region" aria-label={t("lesson.region", { title: lesson.title })}>
      <div className={styles.lessonTop}>
        <div>
          <div className={styles.pillRow}>
            <Badge tone="study">{t("tutor.lessonMode")}</Badge>
            <span className={styles.muted}>
              {t("lesson.step", {
                current: stepIndex + 1,
                total: steps.length,
                label: currentLabel,
              })}
            </span>
          </div>
          <h2 className={styles.lessonTitle}>{lesson.title}</h2>
        </div>
        <div
          className={styles.lessonProgressTrack}
          role="progressbar"
          aria-valuemin={1}
          aria-valuemax={steps.length}
          aria-valuenow={stepIndex + 1}
          aria-label={t("lesson.progress", { label: currentLabel })}
        >
          <div className={styles.lessonProgressFill} style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className={styles.lessonBody} aria-live="polite">
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={reduceMotion ? { opacity: 1 } : { opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduceMotion ? { opacity: 1 } : { opacity: 0, y: -8 }}
            transition={reduceMotion ? { duration: 0 } : { duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          >
            <div
              ref={stepPanelRef}
              tabIndex={-1}
              className={styles.lessonStepPanel}
            >
            {step === "introduction" && (
              <Card lift={false}>
                <div className={styles.lessonIntroRow}>
                  <Naza pose="idle" size={72} speech={t("lesson.nazaIntro")} />
                  <div>
                    <p className={styles.eyebrow}>{t("lesson.intro")}</p>
                {lesson.introduction ? (
                  <MarkdownMessage className={styles.lessonLead}>{lesson.introduction}</MarkdownMessage>
                ) : (
                  <EmptyLine>{t("lesson.introEmpty")}</EmptyLine>
                )}
                  </div>
                </div>
              </Card>
            )}

            {step === "objectives" && (
              <Card lift={false}>
                <p className={styles.eyebrow}>{t("lesson.objectives")}</p>
                <h3 className={styles.sectionTitle}>{t("lesson.objTitle")}</h3>
                {lesson.objectives.length ? (
                  <ul className={styles.lessonList}>
                    {lesson.objectives.map((o) => (
                      <li key={o}>
                        <MarkdownMessage inline>{o}</MarkdownMessage>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyLine>{t("lesson.objEmpty")}</EmptyLine>
                )}
              </Card>
            )}

            {currentSection && sectionIdx != null ? (
              <Card lift={false}>
                <p className={styles.eyebrow}>
                  {t("lesson.conceptOf", {
                    n: sectionIdx + 1,
                    total: lesson.sections.length,
                  })}
                </p>
                <MarkdownMessage className={styles.sectionTitle} inline>
                  {currentSection.heading || t("lesson.conceptN", { n: sectionIdx + 1 })}
                </MarkdownMessage>
                <SectionBody body={currentSection.body || ""} />
                <SectionDiagram
                  section={currentSection}
                  hideDiagrams={hideDiagrams}
                />
              </Card>
            ) : null}

            {step === "concepts" && (
              <div className={styles.lessonStack}>
                {lesson.sections.length ? (
                  lesson.sections.map((section, i) => (
                    <motion.div
                      key={`${section.heading}-${i}`}
                      initial={reduceMotion ? { opacity: 1 } : { opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={reduceMotion ? { duration: 0 } : { delay: i * 0.06 }}
                    >
                      <Card>
                        <MarkdownMessage className={styles.sectionTitle} inline>
                          {section.heading || t("lesson.conceptN", { n: i + 1 })}
                        </MarkdownMessage>
                        <SectionBody body={section.body || ""} />
                        <SectionDiagram
                          section={section}
                          fallbackRefs={i === 0 ? lesson.image_refs : undefined}
                          hideDiagrams={hideDiagrams}
                        />
                      </Card>
                    </motion.div>
                  ))
                ) : (
                  <Card lift={false}>
                    <EmptyLine>{t("lesson.cardsEmpty")}</EmptyLine>
                  </Card>
                )}
              </div>
            )}

            {step === "worked" && (
              <Card lift={false}>
                <p className={styles.eyebrow}>{t("lesson.worked")}</p>
                <MarkdownMessage className={styles.sectionTitle} inline>
                  {lesson.worked_example.problem || t("lesson.worked")}
                </MarkdownMessage>
                {lesson.worked_example.steps.length ? (
                  <ol className={styles.lessonList}>
                    {lesson.worked_example.steps.map((s) => (
                      <li key={s}>
                        <MarkdownMessage inline>{s}</MarkdownMessage>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <EmptyLine>{t("lesson.stepsEmpty")}</EmptyLine>
                )}
                {lesson.worked_example.answer ? (
                  <div className={styles.lessonAnswerBox}>
                    <strong>{t("lesson.answer")}</strong>{" "}
                    <MarkdownMessage inline>{lesson.worked_example.answer}</MarkdownMessage>
                  </div>
                ) : null}
              </Card>
            )}

            {step === "check" && (
              <Card lift={false}>
                <Naza pose="look" size={56} speech={t("lesson.nazaCheck")} />
                <p className={styles.eyebrow}>{t("lesson.check")}</p>
                <MarkdownMessage className={styles.sectionTitle} inline>
                  {lesson.check_understanding.question || t("lesson.checkFallback")}
                </MarkdownMessage>
                <TextArea
                  rows={3}
                  placeholder={t("lesson.checkPh")}
                  value={checkAnswer}
                  onChange={(e) => setCheckAnswer(e.target.value)}
                  aria-label={t("lesson.checkAria")}
                />
                <div className={`${styles.pillRow} ${styles.lessonCheckActions}`}>
                  <Button
                    variant="ghost"
                    onClick={() => setShowHint((v) => !v)}
                    aria-expanded={showHint}
                  >
                    <Lightbulb size={14} /> {showHint ? t("lesson.hideHint") : t("lesson.hint")}
                  </Button>
                  <Button
                    onClick={() =>
                      void grade(
                        "check",
                        checkAnswer,
                        lesson.check_understanding.expected_answer,
                        lesson.check_understanding.question,
                      )
                    }
                    disabled={!checkAnswer.trim() || grading}
                    loading={grading}
                  >
                    {grading ? t("lesson.checking") : t("lesson.checkBtn")}
                  </Button>
                </div>
                {showHint && (
                  <MarkdownMessage className={`${styles.muted} ${styles.lessonHint}`}>
                    {lesson.check_understanding.hint || t("lesson.hintFallback")}
                  </MarkdownMessage>
                )}
              </Card>
            )}

            {step === "practice" && (
              <Card lift={false}>
                <p className={styles.eyebrow}>{t("lesson.practiceEyebrow")}</p>
                <ExamStemNote />
                <MarkdownMessage className={styles.sectionTitle} inline>
                  {lesson.practice.question || t("lesson.practiceQ")}
                </MarkdownMessage>
                {lesson.practice.options?.length ? (
                  <div className={styles.answerGrid} role="radiogroup" aria-label={t("lesson.practiceOpts")}>
                    {lesson.practice.options.map((opt) => {
                      const selected = practiceAnswer === opt;
                      return (
                        <button
                          key={opt}
                          type="button"
                          role="radio"
                          aria-checked={selected}
                          className={`${styles.answerCard} ${selected ? styles.answerSelected : ""}`}
                          onClick={() => setPracticeAnswer(opt)}
                        >
                          <MarkdownMessage inline>{opt}</MarkdownMessage>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <Input
                    placeholder={t("lesson.yourAnswer")}
                    value={practiceAnswer}
                    onChange={(e) => setPracticeAnswer(e.target.value)}
                    className={styles.fieldSpaced}
                    aria-label={t("lesson.practiceAria")}
                  />
                )}
                <div className={`${styles.pillRow} ${styles.sectionBodyGap}`}>
                  <Button
                    onClick={() =>
                      void grade(
                        "practice",
                        practiceAnswer,
                        lesson.practice.correct_answer,
                        lesson.practice.question,
                        lesson.practice.explanation,
                      )
                    }
                    disabled={!practiceAnswer.trim() || grading}
                    loading={grading}
                  >
                    {grading ? t("lesson.checking") : t("lesson.submitPractice")}
                  </Button>
                </div>
              </Card>
            )}

            {step === "feedback" && (
              <Card lift={false}>
                <p className={styles.eyebrow}>
                  <Sparkles size={12} style={{ marginRight: 6 }} />
                  {t("lesson.aiFeedback")}
                </p>
                {feedback ? (
                  <>
                    <Badge tone={feedback.correct ? "success" : "general"}>
                      {feedback.correct ? t("lesson.onTrack") : t("lesson.almost")}
                    </Badge>
                    <MarkdownMessage className={styles.lessonFeedbackText}>
                      {feedback.feedback}
                    </MarkdownMessage>
                    <MarkdownMessage className={`${styles.muted} ${styles.lessonHint}`} inline>
                      {feedback.encouragement}
                    </MarkdownMessage>
                    {gradeError ? (
                      <p className={`${styles.muted} ${styles.localNote}`}>
                        {gradeError}
                      </p>
                    ) : null}
                  </>
                ) : (
                  <p className={styles.muted}>
                    {t("lesson.feedbackEmpty")}
                  </p>
                )}
              </Card>
            )}

            {step === "summary" && (
              <Card lift={false}>
                <p className={styles.eyebrow}>{t("lesson.summary")}</p>
                {lesson.summary.length ? (
                  <ul className={styles.lessonList}>
                    {lesson.summary.map((line) => (
                      <li key={line}>
                        <MarkdownMessage inline>{line}</MarkdownMessage>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyLine>{t("lesson.takeaways")}</EmptyLine>
                )}
              </Card>
            )}

            {step === "revision" && (
              <div className={styles.lessonStack}>
                <button
                  type="button"
                  className={`${styles.flashcard} ${styles.lessonFlash}`}
                  onClick={() => setFlipped((f) => !f)}
                  aria-label={flipped ? t("lesson.flipBack") : t("lesson.flipFront")}
                >
                  <span className={`${styles.muted} ${styles.flashMeta}`}>
                    {flipped ? t("lesson.back") : t("lesson.front")} · {t("lesson.tapFlip")}
                  </span>
                  {flipped ? (
                    <MarkdownMessage inline>
                      {lesson.revision_card.back || t("lesson.answerSide")}
                    </MarkdownMessage>
                  ) : (
                    <MarkdownMessage inline>
                      {lesson.revision_card.front || t("lesson.promptSide")}
                    </MarkdownMessage>
                  )}
                </button>
                <div className={styles.pillRow}>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      saveRevisionCard(
                        lesson.revision_card.front || lesson.title,
                        lesson.revision_card.back || lesson.summary[0] || t("lesson.reviewTopic"),
                      );
                      setSaved(true);
                    }}
                    aria-pressed={saved}
                  >
                    <Bookmark size={14} /> {saved ? t("lesson.saved") : t("lesson.saveRev")}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => onContinueLearning(lesson.title)}
                  >
                    {t("lesson.continue")}
                  </Button>
                  <Button variant="ghost" onClick={onAskFollowUp}>
                    <MessageCircle size={14} /> {t("lesson.follow")}
                  </Button>
                </div>
              </div>
            )}
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      <div className={styles.lessonControls}>
        <Button
          variant="ghost"
          onClick={goPrev}
          disabled={atStart}
          aria-label={t("lesson.prevAria")}
        >
          <ChevronLeft size={16} /> {t("lesson.prev")}
        </Button>
        <span className={`${styles.muted} ${styles.lessonKeysHint}`}>
          {t("lesson.keys")}
        </span>
        {atEnd ? (
          <Button onClick={onAskFollowUp} aria-label={t("lesson.followAria")}>
            <MessageCircle size={14} /> {t("lesson.follow")}
          </Button>
        ) : (
          <Button onClick={goNext} aria-label={t("lesson.nextAria")}>
            {t("lesson.next")} <ChevronRight size={16} />
          </Button>
        )}
      </div>
    </div>
  );
}
