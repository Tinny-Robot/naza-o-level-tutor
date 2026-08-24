import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { Button } from "../ui/Button";
import { fetchStudentSummary, patchPreferences } from "../../services/student";
import { useLanguage } from "../../i18n/LanguageProvider";
import type { AppLanguage } from "../../i18n/types";
import styles from "./layout.module.css";

export function SettingsModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { language: liveLanguage, t, refresh } = useLanguage();
  const [language, setLanguage] = useState<AppLanguage>(liveLanguage);
  const [style, setStyle] = useState("worked_examples");
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    fetchStudentSummary()
      .then((s) => {
        if (cancelled) return;
        const next = s.preferences.language === "Hausa" ? "Hausa" : "English";
        setLanguage(next);
        setStyle(s.preferences.explanation_style || "worked_examples");
        setName(s.display_name || "");
        setGoal(s.goal_today || "");
      })
      .catch(() => {
        /* keep defaults if summary unavailable */
      });
    const id = window.requestAnimationFrame(() => firstFieldRef.current?.focus());
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(id);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await patchPreferences({
        language,
        explanation_style: style,
        display_name: name.trim() || undefined,
        goal_today: goal.trim() || undefined,
      });
      await refresh();
      onClose();
    } catch {
      setError(t("settings.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.modalBackdrop} role="presentation" onClick={onClose}>
      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.modalHead}>
          <h2 id="settings-title">{t("settings.title")}</h2>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={onClose}
            aria-label={t("settings.close")}
          >
            <X size={18} />
          </button>
        </div>
        <p className={styles.modalLead}>{t("settings.lead")}</p>

        <div className={styles.modalSection}>
          <h3>{t("settings.section.profile")}</h3>
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
        </div>

        <div className={styles.modalSection}>
          <h3>{t("settings.section.learning")}</h3>
          <label className={styles.field}>
            <span>{t("settings.goal")}</span>
            <input
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder={t("settings.goalPh")}
            />
          </label>
          <label className={styles.field}>
            <span>{t("settings.style")}</span>
            <select value={style} onChange={(e) => setStyle(e.target.value)}>
              <option value="worked_examples">{t("settings.style.worked")}</option>
              <option value="concise">{t("settings.style.concise")}</option>
              <option value="socratic">{t("settings.style.socratic")}</option>
            </select>
          </label>
        </div>

        <div className={styles.modalSection}>
          <h3>{t("settings.section.about")}</h3>
          <div className={styles.modalMeta}>
            <div>{t("settings.offlineBenefit")}</div>
            <div>{t("settings.privacy")}</div>
          </div>
        </div>

        {error ? <p className={styles.modalError}>{error}</p> : null}
        <div className={styles.modalActions}>
          <Button variant="ghost" onClick={onClose}>
            {t("settings.cancel")}
          </Button>
          <Button onClick={() => void save()} loading={saving}>
            {saving ? t("settings.saving") : t("settings.save")}
          </Button>
        </div>
      </div>
    </div>
  );
}
