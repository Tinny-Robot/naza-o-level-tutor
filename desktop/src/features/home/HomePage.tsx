import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, BookOpen, Flame, Sparkles, Target } from "lucide-react";
import { Link } from "react-router-dom";
import { Naza } from "../../components/naza/Naza";
import { ButtonLink } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { useMotionVariants } from "../../motion/variants";
import {
  fetchStudentSummary,
  type StudentSummary,
} from "../../services/student";
import { fetchSuggestions, type LectureSuggestion } from "../../services/learn";
import { useLanguage } from "../../i18n/LanguageProvider";
import {
  formatActivityAt,
  labelPlanKind,
  labelSubject,
  learnHref,
} from "../../i18n/labels";
import styles from "../pages.module.css";

export function HomePage() {
  const { t } = useLanguage();
  const { container, item } = useMotionVariants();
  const [summary, setSummary] = useState<StudentSummary | null>(null);
  const [suggestions, setSuggestions] = useState<LectureSuggestion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([fetchStudentSummary(), fetchSuggestions()]).then(
      ([summaryRes, suggestRes]) => {
        if (cancelled) return;
        if (summaryRes.status === "fulfilled") {
          setSummary(summaryRes.value);
        } else {
          setError(t("home.reachError"));
        }
        if (suggestRes.status === "fulfilled") {
          setSuggestions(suggestRes.value.suggestions || []);
        }
        setReady(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [t]);

  const continueHref = summary?.continue_learning?.course_id
    ? `/learn/${summary.continue_learning.course_id}`
    : "/learn";
  const teachHref = learnHref(summary?.recommend_topic, summary?.recommend_subject);
  const primaryIsContinue = Boolean(summary?.continue_learning?.course_id);

  if (!ready) {
    return (
      <div className={styles.page}>
        <Card lift={false} className={styles.empty}>
          <Naza pose="look" size={72} />
          <p className={styles.muted} style={{ marginTop: 12 }}>
            {t("home.loading")}
          </p>
        </Card>
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
      <motion.div className={styles.hero} variants={item}>
        <div className={styles.heroCard}>
          <div className={styles.eyebrow}>{t("home.eyebrow")}</div>
          <h1 className={styles.heroTitle}>
            {summary
              ? t("home.welcomeName", { name: summary.display_name })
              : t("home.welcome")}
          </h1>
          <p className={styles.heroLead}>
            {summary?.recommendation || t("home.lead")}
          </p>
          <div className={styles.pillRow}>
            {primaryIsContinue ? (
              <>
                <ButtonLink to={continueHref}>
                  {t("home.continue")} <ArrowRight size={16} />
                </ButtonLink>
                <ButtonLink to={teachHref} variant="ghost">
                  <Sparkles size={16} /> {t("home.recommended")}
                </ButtonLink>
              </>
            ) : (
              <>
                <ButtonLink to={teachHref}>
                  <Sparkles size={16} /> {t("home.recommended")}
                </ButtonLink>
                <ButtonLink to={continueHref} variant="ghost">
                  {t("home.continue")} <ArrowRight size={16} />
                </ButtonLink>
              </>
            )}
          </div>
        </div>

        <Card>
          <div className={`${styles.rowBetween} ${styles.goalHead}`}>
            <div>
              <div className={styles.statLabel}>{t("home.goalToday")}</div>
              <p className={styles.courseTitle}>
                {summary?.goal_today || t("home.goalFallback")}
              </p>
            </div>
            <Target size={28} />
          </div>
          <div className={styles.statsRow}>
            <div>
              <div className={styles.statLabel}>
                <Flame size={12} aria-hidden /> {t("home.streak")}
              </div>
              <div className={styles.statValue}>
                {summary ? summary.streak_days : t("home.statPending")}
              </div>
            </div>
            <div>
              <div className={styles.statLabel}>{t("home.lessons")}</div>
              <div className={styles.statValue}>
                {summary ? summary.lessons_completed : t("home.statPending")}
              </div>
            </div>
            <div>
              <div className={styles.statLabel}>{t("home.practiceAcc")}</div>
              <div className={styles.statValue}>
                {summary?.practice_accuracy != null
                  ? `${Math.round(summary.practice_accuracy * 100)}%`
                  : t("home.statPending")}
              </div>
            </div>
          </div>
        </Card>
      </motion.div>

      {error ? (
        <motion.p className={styles.muted} variants={item} role="alert" aria-live="polite">
          {error}
        </motion.p>
      ) : null}

      <motion.section variants={item}>
        <div className={`${styles.rowBetween} ${styles.sectionHead}`}>
          <h2 className={styles.sectionTitle}>
            {summary?.learning_plan?.title || t("home.planFallback")}
          </h2>
          <span className={styles.muted}>{t("home.aiPlan")}</span>
        </div>
        <div className={styles.stack}>
          {(summary?.learning_plan?.items || []).map((planItem, i) => {
            const to =
              planItem.kind === "exam"
                ? "/exams"
                : planItem.kind === "practice"
                  ? `/practice?subject=${encodeURIComponent(planItem.subject || "")}&topic=${encodeURIComponent(planItem.topic || "")}`
                  : learnHref(planItem.topic || planItem.label, planItem.subject);
            return (
              <Card key={`${planItem.label}-${i}`}>
                <div className={styles.rowBetween}>
                  <div>
                    <div className={styles.eyebrow}>
                      {i + 1}. {labelPlanKind(planItem.kind, t)}
                    </div>
                    <p className={styles.courseTitle}>{planItem.label}</p>
                  </div>
                  <ButtonLink to={to} variant="ghost">
                    {t("home.start")} <ArrowRight size={14} />
                  </ButtonLink>
                </div>
              </Card>
            );
          })}
          {!summary?.learning_plan?.items?.length ? (
            <Card lift={false}>
              <p className={styles.muted}>{t("home.planEmpty")}</p>
            </Card>
          ) : null}
        </div>
      </motion.section>

      <motion.section variants={item}>
        <div className={`${styles.rowBetween} ${styles.sectionHead}`}>
          <h2 className={styles.sectionTitle}>{t("home.suggested")}</h2>
          <Link to="/learn" className={styles.muted}>
            {t("home.openLearn")}
          </Link>
        </div>
        {suggestions.length ? (
          <div className={styles.suggestRow}>
            {suggestions.slice(0, 4).map((s) => (
              <Link
                key={`${s.kind}-${s.subject}-${s.topic}`}
                to={
                  s.course_id
                    ? `/learn/${s.course_id}`
                    : learnHref(s.topic, s.subject)
                }
                className={styles.suggestChip}
              >
                <div>
                  <strong>{s.title}</strong>
                  <span>{s.reason}</span>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <Card lift={false}>
            <p className={styles.muted}>{t("home.suggestEmpty")}</p>
          </Card>
        )}
      </motion.section>

      <motion.section variants={item}>
        <div className={`${styles.rowBetween} ${styles.sectionHead}`}>
          <h2 className={styles.sectionTitle}>{t("home.weak")}</h2>
          <Link to="/progress" className={styles.muted}>
            {t("home.viewProgress")}
          </Link>
        </div>
        <div className={styles.grid3}>
          {(summary?.weak_topics || []).slice(0, 3).map((topic) => (
            <Card key={`${topic.subject}-${topic.topic}`}>
              <div className={styles.eyebrow}>{labelSubject(topic.subject, t)}</div>
              <p className={styles.courseTitle}>{topic.topic}</p>
              <p className={styles.muted}>
                {t("home.mastery", { pct: Math.round(topic.score * 100) })}
              </p>
              <ButtonLink
                to={learnHref(topic.topic, topic.subject)}
                variant="ghost"
                className={styles.inlineAction}
              >
                <BookOpen size={14} /> {t("home.learn")}
              </ButtonLink>
            </Card>
          ))}
          {!summary?.weak_topics?.length ? (
            <Card lift={false}>
              <p className={styles.muted}>{t("home.noWeak")}</p>
            </Card>
          ) : null}
        </div>
      </motion.section>

      <motion.section variants={item}>
        <h2 className={`${styles.sectionTitle} ${styles.sectionHead}`}>
          {t("home.recent")}
        </h2>
        <Card>
          <ul className={styles.activityList}>
            {(summary?.recent_activity || []).map((a, i) => (
              <li key={i}>
                <strong>{labelPlanKind(a.kind || "session", t)}</strong> - {a.label}
                {a.at ? (
                  <span className={styles.muted}> · {formatActivityAt(a.at)}</span>
                ) : null}
              </li>
            ))}
            {!summary?.recent_activity?.length ? (
              <li className={styles.muted}>{t("home.noSessions")}</li>
            ) : null}
          </ul>
        </Card>
      </motion.section>
    </motion.div>
  );
}
