import { Naza } from "./Naza";
import { useLanguage } from "../../i18n/LanguageProvider";
import styles from "./naza.module.css";

type Props = {
  open: boolean;
  title?: string;
  lead?: string;
};

export function PlanningOverlay({ open, title, lead }: Props) {
  const { t } = useLanguage();
  if (!open) return null;
  const heading = title || t("overlay.planTitle");
  const body = lead || t("overlay.planLead");
  return (
    <div
      className={styles.overlay}
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-labelledby="naza-overlay-title"
      aria-describedby="naza-overlay-lead"
    >
      <div className={styles.overlayCard}>
        <Naza pose="fly" size={96} animate />
        <h2 id="naza-overlay-title" className={styles.overlayTitle}>
          {heading}
        </h2>
        <p id="naza-overlay-lead" className={styles.overlayLead}>
          {body}
        </p>
        <div className={styles.shimmer} aria-hidden />
      </div>
    </div>
  );
}
