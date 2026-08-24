import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { ApiError, OFFLINE_ENGINE_MESSAGE } from "../../services/api";
import { getLesson } from "../../services/lesson";
import type { LessonPayload } from "../../services/types";
import styles from "../pages.module.css";

export function LessonPage() {
  const [lesson, setLesson] = useState<LessonPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setLesson(await getLesson());
    } catch (err) {
      setLesson(null);
      setError(err instanceof ApiError ? err.message : OFFLINE_ENGINE_MESSAGE);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className={styles.page}>
        <p className={styles.muted}>Loading lesson…</p>
      </div>
    );
  }

  if (error || !lesson) {
    return (
      <div className={styles.page}>
        <Card lift={false} className={styles.empty}>
          <p style={{ marginBottom: 12 }}>{error ?? OFFLINE_ENGINE_MESSAGE}</p>
          <Button onClick={() => void load()}>Retry</Button>
        </Card>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.eyebrow}>
        {lesson.subject} · {lesson.topic}
      </div>
      <h1 className={styles.heroTitle} style={{ fontSize: 32 }}>
        {lesson.title}
      </h1>
      <p className={styles.muted}>Interactive lesson · ~{lesson.duration_min} min</p>

      {lesson.sections.map((section) => (
        <Card key={section.heading} lift={section.kind !== "illustration"}>
          <h2 className={styles.sectionTitle}>{section.heading}</h2>
          {section.kind === "illustration" ? (
            <div
              className={styles.empty}
              style={{
                marginTop: 12,
                border: "1px dashed var(--color-border-strong)",
                borderRadius: 16,
                background: "rgba(34,211,238,0.05)",
              }}
            >
              {section.body}
            </div>
          ) : (
            <p style={{ marginTop: 8 }} className={section.options ? styles.muted : undefined}>
              {section.body}
            </p>
          )}
          {section.options && (
            <div className={styles.pillRow} style={{ marginTop: 12 }}>
              {section.options.map((opt) => (
                <Button
                  key={opt}
                  variant={opt === section.answer ? "primary" : "ghost"}
                >
                  {opt}
                </Button>
              ))}
            </div>
          )}
        </Card>
      ))}

      <Card lift={false}>
        <h2 className={styles.sectionTitle}>Summary</h2>
        <ul className={styles.muted}>
          {lesson.summary.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </Card>

      <div className={styles.rowBetween}>
        <Link to="/quiz">
          <Button variant="secondary">Mini quiz</Button>
        </Link>
        <Link to="/practice">
          <Button>Next lesson</Button>
        </Link>
      </div>
    </div>
  );
}
