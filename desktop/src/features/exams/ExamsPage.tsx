import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Clock,
  Flag,
  Pause,
  Play,
  X,
} from "lucide-react";
import { PlanningOverlay } from "../../components/naza/PlanningOverlay";
import { Button, ButtonLink } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { useMotionVariants } from "../../motion/variants";
import { labelSubject, learnHref } from "../../i18n/labels";
import layout from "../../components/layout/layout.module.css";
import {
  fetchExamMeta,
  resolveExamImageUrl,
  startExam,
  submitExam,
  type ExamItem,
} from "../../services/exams";
import { useLanguage } from "../../i18n/LanguageProvider";
import { ExamStemNote } from "../../components/layout/ExamStemNote";
import styles from "../pages.module.css";

type Phase = "setup" | "exam" | "results";

export function ExamsPage() {
  const { t } = useLanguage();
  const { container, item } = useMotionVariants();
  const pauseResumeRef = useRef<HTMLButtonElement>(null);
  const submitKeepRef = useRef<HTMLButtonElement>(null);
  const [exams, setExams] = useState<string[]>(["WAEC", "NECO", "JAMB"]);
  const [subjects, setSubjects] = useState<string[]>([
    "english",
    "mathematics",
    "physics",
    "chemistry",
  ]);
  const [sizes, setSizes] = useState<number[]>([10, 20, 40]);
  const [bankInfo, setBankInfo] = useState<string>("");
  const [exam, setExam] = useState("WAEC");
  const [subject, setSubject] = useState("physics");
  const [n, setN] = useState(10);
  const [phase, setPhase] = useState<Phase>("setup");
  const [sessionId, setSessionId] = useState("");
  const [items, setItems] = useState<ExamItem[]>([]);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [flagged, setFlagged] = useState<Set<string>>(new Set());
  const [remaining, setRemaining] = useState(0);
  const [paused, setPaused] = useState(false);
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [reviewFlaggedOnly, setReviewFlaggedOnly] = useState(false);
  const [results, setResults] = useState<{
    score_pct: number;
    correct: number;
    total: number;
    breakdown: {
      topic: string;
      accuracy: number;
      correct: number;
      total: number;
    }[];
    weak_topics: string[];
    incorrect: { topic: string; explanation?: string }[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchExamMeta()
      .then((m) => {
        setExams(m.exams);
        setSubjects(m.subjects);
        setSizes(m.sizes);
        const b = m.bank?.[subject];
        if (b) {
          setBankInfo(
            `${t("exams.bankInfo", { total: b.total, images: b.with_images })}`,
          );
        }
      })
      .catch(() => undefined);
  }, [subject]);

  useEffect(() => {
    if (phase !== "exam") return;
    if (paused) return;
    if (remaining <= 0) return;
    const t = window.setInterval(() => {
      setRemaining((r) => Math.max(0, r - 1));
    }, 1000);
    return () => window.clearInterval(t);
  }, [phase, paused, remaining]);

  useEffect(() => {
    if (phase === "exam" && remaining === 0 && sessionId && !confirmSubmit) {
      void doSubmit();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remaining]);

  useEffect(() => {
    if (paused) pauseResumeRef.current?.focus();
  }, [paused]);

  useEffect(() => {
    if (confirmSubmit) submitKeepRef.current?.focus();
  }, [confirmSubmit]);

  const visibleIndexes = useMemo(() => {
    if (!reviewFlaggedOnly) return items.map((_, i) => i);
    return items
      .map((q, i) => (flagged.has(q.id) ? i : -1))
      .filter((i) => i >= 0);
  }, [items, flagged, reviewFlaggedOnly]);

  const current = items[index];
  const timeLabel = useMemo(() => {
    const m = Math.floor(remaining / 60);
    const s = remaining % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  }, [remaining]);

  const answeredCount = Object.keys(answers).length;

  async function begin() {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const minutes = n <= 10 ? 15 : n <= 20 ? 30 : 60;
      const res = await startExam({ exam, subject, n, minutes });
      setSessionId(res.session_id);
      setItems(res.items);
      setAnswers({});
      setFlagged(new Set());
      setIndex(0);
      setRemaining(res.duration_s);
      setPaused(false);
      setPhase("exam");
      setResults(null);
      setReviewFlaggedOnly(false);
      if (res.delivered < res.requested) {
        setNotice(
          t("exams.notice", {
            delivered: res.delivered,
            exam,
            subject,
            requested: res.requested,
          }),
        );
      }
    } catch {
      setError(t("exams.startError"));
    } finally {
      setBusy(false);
    }
  }

  async function doSubmit() {
    if (!sessionId || busy) return;
    setBusy(true);
    setConfirmSubmit(false);
    try {
      const res = await submitExam({
        session_id: sessionId,
        answers,
        flagged: [...flagged],
      });
      setResults(res);
      setPhase("results");
      setPaused(false);
    } catch {
      setError(t("exams.submitFail"));
    } finally {
      setBusy(false);
    }
  }

  function selectAnswer(opt: string) {
    if (!current) return;
    const letter = opt.trim().charAt(0).toUpperCase();
    const value = letter.match(/[A-D]/) ? letter : opt;
    setAnswers((a) => ({ ...a, [current.id]: value }));
  }

  function toggleFlag() {
    if (!current) return;
    setFlagged((prev) => {
      const next = new Set(prev);
      if (next.has(current.id)) next.delete(current.id);
      else next.add(current.id);
      return next;
    });
  }

  function goRelative(delta: number) {
    const pos = visibleIndexes.indexOf(index);
    const nextPos = Math.max(0, Math.min(visibleIndexes.length - 1, pos + delta));
    setIndex(visibleIndexes[nextPos] ?? index);
  }

  if (phase === "setup") {
    return (
      <motion.div
        className={styles.page}
        variants={container}
        initial="initial"
        animate="animate"
      >
        <motion.header variants={item}>
          <div className={styles.eyebrow}>{t("exams.eyebrow")}</div>
          <h1 className={styles.pageTitle}>{t("exams.title")}</h1>
          <p className={styles.muted}>{t("exams.lead")}</p>
          <ExamStemNote />
          {bankInfo ? (
            <p className={styles.muted} style={{ marginTop: 6 }}>
              {t("exams.bank", { subject: labelSubject(subject, t), info: bankInfo })}
            </p>
          ) : null}
        </motion.header>
        <motion.div className={styles.grid3} variants={item}>
          <label className={styles.fieldBlock}>
            <span>{t("exams.exam")}</span>
            <select value={exam} onChange={(e) => setExam(e.target.value)}>
              {exams.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.fieldBlock}>
            <span>{t("exams.subject")}</span>
            <select value={subject} onChange={(e) => setSubject(e.target.value)}>
              {subjects.map((s) => (
                <option key={s} value={s}>
                  {labelSubject(s, t)}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.fieldBlock}>
            <span>{t("exams.questions")}</span>
            <select value={n} onChange={(e) => setN(Number(e.target.value))}>
              {sizes.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </motion.div>
        {error ? (
          <p className={styles.muted} role="alert" aria-live="polite">
            {error}
          </p>
        ) : null}
        <motion.div variants={item}>
          <Button onClick={() => void begin()} disabled={busy}>
            {busy ? t("exams.preparing") : t("exams.enter")}
          </Button>
        </motion.div>
        <PlanningOverlay
          open={busy}
          title={t("exams.prepTitle")}
          lead={t("exams.prepLead")}
        />
      </motion.div>
    );
  }

  if (phase === "results" && results) {
    const weak = results.weak_topics[0];
    return (
      <motion.div
        className={styles.page}
        variants={container}
        initial="initial"
        animate="animate"
      >
        <motion.header variants={item}>
          <div className={styles.eyebrow}>{t("exams.results")}</div>
          <h1 className={styles.pageTitle}>{results.score_pct}%</h1>
          <p className={styles.muted}>
            {t("exams.scoreLine", {
              correct: results.correct,
              incorrect: results.total - results.correct,
              total: results.total,
            })}
          </p>
        </motion.header>
        <motion.div variants={item}>
          <Card>
            <h3>{t("exams.breakdown")}</h3>
            <ul className={styles.activityList}>
              {results.breakdown.map((b) => (
                <li key={b.topic}>
                  {b.topic}: {b.correct}/{b.total} (
                  {Math.round(b.accuracy * 100)}%)
                </li>
              ))}
            </ul>
          </Card>
        </motion.div>
        <motion.div className={styles.pillRow} variants={item}>
          <ButtonLink to={weak ? learnHref(weak, subject) : "/learn"}>
            {t("exams.practiceWeak")}
          </ButtonLink>
          <Button variant="ghost" onClick={() => setPhase("setup")}>
            {t("exams.new")}
          </Button>
        </motion.div>
      </motion.div>
    );
  }

  return (
    <div className={`${styles.pageFill} ${styles.cbtPage}`}>
      <header className={styles.cbtTopBar}>
        <div className={styles.cbtTopLeft}>
          <strong>
            {exam} · {labelSubject(subject, t)}
          </strong>
          <span className={styles.muted}>
            Q{index + 1}/{items.length}
            {current?.paper_type === "Comprehension" ? ` · ${t("exams.passage")}` : ""}
            {current?.jamb_style ? ` · ${t("exams.jamb")}` : ""}
          </span>
        </div>
        <div className={styles.cbtTimer} data-urgent={remaining < 60}>
          <Clock size={16} />
          {timeLabel}
          {paused ? ` · ${t("exams.paused")}` : ""}
        </div>
        <div className={styles.cbtTopActions}>
          <Button variant="ghost" onClick={() => setPaused((p) => !p)}>
            {paused ? <Play size={14} /> : <Pause size={14} />}
            {paused ? t("exams.resume") : t("exams.pause")}
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setReviewFlaggedOnly((v) => !v);
              if (!reviewFlaggedOnly && flagged.size) {
                const first = items.findIndex((q) => flagged.has(q.id));
                if (first >= 0) setIndex(first);
              }
            }}
          >
            {t("exams.flagged", { n: flagged.size })}
          </Button>
          <Button onClick={() => setConfirmSubmit(true)} disabled={busy}>{t("exams.submit")}</Button>
        </div>
      </header>

      {notice ? (
        <p className={styles.cbtNotice}>{notice}</p>
      ) : null}

      <div className={styles.cbtShell}>
        <aside className={styles.cbtSide}>
          <div className={styles.eyebrow}>{t("exams.nav")}</div>
          <p className={styles.muted} style={{ fontSize: 12, margin: "6px 0 10px" }}>
            {t("exams.answered", { n: answeredCount, total: items.length })}
          </p>
          <div className={styles.cbtPalette}>
            {items.map((q, i) => {
              const classes = [styles.cbtPalBtn];
              if (i === index) classes.push(styles.cbtPalBtnActive);
              if (answers[q.id]) classes.push(styles.cbtPalBtnAnswered);
              if (flagged.has(q.id)) classes.push(styles.cbtPalBtnFlagged);
              return (
                <button
                  key={q.id}
                  type="button"
                  className={classes.join(" ")}
                  onClick={() => setIndex(i)}
                  aria-label={t("exams.qAria", { n: i + 1 })}
                  aria-current={i === index ? "true" : undefined}
                >
                  {i + 1}
                </button>
              );
            })}
          </div>
          <div className={styles.cbtLegend}>
            <span>
              <i className={styles.dotAnswered} /> {t("exams.legendA")}
            </span>
            <span>
              <i className={styles.dotFlagged} /> {t("exams.legendF")}
            </span>
            <span>
              <i className={styles.dotCurrent} /> {t("exams.legendC")}
            </span>
          </div>
        </aside>

        <section className={styles.cbtMain}>
          {current ? (
            <Card lift={false} className={styles.cbtQuestionCard}>
              <div className={styles.rowBetween}>
                <div className={styles.eyebrow}>
                  {current.topic}
                  {current.year ? ` · ${current.year}` : ""}
                  {current.exam_board ? ` · ${current.exam_board}` : ""}
                </div>
                <Button variant="ghost" onClick={toggleFlag}>
                  <Flag size={14} />
                  {flagged.has(current.id) ? t("exams.unflag") : t("exams.flag")}
                </Button>
              </div>

              {current.passage ? (
                <div className={styles.cbtPassage}>
                  <div className={styles.eyebrow}>{t("exams.passage")}</div>
                  <p>{current.passage}</p>
                </div>
              ) : null}

              <p className={styles.cbtStem}>{current.question}</p>

              {(current.images || []).map((img) => {
                const src = resolveExamImageUrl(img.url, img.path);
                return (
                  <figure key={src} className={styles.cbtFigure}>
                    <img src={src} alt={img.caption || t("exams.diagram")} />
                    <figcaption>
                      {img.caption || t("lesson.diagramCap")}
                    </figcaption>
                  </figure>
                );
              })}

              <div
                className={styles.optionStack}
                role="radiogroup"
                aria-label={t("exams.qAria", { n: index + 1 })}
              >
                {current.options.map((opt) => {
                  const letter = opt.trim().charAt(0).toUpperCase();
                  const value = letter.match(/[A-D]/) ? letter : opt;
                  const selected = answers[current.id] === value;
                  return (
                    <button
                      key={opt}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      className={
                        selected ? styles.answerSelected : styles.optionBtn
                      }
                      onClick={() => selectAnswer(opt)}
                    >
                      {opt}
                    </button>
                  );
                })}
              </div>

              <div className={styles.cbtNavRow}>
                <Button
                  variant="ghost"
                  disabled={visibleIndexes.indexOf(index) <= 0}
                  onClick={() => goRelative(-1)}
                >
                  {t("lesson.prev")}
                </Button>
                <Button
                  variant="ghost"
                  disabled={
                    visibleIndexes.indexOf(index) >= visibleIndexes.length - 1
                  }
                  onClick={() => goRelative(1)}
                >
                  {t("lesson.next")}
                </Button>
              </div>
            </Card>
          ) : null}
        </section>
      </div>

      {paused ? (
        <div className={layout.modalBackdrop}>
          <div
            className={layout.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="exam-pause-title"
          >
            <div className={layout.modalHead}>
              <h2 id="exam-pause-title">{t("exams.pausedTitle")}</h2>
            </div>
            <p className={layout.modalLead}>
              {t("exams.pausedLead")}
            </p>
            <div className={layout.modalActions}>
              <Button ref={pauseResumeRef} variant="ghost" onClick={() => setConfirmSubmit(true)}>
                {t("exams.submitNow")}
              </Button>
              <Button onClick={() => setPaused(false)}>
                <Play size={14} /> {t("exams.resume")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {confirmSubmit ? (
        <div className={layout.modalBackdrop}>
          <div
            className={layout.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="exam-submit-title"
          >
            <div className={layout.modalHead}>
              <h2 id="exam-submit-title">{t("exams.submitQ")}</h2>
              <button
                type="button"
                className={layout.iconBtn}
                aria-label={t("settings.close")}
                onClick={() => setConfirmSubmit(false)}
              >
                <X size={18} />
              </button>
            </div>
            <p className={layout.modalLead}>
              {t("exams.submitLead", {
                answered: answeredCount,
                total: items.length,
                flagged: flagged.size
                  ? t("exams.flaggedBit", { n: flagged.size })
                  : "",
              })}
            </p>
            <div className={layout.modalActions}>
              <Button
                ref={submitKeepRef}
                variant="ghost"
                onClick={() => setConfirmSubmit(false)}
                disabled={busy}
              >
                {t("exams.keep")}
              </Button>
              <Button onClick={() => void doSubmit()} disabled={busy}>
                {busy ? t("exams.submitting") : t("exams.confirm")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <PlanningOverlay
        open={busy && phase === "exam"}
        title={t("exams.markTitle")}
        lead={t("exams.markLead")}
      />

      {error ? <p className={styles.cbtNotice}>{error}</p> : null}
    </div>
  );
}
