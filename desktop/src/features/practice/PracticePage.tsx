import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useSearchParams } from "react-router-dom";
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
import { useLanguage } from "../../i18n/LanguageProvider";
import { labelSubject } from "../../i18n/labels";
import { ExamStemNote } from "../../components/layout/ExamStemNote";
import styles from "../pages.module.css";

const SUBJECTS = ["english", "mathematics", "physics", "chemistry"] as const;

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
    encouragement: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    try {
      const res = await fetchNextPractice({
        subject,
        topic: topic || null,
        exam: "WAEC",
        n: 1,
      });
      setItemQ(res.items[0] || null);
      if (!res.items[0]) setError(t("practice.none"));
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
      setFeedback({
        correct: res.correct,
        feedback: res.feedback,
        encouragement: res.encouragement,
      });
    } catch {
      setError(t("practice.gradeError"));
    } finally {
      setChecking(false);
    }
  }

  const correctLetter = String(itemQ?.answer || "").charAt(0).toUpperCase();

  return (
    <motion.div
      className={styles.page}
      variants={container}
      initial="initial"
      animate="animate"
    >
      <motion.header variants={item}>
        <div className={styles.eyebrow}>{t("practice.eyebrow")}</div>
        <h1 className={styles.pageTitle}>{t("practice.title")}</h1>
        <p className={styles.muted}>{t("practice.lead")}</p>
      </motion.header>

      <motion.div className={styles.grid2} variants={item}>
        <label className={styles.fieldBlock}>
          <span>{t("practice.subject")}</span>
          <select
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          >
            {SUBJECTS.map((s) => (
              <option key={s} value={s}>
                {labelSubject(s, t)}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.fieldBlock}>
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
      </motion.div>

      <motion.div variants={item} className={styles.pillRow}>
        <Button onClick={() => void loadNext()} loading={loading} disabled={checking}>
          {loading ? t("practice.loading") : itemQ ? t("practice.next") : t("practice.start")}
        </Button>
      </motion.div>

      {error ? (
        <p className={styles.muted} role="alert" aria-live="polite">
          {error}
        </p>
      ) : null}

      {itemQ ? (
        <motion.div variants={item}>
          <Card>
            <div className={styles.eyebrow}>
              {itemQ.exam_board} · {itemQ.topic}
              {itemQ.year ? ` · ${itemQ.year}` : ""}
            </div>
            <ExamStemNote />
            <p className={`${styles.courseTitle} ${styles.fieldSpaced}`}>{itemQ.question}</p>
            <div
              className={styles.optionStack}
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
            {!feedback ? (
              <Button
                onClick={() => void check()}
                disabled={!choice || loading || checking}
                loading={checking}
                className={styles.inlineAction}
              >
                {checking ? t("practice.grading") : t("lesson.checkBtn")}
              </Button>
            ) : (
              <div className={styles.feedbackBlock} role="status" aria-live="polite">
                <p className={styles.courseTitle}>
                  {feedback.correct ? t("practice.ok") : t("practice.fix")}
                </p>
                <p>{feedback.feedback}</p>
                <p className={styles.muted}>{feedback.encouragement}</p>
                <Button
                  onClick={() => void loadNext()}
                  loading={loading}
                  className={styles.inlineAction}
                >
                  {loading ? t("practice.loading") : t("practice.next")}
                </Button>
              </div>
            )}
          </Card>
        </motion.div>
      ) : (
        <motion.div variants={item}>
          <Card lift={false} className={styles.empty}>
            <Naza pose="look" size={64} />
            <p className={`${styles.courseTitle} ${styles.fieldSpaced}`}>
              {t("practice.start")}
            </p>
            <p className={styles.muted}>{t("practice.startLead")}</p>
          </Card>
        </motion.div>
      )}
    </motion.div>
  );
}
