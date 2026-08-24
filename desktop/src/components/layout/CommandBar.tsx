import { useEffect, useState, type RefObject } from "react";
import { Flame, Search, Settings } from "lucide-react";
import { Badge } from "../ui/Badge";
import { fetchStudentSummary } from "../../services/student";
import { useLanguage } from "../../i18n/LanguageProvider";
import styles from "./layout.module.css";

function shortcutLabel() {
  if (typeof navigator === "undefined") return "Ctrl+K";
  const mac = /Mac|iPhone|iPad/.test(navigator.platform) || /Mac/.test(navigator.userAgent);
  return mac ? "⌘K" : "Ctrl+K";
}

export function CommandBar({
  onOpenPalette,
  onOpenSettings,
  searchButtonRef,
}: {
  onOpenPalette?: () => void;
  onOpenSettings?: () => void;
  searchButtonRef?: RefObject<HTMLButtonElement | null>;
}) {
  const { t } = useLanguage();
  const [streak, setStreak] = useState<number | null>(null);
  const [hotkey, setHotkey] = useState("Ctrl+K");

  useEffect(() => {
    setHotkey(shortcutLabel());
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchStudentSummary()
      .then((s) => {
        if (!cancelled) setStreak(s.streak_days || 0);
      })
      .catch(() => {
        if (!cancelled) setStreak(0);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <header className={styles.topbar}>
      <button
        ref={searchButtonRef}
        type="button"
        className={styles.searchPill}
        onClick={onOpenPalette}
        aria-label={t("top.ask")}
      >
        <Search size={16} aria-hidden />
        <span>{t("top.ask")}</span>
        <span className={styles.kbd}>{hotkey}</span>
      </button>
      <div className={styles.topMeta}>
        {streak != null ? (
          <Badge tone="success">
            <Flame size={14} />
            {t("top.streak", { n: streak })}
          </Badge>
        ) : null}
        <button
          type="button"
          className={styles.iconBtn}
          aria-label={t("top.settings")}
          onClick={onOpenSettings}
        >
          <Settings size={18} />
        </button>
      </div>
    </header>
  );
}
