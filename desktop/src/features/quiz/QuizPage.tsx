import { useCallback, useEffect, useState } from "react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { ApiError, OFFLINE_ENGINE_MESSAGE } from "../../services/api";
import { getQuiz } from "../../services/quiz";
import type { QuizPayload } from "../../services/types";
import styles from "../pages.module.css";

export function QuizPage() {
  const [quiz, setQuiz] = useState<QuizPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [picked, setPicked] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPicked(null);
    setDone(false);
    try {
      setQuiz(await getQuiz());
    } catch (err) {
      setQuiz(null);
      setError(err instanceof ApiError ? err.message : OFFLINE_ENGINE_MESSAGE);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const key = e.key.toUpperCase();
      if (["A", "B", "C", "D"].includes(key) && !done) setPicked(key);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [done]);

  if (loading) {
    return (
      <div className={styles.page}>
        <p className={styles.muted}>Loading quiz…</p>
      </div>
    );
  }

  if (error || !quiz) {
    return (
      <div className={styles.page}>
        <Card lift={false} className={styles.empty}>
          <p style={{ marginBottom: 12 }}>{error ?? OFFLINE_ENGINE_MESSAGE}</p>
          <Button onClick={() => void load()}>Retry</Button>
        </Card>
      </div>
    );
  }

  const correct = picked === quiz.answer;

  return (
    <div className={styles.page}>
      <div className={styles.rowBetween}>
        <div>
          <div className={styles.eyebrow}>{quiz.subject} · Keyboard A-D</div>
          <h1 className={styles.heroTitle} style={{ fontSize: 28 }}>
            Quiz
          </h1>
        </div>
        <span className={styles.muted}>Question 1 / 1</span>
      </div>

      <Card lift={false}>
        <p style={{ fontSize: 20, fontFamily: "var(--font-display)", fontWeight: 600 }}>
          {quiz.prompt}
        </p>
        <div className={styles.answerGrid}>
          {quiz.options.map((o) => {
            let cls = styles.answerCard;
            if (done && o.key === quiz.answer) cls += ` ${styles.answerCorrect}`;
            else if (done && picked === o.key && !correct) cls += ` ${styles.answerWrong}`;
            return (
              <button
                key={o.key}
                type="button"
                className={cls}
                onClick={() => !done && setPicked(o.key)}
              >
                <span className={styles.answerKey}>{o.key}</span>
                {o.text}
              </button>
            );
          })}
        </div>
        <div className={styles.pillRow} style={{ marginTop: 20 }}>
          {!done ? (
            <Button disabled={!picked} onClick={() => setDone(true)}>
              Check answer
            </Button>
          ) : (
            <>
              <strong style={{ color: correct ? "var(--color-success)" : "var(--color-error)" }}>
                {correct ? "Nice - that’s correct." : `Answer is ${quiz.answer}.`}
              </strong>
              <Button
                variant="ghost"
                onClick={() => {
                  setPicked(null);
                  setDone(false);
                }}
              >
                Review again
              </Button>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
