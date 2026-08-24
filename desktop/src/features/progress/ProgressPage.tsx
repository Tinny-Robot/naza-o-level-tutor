import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { Naza } from "../../components/naza/Naza";
import { ButtonLink } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { ProgressRing } from "../../components/ui/ProgressRing";
import { useMotionVariants } from "../../motion/variants";
import {
  fetchStudentSummary,
  type StudentSummary,
} from "../../services/student";
import { useLanguage } from "../../i18n/LanguageProvider";
import { labelSubject, learnHref } from "../../i18n/labels";
import styles from "../pages.module.css";

export function ProgressPage() {
  const { t } = useLanguage();
  const { container, item } = useMotionVariants();
  const [summary, setSummary] = useState<StudentSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    fetchStudentSummary()
      .then((s) => setSummary(s))
      .catch(() => setError(t("progress.loadError")))
      .finally(() => setReady(true));
  }, [t]);

  if (!ready) {
    return (
      <div className={styles.page}>
        <Card lift={false} className={styles.empty}>
          <Naza pose="look" size={72} />
          <p className={styles.muted} style={{ marginTop: 12 }}>
            {t("progress.loading")}
          </p>
        </Card>
      </div>
    );
  }

  const nextHref = learnHref(summary?.recommend_topic, summary?.recommend_subject);

  return (
    <motion.div
      className={styles.page}
      variants={container}
      initial="initial"
      animate="animate"
    >
      <motion.header variants={item}>
        <div className={styles.eyebrow}>{t("progress.eyebrow")}</div>
        <h1 className={styles.pageTitle}>{t("progress.title")}</h1>
        <p className={styles.muted}>{t("progress.lead")}</p>
        {summary?.recommend_topic ? (
          <p className={styles.nextLine}>
            {t("progress.next", { topic: summary.recommend_topic })}{" "}
            <Link to={nextHref}>{t("home.learn")}</Link>
          </p>
        ) : null}
      </motion.header>

      {error ? (
        <p className={styles.muted} role="alert" aria-live="polite">
          {error}
        </p>
      ) : null}

      <motion.div className={styles.grid3} variants={item}>
        <Card>
          <div className={styles.statLabel}>{t("progress.streak")}</div>
          <div className={styles.statValue}>
            {summary ? summary.streak_days : t("home.statPending")}
          </div>
        </Card>
        <Card>
          <div className={styles.statLabel}>{t("progress.lessons")}</div>
          <div className={styles.statValue}>
            {summary ? summary.lessons_completed : t("home.statPending")}
          </div>
        </Card>
        <Card>
          <div className={styles.statLabel}>{t("progress.acc")}</div>
          <div className={styles.statValue}>
            {summary?.practice_accuracy != null
              ? `${Math.round(summary.practice_accuracy * 100)}%`
              : t("home.statPending")}
          </div>
        </Card>
      </motion.div>

      <motion.section variants={item}>
        <h2 className={styles.sectionTitle}>{t("progress.mastery")}</h2>
        <div className={`${styles.grid4} ${styles.sectionBodyGap}`}>
          {(summary?.subjects || []).map((s) => (
            <Card key={s.subject}>
              <div className={styles.rowBetween}>
                <div>
                  <div className={styles.eyebrow}>{labelSubject(s.subject, t)}</div>
                  <p className={styles.courseTitle}>
                    {t("progress.topics", { n: s.topics })}
                  </p>
                </div>
                <ProgressRing value={Math.round(s.mastery * 100)} />
              </div>
            </Card>
          ))}
          {!summary?.subjects?.length ? (
            <Card lift={false}>
              <p className={styles.muted}>{t("progress.emptyMastery")}</p>
            </Card>
          ) : null}
        </div>
      </motion.section>

      <motion.section variants={item}>
        <div className={styles.rowBetween}>
          <h2 className={styles.sectionTitle}>{t("progress.weak")}</h2>
        </div>
        <div className={`${styles.stack} ${styles.sectionBodyGap}`}>
          {(summary?.weak_topics || []).map((topic) => (
            <Card key={`${topic.subject}-${topic.topic}`}>
              <div className={styles.rowBetween}>
                <div>
                  <div className={styles.eyebrow}>{labelSubject(topic.subject, t)}</div>
                  <p className={styles.courseTitle}>{topic.topic}</p>
                </div>
                <div className={styles.pillRow}>
                  <span>{Math.round(topic.score * 100)}%</span>
                  <ButtonLink
                    to={learnHref(topic.topic, topic.subject)}
                    variant="ghost"
                  >
                    {t("home.learn")}
                  </ButtonLink>
                </div>
              </div>
            </Card>
          ))}
          {!summary?.weak_topics?.length ? (
            <Card lift={false}>
              <p className={styles.muted}>{t("progress.noWeak")}</p>
            </Card>
          ) : null}
        </div>
      </motion.section>

      <motion.section variants={item}>
        <h2 className={styles.sectionTitle}>{t("progress.plan")}</h2>
        <Card lift={false} className={styles.sectionBodyGap}>
          {(summary?.learning_plan?.items || []).length ? (
            <ul className={styles.activityList}>
              {(summary?.learning_plan?.items || []).map((planItem, i) => {
                const to =
                  planItem.kind === "exam"
                    ? "/exams"
                    : planItem.kind === "practice"
                      ? `/practice?subject=${encodeURIComponent(planItem.subject || "")}&topic=${encodeURIComponent(planItem.topic || "")}`
                      : learnHref(planItem.topic || planItem.label, planItem.subject);
                return (
                  <li key={i}>
                    {i + 1}. {planItem.label}{" "}
                    <Link to={to}>{t("progress.open")}</Link>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className={styles.muted}>{t("progress.planEmpty")}</p>
          )}
          <p className={`${styles.muted} ${styles.metaFoot}`}>
            {t("progress.examsTaken", { n: summary?.exams_taken ?? 0 })}
          </p>
        </Card>
      </motion.section>

      {summary?.focus_areas?.length ? (
        <motion.section variants={item}>
          <h2 className={styles.sectionTitle}>{t("progress.focus")}</h2>
          <Card className={styles.sectionBodyGap}>
            <p className={styles.muted}>{t("progress.focusLead")}</p>
            <ul className={styles.activityList}>
              {summary.focus_areas.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </Card>
        </motion.section>
      ) : null}
    </motion.div>
  );
}
