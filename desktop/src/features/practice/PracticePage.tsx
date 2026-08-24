import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useSearchParams } from "react-router-dom";
import { Check, Clock, Flame, Trophy, X, Zap } from "lucide-react";
import { Naza } from "../../components/naza/Naza";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { useMotionVariants } from "../../motion/variants";
import {
  fetchNextPractice,
  fetchPracticeTopics,
  submitPracticeAnswer,
  type PracticeQuestion,
} from "../../services/practice";
import { resolveExamImageUrl } from "../../services/exams";
import { useLanguage } from "../../i18n/LanguageProvider";
import type { MessageKey } from "../../i18n/en";
import { labelSubject } from "../../i18n/labels";
import { ExamStemNote } from "../../components/layout/ExamStemNote";
import layout from "../../components/layout/layout.module.css";
import styles from "../pages.module.css";

const SUBJECTS = ["english", "mathematics", "physics", "chemistry"] as const;
const RATE_AFTER = 10;
const TRACK_WINDOW = 10;
const BEST_KEY = "naza.practice.best.v4";
const STREAK_KEY = "naza.practice.bestStreak.v2";

type Best = { percent: number; correct: number; answered: number; elapsed: number };

function loadBest(): Best | null {
  try {
    const raw = localStorage.getItem(BEST_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Best;
    if (typeof parsed.percent === "number" && parsed.answered >= RATE_AFTER) return parsed;
  } catch {
    /* ignore */
  }
  return null;
}

function saveBest(b: Best) {
  try {
    localStorage.setItem(BEST_KEY, JSON.stringify(b));
  } catch {
    /* ignore */
  }
}

function loadBestStreak(): number {
  try {
    const n = Number(localStorage.getItem(STREAK_KEY) || "0");
    return Number.isFinite(n) && n > 0 ? n : 0;
  } catch {
    return 0;
  }
}

function saveBestStreak(n: number) {
  try {
    localStorage.setItem(STREAK_KEY, String(n));
  } catch {
    /* ignore */
  }
}

function formatTime(secs: number) {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

type Tier = "perfect" | "great" | "solid" | "building" | "warmup";

function getTier(correct: number, answered: number): Tier {
  if (answered === 0) return "warmup";
  const pct = correct / answered;
  if (pct === 1) return "perfect";
  if (pct >= 0.8) return "great";
  if (pct >= 0.6) return "solid";
  if (pct >= 0.4) return "building";
  return "warmup";
}

export function PracticePage() {
  const { t } = useLanguage();
  const { container, item } = useMotionVariants();
  const [params] = useSearchParams();
  const requestedSubject = (params.get("subject") || "").toLowerCase();
  const requestedTopic = (params.get("topic") || "").trim();
  const [subject, setSubject] = useState<string>(
    SUBJECTS.includes(requestedSubject as (typeof SUBJECTS)[number])
      ? requestedSubject
      : "chemistry",
  );
  const [topics, setTopics] = useState<string[]>([]);
  const [topic, setTopic] = useState<string>(requestedTopic);
  const [itemQ, setItemQ] = useState<PracticeQuestion | null>(null);
  const [choice, setChoice] = useState<string>("");
  const [feedback, setFeedback] = useState<{
    correct: boolean;
    feedback: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [sessionStarted, setSessionStarted] = useState(false);
  /** Full session history - never cleared mid-session. */
  const [history, setHistory] = useState<boolean[]>([]);
  const [streak, setStreak] = useState(0);
  const [bestStreak, setBestStreak] = useState(loadBestStreak);
  const [elapsed, setElapsed] = useState(0);
  const [best, setBest] = useState<Best | null>(loadBest);
  const [showModal, setShowModal] = useState(false);
  const [showEndModal, setShowEndModal] = useState(false);
  const [endSummary, setEndSummary] = useState<{
    correct: number;
    answered: number;
    percent: number | null;
    streak: number;
    elapsed: number;
  } | null>(null);
  const [lastResult, setLastResult] = useState<{
    correct: boolean;
    feedback: string;
    rated: boolean;
    percent: number | null;
    newBest: boolean;
  } | null>(null);
  const timerRef = useRef<number | null>(null);

  const answered = history.length;
  const correct = history.filter(Boolean).length;
  const rated = answered >= RATE_AFTER;
  const sessionPct = answered > 0 ? Math.round((correct / answered) * 100) : 0;
  const recent = history.slice(-TRACK_WINDOW);

  const startTimer = useCallback(() => {
    if (timerRef.current !== null) return;
    timerRef.current = window.setInterval(() => setElapsed((e) => e + 1), 1000);
  }, []);

  function stopTimer() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  function endPractice() {
    if (!sessionStarted) return;
    stopTimer();
    setShowModal(false);
    setEndSummary({
      correct,
      answered,
      percent: rated ? sessionPct : null,
      streak,
      elapsed,
    });
    setShowEndModal(true);
    setSessionStarted(false);
    setItemQ(null);
    setChoice("");
    setFeedback(null);
    setHistory([]);
    setStreak(0);
    setElapsed(0);
    setError(null);
  }

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    };
  }, []);

  useEffect(() => {
    fetchPracticeTopics(subject)
      .then((r) => setTopics(r.topics || []))
      .catch(() => setTopics([]));
  }, [subject]);

  useEffect(() => {
    if (
      requestedSubject &&
      SUBJECTS.includes(requestedSubject as (typeof SUBJECTS)[number])
    ) {
      setSubject(requestedSubject);
    }
    if (requestedTopic) setTopic(requestedTopic);
  }, [requestedSubject, requestedTopic]);

  async function loadNext() {
    if (loading || checking) return;
    setLoading(true);
    setError(null);
    setFeedback(null);
    setChoice("");
    setShowModal(false);
    try {
      const res = await fetchNextPractice({
        subject,
        topic: topic || null,
        exam: "WAEC",
        n: 6,
      });
      const withImg = res.items.find((q) => (q.images || []).length > 0);
      const pick = withImg || res.items[0] || null;
      setItemQ(pick);
      if (!pick) {
        setError(t("practice.none"));
      } else if (!sessionStarted) {
        setSessionStarted(true);
        startTimer();
      }
    } catch {
      setError(t("practice.loadError"));
      setItemQ(null);
    } finally {
      setLoading(false);
    }
  }

  async function check() {
    if (!itemQ || !choice || loading || checking) return;
    setChecking(true);
    setError(null);
    try {
      const res = await submitPracticeAnswer({
        subject: itemQ.subject,
        topic: itemQ.topic,
        question_id: itemQ.id,
        question: itemQ.question,
        options: itemQ.options,
        answer: itemQ.answer,
        student_answer: choice,
        explanation: itemQ.explanation,
      });

      const nextHistory = [...history, res.correct];
      const nextAnswered = nextHistory.length;
      const nextCorrect = nextHistory.filter(Boolean).length;
      const nowRated = nextAnswered >= RATE_AFTER;
      const percent = nowRated ? Math.round((nextCorrect / nextAnswered) * 100) : null;

      let newBest = false;
      if (nowRated && percent !== null) {
        const isBetter =
          !best ||
          percent > best.percent ||
          (percent === best.percent && nextCorrect > best.correct) ||
          (percent === best.percent &&
            nextCorrect === best.correct &&
            elapsed < best.elapsed);
        if (isBetter) {
          const nextBest = {
            percent,
            correct: nextCorrect,
            answered: nextAnswered,
            elapsed,
          };
          setBest(nextBest);
          saveBest(nextBest);
          newBest = true;
        }
      }

      const nextStreak = res.correct ? streak + 1 : 0;
      setStreak(nextStreak);
      if (nextStreak > bestStreak) {
        setBestStreak(nextStreak);
        saveBestStreak(nextStreak);
      }

      setHistory(nextHistory);
      setFeedback({ correct: res.correct, feedback: res.feedback });
      setLastResult({
        correct: res.correct,
        feedback: res.feedback,
        rated: nowRated,
        percent,
        newBest,
      });
      setShowModal(true);
    } catch {
      setError(t("practice.gradeError"));
    } finally {
      setChecking(false);
    }
  }

  const correctLetter = String(itemQ?.answer || "").charAt(0).toUpperCase();
  const progressSlots = Array.from({ length: TRACK_WINDOW }, (_, i) => {
    if (i < recent.length) return recent[i] ? "hit" : "miss";
    if (i === recent.length && itemQ && !feedback) return "current";
    return "empty";
  });

  function motivationalText() {
    const c = correct;
    const a = answered || 1;
    const tier = getTier(c, a);
    const variant = a % 3;
    const key = `practice.tier.${tier}.${variant}` as MessageKey;
    return t(key, { correct: String(c), answered: String(a) });
  }

  return (
    <motion.div
      className={`${styles.page} ${styles.practicePage}`}
      variants={container}
      initial="initial"
      animate="animate"
    >
      <motion.div variants={item} className={styles.practiceTopBar}>
        <div className={styles.practiceTitleBlock}>
          <div className={styles.eyebrow}>{t("practice.eyebrow")}</div>
          <h1 className={styles.practiceTitle}>{t("practice.title")}</h1>
        </div>
        <div className={styles.practiceFilters}>
          <label className={styles.fieldBlockCompact}>
            <span>{t("practice.subject")}</span>
            <select value={subject} onChange={(e) => setSubject(e.target.value)}>
              {SUBJECTS.map((s) => (
                <option key={s} value={s}>
                  {labelSubject(s, t)}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.fieldBlockCompact}>
            <span>{t("practice.topic")}</span>
            <select value={topic} onChange={(e) => setTopic(e.target.value)}>
              <option value="">{t("practice.adaptive")}</option>
              {topic && !topics.includes(topic) ? (
                <option value={topic}>{topic}</option>
              ) : null}
              {topics.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <Button onClick={() => void loadNext()} loading={loading} disabled={checking}>
            {loading ? t("practice.loading") : itemQ ? t("practice.next") : t("practice.start")}
          </Button>
          {sessionStarted ? (
            <Button
              variant="ghost"
              onClick={endPractice}
              disabled={loading || checking}
            >
              {t("practice.end")}
            </Button>
          ) : null}
        </div>
      </motion.div>

      <motion.div variants={item} className={styles.practiceArenaCompact}>
        <div className={styles.practiceHudRow}>
          <div className={styles.hudChip}>
            <Clock size={15} />
            <div>
              <div className={styles.hudLabel}>{t("practice.timer")}</div>
              <div className={styles.hudValue}>{formatTime(elapsed)}</div>
            </div>
          </div>
          <div className={styles.hudChip}>
            <Zap size={15} />
            <div>
              <div className={styles.hudLabel}>{t("practice.score")}</div>
              <div className={styles.hudValue}>
                {correct}/{answered}
                {rated ? <span className={styles.hudMicro}> · {sessionPct}%</span> : null}
              </div>
            </div>
          </div>
          <div className={`${styles.hudChip} ${streak > 0 ? styles.hudChipHot : ""}`}>
            <Flame size={15} />
            <div>
              <div className={styles.hudLabel}>{t("practice.streak")}</div>
              <div className={styles.hudValue}>
                {streak}
                {bestStreak > 0 ? (
                  <span className={styles.hudMicro}>
                    {" "}
                    · {t("practice.streakBest", { n: String(bestStreak) })}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          <div className={styles.hudChip}>
            <Trophy size={15} />
            <div>
              <div className={styles.hudLabel}>{t("practice.best")}</div>
              <div className={styles.hudValue}>
                {best ? (
                  <>
                    {best.percent}%
                    <span className={styles.hudMicro}>
                      {" "}
                      · {best.correct}/{best.answered}
                    </span>
                  </>
                ) : (
                  <span className={styles.practiceBestLockedInline}>
                    {t("practice.bestLockedShort", { n: String(RATE_AFTER) })}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className={styles.practiceTrackCompact} aria-label={t("practice.roundProgress")}>
          <div className={styles.practiceTrackHead}>
            <span>
              {rated
                ? t("practice.recentWindow")
                : t("practice.untilRated", {
                    left: String(Math.max(0, RATE_AFTER - answered)),
                  })}
            </span>
            <strong>
              {answered}
              {!rated ? ` / ${RATE_AFTER}` : ""}
            </strong>
          </div>
          <div className={styles.practiceDots} role="list">
            {progressSlots.map((state, i) => (
              <span
                key={i}
                role="listitem"
                className={
                  state === "hit"
                    ? styles.dotHit
                    : state === "miss"
                      ? styles.dotMiss
                      : state === "current"
                        ? styles.dotCurrent
                        : styles.dotEmpty
                }
              />
            ))}
          </div>
        </div>
      </motion.div>

      {error ? (
        <p className={styles.muted} role="alert" aria-live="polite">
          {error}
        </p>
      ) : null}

      <motion.div variants={item} className={styles.practiceMain}>
        {itemQ ? (
          <Card className={styles.practiceQuestionCard}>
            <div className={styles.practiceQMeta}>
              <span className={styles.eyebrow}>
                {itemQ.exam_board} · {itemQ.topic}
                {itemQ.year ? ` · ${itemQ.year}` : ""}
              </span>
              <ExamStemNote />
            </div>
            <p className={styles.practiceStem}>{itemQ.question}</p>
            {(itemQ.images || []).length > 0 ? (
              <div className={styles.practiceFigures}>
                {(itemQ.images || []).map((img) => {
                  const src = resolveExamImageUrl(img.url, img.path);
                  return (
                    <figure key={src} className={styles.practiceFigure}>
                      <img
                        src={src}
                        alt={img.caption || t("exams.diagram")}
                        loading="lazy"
                      />
                    </figure>
                  );
                })}
              </div>
            ) : null}
            <div
              className={styles.optionStackCompact}
              role="radiogroup"
              aria-label={t("lesson.practiceOpts")}
            >
              {itemQ.options.map((opt) => {
                const letter = opt.trim().charAt(0).toUpperCase();
                const selected = choice === letter || choice === opt;
                const mark =
                  feedback && letter === correctLetter
                    ? styles.answerCorrect
                    : feedback && selected && letter !== correctLetter
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
                    onClick={() => setChoice(letter.match(/[A-D]/) ? letter : opt)}
                    disabled={!!feedback || loading || checking}
                  >
                    {opt}
                  </button>
                );
              })}
            </div>
            <div className={styles.practiceActions}>
              {!feedback ? (
                <Button
                  onClick={() => void check()}
                  disabled={!choice || loading || checking}
                  loading={checking}
                >
                  {checking ? t("practice.grading") : t("lesson.checkBtn")}
                </Button>
              ) : (
                <Button onClick={() => void loadNext()} loading={loading}>
                  {loading ? t("practice.loading") : t("practice.next")}
                </Button>
              )}
            </div>
          </Card>
        ) : (
          <Card lift={false} className={`${styles.empty} ${styles.practiceEmpty}`}>
            <Naza pose="look" size={64} />
            <p className={styles.courseTitle}>{t("practice.start")}</p>
            <p className={styles.muted}>{t("practice.startLeadRated")}</p>
          </Card>
        )}
      </motion.div>

      {showModal && lastResult ? (
        <div className={layout.modalBackdrop}>
          <div
            className={`${layout.modal} ${styles.practiceResultModal}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="practice-result-title"
          >
            <div className={layout.modalHead}>
              <h2 id="practice-result-title">
                {lastResult.correct ? t("practice.ok") : t("practice.fix")}
              </h2>
              <button
                type="button"
                className={layout.iconBtn}
                aria-label={t("settings.close")}
                onClick={() => setShowModal(false)}
              >
                <X size={18} />
              </button>
            </div>
            <div className={styles.practiceResultBody}>
              <div
                className={
                  lastResult.correct ? styles.practiceResultMarkOk : styles.practiceResultMarkBad
                }
              >
                {lastResult.correct ? <Check size={28} /> : <X size={28} />}
              </div>
              <p className={styles.practiceResultScore}>
                {correct}/{answered}
                {lastResult.rated && lastResult.percent !== null
                  ? ` · ${lastResult.percent}%`
                  : ""}
              </p>
              {lastResult.newBest ? (
                <span className={styles.practiceNewBest}>{t("practice.newBest")}</span>
              ) : null}
              {streak > 0 && lastResult.correct ? (
                <p className={styles.practiceStreakCallout}>
                  <Flame size={14} /> {t("practice.streakNow", { n: String(streak) })}
                </p>
              ) : null}
              {!lastResult.rated ? (
                <p className={styles.muted}>
                  {t("practice.untilRated", {
                    left: String(Math.max(0, RATE_AFTER - answered)),
                  })}
                </p>
              ) : null}
              <p className={styles.practiceMotivate}>{motivationalText()}</p>
              <p className={styles.muted}>{lastResult.feedback}</p>
            </div>
            <div className={layout.modalActions}>
              <Button variant="ghost" onClick={() => setShowModal(false)}>
                {t("practice.resultClose")}
              </Button>
              <Button onClick={() => void loadNext()} loading={loading}>
                {t("practice.resultNext")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {showEndModal && endSummary ? (
        <div className={layout.modalBackdrop}>
          <div
            className={`${layout.modal} ${styles.practiceResultModal}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="practice-end-title"
          >
            <div className={layout.modalHead}>
              <h2 id="practice-end-title">{t("practice.endedTitle")}</h2>
              <button
                type="button"
                className={layout.iconBtn}
                aria-label={t("settings.close")}
                onClick={() => setShowEndModal(false)}
              >
                <X size={18} />
              </button>
            </div>
            <div className={styles.practiceResultBody}>
              <Naza pose="look" size={56} />
              <p className={styles.muted}>{t("practice.endedLead")}</p>
              <p className={styles.practiceResultScore}>
                {endSummary.correct}/{endSummary.answered}
                {endSummary.percent !== null ? ` · ${endSummary.percent}%` : ""}
              </p>
              <p className={styles.practiceStreakCallout}>
                <Flame size={14} /> {t("practice.streak")}: {endSummary.streak}
              </p>
              <p className={styles.muted}>
                <Clock size={12} style={{ verticalAlign: "middle" }} />{" "}
                {formatTime(endSummary.elapsed)}
              </p>
              {best ? (
                <p className={styles.muted}>
                  {t("practice.best")}: {best.percent}% · {best.correct}/{best.answered}
                </p>
              ) : null}
            </div>
            <div className={layout.modalActions}>
              <Button variant="ghost" onClick={() => setShowEndModal(false)}>
                {t("practice.endedDone")}
              </Button>
              <Button
                onClick={() => {
                  setShowEndModal(false);
                  void loadNext();
                }}
                loading={loading}
              >
                {t("practice.endedAgain")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </motion.div>
  );
}
