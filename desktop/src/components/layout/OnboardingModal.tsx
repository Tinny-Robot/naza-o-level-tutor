import { useEffect, useRef, useState } from "react";
import { Naza } from "../naza/Naza";
import { Button } from "../ui/Button";
import { fetchStudentSummary, patchPreferences } from "../../services/student";
import { useLanguage } from "../../i18n/LanguageProvider";
import type { AppLanguage } from "../../i18n/types";
import styles from "./layout.module.css";

export function OnboardingModal() {
  const { t, refresh } = useLanguage();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [language, setLanguage] = useState<AppLanguage>("English");
  const [goal, setGoal] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchStudentSummary()
      .then((s) => {
        if (cancelled) return;
        if (s.preferences?.onboarded) {
          setOpen(false);
          return;
        }
        setName(s.display_name && s.display_name !== "Student" ? s.display_name : "");
        setLanguage(s.preferences?.language === "Hausa" ? "Hausa" : "English");
        setGoal(s.goal_today || "");
        setOpen(true);
      })
      .catch(() => {
        if (!cancelled) setOpen(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const id = window.requestAnimationFrame(() => firstFieldRef.current?.focus());
    return () => window.cancelAnimationFrame(id);
  }, [open]);

  if (!open) return null;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await patchPreferences({
        display_name: name.trim() || "Student",
        language,
        goal_today: goal.trim() || undefined,
        onboarded: true,
      });
      await refresh();
      setOpen(false);
    } catch {
      setError(t("onboard.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.modalBackdrop} role="presentation">
      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboard-title"
      >
        <div className={styles.onboardHero}>
          <Naza pose="look" size={80} speech={t("onboard.speech")} />
        </div>
        <div className={styles.modalHead}>
          <h2 id="onboard-title">{t("onboard.title")}</h2>
        </div>
        <p className={styles.modalLead}>{t("onboard.lead")}</p>
        <label className={styles.field}>
          <span>{t("settings.name")}</span>
          <input
            ref={firstFieldRef}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("settings.namePh")}
            autoComplete="name"
          />
        </label>
        <label className={styles.field}>
          <span>{t("settings.language")}</span>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value === "Hausa" ? "Hausa" : "English")}
          >
            <option value="English">{t("lang.english")}</option>
            <option value="Hausa">{t("lang.hausa")}</option>
          </select>
        </label>
        <label className={styles.field}>
          <span>{t("settings.goal")}</span>
          <input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder={t("settings.goalPh")}
          />
        </label>
        {error ? <p className={styles.modalError}>{error}</p> : null}
        <div className={styles.modalActions}>
          <Button onClick={() => void save()} loading={saving}>
            {saving ? t("onboard.saving") : t("onboard.continue")}
          </Button>
        </div>
      </div>
    </div>
  );
}
