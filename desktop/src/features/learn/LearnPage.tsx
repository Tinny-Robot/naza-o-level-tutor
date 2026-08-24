import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { PlanningOverlay } from "../../components/naza/PlanningOverlay";
import { Naza } from "../../components/naza/Naza";
import { Button, ButtonLink } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { useMotionVariants } from "../../motion/variants";
import {
  completeCourseLesson,
  fetchCourse,
  fetchCourseAssessment,
  fetchSuggestions,
  generateCourseLesson,
  listCourses,
  planCourse,
  regenerateCourse,
  updateCourseProgress,
  type AssessItem,
  type Course,
  type CourseLesson,
  type LectureSuggestion,
} from "../../services/learn";
import { LessonView } from "../tutor/LessonView";
import type { LessonResponse } from "../../services/types";
import { useLanguage } from "../../i18n/LanguageProvider";
import type { MessageKey } from "../../i18n/en";
import {
  labelLearnKind,
  labelLearnStatus,
  labelSubject,
} from "../../i18n/labels";
import { ExamStemNote } from "../../components/layout/ExamStemNote";
import styles from "../pages.module.css";

const SUBJECTS = ["english", "mathematics", "physics", "chemistry"] as const;
const GOAL_IDS = ["understand", "exam", "master", "basics"] as const;
const GOAL_KEYS: Record<(typeof GOAL_IDS)[number], MessageKey> = {
  understand: "learn.goal.understand",
  exam: "learn.goal.exam",
  master: "learn.goal.master",
  basics: "learn.goal.basics",
};
const CONF_IDS = ["beginner", "some", "confident"] as const;
const CONF_KEYS: Record<(typeof CONF_IDS)[number], MessageKey> = {
  beginner: "learn.conf.beginner",
  some: "learn.conf.some",
  confident: "learn.conf.confident",
};
const STYLE_IDS = ["worked_examples", "examples_first", "visual", "exam"] as const;
const STYLE_KEYS: Record<(typeof STYLE_IDS)[number], MessageKey> = {
  worked_examples: "learn.style.worked",
  examples_first: "learn.style.examples",
  visual: "learn.style.visual",
  exam: "learn.style.exam",
};

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      className={`${styles.chip} ${active ? styles.chipActive : ""}`}
      onClick={onClick}
      aria-pressed={active}
    >
      {children}
    </button>
  );
}

export function LearnPage() {
  const { courseId } = useParams();
  if (courseId) return <CoursePlayer courseId={courseId} />;
  return <LearnHub />;
}

function LearnHub() {
  const { t, language } = useLanguage();
  const { container, item } = useMotionVariants();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [topic, setTopic] = useState(params.get("topic") || "");
  const [subject, setSubject] = useState(params.get("subject") || "");
  const [goal, setGoal] = useState("understand");
  const [confidence, setConfidence] = useState("some");
  const [style, setStyle] = useState("worked_examples");
  const [courses, setCourses] = useState<Course[]>([]);
  const [suggestions, setSuggestions] = useState<LectureSuggestion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const nextTopic = params.get("topic");
    if (nextTopic) setTopic(nextTopic);
    const nextSubject = params.get("subject");
    if (nextSubject) setSubject(nextSubject);
  }, [params]);

  useEffect(() => {
    listCourses()
      .then((r) => setCourses(r.courses || []))
      .catch(() => setCourses([]));
    fetchSuggestions()
      .then((r) => setSuggestions(r.suggestions || []))
      .catch(() => setSuggestions([]));
  }, []);

  async function create(from?: LectureSuggestion) {
    const nextTopic = from?.topic || topic.trim();
    if (!nextTopic) {
      setError(t("learn.needTopic"));
      return;
    }
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const course = await planCourse({
        topic: nextTopic,
        subject: from?.subject || subject || undefined,
        goal,
        confidence,
        style,
      });
      navigate(`/learn/${course.id}`);
    } catch {
      setError(t("learn.createError"));
    } finally {
      setBusy(false);
    }
  }

  async function rebuild(courseId: string, courseLang?: string) {
    const target = language === "Hausa" ? "Hausa" : "English";
    if (courseLang === target) return;
    if (!window.confirm(t("learn.rebuildConfirm", { lang: target }))) return;
    setBusy(true);
    setError(null);
    try {
      await regenerateCourse(courseId);
      const r = await listCourses();
      setCourses(r.courses || []);
    } catch {
      setError(t("learn.rebuildError"));
    } finally {
      setBusy(false);
    }
  }

  const visibleCourses = courses.filter((c) => c.status !== "archived");

  return (
    <motion.div
      className={styles.page}
      variants={container}
      initial="initial"
      animate="animate"
    >
      <motion.header variants={item}>
        <div className={styles.eyebrow}>{t("learn.eyebrow")}</div>
        <h1 className={styles.pageTitle}>{t("learn.title")}</h1>
        <p className={styles.muted}>{t("learn.lead")}</p>
      </motion.header>

      <div className={styles.learnHub}>
        <motion.section className={styles.learnPrimary} variants={item}>
          <Card lift={false}>
            <div className={styles.eyebrow}>{t("learn.new")}</div>
            <h2 className={styles.sectionTitle}>{t("learn.what")}</h2>
            <label className={`${styles.fieldBlock} ${styles.fieldSpaced}`}>
              <span>{t("learn.topic")}</span>
              <input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder={t("learn.topicPh")}
              />
            </label>
            <p className={`${styles.muted} ${styles.fieldSpaced}`}>{t("learn.subject")}</p>
            <div className={`${styles.chipRow} ${styles.chipSpaced}`}>
              <Chip active={!subject} onClick={() => setSubject("")}>
                {t("learn.auto")}
              </Chip>
              {SUBJECTS.map((s) => (
                <Chip key={s} active={subject === s} onClick={() => setSubject(s)}>
                  {t(
                    s === "english"
                      ? "learn.subjects.english"
                      : s === "mathematics"
                        ? "learn.subjects.mathematics"
                        : s === "physics"
                          ? "learn.subjects.physics"
                          : "learn.subjects.chemistry",
                  )}
                </Chip>
              ))}
            </div>
            <p className={`${styles.muted} ${styles.fieldSpaced}`}>{t("learn.goal")}</p>
            <div className={`${styles.chipRow} ${styles.chipSpaced}`}>
              {GOAL_IDS.map((id) => (
                <Chip key={id} active={goal === id} onClick={() => setGoal(id)}>
                  {t(GOAL_KEYS[id])}
                </Chip>
              ))}
            </div>
            <p className={`${styles.muted} ${styles.fieldSpaced}`}>{t("learn.confidence")}</p>
            <div className={`${styles.chipRow} ${styles.chipSpaced}`}>
              {CONF_IDS.map((id) => (
                <Chip
                  key={id}
                  active={confidence === id}
                  onClick={() => setConfidence(id)}
                >
                  {t(CONF_KEYS[id])}
                </Chip>
              ))}
            </div>
            <p className={`${styles.muted} ${styles.fieldSpaced}`}>{t("learn.how")}</p>
            <div className={`${styles.segmentRow} ${styles.chipSpaced}`}>
              {STYLE_IDS.map((id) => (
                <Chip key={id} active={style === id} onClick={() => setStyle(id)}>
                  {t(STYLE_KEYS[id])}
                </Chip>
              ))}
            </div>
            {error ? (
              <p className={`${styles.muted} ${styles.fieldSpaced}`} role="alert" aria-live="polite">
                {error}
              </p>
            ) : null}
            <Button
              onClick={() => void create()}
              disabled={busy}
              className={styles.inlineAction}
            >
              <Sparkles size={16} /> {busy ? t("learn.planning") : t("learn.create")}
            </Button>
          </Card>
        </motion.section>

        <aside className={styles.learnAside}>
          <motion.section variants={item}>
            <h2 className={styles.sectionTitle}>{t("learn.suggested")}</h2>
            <div className={styles.suggestRow}>
              {suggestions.length ? (
                suggestions.map((s) =>
                  s.course_id ? (
                    <Link
                      key={`${s.kind}-${s.subject}-${s.topic}`}
                      to={`/learn/${s.course_id}`}
                      className={styles.suggestChip}
                    >
                      <div>
                        <strong>{s.title}</strong>
                        <span>{s.reason}</span>
                      </div>
                    </Link>
                  ) : (
                    <button
                      key={`${s.kind}-${s.subject}-${s.topic}`}
                      type="button"
                      className={styles.suggestChip}
                      onClick={() => void create(s)}
                      disabled={busy}
                    >
                      <div>
                        <strong>{s.title}</strong>
                        <span>{s.reason}</span>
                      </div>
                    </button>
                  ),
                )
              ) : (
                <div className={styles.suggestChip}>
                  <Naza pose="look" size={36} />
                  <div>
                    <strong>{t("learn.ready")}</strong>
                    <span>{t("learn.weakHint")}</span>
                  </div>
                </div>
              )}
            </div>
          </motion.section>

          <motion.section variants={item}>
            <h2 className={styles.sectionTitle}>{t("learn.myCourses")}</h2>
            <div className={styles.stack}>
              {visibleCourses.length ? (
                visibleCourses.map((c) => (
                  <Card key={c.id}>
                    <div className={styles.rowBetween}>
                      <div>
                        <div className={styles.eyebrow}>
                          {labelSubject(c.subject, t)} · {labelLearnStatus(c.status, t)}
                        </div>
                        <p className={styles.courseTitle}>{c.title}</p>
                        <p className={styles.muted}>
                          {t("learn.lessonOf", {
                            current: (c.progress?.current_index || 0) + 1,
                            total: c.progress?.total || c.lessons.length,
                          })}
                          {c.progress?.pct != null
                            ? ` · ${t("learn.pctComplete", { pct: Math.round(c.progress.pct) })}`
                            : ""}
                        </p>
                        {(c.language || "English") !== language ? (
                          <p className={styles.muted}>
                            {t("learn.savedIn", { lang: c.language || "English" })}
                          </p>
                        ) : null}
                      </div>
                      <div className={styles.courseActions}>
                        {(c.language || "English") !== language ? (
                          <Button
                            variant="ghost"
                            disabled={busy}
                            onClick={() => void rebuild(c.id, c.language)}
                          >
                            {t("learn.rebuild", { lang: language })}
                          </Button>
                        ) : null}
                        <ButtonLink to={`/learn/${c.id}`} variant="ghost">
                          {t("learn.open")}
                        </ButtonLink>
                      </div>
                    </div>
                  </Card>
                ))
              ) : (
                <Card lift={false} className={styles.empty}>
                  <Naza pose="look" size={48} />
                  <p className={styles.courseTitle}>{t("learn.noCourses")}</p>
                  <p className={styles.muted}>{t("learn.noCoursesLead")}</p>
                </Card>
              )}
            </div>
          </motion.section>
        </aside>
      </div>
      <PlanningOverlay open={busy} />
    </motion.div>
  );
}

function CoursePlayer({ courseId }: { courseId: string }) {
  const { t, language } = useLanguage();
  const { container, item } = useMotionVariants();
  const navigate = useNavigate();
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [checkCorrect, setCheckCorrect] = useState<boolean | null>(null);
  const [practiceCorrect, setPracticeCorrect] = useState<boolean | null>(null);
  const [assessItems, setAssessItems] = useState<AssessItem[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [assessDone, setAssessDone] = useState(false);

  const current = useMemo(() => {
    if (!course?.lessons?.length) return null;
    const idx = Math.max(
      0,
      Math.min(course.current_index || 0, course.lessons.length - 1),
    );
    return course.lessons[idx];
  }, [course]);

  async function refresh() {
    const next = await fetchCourse(courseId);
    setCourse(next);
    return next;
  }

  useEffect(() => {
    refresh().catch(() => setError(t("learn.loadError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  async function openLesson(lesson: CourseLesson) {
    if (busy) return;
    setError(null);
    setBusy(true);
    setCheckCorrect(null);
    setPracticeCorrect(null);
    setAssessItems(null);
    setAssessDone(false);
    setAnswers({});
    try {
      await updateCourseProgress(courseId, { lesson_id: lesson.id });
      let next = await generateCourseLesson(courseId, lesson.id);
      setCourse(next);
      const updated = next.lessons.find((l) => l.id === lesson.id);
      if (updated?.kind === "assessment") {
        const bank = await fetchCourseAssessment(courseId);
        setAssessItems(bank.items);
      }
      setPlaying(true);
    } catch {
      setError(t("learn.openError"));
    } finally {
      setBusy(false);
    }
  }

  async function finishLesson() {
    if (!current || busy) return;
    setBusy(true);
    try {
      const next = await completeCourseLesson(courseId, current.id, {
        check_correct: checkCorrect,
        practice_correct: practiceCorrect,
        struggled: checkCorrect === false || practiceCorrect === false,
      });
      setCourse(next);
      setPlaying(false);
    } catch {
      setError(t("learn.saveError"));
    } finally {
      setBusy(false);
    }
  }

  if (!course) {
    return (
      <div className={styles.page}>
        <p className={styles.muted} role="status" aria-live="polite">
          {error || t("learn.loading")}
        </p>
      </div>
    );
  }

  const action = course.next_action;
  const payload = current?.payload as LessonResponse | undefined;

  if (playing && current?.kind === "assessment" && assessItems) {
    const scored = assessItems.filter((assessItem) => {
      const letter = (answers[assessItem.id] || "").charAt(0).toUpperCase();
      return assessItem.answer && letter === String(assessItem.answer).charAt(0).toUpperCase();
    }).length;
    return (
      <div className={styles.page}>
        <div className={styles.eyebrow}>
          {labelSubject(course.subject, t)} · {t("learn.assessment")}
        </div>
        <h1 className={styles.pageTitle}>{current.title}</h1>
        <ExamStemNote />
        {assessItems.map((assessItem, i) => {
          const correctLetter = String(assessItem.answer || "").charAt(0).toUpperCase();
          return (
            <Card key={assessItem.id} lift={false} className={styles.sectionBodyGap}>
              <div className={styles.eyebrow}>
                {t("learn.qLabel", { n: i + 1 })}
              </div>
              {assessItem.passage ? <p className={styles.muted}>{assessItem.passage}</p> : null}
              <p className={styles.courseTitle}>{assessItem.question}</p>
              <div
                className={styles.optionStack}
                role="radiogroup"
                aria-label={t("learn.qLabel", { n: i + 1 })}
              >
                {assessItem.options.map((opt) => {
                  const letter = opt.trim().charAt(0).toUpperCase();
                  const selected = answers[assessItem.id] === letter;
                  const mark =
                    assessDone && letter === correctLetter
                      ? styles.answerCorrect
                      : assessDone && selected && letter !== correctLetter
                        ? styles.answerWrong
                        : selected
                          ? styles.answerSelected
                          : styles.optionBtn;
                  return (
                    <button
                      key={opt}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      className={mark}
                      onClick={() =>
                        setAnswers((a) => ({ ...a, [assessItem.id]: letter }))
                      }
                      disabled={assessDone}
                    >
                      {opt}
                    </button>
                  );
                })}
              </div>
              {assessDone && assessItem.explanation ? (
                <p className={`${styles.muted} ${styles.metaFoot}`}>
                  {assessItem.answer}. {assessItem.explanation}
                </p>
              ) : null}
            </Card>
          );
        })}
        <div className={`${styles.pillRow} ${styles.sectionBodyGap}`}>
          {!assessDone ? (
            <Button
              onClick={() => {
                setAssessDone(true);
                setPracticeCorrect(
                  scored / Math.max(1, assessItems.length) >= 0.6,
                );
              }}
            >
              {t("learn.checkAnswers")}
            </Button>
          ) : (
            <>
              <p className={styles.muted} aria-live="polite">
                {t("learn.score", { scored, total: assessItems.length })}
              </p>
              <Button onClick={() => void finishLesson()} disabled={busy}>
                {t("learn.finish")}
              </Button>
            </>
          )}
          <Button variant="ghost" onClick={() => setPlaying(false)}>
            {t("learn.backOverview")}
          </Button>
        </div>
        <PlanningOverlay
          open={busy}
          title={t("learn.savingTitle")}
          lead={t("learn.stay")}
        />
      </div>
    );
  }

  if (playing && payload && current) {
    return (
      <div className={`${styles.page} ${styles.pageFill}`}>
        {action?.kind === "practice" ? (
          <p className={styles.banner}>
            {action.reason || t("learn.practiceBanner")}{" "}
            <Link
              to={`/practice?subject=${encodeURIComponent(course.subject)}&topic=${encodeURIComponent(course.topic)}`}
            >
              {t("learn.practiceLink")}
            </Link>
          </p>
        ) : null}
        <div className={styles.learnShell}>
          <aside className={styles.learnRail}>
            {course.lessons.map((l, i) => (
              <button
                key={l.id}
                type="button"
                className={`${styles.learnRailBtn} ${l.id === current.id ? styles.learnRailBtnActive : ""}`}
                onClick={() => void openLesson(l)}
                disabled={busy}
                aria-current={l.id === current.id ? "step" : undefined}
              >
                {i + 1}. {l.title}
              </button>
            ))}
          </aside>
          <LessonView
            key={current.id}
            lesson={payload}
            hideDiagrams
            deepSections
            onAskFollowUp={() =>
              navigate(
                `/tutor?topic=${encodeURIComponent(current.title || course.topic)}`,
              )
            }
            onContinueLearning={() => void finishLesson()}
            onOutcome={(partial) => {
              if (partial.check_correct != null) setCheckCorrect(partial.check_correct);
              if (partial.practice_correct != null)
                setPracticeCorrect(partial.practice_correct);
            }}
          />
        </div>
        <PlanningOverlay
          open={busy}
          title={t("learn.prepTitle")}
          lead={t("learn.prepLead")}
        />
      </div>
    );
  }

  return (
    <motion.div
      className={styles.page}
      variants={container}
      initial="initial"
      animate="animate"
    >
      <motion.header variants={item}>
        <div className={styles.eyebrow}>
          {labelSubject(course.subject, t)} · {course.exam} · {labelLearnStatus(course.status, t)}
        </div>
        <h1 className={styles.pageTitle}>{course.title}</h1>
        <p className={styles.muted}>{course.objective}</p>
        {(course.language || "English") !== language ? (
          <p className={styles.muted}>
            {t("learn.savedIn", { lang: course.language || "English" })}{" "}
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => {
                if (
                  !window.confirm(
                    t("learn.rebuildConfirm", { lang: language }),
                  )
                ) {
                  return;
                }
                setBusy(true);
                regenerateCourse(courseId)
                  .then((next) => setCourse(next))
                  .catch(() => setError(t("learn.rebuildError")))
                  .finally(() => setBusy(false));
              }}
            >
              {t("learn.rebuild", { lang: language })}
            </Button>
          </p>
        ) : null}
      </motion.header>
      {action?.kind === "practice" ? (
        <motion.p className={styles.banner} variants={item}>
          {action.reason || t("learn.practiceBanner")}{" "}
          <Link
            to={`/practice?subject=${encodeURIComponent(course.subject)}&topic=${encodeURIComponent(course.topic)}`}
          >
            {t("learn.practiceTopic")}
          </Link>
        </motion.p>
      ) : null}
      {(course.skipped_because || []).length ? (
        <motion.p className={styles.muted} variants={item}>
          {t("learn.skipped")}{" "}
          {course.skipped_because
            ?.map((s) => `${s.title} (${s.skipped_because})`)
            .join("; ")}
        </motion.p>
      ) : null}
      {error ? (
        <p className={styles.muted} role="alert" aria-live="polite">
          {error}
        </p>
      ) : null}
      <motion.div className={styles.stack} variants={item}>
        {course.lessons.map((lesson, i) => (
          <Card
            key={lesson.id}
            className={lesson.id === current?.id ? styles.lessonCardCurrent : ""}
          >
            <div className={styles.rowBetween}>
              <div>
                <div className={styles.eyebrow}>
                  {t("learn.lessonMeta", {
                    n: i + 1,
                    kind: labelLearnKind(lesson.kind, t),
                    status: labelLearnStatus(lesson.status, t),
                  })}
                </div>
                <p className={styles.courseTitle}>{lesson.title}</p>
                {lesson.rationale ? (
                  <p className={styles.muted}>{lesson.rationale}</p>
                ) : null}
              </div>
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => void openLesson(lesson)}
              >
                {busy
                  ? t("learn.opening")
                  : lesson.status === "complete"
                    ? t("learn.review")
                    : t("learn.open")}
              </Button>
            </div>
          </Card>
        ))}
      </motion.div>
      <motion.div className={styles.pillRow} variants={item}>
        <ButtonLink to="/learn" variant="ghost">
          {t("learn.all")}
        </ButtonLink>
        <ButtonLink
          to={`/practice?subject=${encodeURIComponent(course.subject)}&topic=${encodeURIComponent(course.topic)}`}
          variant="ghost"
        >
          {t("learn.practiceTopic")}
        </ButtonLink>
      </motion.div>
      <PlanningOverlay
        open={busy}
        title={t("learn.prepTitle")}
        lead={t("learn.prepLead")}
      />
    </motion.div>
  );
}
